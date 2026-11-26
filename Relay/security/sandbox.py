"""Command execution sandbox with timeouts and output bounds (Section 8.5 & 9.3)."""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from Relay.utils.logging import redact_secrets
from Relay.utils.platform import is_windows, terminate_process_tree

_QUOTED_DRIVE_PATH_RE = re.compile(r'"([A-Za-z]):\\([^"]+)"')
_DRIVE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_\\])([A-Za-z]):\\([^\s\"'`|&;<>()]+)")
_REL_DOT_VENV_PATH_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s\"'=;|&(]))(\.\.?|\.venv|venv)\\([^\s\"'`|&;<>()]+)"
)
_MULTI_SEG_PATH_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s\"'=;|&(]))([A-Za-z0-9_.\-]+(?:\\[A-Za-z0-9_.\-]+){2,})(?=$|[\s\"'|&;<>()])"
)
_EXT_PATH_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s\"'=;|&(]))([A-Za-z0-9_.\-]+\\[A-Za-z0-9_.\-]+\.(?:py|exe|csv|json|txt|md|toml|yaml|yml|bat|cmd|ps1|sh))(?=$|[\s\"'|&;<>()])",
    re.IGNORECASE,
)


def normalize_windows_paths_for_bash(command: str) -> str:
    """Convert unquoted/double-quoted Windows backslash paths to forward slashes for Git Bash."""
    if "\\" not in command:
        return command

    # Split by single-quoted segments so literal '...' strings in bash stay untouched
    parts = re.split(r"('[^']*')", command)
    for idx in range(0, len(parts), 2):
        seg = parts[idx]
        seg = _QUOTED_DRIVE_PATH_RE.sub(lambda m: f'"{m.group(1)}:/' + m.group(2).replace("\\", "/") + '"', seg)
        seg = _DRIVE_PATH_RE.sub(lambda m: f"{m.group(1)}:/" + m.group(2).replace("\\", "/"), seg)
        seg = _REL_DOT_VENV_PATH_RE.sub(lambda m: f"{m.group(1)}/" + m.group(2).replace("\\", "/"), seg)
        seg = _MULTI_SEG_PATH_RE.sub(lambda m: m.group(1).replace("\\", "/"), seg)
        seg = _EXT_PATH_RE.sub(lambda m: m.group(1).replace("\\", "/"), seg)
        parts[idx] = seg
    return "".join(parts)


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False

    @property
    def output(self) -> str:
        combined = (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()
        return redact_secrets(combined or "(no output)")


class SandboxRunner:
    """Executes commands with process tree isolation, timeouts, and output limits."""

    def __init__(
        self,
        workspace_root: Path,
        timeout_seconds: int = 120,
        max_output_bytes: int = 200_000,
    ):
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _resolve_shell(self) -> Tuple[list[str], bool]:
        if is_windows():
            # Try Git Bash first
            candidates = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
                Path(os.environ.get("LocalAppData", "")) / "Programs" / "Git" / "bin" / "bash.exe",
            ]
            for c in candidates:
                if c.is_file():
                    return [str(c), "-c"], False
            powershell = shutil.which("powershell.exe") or shutil.which("powershell")
            if powershell:
                return [powershell, "-NoProfile", "-Command"], False
            return [], True
        return ["/bin/sh", "-c"], False

    def run(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Run a command inside the workspace directory."""
        effective_timeout = timeout or self.timeout_seconds
        shell_prefix, use_shell = self._resolve_shell()
        effective_cmd = command
        if is_windows() and shell_prefix and Path(shell_prefix[0]).name.lower() == "bash.exe":
            effective_cmd = normalize_windows_paths_for_bash(command)
        cmd = shell_prefix + [effective_cmd] if shell_prefix else effective_cmd

        import time
        start_time = time.time()

        env = dict(os.environ)
        current_path = env.get("PATH", "")

        # Prioritize workspace virtual environment ahead of Relay's own venv
        scripts_dir = "Scripts" if is_windows() else "bin"
        ws_venv = None
        for venv_name in (".venv", "venv"):
            cand = self.workspace_root / venv_name / scripts_dir
            if cand.is_dir():
                ws_venv = cand
                env["VIRTUAL_ENV"] = str(self.workspace_root / venv_name)
                break

        prepend_dirs = []
        if ws_venv is not None:
            prepend_dirs.append(str(ws_venv))
        relay_bin = str(Path(sys.executable).parent)
        if ws_venv is None and relay_bin not in current_path:
            prepend_dirs.append(relay_bin)

        if prepend_dirs:
            env["PATH"] = f"{os.pathsep.join(prepend_dirs)}{os.pathsep}{current_path}"

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace_root,
                env=env,
                shell=use_shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = proc.communicate(timeout=effective_timeout)
            duration_ms = int((time.time() - start_time) * 1000)

            # Enforce output length limit
            if len(stdout) > self.max_output_bytes:
                stdout = stdout[:self.max_output_bytes] + f"\n\n[Output truncated: exceeded {self.max_output_bytes} bytes]"
            if len(stderr) > self.max_output_bytes:
                stderr = stderr[:self.max_output_bytes] + f"\n\n[Output truncated: exceeded {self.max_output_bytes} bytes]"

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            terminate_process_tree(proc.pid)
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {effective_timeout} seconds and was killed.",
                exit_code=124,
                duration_ms=duration_ms,
                timed_out=True,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                stdout="",
                stderr=f"Failed to execute command: {e}",
                exit_code=1,
                duration_ms=duration_ms,
                timed_out=False,
            )
