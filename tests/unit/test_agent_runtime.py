"""Unit tests for AgentState, StopConditionEvaluator, and RetryPolicy (Section 7)."""

from pathlib import Path
from Relay.agent.events import AgentEvent
from Relay.agent.messages import (
    assistant_message,
    deserialize_from_storage,
    serialize_for_storage,
    tool_result_message,
    user_message,
)
from Relay.agent.retries import RetryPolicy, is_transient_error
from Relay.agent.state import AgentState
from Relay.agent.stop_conditions import StopConditionEvaluator
from Relay.config.schemas import AgentConfig
from Relay.providers.base import ToolCall
from Relay.tools.base import ToolResult
from Relay.utils.errors import AuthenticationError, NetworkTimeoutError, RateLimitError


def test_agent_state_usage_and_changed_files():
    state = AgentState(
        session_id="sess_123",
        workspace_root=Path("/mock/workspace"),
        provider_name="groq",
        model_name="llama-3.3-70b-versatile",
    )

    state.update_usage(100, 50)
    assert state.prompt_tokens_used == 100
    assert state.completion_tokens_used == 50
    assert state.total_tokens_used == 150

    state.add_changed_file("src/main.py")
    state.add_changed_file("src/main.py")
    assert state.changed_files == ["src/main.py"]

    data = state.to_dict()
    assert data["session_id"] == "sess_123"
    assert data["total_tokens_used"] == 150


def test_stop_conditions_evaluation():
    config = AgentConfig(
        max_iterations=5,
        max_tool_calls=10,
        task_timeout_seconds=60,
        max_context_tokens=1000,
    )
    state = AgentState(
        session_id="s1",
        workspace_root=Path("/mock"),
        provider_name="groq",
        model_name="m1",
    )

    # 1. Normal state - no stop condition
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=2, elapsed_seconds=10.0, config=config)
    assert res is None

    # 2. Max iterations
    state.iteration_count = 5
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=2, elapsed_seconds=10.0, config=config)
    assert res is not None
    assert res[0] == "max_iterations"
    state.iteration_count = 0

    # 3. Max tool calls
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=10, elapsed_seconds=10.0, config=config)
    assert res is not None
    assert res[0] == "max_tool_calls"

    # 4. Timeout
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=1, elapsed_seconds=65.0, config=config)
    assert res is not None
    assert res[0] == "task_timeout"

    # 5. Token limit
    state.total_tokens_used = 1500
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=1, elapsed_seconds=5.0, config=config)
    assert res is not None
    assert res[0] == "token_limit"
    state.total_tokens_used = 0

    # 6. User cancellation
    state.is_cancelled = True
    res = StopConditionEvaluator.evaluate(state, turn_tool_calls=1, elapsed_seconds=5.0, config=config)
    assert res is not None
    assert res[0] == "cancelled"


def test_retry_policy_classification_and_backoff():
    # Transient classifications
    assert is_transient_error(RateLimitError("Rate limited")) is True
    assert is_transient_error(NetworkTimeoutError("Timed out")) is True
    assert is_transient_error(Exception("503 Service Unavailable")) is True
    assert is_transient_error(Exception("Server overloaded, retry in a moment")) is True

    # Non-transient classifications
    assert is_transient_error(AuthenticationError("Invalid API key")) is False
    assert is_transient_error(ValueError("Invalid syntax")) is False

    # Backoff calculation
    policy = RetryPolicy(initial_delay=1.0, backoff_factor=2.0, max_delay=10.0, jitter=False)
    assert policy.get_delay(0) == 1.0
    assert policy.get_delay(1) == 2.0
    assert policy.get_delay(2) == 4.0
    assert policy.get_delay(3) == 8.0
    assert policy.get_delay(4) == 10.0  # capped at max_delay


def test_message_serialization_roundtrip():
    # User message
    u = user_message("Hello world")
    u_data = serialize_for_storage(u)
    assert u_data["role"] == "user"
    assert u_data["content"] == "Hello world"
    u_back = deserialize_from_storage(u_data)
    assert u_back.role == "user"
    assert u_back.content == "Hello world"

    # Assistant with tool calls
    ast = assistant_message(
        content="Inspecting project",
        tool_calls=[ToolCall(id="call_1", name="list_files", arguments='{"path": "."}')],
    )
    ast_data = serialize_for_storage(ast)
    ast_back = deserialize_from_storage(ast_data)
    assert ast_back.role == "assistant"
    assert ast_back.content == "Inspecting project"
    assert len(ast_back.tool_calls) == 1
    assert ast_back.tool_calls[0].name == "list_files"
    assert ast_back.tool_calls[0].parsed_arguments() == {"path": "."}

    # Tool result
    t_res = ToolResult(content="file1.py\nfile2.py", success=True)
    t_msg = tool_result_message("call_1", t_res)
    t_data = serialize_for_storage(t_msg)
    t_back = deserialize_from_storage(t_data)
    assert t_back.role == "tool"
    assert t_back.content == "file1.py\nfile2.py"
    assert t_back.tool_call_id == "call_1"
