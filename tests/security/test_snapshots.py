from pathlib import Path
import pytest
from Relay.security.snapshots import SnapshotManager


def test_snapshot_capture_and_rollback(tmp_path):
    file_path = tmp_path / "code.py"
    file_path.write_text("initial version", encoding="utf-8")

    mgr = SnapshotManager(tmp_path)
    snapshot = mgr.capture_snapshot(file_path)
    assert snapshot is not None
    assert snapshot.content == "initial version"

    # Modify file
    file_path.write_text("modified version", encoding="utf-8")

    # Generate diff
    diff = SnapshotManager.create_diff(snapshot.content, "modified version", "code.py")
    assert "-initial version" in diff
    assert "+modified version" in diff

    # Roll back
    success = mgr.rollback(file_path)
    assert success is True
    assert file_path.read_text(encoding="utf-8") == "initial version"
