"""Ollama provider adapter for local models (Section 6.2)."""

from typing import List, Optional
import httpx
from Relay.providers.base import ModelInfo, ProviderHealth
from Relay.providers.openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Adapter for local Ollama daemon."""

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 60.0):
        url = (base_url or "http://localhost:11434").rstrip("/")
        v1_url = f"{url}/v1" if not url.endswith("/v1") else url
        self.raw_base_url = url.replace("/v1", "")

        super().__init__(
            name="ollama",
            base_url=v1_url,
            api_key=api_key or "ollama",  # local instance doesn't require real key
            timeout=timeout,
        )

    async def validate(self) -> ProviderHealth:
        """Validate that local Ollama daemon is reachable and list installed models."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                res = await client.get(f"{self.raw_base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return ProviderHealth(
                        healthy=True,
                        provider="ollama",
                        message=f"Ollama daemon reachable at {self.raw_base_url}. Installed models: {len(models)}",
                        models=models,
                    )
                return ProviderHealth(
                    healthy=False,
                    provider="ollama",
                    message=f"Ollama daemon returned status {res.status_code}",
                )
            except Exception as e:
                return ProviderHealth(
                    healthy=False,
                    provider="ollama",
                    message=f"Ollama daemon not reachable at {self.raw_base_url}: {e}",
                )

    async def list_models(self) -> List[ModelInfo]:
        """Fetch models installed in local Ollama instance."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                res = await client.get(f"{self.raw_base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [
                        ModelInfo(
                            id=m["name"],
                            name=m["name"],
                            capabilities=self.get_capabilities(m["name"]),
                        )
                        for m in data.get("models", [])
                    ]
            except Exception:
                pass
        return []
