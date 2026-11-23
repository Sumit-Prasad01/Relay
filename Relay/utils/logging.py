"""Structured logging with automatic secret redaction."""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict

# Secret patterns for redaction
_SECRET_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9]{40,}", re.IGNORECASE),  # Groq API key
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),  # OpenAI / general sk
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),  # Anthropic key
    re.compile(r"sk-or-v1-[a-zA-Z0-9]{32,}", re.IGNORECASE),  # OpenRouter key
    re.compile(r"AIzaSy[a-zA-Z0-9_\-]{30,}", re.IGNORECASE),  # Google Gemini key
    re.compile(r"(api[_-]?key|secret|password|bearer|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Redact known API keys and secret patterns from text."""
    if not isinstance(text, str):
        return text

    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups > 1:
            redacted = pattern.sub(r"\1=***REDACTED***", redacted)
        else:
            redacted = pattern.sub("***REDACTED***", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """Logging formatter that redacts secrets and formats structured JSON or plain text."""

    def __init__(self, json_format: bool = False):
        super().__init__()
        self.json_format = json_format

    def format(self, record: logging.LogRecord) -> str:
        orig_msg = record.getMessage()
        safe_msg = redact_secrets(orig_msg)

        if self.json_format:
            payload: Dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": safe_msg,
            }
            if hasattr(record, "extra") and isinstance(record.extra, dict):
                payload.update({k: redact_secrets(str(v)) for k, v in record.extra.items()})
            if record.exc_info:
                payload["exception"] = redact_secrets(self.formatException(record.exc_info))
            return json.dumps(payload)

        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{timestamp}] [{record.levelname:<5}] [{record.name}]"
        if record.exc_info:
            return f"{prefix} {safe_msg}\n{redact_secrets(self.formatException(record.exc_info))}"
        return f"{prefix} {safe_msg}"


def configure_logging(debug: bool = False, json_logs: bool = False) -> None:
    """Configure root logger with redacting formatter."""
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(RedactingFormatter(json_format=json_logs))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
