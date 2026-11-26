from pathlib import Path
from Relay.tools.patch import ApplyPatchTool, EditFileTool


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


def test_apply_patch_tool_modifies_file_and_rejects_bad_hunks(tmp_path):
    ctx = MockContext(tmp_path)
    target = tmp_path / "users.csv"
    target.write_text("name,role\nAlice,Dev\nBob,PM\n", encoding="utf-8")

    patcher = ApplyPatchTool()
    good_patch = "--- a/users.csv\n+++ b/users.csv\n@@ -1,3 +1,3 @@\n name,role\n-Alice,Dev\n+Alice,Staff Dev\n Bob,PM\n"
    res = patcher.run({"path": "users.csv", "patch": good_patch}, ctx)
    assert res.success is True
    assert "Successfully applied patch" in res.content
    assert target.read_text(encoding="utf-8") == "name,role\nAlice,Staff Dev\nBob,PM\n"

    # Line-number prefix from read_file is rejected clearly instead of silently returning success
    bad_prefix_patch = "@@\n-   2 | Alice,Staff Dev\n+   2 | Alice,VP\n"
    res_prefix = patcher.run({"path": "users.csv", "patch": bad_prefix_patch}, ctx)
    assert res_prefix.success is False
    assert "line-number prefixes" in res_prefix.content
    assert target.read_text(encoding="utf-8") == "name,role\nAlice,Staff Dev\nBob,PM\n"

    # Non-matching context fails explicitly
    res_miss = patcher.run({"path": "users.csv", "patch": "@@\n-NotHere\n+Updated\n"}, ctx)
    assert res_miss.success is False
    assert "did not match" in res_miss.content
