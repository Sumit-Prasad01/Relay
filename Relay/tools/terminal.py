"""Terminal execution tool (Section 8.5)."""

from pathlib import Path
from typing import Any, Dict
from Relay.security.sandbox import SandboxRunner
from Relay.tools.base import BaseTool, ToolResult


class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Run a terminal shell command inside the workspace directory."
    category = "execute"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "integer", "description": "Command timeout in seconds", "default": 120},
        },
        "required": ["command"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        sandbox = getattr(context, "sandbox", None) or SandboxRunner(workspace_root)

        res = sandbox.run(
            command=arguments["command"],
            timeout=arguments.get("timeout"),
        )

        return ToolResult(
            content=res.output,
            success=res.exit_code == 0,
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
            error=res.stderr if res.exit_code != 0 else None,
        )
