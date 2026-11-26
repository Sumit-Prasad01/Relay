"""Core agent execution loop with streaming, tool dispatch, and eventing (Section 7.2)."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Dict, List, Tuple

from Relay.agent.events import AgentEvent
from Relay.agent.messages import (
    assistant_message,
    serialize_for_storage,
    tool_result_message,
    user_message,
)
from Relay.agent.retries import RetryPolicy
from Relay.agent.state import AgentState
from Relay.agent.stop_conditions import StopConditionEvaluator
from Relay.config.schemas import RootConfig
from Relay.context.builder import ContextBuilder
from Relay.providers.base import LLMProvider, ModelRequest, ToolCall
from Relay.security.snapshots import SnapshotManager
from Relay.storage.event_store import EventStore
from Relay.storage.session_store import SessionStore
from Relay.tools.registry import ToolRegistry


@dataclass
class ToolExecutionContext:
    """Runtime context passed into tool execution."""

    workspace_root: Path
    session_id: str
    session_store: SessionStore
    snapshots: SnapshotManager


class AgentLoop:
    """Orchestrates an agent turn by cycling between model generation and tool execution."""

    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        context_builder: ContextBuilder,
        session_store: SessionStore,
        event_store: EventStore,
        config: RootConfig,
        base_system_prompt: str,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.context_builder = context_builder
        self.session_store = session_store
        self.event_store = event_store
        self.config = config
        self.base_system_prompt = base_system_prompt
        self.retry_policy = RetryPolicy()

    async def run_turn(
        self,
        state: AgentState,
        user_input: str,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a full turn for user input, streaming events as progress occurs."""
        state.turn_count += 1
        turn_start_time = time.time()
        turn_tool_calls = 0

        # 1. Record and append user message
        u_msg = user_message(user_input)
        state.messages.append(u_msg)
        stored_dict = serialize_for_storage(u_msg)
        self.session_store.append_message(
            session_id=state.session_id,
            role=stored_dict["role"],
            content=stored_dict["content"],
            raw_payload=stored_dict["raw_payload"],
        )

        yield AgentEvent(
            event_type="turn_started",
            session_id=state.session_id,
            turn=state.turn_count,
            message=f"Turn {state.turn_count} started",
        )

        tool_exec_context = ToolExecutionContext(
            workspace_root=state.workspace_root,
            session_id=state.session_id,
            session_store=self.session_store,
            snapshots=SnapshotManager(state.workspace_root),
        )

        # 2. Agent cycle
        tool_validation_retries = 0
        read_only_tools = {
            "list_files",
            "read_file",
            "search_code",
            "git_status",
            "git_diff",
            "git_log",
            "diagnose_project",
            "get_environment",
        }
        mutating_tools = {"write_file", "edit_file", "apply_patch", "run_command", "git_commit", "git_branch", "run_tests"}
        read_cache: Dict[Tuple[str, str], str] = {}
        failed_calls: set[Tuple[str, str]] = set()
        consecutive_all_duplicate_iters = 0
        while True:
            elapsed = time.time() - turn_start_time
            stop_check = StopConditionEvaluator.evaluate(
                state=state,
                turn_tool_calls=turn_tool_calls,
                elapsed_seconds=elapsed,
                config=self.config.agent,
            )
            if stop_check:
                reason, reason_msg = stop_check
                state.is_finished = True
                state.finish_reason = reason
                yield AgentEvent(
                    event_type="stop_condition_met",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    message=reason_msg,
                    metadata={"reason": reason},
                )
                break

            # Build system prompt with instructions and environment
            system_prompt = self.context_builder.build_system_prompt(self.base_system_prompt)
            fitted_messages = self.context_builder.fit_messages(system_prompt, state.messages)
            tool_schemas = self.tool_registry.get_schemas()

            req = ModelRequest(
                model=state.model_name,
                messages=fitted_messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=0.2,
                timeout=float(self.config.terminal.timeout_seconds),
            )

            yield AgentEvent(
                event_type="model_request_started",
                session_id=state.session_id,
                turn=state.turn_count,
                message=f"Requesting completion from {state.provider_name}/{state.model_name}",
            )

            # Stream or generate
            assistant_content_parts: List[str] = []
            collected_tool_calls: List[ToolCall] = []

            try:
                if self.config.agent.stream:
                    async for event in self.provider.stream(req):
                        if event.event_type == "text_delta" and event.text_delta:
                            assistant_content_parts.append(event.text_delta)
                            yield AgentEvent(
                                event_type="text_delta",
                                session_id=state.session_id,
                                turn=state.turn_count,
                                text_delta=event.text_delta,
                            )
                        elif event.event_type == "tool_call_delta" and event.tool_call:
                            collected_tool_calls.append(event.tool_call)
                            yield AgentEvent(
                                event_type="tool_call_delta",
                                session_id=state.session_id,
                                turn=state.turn_count,
                                tool_call=event.tool_call,
                            )
                        elif event.event_type == "usage" and event.usage:
                            state.update_usage(event.usage.prompt_tokens, event.usage.completion_tokens)
                            yield AgentEvent(
                                event_type="usage_update",
                                session_id=state.session_id,
                                turn=state.turn_count,
                                usage=event.usage,
                            )
                else:
                    res = await self.provider.generate(req)
                    if res.content:
                        assistant_content_parts.append(res.content)
                        yield AgentEvent(
                            event_type="text_delta",
                            session_id=state.session_id,
                            turn=state.turn_count,
                            text_delta=res.content,
                        )
                    if res.tool_calls:
                        collected_tool_calls.extend(res.tool_calls)
                    if res.usage:
                        state.update_usage(res.usage.prompt_tokens, res.usage.completion_tokens)
            except Exception as e:
                err_str = str(e)
                err_lower = err_str.lower()
                is_tool_parse_err = (
                    "failed to parse tool call arguments as json" in err_lower
                    or "tool_use_failed" in err_lower
                    or "failed_generation" in err_lower
                )
                is_tool_name_err = (
                    "not in request.tools" in err_lower
                    or "tool call validation failed" in err_lower
                )
                if (is_tool_parse_err or is_tool_name_err) and tool_schemas and tool_validation_retries < 3:
                    tool_validation_retries += 1
                    allowed = ", ".join(t.name for t in tool_schemas)
                    if is_tool_parse_err:
                        correction_text = (
                            f"Your previous tool call failed JSON argument parsing on the provider ({err_str}). "
                            "Make sure all newlines (\\n), quotes (\\\"), and backslashes (\\\\) inside string values are properly JSON-escaped, "
                            f"or break large file edits into smaller steps. Available tools: {allowed}. Please retry cleanly."
                        )
                        retry_msg = f"Provider could not parse tool-call JSON; retrying ({tool_validation_retries}/3)"
                    else:
                        correction_text = (
                            f"Tool selection error: {err_str}. "
                            f"Only call tools from this exact list: {allowed}. Please retry using valid tool names."
                        )
                        retry_msg = f"Model called undeclared tool; prompting correction ({tool_validation_retries}/3)"

                    state.messages.append(user_message(correction_text))
                    yield AgentEvent(
                        event_type="retry_attempt",
                        session_id=state.session_id,
                        turn=state.turn_count,
                        message=retry_msg,
                    )
                    state.iteration_count += 1
                    continue

                yield AgentEvent(
                    event_type="error",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    error=err_str,
                )
                state.last_error = err_str
                break

            full_content = "".join(assistant_content_parts)

            # Deduplicate identical tool calls within a single response (ignoring distinct IDs)
            def _canonical_args(raw: str) -> str:
                try:
                    return json.dumps(json.loads(raw), sort_keys=True)
                except Exception:
                    return raw.strip()

            unique_tool_calls: List[ToolCall] = []
            seen_batch_calls: set[Tuple[str, str]] = set()
            for idx, tc in enumerate(collected_tool_calls):
                canonical = _canonical_args(tc.arguments)
                batch_key = (tc.name, canonical)
                if batch_key not in seen_batch_calls:
                    seen_batch_calls.add(batch_key)
                    if not tc.id:
                        tc.id = f"call_{state.iteration_count}_{idx}"
                    unique_tool_calls.append(tc)

            # Record assistant message
            ast_msg = assistant_message(
                content=full_content,
                tool_calls=unique_tool_calls if unique_tool_calls else None,
            )
            state.messages.append(ast_msg)
            stored_ast = serialize_for_storage(ast_msg)
            self.session_store.append_message(
                session_id=state.session_id,
                role=stored_ast["role"],
                content=stored_ast["content"],
                raw_payload=stored_ast["raw_payload"],
            )

            # If no tool calls were requested, turn is complete
            if not unique_tool_calls:
                yield AgentEvent(
                    event_type="turn_completed",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    message="Turn completed with final answer.",
                )
                break

            # Execute tool calls
            executed_fresh_call = False
            for tc in unique_tool_calls:
                turn_tool_calls += 1
                call_id = tc.id or f"call_{turn_tool_calls}"
                canonical_key = (tc.name, _canonical_args(tc.arguments))

                # Guard against repeating unchanged read calls or already-rejected identical calls
                if tc.name in read_only_tools and canonical_key in read_cache:
                    from Relay.tools.base import ToolResult

                    cached_msg = (
                        f"Already executed '{tc.name}' with identical arguments earlier in this turn and no files changed since. "
                        f"Do not repeat this call; proceed to the next step using the earlier output:\n{read_cache[canonical_key]}"
                    )
                    cached_res = ToolResult(content=cached_msg, success=True)
                    t_msg = tool_result_message(call_id, cached_res)
                    state.messages.append(t_msg)
                    stored_tool = serialize_for_storage(t_msg)
                    self.session_store.append_message(
                        session_id=state.session_id,
                        role=stored_tool["role"],
                        content=stored_tool["content"],
                        raw_payload=stored_tool["raw_payload"],
                    )
                    continue

                if tc.name not in read_only_tools and canonical_key in failed_calls:
                    from Relay.tools.base import ToolResult

                    dup_err = (
                        f"Skipped repeated call to '{tc.name}' with identical arguments after earlier failure or rejection. "
                        "Use a different approach or summarize status to the user."
                    )
                    dup_res = ToolResult(content=dup_err, success=False, error="duplicate_call_skipped")
                    t_msg = tool_result_message(call_id, dup_res)
                    state.messages.append(t_msg)
                    stored_tool = serialize_for_storage(t_msg)
                    self.session_store.append_message(
                        session_id=state.session_id,
                        role=stored_tool["role"],
                        content=stored_tool["content"],
                        raw_payload=stored_tool["raw_payload"],
                    )
                    continue

                executed_fresh_call = True
                yield AgentEvent(
                    event_type="tool_call_requested",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    tool_call=tc,
                )

                # Parse arguments once strictly before dispatching
                try:
                    args = tc.parse_arguments_strict()
                except ValueError as parse_err:
                    from Relay.tools.base import ToolResult

                    err_msg = f"Invalid tool arguments for '{tc.name}': {parse_err}"
                    self.session_store.record_tool_call(
                        session_id=state.session_id,
                        call_id=call_id,
                        tool_name=tc.name,
                        arguments={"_raw_arguments": tc.arguments},
                        status="failed",
                    )
                    bad_result = ToolResult(
                        content=err_msg,
                        success=False,
                        error="invalid_arguments",
                    )
                    self.session_store.record_tool_result(
                        call_id=call_id,
                        output=bad_result.content,
                        exit_code=None,
                    )
                    yield AgentEvent(
                        event_type="tool_call_failed",
                        session_id=state.session_id,
                        turn=state.turn_count,
                        tool_call=tc,
                        tool_result=bad_result,
                        error=err_msg,
                    )
                    t_msg = tool_result_message(call_id, bad_result)
                    state.messages.append(t_msg)
                    stored_tool = serialize_for_storage(t_msg)
                    self.session_store.append_message(
                        session_id=state.session_id,
                        role=stored_tool["role"],
                        content=stored_tool["content"],
                        raw_payload=stored_tool["raw_payload"],
                    )
                    continue

                self.session_store.record_tool_call(
                    session_id=state.session_id,
                    call_id=call_id,
                    tool_name=tc.name,
                    arguments=args,
                    status="executing",
                )

                yield AgentEvent(
                    event_type="tool_call_started",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    tool_call=tc,
                )

                # Execute with permission and error containment
                tool_result = self.tool_registry.execute(
                    name=tc.name,
                    arguments=args,
                    context=tool_exec_context,
                )

                # Record tool result in database
                self.session_store.record_tool_result(
                    call_id=call_id,
                    output=tool_result.content,
                    exit_code=tool_result.exit_code,
                )

                if tool_result.success:
                    if tc.name in read_only_tools:
                        read_cache[canonical_key] = tool_result.content
                    elif tc.name in mutating_tools:
                        read_cache.clear()
                        failed_calls.clear()
                else:
                    if tc.name not in read_only_tools and tool_result.error != "user_instructed":
                        failed_calls.add(canonical_key)

                # Check if tool resulted in file modification
                if tc.name in ("write_file", "edit_file", "apply_patch") and tool_result.success:
                    file_path = args.get("path", "")
                    if file_path:
                        state.add_changed_file(file_path)
                        yield AgentEvent(
                            event_type="file_changed",
                            session_id=state.session_id,
                            turn=state.turn_count,
                            file_path=file_path,
                            message=f"Modified file: {file_path}",
                        )

                if tool_result.success:
                    yield AgentEvent(
                        event_type="tool_call_completed",
                        session_id=state.session_id,
                        turn=state.turn_count,
                        tool_call=tc,
                        tool_result=tool_result,
                    )
                else:
                    yield AgentEvent(
                        event_type="tool_call_failed",
                        session_id=state.session_id,
                        turn=state.turn_count,
                        tool_call=tc,
                        tool_result=tool_result,
                        error=tool_result.error,
                    )

                # Append tool result message to conversation
                t_msg = tool_result_message(call_id, tool_result)
                state.messages.append(t_msg)
                stored_tool = serialize_for_storage(t_msg)
                self.session_store.append_message(
                    session_id=state.session_id,
                    role=stored_tool["role"],
                    content=stored_tool["content"],
                    raw_payload=stored_tool["raw_payload"],
                )

            if not executed_fresh_call:
                consecutive_all_duplicate_iters += 1
                if consecutive_all_duplicate_iters >= 2:
                    yield AgentEvent(
                        event_type="stop_condition_met",
                        session_id=state.session_id,
                        turn=state.turn_count,
                        message="Stopped repetitive tool-call loop with no new actions.",
                        metadata={"reason": "repetitive_tool_loop"},
                    )
                    break
            else:
                consecutive_all_duplicate_iters = 0

            state.iteration_count += 1
