from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from Relay.providers.anthropic_adapter import AnthropicProvider
from Relay.providers.base import ModelMessage, ModelRequest, ToolDefinition


@pytest.mark.asyncio
async def test_anthropic_generate_mocked():
    provider = AnthropicProvider(api_key="sk-ant-test-key")

    mock_response_data = {
        "content": [
            {"type": "text", "text": "Anthropic response"},
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "bash",
                "input": {"command": "ls"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 50, "output_tokens": 20},
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = mock_response_data

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_http_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        req = ModelRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[
                ModelMessage(role="system", content="System instructions"),
                ModelMessage(role="user", content="Hello"),
            ],
            tools=[ToolDefinition(name="bash", description="Execute command", parameters={})],
        )
        response = await provider.generate(req)

        assert response.content == "Anthropic response"
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "bash"
        assert response.tool_calls[0].parsed_arguments() == {"command": "ls"}
        assert response.finish_reason == "tool_use"
        assert response.usage.prompt_tokens == 50
        assert response.usage.completion_tokens == 20
