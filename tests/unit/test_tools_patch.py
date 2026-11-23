from pathlib import Path
import pytest
from Relay.tools.patch import EditFileTool


class MockContext:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root


def test_edit_file_tool(tmp_path):
    ctx = MockContext(tmp_path)
    file_path = tmp_path / "app.py"
    file_path.write_text("def run():\n    print('old')\n", encoding="utf-8")

    editor = EditFileTool()

    # Successful targeted edit
    res = editor.run({"path": "app.py", "old_str": "print('old')", "new_str": "print('new')"}, ctx)
    assert res.success is True
    assert "Diff:" in res.content
    assert "print('new')" in file_path.read_text(encoding="utf-8")

    # Target not found
    res_fail = editor.run({"path": "app.py", "old_str": "missing_string", "new_str": "x"}, ctx)
    assert res_fail.success is False
    assert "not found" in res_fail.content


def test_edit_file_multiple_matches(tmp_path):
    ctx = MockContext(tmp_path)
    file_path = tmp_path / "app.py"
    file_path.write_text("val = 1\nval = 1\n", encoding="utf-8")

    editor = EditFileTool()

    # Fails when multiple matches without allow_multi_edit
    res = editor.run({"path": "app.py", "old_str": "val = 1", "new_str": "val = 2"}, ctx)
    assert res.success is False
    assert "matches 2 locations" in res.content

    # Succeeds with allow_multi_edit
    res_multi = editor.run({"path": "app.py", "old_str": "val = 1", "new_str": "val = 2", "allow_multi_edit": True}, ctx)
    assert res_multi.success is True
    assert file_path.read_text(encoding="utf-8") == "val = 2\nval = 2\n"
