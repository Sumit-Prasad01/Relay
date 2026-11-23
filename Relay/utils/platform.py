"""OS detection, process management, and platform utilities."""

import os
import signal
import subprocess
import sys


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def get_platform_name() -> str:
    if is_windows():
        return "windows"
    if is_macos():
        return "macos"
    if is_linux():
        return "linux"
    return "unknown"


def terminate_process_tree(pid: int) -> None:
    """Terminate a process and all its children across platforms."""
    if is_windows():
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def sanitize_filename(name: str) -> str:
    """Convert arbitrary strings into safe filenames cross-platform."""
    for ch in [":", "/", "\\", "?", "*", "<", ">", "|", "\""]:
        name = name.replace(ch, "_")
    return name.strip()
