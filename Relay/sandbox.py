"""Kernel-enforced limits on what bash can touch.

One policy - read anything, write only inside the project, no network - and a
different enforcement mechanism per OS. The idea ports; the mechanism never does.

The macOS profile is adapted from openai/codex (Apache-2.0), simplified.
https://github.com/openai/codex
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path.cwd().resolve()

PROFILE = f"""(version 1)
(deny default)
(allow process-exec process-fork signal)
(allow file-read*)
(allow sysctl-read)
(deny network*)
(allow file-write* (subpath "{PROJECT.as_posix()}") (literal "/dev/null"))
(deny file-write* (subpath "{PROJECT.as_posix()}/.git"))
"""


def _find_windows_bash():
    """Find a functional bash executable on Windows, avoiding broken WSL stubs."""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("LocalAppData", "")) / "Programs" / "Git" / "bin" / "bash.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    # Check PATH, but avoid the System32\bash.exe WSL stub which fails if WSL has no distro
    found = shutil.which("bash.exe") or shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    return None


def wrap(command):
    """Wrap a shell command in an OS sandbox. None means we have no sandbox."""
    if sys.platform == "darwin":
        profile = Path(tempfile.gettempdir()) / "neuralcode.sb"
        profile.write_text(PROFILE, encoding="utf-8")
        return ["sandbox-exec", "-f", str(profile), "/bin/sh", "-c", command]

    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--bind", str(PROJECT), str(PROJECT),
            "--dev", "/dev", "--proc", "/proc",
            "--unshare-net", "--die-with-parent",
            "/bin/sh", "-c", command,
        ]

    return None  # Windows, or Linux without bubblewrap


def name():
    if sys.platform == "darwin":
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bubblewrap"
    return "none"


def run(command, timeout=60):
    """Run a command, sandboxed when the OS lets us."""
    sandboxed = wrap(command)
    cmd = sandboxed
    shell = False

    if cmd is None:
        if sys.platform == "win32":
            bash_bin = _find_windows_bash()
            if bash_bin:
                cmd = [bash_bin, "-c", command]
            else:
                powershell = shutil.which("powershell.exe") or shutil.which("powershell")
                if powershell:
                    cmd = [powershell, "-NoProfile", "-Command", command]
                else:
                    cmd = command
                    shell = True
        else:
            cmd = command
            shell = True

    return subprocess.run(
        cmd,
        shell=shell,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )