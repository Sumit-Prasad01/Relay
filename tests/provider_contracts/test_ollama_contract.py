from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from Relay.providers.ollama_adapter import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_validation_mocked():
    provider = OllamaProvider(base_url="http://localhost:11434")

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "models": [
            {"name": "qwen2.5-coder:latest"},
            {"name": "llama3.1:latest"},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_http_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        health = await provider.validate()
        assert health.healthy is True
        assert health.provider == "ollama"
        assert len(health.models) == 2
        assert "qwen2.5-coder:latest" in health.models


@pytest.mark.asyncio
async def test_ollama_list_models_mocked():
    provider = OllamaProvider(base_url="http://localhost:11434")

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "models": [
            {"name": "qwen2.5-coder"},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_http_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        models = await provider.list_models()
        assert len(models) == 1
        assert models[0].id == "qwen2.5-coder"
        assert models[0].capabilities.tool_calling is True
