"""Configuration loader implementing precedence hierarchy (Section 15)."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from Relay.config.defaults import get_default_config
from Relay.config.schemas import RootConfig
from Relay.utils.errors import ConfigurationError
from Relay.utils.paths import get_default_config_path


def _deep_update(source: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, dict) and key in source and isinstance(source[key], dict):
            _deep_update(source[key], value)
        else:
            source[key] = value
    return source


def _read_toml_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise ConfigurationError(f"Failed to parse configuration file {path}: {e}")


def load_config(
    workspace_root: Optional[Path] = None,
    config_path: Optional[Path] = None,
    cli_provider: Optional[str] = None,
    cli_model: Optional[str] = None,
    cli_api_key: Optional[str] = None,
) -> RootConfig:
    """Load configuration following precedence:
    1. CLI flags (provider, model, api_key)
    2. Environment variables
    3. Workspace configuration (.relay/config.toml or relay.toml)
    4. User configuration (~/.config/relay/config.toml)
    5. Application defaults
    """
    base = get_default_config()
    raw = base.model_dump()

    # 4. User configuration
    user_cfg_path = config_path or get_default_config_path()
    user_data = _read_toml_file(user_cfg_path)
    _deep_update(raw, user_data)

    # 3. Workspace configuration
    if workspace_root:
        ws_candidates = [
            workspace_root / ".relay" / "config.toml",
            workspace_root / "relay.toml",
        ]
        for ws_file in ws_candidates:
            if ws_file.is_file():
                ws_data = _read_toml_file(ws_file)
                if "providers" in ws_data:
                    for p in ws_data["providers"].values():
                        if isinstance(p, dict):
                            p.pop("credential_ref", None)
                _deep_update(raw, ws_data)
                break

    # 2. Environment variables
    if os.environ.get("RELAY_DEFAULT_PROVIDER"):
        raw["default_provider"] = os.environ["RELAY_DEFAULT_PROVIDER"]
    if os.environ.get("RELAY_DEFAULT_MODEL"):
        raw["default_model"] = os.environ["RELAY_DEFAULT_MODEL"]
    if os.environ.get("RELAY_PERMISSION_MODE"):
        raw["permission_mode"] = os.environ["RELAY_PERMISSION_MODE"]

    # 1. CLI flags (highest priority)
    if cli_provider:
        raw["default_provider"] = cli_provider.lower().strip()
    if cli_model:
        raw["default_model"] = cli_model.strip()
        # Also ensure provider's configured model reflects this override
        curr_provider = raw["default_provider"]
        if curr_provider in raw.get("providers", {}):
            raw["providers"][curr_provider]["model"] = cli_model.strip()

    if cli_api_key:
        curr_provider = raw["default_provider"]
        # Set environment variable temporarily for runtime lookup
        env_var_name = f"{curr_provider.upper()}_API_KEY"
        os.environ[env_var_name] = cli_api_key.strip()

    try:
        return RootConfig.model_validate(raw)
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")
