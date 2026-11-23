"""OpenAI provider adapter (Section 6.2)."""

from typing import Optional
from Relay.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """Adapter for official OpenAI Chat Completions API."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 60.0):
        super().__init__(
            name="openai",
            base_url=base_url or self.DEFAULT_BASE_URL,
            api_key=api_key,
            timeout=timeout,
        )
