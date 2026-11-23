import pytest
from Relay.config.schemas import ProviderConfig
from Relay.providers.factory import create_provider
from Relay.providers.groq_adapter import GroqProvider
from Relay.providers.openrouter_adapter import OpenRouterProvider
from Relay.providers.openai_adapter import OpenAIProvider
from Relay.providers.anthropic_adapter import AnthropicProvider
from Relay.providers.gemini_adapter import GeminiProvider
from Relay.providers.ollama_adapter import OllamaProvider


def test_create_registered_providers():
    p_groq = create_provider("groq", ProviderConfig(enabled=True, model="llama-3.3-70b-versatile"), api_key="gsk-test")
    assert isinstance(p_groq, GroqProvider)
    assert p_groq.name == "groq"

    p_openrouter = create_provider("openrouter", ProviderConfig(enabled=True, model="anthropic/claude-3.5-sonnet"), api_key="sk-or-test")
    assert isinstance(p_openrouter, OpenRouterProvider)

    p_openai = create_provider("openai", ProviderConfig(enabled=True, model="gpt-4o"), api_key="sk-test")
    assert isinstance(p_openai, OpenAIProvider)

    p_anthropic = create_provider("anthropic", ProviderConfig(enabled=True, model="claude-3-5-sonnet-20241022"), api_key="sk-ant-test")
    assert isinstance(p_anthropic, AnthropicProvider)

    p_gemini = create_provider("gemini", ProviderConfig(enabled=True, model="gemini-1.5-pro"), api_key="AIzaSy-test")
    assert isinstance(p_gemini, GeminiProvider)

    p_ollama = create_provider("ollama", ProviderConfig(enabled=True, model="qwen2.5-coder"))
    assert isinstance(p_ollama, OllamaProvider)


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("unsupported_provider")
