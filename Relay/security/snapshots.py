"""Pre-change snapshotting and rollback manager (Section 8.2 & 8.4)."""

import difflib
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class FileSnapshot:
    path: str
    content: str
    sha256: str
    timestamp: str


class SnapshotManager:
    """Maintains pre-change snapshots to allow diff calculation and atomic rollback."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self._snapshots: Dict[str, List[FileSnapshot]] = {}

    def capture_snapshot(self, path: Path) -> Optional[FileSnapshot]:
        """Capture state of an existing file before modification."""
        if not path.is_file():
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            rel_path = path.relative_to(self.workspace_root).as_posix()
            snapshot = FileSnapshot(
                path=rel_path,
                content=content,
                sha256=h,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._snapshots.setdefault(rel_path, []).append(snapshot)
            return snapshot
        except Exception:
            return None

    def rollback(self, path: Path) -> bool:
        """Roll back file to its latest snapshot."""
        try:
            rel_path = path.relative_to(self.workspace_root).as_posix()
        except Exception:
            return False

        snapshots = self._snapshots.get(rel_path, [])
        if not snapshots:
            return False

        last_snapshot = snapshots.pop()
        path.write_text(last_snapshot.content, encoding="utf-8")
        return True

    @staticmethod
    def create_diff(before_text: str, after_text: str, file_name: str = "file") -> str:
        """Generate unified diff between before and after versions."""
        before_lines = before_text.splitlines(keepends=True)
        after_lines = after_text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_name}",
            tofile=f"b/{file_name}",
        )
        return "".join(diff)
