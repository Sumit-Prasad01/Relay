"""Targeted file editing and unified diff patcher tools (Section 8.4)."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Relay.security.snapshots import SnapshotManager
from Relay.tools.base import BaseTool, ToolResult

_HUNK_HEADER_RE = re.compile(r"^@@\s*(?:-(\d+)(?:,(\d+))?)?\s*(?:\+(\d+)(?:,(\d+))?)?\s*@@")
_LINE_PREFIX_RE = re.compile(r"^\s*\d+\s*\|\s")


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


def _parse_unified_hunks(patch_text: str) -> List[Tuple[Optional[int], List[str], List[str]]]:
    """Parse unified diff text into a list of (optional_1_based_start, old_lines, new_lines)."""
    hunks: List[Tuple[Optional[int], List[str], List[str]]] = []
    cur_start: Optional[int] = None
    old_lines: List[str] = []
    new_lines: List[str] = []
    in_hunk = False

    for line in patch_text.splitlines():
        if line.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            continue

        hunk_match = _HUNK_HEADER_RE.match(line)
        if hunk_match:
            if in_hunk:
                hunks.append((cur_start, old_lines, new_lines))
            cur_start = int(hunk_match.group(1)) if hunk_match.group(1) else None
            old_lines = []
            new_lines = []
            in_hunk = True
            continue

        if line.startswith("\\ No newline"):
            continue

        if not in_hunk:
            # Allow bare diff lines even without @@ header
            if line.startswith(("+", "-", " ")):
                in_hunk = True
                cur_start = None
            else:
                continue

        if line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith(" "):
            text = line[1:]
            old_lines.append(text)
            new_lines.append(text)
        else:
            # Context line missing leading space
            old_lines.append(line)
            new_lines.append(line)

    if in_hunk:
        hunks.append((cur_start, old_lines, new_lines))

    return hunks


def _find_subsequence(haystack: List[str], needle: List[str], hint_idx: int = 0) -> Optional[int]:
    """Find unique or hint-nearest index of needle inside haystack."""
    if not needle:
        return min(max(0, hint_idx), len(haystack))

    matches = [
        i for i in range(len(haystack) - len(needle) + 1)
        if haystack[i: i + len(needle)] == needle
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return min(matches, key=lambda idx: abs(idx - hint_idx))


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a unified diff patch to an existing file."
    category = "write"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
            "patch": {"type": "string", "description": "Unified diff patch to apply (without read_file line numbers)"},
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
        hunks = _parse_unified_hunks(patch_text)

        if not hunks:
            return ToolResult(
                content="Error: Patch contained no valid diff hunks. Use edit_file with exact old_str/new_str or provide a unified diff.",
                success=False,
            )

        lines = content.splitlines()
        trailing_newline = content.endswith("\n")
        offset_shift = 0

        for start_line, old_lines, new_lines in hunks:
            # Guard against LLM copying read_file line numbers ('   51 | ...') into patch
            if any(_LINE_PREFIX_RE.match(l) for l in old_lines + new_lines) and not any(_LINE_PREFIX_RE.match(fl) for fl in lines):
                return ToolResult(
                    content=(
                        f"Error: Patch for '{arguments['path']}' contains read_file line-number prefixes (e.g. '51 | '). "
                        "Re-submit without line-number prefixes, or use edit_file."
                    ),
                    success=False,
                )

            hint = max(0, (start_line - 1 + offset_shift)) if start_line else 0
            match_idx = _find_subsequence(lines, old_lines, hint_idx=hint)
            if match_idx is None:
                return ToolResult(
                    content=(
                        f"Error: Patch hunk did not match '{arguments['path']}'. "
                        "Verify exact file contents via read_file or use edit_file instead."
                    ),
                    success=False,
                )

            lines = lines[:match_idx] + new_lines + lines[match_idx + len(old_lines):]
            offset_shift += len(new_lines) - len(old_lines)

        updated = "\n".join(lines) + ("\n" if trailing_newline or (lines and not content) else "")
        if updated == content:
            return ToolResult(
                content=f"No changes applied to '{arguments['path']}' (patch produced identical content).",
                success=False,
            )

        snapshots = getattr(context, "snapshots", None) or SnapshotManager(workspace_root)
        snapshots.capture_snapshot(file_path)
        file_path.write_text(updated, encoding="utf-8")

        diff = SnapshotManager.create_diff(content, updated, arguments["path"])
        return ToolResult(
            content=f"Successfully applied patch to '{arguments['path']}'. Diff:\n\n{diff}",
            success=True,
        )
