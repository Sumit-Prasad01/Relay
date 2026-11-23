import pytest
from Relay.config.secrets import SecretManager
from Relay.utils.logging import redact_secrets


def test_groq_env_credential_retrieval(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test1234567890abcdef1234567890abcdef1234567890")
    secret = SecretManager.get_credential("relay/groq")
    assert secret == "gsk_test1234567890abcdef1234567890abcdef1234567890"


def test_secret_redaction():
    raw = "Connecting with key gsk_1234567890abcdef1234567890abcdef1234567890 and api_key='secret-pass'"
    redacted = redact_secrets(raw)
    assert "gsk_1234567890abcdef1234567890abcdef1234567890" not in redacted
    assert "***REDACTED***" in redacted
