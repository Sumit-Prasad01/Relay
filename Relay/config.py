"""Settings: real environment variables first, then ~/.agents/env or .env."""

import os
from pathlib import Path


def _load_env(path: Path):
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return
    for line in content.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)


# Load from common .env locations (current dir, parent dir, ~/.agents/env, ~/.agents/.env)
_CANDIDATE_ENV_FILES = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
    Path.home() / ".agents" / "env",
    Path.home() / ".agents" / ".env",
]

for env_path in _CANDIDATE_ENV_FILES:
    _load_env(env_path)


BASE_URL = os.environ.get("BASE_URL")
if BASE_URL:
    BASE_URL = BASE_URL.strip()
    if "openrouter.ai" in BASE_URL and not BASE_URL.rstrip("/").endswith("/api/v1"):
        BASE_URL = BASE_URL.rstrip("/") + "/api/v1"

API_KEY = os.environ.get("API_KEY")

# Default base_url to openrouter if api_key is an openrouter key and no base_url was set
if not BASE_URL and API_KEY and API_KEY.startswith("sk-or-"):
    BASE_URL = "https://openrouter.ai/api/v1"
elif not BASE_URL:
    BASE_URL = "https://openrouter.ai/api/v1"

MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")


# How much room the model has, and how we spend it.
CONTEXT_WINDOW = int(os.environ.get("CONTEXT_WINDOW", 128_000))
COMPACT_AT = float(os.environ.get("COMPACT_AT", 0.85))  # compact once the prompt crosses this much of the window
COMPACT_TO = float(os.environ.get("COMPACT_TO", 0.35))  # and cut back to this much, so it does not retrigger soon
