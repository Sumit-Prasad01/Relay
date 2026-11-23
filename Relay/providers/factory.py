"""Provider factory (Section 6)."""

from typing import Optional
from Relay.config.schemas import ProviderConfig
from Relay.config.secrets import SecretManager
from Relay.providers.base import LLMProvider
from Relay.providers.registry import ProviderRegistry


def create_provider(
    name: str,
    config: Optional[ProviderConfig] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """Instantiate a provider adapter with configured secrets and base URL."""
    provider_cls = ProviderRegistry.get(name)
    resolved_api_key = api_key

    # Retrieve secret from config credential_ref or SecretManager if not passed directly
    if not resolved_api_key:
        ref = config.credential_ref if config and config.credential_ref else f"relay/{name.lower()}"
        resolved_api_key = SecretManager.get_credential(ref)

    base_url = config.base_url if config and config.base_url else None
    timeout = config.timeout_seconds if config and config.timeout_seconds else 60.0

    return provider_cls(
        api_key=resolved_api_key,
        base_url=base_url,
        timeout=timeout,
    )
