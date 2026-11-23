from pathlib import Path
import pytest
from Relay.security.permissions import PermissionManager
from Relay.tools.registry import create_default_registry


class MockContext:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root


def test_default_registry_and_permissions(tmp_path):
    perm_mgr = PermissionManager(tmp_path, mode="plan")
    registry = create_default_registry(permission_manager=perm_mgr)
    ctx = MockContext(tmp_path)

    # Verify initial catalog tools registered
    tool_names = {t.name for t in registry.list_tools()}
    expected = {
        "list_files",
        "read_file",
        "write_file",
        "edit_file",
        "apply_patch",
        "search_code",
        "run_command",
        "run_tests",
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
        "git_commit",
        "diagnose_project",
        "get_environment",
    }
    assert expected.issubset(tool_names)

    # Plan mode blocks write_file execution
    res = registry.execute("write_file", {"path": "test.txt", "content": "data"}, ctx)
    assert res.success is False
    assert "plan" in res.content
    assert res.error == "permission_denied"

    # Plan mode allows read_file
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello", encoding="utf-8")
    res_read = registry.execute("read_file", {"path": "hello.txt"}, ctx)
    assert res_read.success is True
    assert "hello" in res_read.content
