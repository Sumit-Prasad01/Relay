"""Model capability registry and resolution (Section 6.3)."""

from typing import Dict, Optional
from Relay.providers.base import ModelCapabilities

# Maintained registry of known models across providers
KNOWN_CAPABILITIES: Dict[str, ModelCapabilities] = {
    # Groq models
    "llama-3.3-70b-versatile": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        parallel_tool_calls=True,
        max_context_tokens=128000,
        max_output_tokens=32768,
        structured_output=True,
    ),
    "llama-3.1-8b-instant": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        parallel_tool_calls=True,
        max_context_tokens=128000,
        max_output_tokens=8192,
        structured_output=True,
    ),
    "mixtral-8x7b-32768": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        parallel_tool_calls=False,
        max_context_tokens=32768,
        max_output_tokens=32768,
    ),
    # OpenAI models
    "gpt-4o": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        parallel_tool_calls=True,
        max_context_tokens=128000,
        max_output_tokens=16384,
    ),
    "gpt-4o-mini": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        parallel_tool_calls=True,
        max_context_tokens=128000,
        max_output_tokens=16384,
    ),
    "o1": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        max_context_tokens=200000,
        max_output_tokens=100000,
        reasoning_controls=True,
    ),
    "o3-mini": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        structured_output=True,
        max_context_tokens=200000,
        max_output_tokens=100000,
        reasoning_controls=True,
    ),
    # Anthropic models
    "claude-3-5-sonnet-20241022": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        parallel_tool_calls=True,
        max_context_tokens=200000,
        max_output_tokens=8192,
    ),
    "claude-3-5-haiku-20241022": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        parallel_tool_calls=True,
        max_context_tokens=200000,
        max_output_tokens=8192,
    ),
    "claude-3-opus-20240229": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        max_context_tokens=200000,
        max_output_tokens=4096,
    ),
    # Gemini models
    "gemini-1.5-pro": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        max_context_tokens=2000000,
        max_output_tokens=8192,
    ),
    "gemini-1.5-flash": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        max_context_tokens=1000000,
        max_output_tokens=8192,
    ),
    "gemini-2.0-flash": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        vision=True,
        structured_output=True,
        max_context_tokens=1000000,
        max_output_tokens=8192,
    ),
    # Ollama models
    "qwen2.5-coder": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        max_context_tokens=32768,
        max_output_tokens=8192,
    ),
    "llama3.1": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        max_context_tokens=128000,
        max_output_tokens=8192,
    ),
    "deepseek-coder-v2": ModelCapabilities(
        tool_calling=True,
        streaming=True,
        max_context_tokens=64000,
        max_output_tokens=8192,
    ),
}


class CapabilityRegistry:
    """Resolves model capabilities following the priority:
    1. User-supplied overrides
    2. Maintained registry
    3. Conservative unknown default
    """

    def __init__(self, user_overrides: Optional[Dict[str, ModelCapabilities]] = None):
        self._user_overrides = user_overrides or {}

    def get_capabilities(self, model: str) -> ModelCapabilities:
        clean_model = model.split("/")[-1].lower() if "/" in model else model.lower()

        # 1. User overrides
        if model in self._user_overrides:
            return self._user_overrides[model]
        if clean_model in self._user_overrides:
            return self._user_overrides[clean_model]

        # 2. Maintained registry
        if model.lower() in KNOWN_CAPABILITIES:
            return KNOWN_CAPABILITIES[model.lower()]
        for known_key, caps in KNOWN_CAPABILITIES.items():
            if known_key in clean_model or clean_model in known_key:
                return caps

        # 3. Conservative default for unknown models
        return ModelCapabilities(
            tool_calling=False,
            streaming=True,
            max_context_tokens=32768,
            max_output_tokens=4096,
        )
