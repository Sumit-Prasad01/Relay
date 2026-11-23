"""Standard directory and path resolution for Relay Agent."""

import os
import tempfile
from pathlib import Path


def _get_writable_dir(candidates: list[Path]) -> Path:
    """Return the first candidate directory that can be created/written to."""
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Verify write access
            test_file = candidate / ".test_write"
            test_file.touch()
            test_file.unlink()
            return candidate
        except (PermissionError, OSError):
            continue

    # Absolute fallback: tempdir
    fallback = Path(tempfile.gettempdir()) / "relay"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_user_config_dir() -> Path:
    """User configuration directory (~/.config/relay or %APPDATA%/relay, with sandbox fallback)."""
    if os.environ.get("RELAY_CONFIG_DIR"):
        return _get_writable_dir([Path(os.environ["RELAY_CONFIG_DIR"])])

    if os.name == "nt":
        primary = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "relay"
    else:
        primary = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "relay"

    candidates = [
        primary,
        Path.home() / ".relay",
        Path.cwd() / ".relay",
        Path(tempfile.gettempdir()) / "relay" / "config",
    ]
    return _get_writable_dir(candidates)


def get_user_data_dir() -> Path:
    """User data directory (~/.local/share/relay or %LOCALAPPDATA%/relay, with sandbox fallback)."""
    if os.environ.get("RELAY_DATA_DIR"):
        return _get_writable_dir([Path(os.environ["RELAY_DATA_DIR"])])

    if os.name == "nt":
        primary = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "relay"
    else:
        primary = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "relay"

    candidates = [
        primary,
        Path.home() / ".relay" / "data",
        Path.cwd() / ".relay" / "data",
        Path(tempfile.gettempdir()) / "relay" / "data",
    ]
    return _get_writable_dir(candidates)


def get_default_config_path() -> Path:
    return get_user_config_dir() / "config.toml"


def get_default_database_path() -> Path:
    return get_user_data_dir() / "state.db"


def find_workspace_root(start_dir: Path | None = None) -> Path:
    """Locate the root of the active workspace by checking for .git or .relay/ or relay.toml."""
    current = (start_dir or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").is_dir() or (parent / ".relay").is_dir() or (parent / "relay.toml").is_file():
            return parent
    return current
