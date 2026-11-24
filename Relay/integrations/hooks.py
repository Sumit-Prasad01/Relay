"""Configurable lifecycle hooks with timeout and security bounding (Section 14.3)."""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.utils.logging import get_logger, redact_secrets

logger = get_logger(__name__)


class HookType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_EXECUTE = "pre_tool_execute"
    POST_TOOL_EXECUTE = "post_tool_execute"
    PRE_FILE_MODIFY = "pre_file_modify"
    POST_FILE_MODIFY = "post_file_modify"


@dataclass
class HookConfig:
    hook_type: HookType
    command: str
    timeout_seconds: int = 15


class HookManager:
    """Dispatches lifecycle hooks safely without blocking agent flow on failure."""

    def __init__(self, workspace_root: Path, hooks: Optional[List[HookConfig]] = None):
        self.workspace_root = workspace_root.resolve()
        self.hooks = hooks or []

    def execute_hook(
        self,
        hook_type: HookType,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Trigger configured hooks for a given lifecycle event."""
        matching = [h for h in self.hooks if h.hook_type == hook_type]
        if not matching:
            return

        env = dict(os.environ)
        if context:
            for k, v in context.items():
                env[f"RELAY_HOOK_{k.upper()}"] = str(v)

        for h in matching:
            try:
                logger.info(f"Executing hook {h.hook_type}: {h.command}")
                proc = subprocess.run(
                    h.command,
                    shell=True,
                    cwd=self.workspace_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=h.timeout_seconds,
                )
                if proc.returncode != 0:
                    logger.warning(f"Hook {h.hook_type} exited with status {proc.returncode}: {redact_secrets(proc.stderr)}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Hook {h.hook_type} timed out after {h.timeout_seconds}s")
            except Exception as e:
                logger.warning(f"Failed to execute hook {h.hook_type}: {e}")
