"""Default configuration constants and standard provider profiles (including Groq)."""

from Relay.config.schemas import ProviderConfig, RootConfig
from Relay.utils.paths import get_default_database_path

DEFAULT_PROVIDERS = {
    "groq": ProviderConfig(
        enabled=True,
        model="llama-3.3-70b-versatile",
        credential_ref="relay/groq",
        base_url="https://api.groq.com/openai/v1",
    ),
    "openrouter": ProviderConfig(
        enabled=True,
        model="anthropic/claude-3.5-sonnet",
        credential_ref="relay/openrouter",
        base_url="https://openrouter.ai/api/v1",
    ),
    "openai": ProviderConfig(
        enabled=True,
        model="gpt-4o",
        credential_ref="relay/openai",
    ),
    "anthropic": ProviderConfig(
        enabled=True,
        model="claude-3-5-sonnet-20241022",
        credential_ref="relay/anthropic",
    ),
    "gemini": ProviderConfig(
        enabled=True,
        model="gemini-1.5-pro",
        credential_ref="relay/gemini",
    ),
    "ollama": ProviderConfig(
        enabled=True,
        model="qwen2.5-coder",
        base_url="http://localhost:11434",
    ),
}


def get_default_config() -> RootConfig:
    cfg = RootConfig()
    cfg.providers = {k: v.model_copy() for k, v in DEFAULT_PROVIDERS.items()}
    cfg.storage.database_path = str(get_default_database_path())
    return cfg
