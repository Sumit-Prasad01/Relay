import pytest
from Relay.providers.base import (
    ModelEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolDefinition,
    UsageInfo,
)


def test_tool_call_parsed_arguments():
    tc = ToolCall(id="call_1", name="read_file", arguments='{"path": "README.md"}')
    assert tc.parsed_arguments() == {"path": "README.md"}

    bad_tc = ToolCall(id="call_2", name="read_file", arguments="invalid-json")
    assert bad_tc.parsed_arguments() == {}


def test_model_request_and_response():
    req = ModelRequest(
        model="llama-3.3-70b-versatile",
        messages=[ModelMessage(role="user", content="Hello")],
        tools=[ToolDefinition(name="read_file", description="Read file", parameters={"type": "object"})],
        temperature=0.7,
    )
    assert req.model == "llama-3.3-70b-versatile"
    assert len(req.messages) == 1
    assert len(req.tools) == 1

    res = ModelResponse(
        content="Response text",
        tool_calls=[ToolCall(id="call_123", name="bash", arguments='{"command": "ls"}')],
        finish_reason="tool_calls",
        usage=UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="llama-3.3-70b-versatile",
        provider="groq",
    )
    assert res.finish_reason == "tool_calls"
    assert len(res.tool_calls) == 1
    assert res.usage.total_tokens == 15


def test_model_event_creation():
    ev_text = ModelEvent(event_type="text_delta", text_delta="Hello")
    assert ev_text.event_type == "text_delta"
    assert ev_text.text_delta == "Hello"

    ev_tool = ModelEvent(
        event_type="tool_call_delta",
        tool_call=ToolCall(id="call_abc", name="test", arguments="{}"),
    )
    assert ev_tool.event_type == "tool_call_delta"
    assert ev_tool.tool_call.name == "test"
