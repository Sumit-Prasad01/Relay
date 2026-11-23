"""Provider registry for mapping provider names to implementation classes."""

from typing import Dict, List, Type
from Relay.providers.base import LLMProvider
from Relay.providers.groq_adapter import GroqProvider
from Relay.providers.openrouter_adapter import OpenRouterProvider
from Relay.providers.openai_adapter import OpenAIProvider
from Relay.providers.anthropic_adapter import AnthropicProvider
from Relay.providers.gemini_adapter import GeminiProvider
from Relay.providers.ollama_adapter import OllamaProvider

_REGISTRY: Dict[str, Type[LLMProvider]] = {
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


class ProviderRegistry:
    """Manages provider adapter registrations."""

    @classmethod
    def register(cls, name: str, provider_cls: Type[LLMProvider]) -> None:
        _REGISTRY[name.lower().strip()] = provider_cls

    @classmethod
    def get(cls, name: str) -> Type[LLMProvider]:
        key = name.lower().strip()
        if key not in _REGISTRY:
            raise ValueError(
                f"Unknown provider '{name}'. Available providers: {', '.join(cls.list_providers())}"
            )
        return _REGISTRY[key]

    @classmethod
    def list_providers(cls) -> List[str]:
        return list(_REGISTRY.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name.lower().strip() in _REGISTRY
