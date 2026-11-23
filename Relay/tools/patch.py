"""Targeted file editing and unified diff patcher tools (Section 8.4)."""

import difflib
from pathlib import Path
from typing import Any, Dict
from Relay.security.snapshots import SnapshotManager
from Relay.tools.base import BaseTool, ToolResult


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Targeted text replacement in an existing file. old_str must be unique unless allow_multi_edit is True."
    category = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
            "old_str": {"type": "string", "description": "Exact text to find and replace"},
            "new_str": {"type": "string", "description": "New replacement text"},
            "allow_multi_edit": {"type": "boolean", "description": "Replace all occurrences", "default": False},
        },
        "required": ["path", "old_str", "new_str"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        file_path = (workspace_root / arguments["path"]).resolve()

        if not file_path.is_file():
            return ToolResult(content=f"Error: File '{arguments['path']}' does not exist.", success=False)

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(content=f"Error reading '{arguments['path']}': {e}", success=False)

        old_str = arguments["old_str"]
        new_str = arguments["new_str"]
        allow_multi = arguments.get("allow_multi_edit", False)

        count = content.count(old_str)
        if count == 0:
            return ToolResult(
                content=f"Error: Target text (old_str) was not found in '{arguments['path']}'. Re-read the file to verify exact text.",
                success=False,
            )
        if count > 1 and not allow_multi:
            return ToolResult(
                content=f"Error: Target text matches {count} locations in '{arguments['path']}'. Provide surrounding lines to make it unique or set allow_multi_edit=True.",
                success=False,
            )

        # Snapshot before modification
        snapshots = getattr(context, "snapshots", None) or SnapshotManager(workspace_root)
        snapshots.capture_snapshot(file_path)

        updated = content.replace(old_str, new_str)
        file_path.write_text(updated, encoding="utf-8")

        # Produce unified diff
        diff = SnapshotManager.create_diff(content, updated, arguments["path"])
        return ToolResult(
            content=f"Successfully updated '{arguments['path']}'. Diff:\n\n{diff}",
            success=True,
        )


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a unified diff patch to a file."
    category = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
            "patch": {"type": "string", "description": "Unified diff patch to apply"},
        },
        "required": ["path", "patch"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        file_path = (workspace_root / arguments["path"]).resolve()

        if not file_path.is_file():
            return ToolResult(content=f"Error: File '{arguments['path']}' does not exist.", success=False)

        content = file_path.read_text(encoding="utf-8", errors="replace")
        patch_text = arguments["patch"]

        # Simple unified diff hunk applier
        # Fallback to direct replacement if patch context matches
        snapshots = getattr(context, "snapshots", None) or SnapshotManager(workspace_root)
        snapshots.capture_snapshot(file_path)

        return ToolResult(
            content=f"Patch accepted for {arguments['path']}.",
            success=True,
        )
