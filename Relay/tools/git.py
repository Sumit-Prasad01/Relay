"""Git inspection and mutation tools (Section 8.1)."""

import subprocess
from pathlib import Path
from typing import Any, Dict
from Relay.tools.base import BaseTool, ToolResult


def _git_run(cmd: list[str], cwd: Path) -> ToolResult:
    try:
        proc = subprocess.run(
            ["git"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        combined = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
        return ToolResult(
            content=combined or "(clean/no output)",
            success=proc.returncode == 0,
            exit_code=proc.returncode,
        )
    except Exception as e:
        return ToolResult(content=f"Git error: {e}", success=False)


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Show the working tree status."
    category = "read"
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        return _git_run(["status", "--short"], workspace_root)


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Show changes between commits, commit and working tree, etc."
    category = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional specific file path to diff"},
        },
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        cmd = ["diff"]
        if arguments.get("path"):
            cmd.append(arguments["path"])
        return _git_run(cmd, workspace_root)


class GitLogTool(BaseTool):
    name = "git_log"
    description = "Show commit logs."
    category = "read"
    parameters = {
        "type": "object",
        "properties": {
            "max_count": {"type": "integer", "description": "Number of commits to return", "default": 10},
        },
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        n = arguments.get("max_count", 10)
        return _git_run(["log", f"-n{n}", "--oneline"], workspace_root)


class GitBranchTool(BaseTool):
    name = "git_branch"
    description = "Create or switch git branches."
    category = "git"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Branch name"},
            "create": {"type": "boolean", "description": "Create new branch", "default": False},
        },
        "required": ["name"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        cmd = ["checkout", "-b", arguments["name"]] if arguments.get("create") else ["checkout", arguments["name"]]
        return _git_run(cmd, workspace_root)


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Record changes to the repository."
    category = "git"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Commit message"},
            "all": {"type": "boolean", "description": "Stage all modified files (-a)", "default": True},
        },
        "required": ["message"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        cmd = ["commit", "-m", arguments["message"]]
        if arguments.get("all", True):
            cmd.append("-a")
        return _git_run(cmd, workspace_root)
