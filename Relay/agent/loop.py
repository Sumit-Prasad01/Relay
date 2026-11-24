"""Core agent execution loop with streaming, tool dispatch, and eventing (Section 7.2)."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from Relay.agent.events import AgentEvent
from Relay.agent.messages import (
    assistant_message,
    deserialize_from_storage,
    serialize_for_storage,
    tool_result_message,
    user_message,
)
from Relay.agent.retries import RetryPolicy
from Relay.agent.state import AgentState
from Relay.agent.stop_conditions import StopConditionEvaluator
from Relay.config.schemas import RootConfig
from Relay.context.builder import ContextBuilder
from Relay.providers.base import LLMProvider, ModelEvent, ModelMessage, ModelRequest, ToolCall
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
                yield AgentEvent(
                    event_type="error",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    error=str(e),
                )
                state.last_error = str(e)
                break

            full_content = "".join(assistant_content_parts)

            # Deduplicate or group tool calls if needed
            unique_tool_calls: List[ToolCall] = []
            seen_calls = set()
            for tc in collected_tool_calls:
                call_key = (tc.id or "", tc.name, tc.arguments)
                if call_key not in seen_calls:
                    seen_calls.add(call_key)
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
            for tc in unique_tool_calls:
                turn_tool_calls += 1
                yield AgentEvent(
                    event_type="tool_call_requested",
                    session_id=state.session_id,
                    turn=state.turn_count,
                    tool_call=tc,
                )

                # Record in session store
                args = tc.parsed_arguments()
                self.session_store.record_tool_call(
                    session_id=state.session_id,
                    call_id=tc.id or f"call_{turn_tool_calls}",
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
                    call_id=tc.id or f"call_{turn_tool_calls}",
                    output=tool_result.content,
                    exit_code=tool_result.exit_code,
                )

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
                t_msg = tool_result_message(tc.id or f"call_{turn_tool_calls}", tool_result)
                state.messages.append(t_msg)
                stored_tool = serialize_for_storage(t_msg)
                self.session_store.append_message(
                    session_id=state.session_id,
                    role=stored_tool["role"],
                    content=stored_tool["content"],
                    raw_payload=stored_tool["raw_payload"],
                )

            state.iteration_count += 1
