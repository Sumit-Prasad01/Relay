"""OpenRouter provider adapter (Section 6.2)."""

from typing import Optional
from Relay.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """Adapter for OpenRouter API with attribution headers and model routing."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 60.0):
        headers = {
            "HTTP-Referer": "https://github.com/relay-agent/relay",
            "X-Title": "Relay Coding Agent",
        }
        super().__init__(
            name="openrouter",
            base_url=base_url or self.DEFAULT_BASE_URL,
            api_key=api_key,
            default_headers=headers,
            timeout=timeout,
        )
