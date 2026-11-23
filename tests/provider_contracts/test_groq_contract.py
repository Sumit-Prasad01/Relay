from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from Relay.providers.base import ModelMessage, ModelRequest, ToolCall, ToolDefinition
from Relay.providers.groq_adapter import GroqProvider
from Relay.utils.errors import AuthenticationError, RateLimitError


@pytest.mark.asyncio
async def test_groq_generate_mocked():
    provider = GroqProvider(api_key="gsk-mock-key")

    mock_choice = MagicMock()
    mock_choice.message.content = "Groq generated answer"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_res = MagicMock()
    mock_res.choices = [mock_choice]
    mock_res.usage.prompt_tokens = 25
    mock_res.usage.completion_tokens = 15
    mock_res.usage.total_tokens = 40
    mock_res.usage.prompt_tokens_details.cached_tokens = 5
    mock_res.usage.completion_tokens_details.reasoning_tokens = 0

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_res)

    with patch.object(provider, "_get_client", return_value=mock_client):
        req = ModelRequest(
            model="llama-3.3-70b-versatile",
            messages=[ModelMessage(role="user", content="Test prompt")],
        )
        response = await provider.generate(req)

        assert response.content == "Groq generated answer"
        assert response.finish_reason == "stop"
        assert response.usage.prompt_tokens == 25
        assert response.usage.completion_tokens == 15
        assert response.provider == "groq"


@pytest.mark.asyncio
async def test_groq_streaming_tool_accumulation_mocked():
    provider = GroqProvider(api_key="gsk-mock-key")

    # Simulate chunks where tool call arrives in fragments
    chunk1 = MagicMock()
    chunk1.usage = None
    tc_delta1 = MagicMock()
    tc_delta1.index = 0
    tc_delta1.id = "call_abc123"
    tc_delta1.function.name = "read_file"
    tc_delta1.function.arguments = '{"path": '
    chunk1.choices = [MagicMock(delta=MagicMock(content=None, tool_calls=[tc_delta1]), finish_reason=None)]

    chunk2 = MagicMock()
    chunk2.usage = None
    tc_delta2 = MagicMock()
    tc_delta2.index = 0
    tc_delta2.id = None
    tc_delta2.function.name = None
    tc_delta2.function.arguments = '"test.py"}'
    chunk2.choices = [MagicMock(delta=MagicMock(content=None, tool_calls=[tc_delta2]), finish_reason="tool_calls")]

    async def mock_chunk_generator():
        yield chunk1
        yield chunk2

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_chunk_generator())

    with patch.object(provider, "_get_client", return_value=mock_client):
        req = ModelRequest(
            model="llama-3.3-70b-versatile",
            messages=[ModelMessage(role="user", content="Read test.py")],
            tools=[ToolDefinition(name="read_file", description="Read file", parameters={})],
        )
        events = []
        async for ev in provider.stream(req):
            events.append(ev)

        assert len(events) == 2
        assert events[0].event_type == "tool_call_delta"
        assert events[0].tool_call.name == "read_file"
        assert events[0].tool_call.arguments == '{"path": "test.py"}'
        assert events[1].event_type == "completion"
        assert events[1].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_groq_auth_error_translation():
    provider = GroqProvider(api_key="gsk-invalid-key")

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("401 Unauthorized: Invalid API key"))

    with patch.object(provider, "_get_client", return_value=mock_client):
        req = ModelRequest(model="llama-3.3-70b-versatile", messages=[])
        with pytest.raises(AuthenticationError):
            await provider.generate(req)
