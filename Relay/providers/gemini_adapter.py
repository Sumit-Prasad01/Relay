"""Google Gemini provider adapter (Section 6.2)."""

from typing import Optional
from Relay.providers.openai_compatible import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    """Adapter for Google Gemini via its OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 60.0):
        super().__init__(
            name="gemini",
            base_url=base_url or self.DEFAULT_BASE_URL,
            api_key=api_key,
            timeout=timeout,
        )
