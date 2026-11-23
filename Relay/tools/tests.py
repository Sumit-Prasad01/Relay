"""Automated test execution tool (Section 8.1 & 8.5)."""

from pathlib import Path
from typing import Any, Dict, Optional
from Relay.context.project import ProjectDiscovery
from Relay.security.sandbox import SandboxRunner
from Relay.tools.base import BaseTool, ToolResult


class RunTestsTool(BaseTool):
    name = "run_tests"
    description = "Run the project's test suite or a targeted test command."
    category = "execute"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Specific test command to run (e.g. 'pytest tests/test_calc.py')"},
        },
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        sandbox = getattr(context, "sandbox", None) or SandboxRunner(workspace_root)

        cmd = arguments.get("command")
        if not cmd:
            discovery = ProjectDiscovery(workspace_root)
            info = discovery.discover()
            if info.test_commands:
                cmd = info.test_commands[0]
            else:
                return ToolResult(content="Error: No automated test command detected in project.", success=False)

        res = sandbox.run(cmd)
        return ToolResult(
            content=res.output,
            success=res.exit_code == 0,
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
        )
