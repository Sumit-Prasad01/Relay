"""Project and runtime environment diagnostic tools (Section 8.1)."""

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict
from Relay.context.project import ProjectDiscovery
from Relay.tools.base import BaseTool, ToolResult


class DiagnoseProjectTool(BaseTool):
    name = "diagnose_project"
    description = "Detect repository languages, manifests, test commands, and instruction files."
    category = "read"
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        discovery = ProjectDiscovery(workspace_root)
        info = discovery.discover()

        lines = [
            f"Workspace: {info.workspace_root}",
            f"Git: {'Yes (' + str(info.git_branch) + ')' if info.is_git else 'No'}",
            f"Languages: {', '.join(info.languages) or 'Unknown'}",
            f"Manifests: {', '.join(info.manifests) or 'None'}",
            f"Test Commands: {', '.join(info.test_commands) or 'None'}",
            f"Lint Commands: {', '.join(info.lint_commands) or 'None'}",
            f"Instruction Files: {', '.join(info.instruction_files) or 'None'}",
        ]
        return ToolResult(content="\n".join(lines), success=True)


class GetEnvironmentTool(BaseTool):
    name = "get_environment"
    description = "Return runtime details: OS, Python version, platform architecture."
    category = "read"
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        lines = [
            f"OS: {platform.system()} {platform.release()}",
            f"Platform: {sys.platform}",
            f"Python: {sys.version.split()[0]}",
            f"Architecture: {platform.machine()}",
        ]
        return ToolResult(content="\n".join(lines), success=True)
