import pytest
from Relay.providers.base import ModelCapabilities
from Relay.providers.capabilities import CapabilityRegistry


def test_known_capabilities():
    registry = CapabilityRegistry()

    groq_caps = registry.get_capabilities("llama-3.3-70b-versatile")
    assert groq_caps.tool_calling is True
    assert groq_caps.streaming is True
    assert groq_caps.max_context_tokens == 128000

    openai_caps = registry.get_capabilities("gpt-4o")
    assert openai_caps.tool_calling is True
    assert openai_caps.vision is True
    assert openai_caps.parallel_tool_calls is True

    anthropic_caps = registry.get_capabilities("claude-3-5-sonnet-20241022")
    assert anthropic_caps.tool_calling is True
    assert anthropic_caps.max_context_tokens == 200000

    ollama_caps = registry.get_capabilities("qwen2.5-coder")
    assert ollama_caps.tool_calling is True


def test_user_override():
    custom_override = {
        "custom-model": ModelCapabilities(
            tool_calling=True,
            streaming=True,
            max_context_tokens=65536,
        )
    }
    registry = CapabilityRegistry(user_overrides=custom_override)
    caps = registry.get_capabilities("custom-model")
    assert caps.tool_calling is True
    assert caps.max_context_tokens == 65536


def test_unknown_model_fallback():
    registry = CapabilityRegistry()
    caps = registry.get_capabilities("unknown-future-model-v9")
    # Conservative unknown model default
    assert caps.tool_calling is False
    assert caps.streaming is True
    assert caps.max_context_tokens == 32768
