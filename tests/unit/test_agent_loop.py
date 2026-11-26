"""Unit tests for AgentLoop and AgentRuntime orchestration (Section 7)."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from Relay.agent.loop import AgentLoop
from Relay.agent.runtime import AgentRuntime
from Relay.agent.state import AgentState
from Relay.app import create_app_context
from Relay.config.schemas import RootConfig
from Relay.context.builder import ContextBuilder
from Relay.context.tokenizer import TokenBudget
from Relay.providers.base import ModelEvent, ToolCall
from Relay.storage.database import Database
from Relay.storage.event_store import EventStore
from Relay.storage.session_store import SessionStore
from Relay.tools.base import BaseTool, ToolResult
from Relay.tools.registry import ToolRegistry


class DummyMockTool(BaseTool):
    name = "dummy_mock_tool"
    description = "Mock tool for testing loop"
    category = "read"
    parameters = {"type": "object", "properties": {"val": {"type": "string"}}}

    def run(self, arguments, context):
        return ToolResult(content=f"Dummy echoed: {arguments.get('val')}", success=True)


@pytest.mark.asyncio
async def test_agent_loop_turn_execution(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.run_migrations()

    session_store = SessionStore(db)
    event_store = EventStore(db)
    session_id = session_store.create_session(
        workspace=tmp_path,
        provider="mock_p",
        model="mock_m",
        title="Test session",
    )

    state = AgentState(
        session_id=session_id,
        workspace_root=tmp_path,
        provider_name="mock_p",
        model_name="mock_m",
    )

    registry = ToolRegistry()
    registry.register(DummyMockTool())

    context_builder = ContextBuilder(workspace_root=tmp_path, budget=TokenBudget(max_context_tokens=10000))

    # Mock provider: first call returns tool use, second call returns final answer
    provider = MagicMock()

    call_count = 0

    async def mock_stream(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield ModelEvent(event_type="text_delta", text_delta="Calling tool...")
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(
                    id="call_99",
                    name="dummy_mock_tool",
                    arguments='{"val": "hello-agent"}',
                ),
            )
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Done! Final answer.")

    provider.stream = mock_stream

    config = RootConfig()
    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        context_builder=context_builder,
        session_store=session_store,
        event_store=event_store,
        config=config,
        base_system_prompt="System prompt",
    )

    events = []
    async for ev in loop.run_turn(state=state, user_input="Execute mock task"):
        events.append(ev)

    event_types = [e.event_type for e in events]
    assert "turn_started" in event_types
    assert "tool_call_requested" in event_types
    assert "tool_call_completed" in event_types
    assert "turn_completed" in event_types

    # Verify messages in SQLite
    msgs = session_store.get_messages(session_id)
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_agent_runtime_session_lifecycle(tmp_path: Path):
    db_path = tmp_path / "state.db"
    cfg = RootConfig()
    cfg.storage.database_path = str(db_path)

    app_ctx = create_app_context(workspace_root=tmp_path)
    runtime = AgentRuntime(app_context=app_ctx)

    state = runtime.create_session(title="Unit test session", provider="groq", model="llama-3.3-70b-versatile")
    assert state.session_id is not None
    assert state.provider_name == "groq"
    assert state.model_name == "llama-3.3-70b-versatile"

    # Resuming session
    resumed = runtime.resume_session(state.session_id)
    assert resumed.session_id == state.session_id
    assert resumed.provider_name == "groq"
    assert resumed.model_name == "llama-3.3-70b-versatile"

    # Summary
    summary = runtime.summarize_changes(state)
    assert summary["session_id"] == state.session_id
    assert summary["turns"] == 0


def test_system_prompt_only_references_registered_tools(tmp_path: Path):
    from Relay.tools.registry import create_default_registry

    app_ctx = create_app_context(workspace_root=tmp_path)
    runtime = AgentRuntime(app_context=app_ctx)
    assert "search_files" not in runtime.base_system_prompt
    registered = {t.name for t in create_default_registry().list_tools()}
    for expected in ("list_files", "read_file", "search_code", "edit_file", "write_file", "run_command"):
        assert expected in registered
        assert expected in runtime.base_system_prompt


@pytest.mark.asyncio
async def test_agent_loop_recovers_from_undeclared_tool_validation_error(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    runtime = AgentRuntime(app_context=app_ctx)
    state = runtime.create_session(provider="groq", model="test-model")

    registry = ToolRegistry()
    registry.register(DummyMockTool())

    call_idx = 0

    async def mock_stream(request):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            raise RuntimeError(
                "Tool call validation failed: attempted to call tool 'search_files' which was not in request.tools"
            )
        yield ModelEvent(event_type="text_delta", text_delta="Recovered using valid tools.")

    provider = MagicMock()
    provider.stream = mock_stream

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    events = [ev async for ev in loop.run_turn(state, "Check files")]
    types = [e.event_type for e in events]
    assert "retry_attempt" in types
    assert "turn_completed" in types
    assert "error" not in types


@pytest.mark.asyncio
async def test_agent_loop_recovers_from_provider_tool_json_parse_error(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    runtime = AgentRuntime(app_context=app_ctx)
    state = runtime.create_session(provider="groq", model="test-model")

    registry = ToolRegistry()
    registry.register(DummyMockTool())

    call_idx = 0

    async def mock_stream(request):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            raise RuntimeError("Failed to parse tool call arguments as JSON")
        yield ModelEvent(event_type="text_delta", text_delta="Re-formatted tool call and succeeded.")

    provider = MagicMock()
    provider.stream = mock_stream

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    events = [ev async for ev in loop.run_turn(state, "Write script")]
    types = [e.event_type for e in events]
    assert "retry_attempt" in types
    assert "turn_completed" in types
    assert "error" not in types


@pytest.mark.asyncio
async def test_agent_loop_deduplicates_batch_and_blocks_repeated_reads(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    runtime = AgentRuntime(app_context=app_ctx)
    state = runtime.create_session(provider="groq", model="test-model")

    exec_count = 0

    class CountingReadTool(BaseTool):
        name = "list_files"
        description = "Count executions"
        category = "read"
        parameters = {"type": "object", "properties": {"path": {"type": "string"}}}

        def run(self, arguments, context):
            nonlocal exec_count
            exec_count += 1
            return ToolResult(content="data/", success=True)

    registry = ToolRegistry()
    registry.register(CountingReadTool())

    call_idx = 0

    async def mock_stream(request):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            # Emits 3 identical calls in the same response with different IDs
            yield ModelEvent(event_type="tool_call_delta", tool_call=ToolCall(id="a1", name="list_files", arguments='{"path": "."}'))
            yield ModelEvent(event_type="tool_call_delta", tool_call=ToolCall(id="a2", name="list_files", arguments='{"path": "."}'))
            yield ModelEvent(event_type="tool_call_delta", tool_call=ToolCall(id="a3", name="list_files", arguments='{ "path" : "." }'))
        elif call_idx in (2, 3):
            # Model tries repeating the exact same read call in consecutive iterations
            yield ModelEvent(event_type="tool_call_delta", tool_call=ToolCall(id=f"b{call_idx}", name="list_files", arguments='{"path": "."}'))
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Done.")

    provider = MagicMock()
    provider.stream = mock_stream

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    events = [ev async for ev in loop.run_turn(state, "List root")]
    # Executed ONLY once despite 3 in-batch + 2 subsequent repeated calls
    assert exec_count == 1
    assert any(e.event_type == "stop_condition_met" and e.metadata.get("reason") == "repetitive_tool_loop" for e in events)
