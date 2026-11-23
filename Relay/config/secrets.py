"""Secure credential management using OS keyring with environment variable fallback (Section 6.5)."""

import os
import warnings
from typing import Optional

try:
    import keyring
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False


ENV_KEY_MAP = {
    "relay/groq": ["GROQ_API_KEY"],
    "relay/openai": ["OPENAI_API_KEY"],
    "relay/anthropic": ["ANTHROPIC_API_KEY"],
    "relay/gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "relay/openrouter": ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "API_KEY"],
}


class SecretManager:
    """Manages secure retrieval and storage of provider secrets."""

    SERVICE_NAME = "relay-agent"

    @classmethod
    def get_credential(cls, ref: str) -> Optional[str]:
        """Fetch secret by reference, checking environment variables first, then keyring."""
        env_vars = ENV_KEY_MAP.get(ref, [])
        for env_var in env_vars:
            val = os.environ.get(env_var)
            if val and val.strip():
                return val.strip()

        direct_env = os.environ.get(ref.replace("/", "_").upper())
        if direct_env and direct_env.strip():
            return direct_env.strip()

        if KEYRING_AVAILABLE:
            try:
                secret = keyring.get_password(cls.SERVICE_NAME, ref)
                if secret:
                    return secret.strip()
            except Exception as e:
                warnings.warn(f"Keyring access failed for {ref}: {e}")

        return None

    @classmethod
    def set_credential(cls, ref: str, secret: str) -> bool:
        """Store secret in OS keyring."""
        if not KEYRING_AVAILABLE:
            raise RuntimeError(
                "Keyring is unavailable on this platform. "
                "Please configure credentials using environment variables instead."
            )
        keyring.set_password(cls.SERVICE_NAME, ref, secret)
        return True

    @classmethod
    def delete_credential(cls, ref: str) -> bool:
        """Remove secret from OS keyring."""
        if not KEYRING_AVAILABLE:
            return False
        try:
            keyring.delete_password(cls.SERVICE_NAME, ref)
            return True
        except Exception:
            return False

    @classmethod
    def is_keyring_available(cls) -> bool:
        return KEYRING_AVAILABLE
