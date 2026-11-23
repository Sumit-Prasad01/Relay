"""Filesystem inspection and modification tools (Section 8.2)."""

from pathlib import Path
from typing import Any, Dict
from Relay.context.ignore import IgnoreRules
from Relay.security.snapshots import SnapshotManager
from Relay.tools.base import BaseTool, ToolResult


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories in the workspace."
    category = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path (default: root)"},
            "max_results": {"type": "integer", "description": "Maximum number of files to return", "default": 50},
        },
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        ignore_rules = IgnoreRules(workspace_root)
        rel = arguments.get("path", "") or "."
        target_dir = (workspace_root / rel).resolve()
        max_results = arguments.get("max_results", 50)

        if not target_dir.is_dir():
            return ToolResult(content=f"Error: Directory '{rel}' not found.", success=False)

        items = []
        for p in sorted(target_dir.iterdir()):
            if len(items) >= max_results:
                break
            if ignore_rules.is_ignored(p):
                continue
            item_type = "dir" if p.is_dir() else "file"
            items.append(f"{p.name}/" if p.is_dir() else p.name)

        output = "\n".join(items) if items else "(empty directory)"
        return ToolResult(content=output, success=True)


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a text file with line numbers."
    category = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path to read"},
            "offset": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
            "limit": {"type": "integer", "description": "Maximum lines to read", "default": 500},
        },
        "required": ["path"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        file_path = (workspace_root / arguments["path"]).resolve()

        if not file_path.is_file():
            return ToolResult(content=f"Error: File '{arguments['path']}' does not exist.", success=False)

        try:
            raw = file_path.read_bytes()
            if b"\x00" in raw[:1024]:
                return ToolResult(content=f"Error: '{arguments['path']}' is a binary file.", success=False)

            lines = raw.decode("utf-8", errors="replace").splitlines()
            offset = max(1, arguments.get("offset", 1)) - 1
            limit = arguments.get("limit", 500)
            selected = lines[offset: offset + limit]

            numbered = [f"{offset + idx + 1:>5} | {line}" for idx, line in enumerate(selected)]
            return ToolResult(content="\n".join(numbered) or "(empty file)", success=True)
        except Exception as e:
            return ToolResult(content=f"Error reading '{arguments['path']}': {e}", success=False)


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Create or overwrite a file with full contents."
    category = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path to write"},
            "content": {"type": "string", "description": "Full file contents"},
        },
        "required": ["path", "content"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        file_path = (workspace_root / arguments["path"]).resolve()
        content = arguments["content"]

        # Capture pre-change snapshot
        snapshots = getattr(context, "snapshots", None) or SnapshotManager(workspace_root)
        snapshots.capture_snapshot(file_path)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return ToolResult(content=f"Successfully wrote {len(content)} characters to {arguments['path']}.")
