"""Command execution sandbox with timeouts and output bounds (Section 8.5 & 9.3)."""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from Relay.utils.logging import redact_secrets
from Relay.utils.platform import is_windows, terminate_process_tree


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
        cmd = shell_prefix + [command] if shell_prefix else command

        import time
        start_time = time.time()

        env = dict(os.environ)
        venv_bin = str(Path(sys.executable).parent)
        current_path = env.get("PATH", "")
        if venv_bin not in current_path:
            env["PATH"] = f"{venv_bin}{os.pathsep}{current_path}"

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
