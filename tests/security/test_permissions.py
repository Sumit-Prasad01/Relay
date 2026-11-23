from pathlib import Path
import pytest
from Relay.security.permissions import PermissionAction, PermissionManager


def test_plan_mode_blocks_mutations(tmp_path):
    mgr = PermissionManager(tmp_path, mode="plan")

    # Read allowed
    act, _ = mgr.evaluate_tool("read_file", "read", {"path": "main.py"})
    assert act == PermissionAction.ALLOW

    # Write denied
    act, reason = mgr.evaluate_tool("write_file", "write", {"path": "main.py", "content": "..."})
    assert act == PermissionAction.DENY
    assert "plan" in reason

    # Execution denied
    act, reason = mgr.evaluate_tool("run_command", "execute", {"command": "ls"})
    assert act == PermissionAction.DENY


def test_path_traversal_blocked(tmp_path):
    mgr = PermissionManager(tmp_path, mode="auto-edit")

    # Path escaping workspace root
    escaped_path = "../../etc/passwd"
    act, reason = mgr.evaluate_tool("read_file", "read", {"path": escaped_path})
    assert act == PermissionAction.DENY
    assert "traversal blocked" in reason.lower()


def test_modes_evaluation(tmp_path):
    # Ask mode: prompts for writes and commands
    ask_mgr = PermissionManager(tmp_path, mode="ask")
    act, _ = ask_mgr.evaluate_tool("write_file", "write", {"path": "test.txt"})
    assert act == PermissionAction.ASK

    # Auto-edit mode: allows writes inside workspace
    edit_mgr = PermissionManager(tmp_path, mode="auto-edit")
    act, _ = edit_mgr.evaluate_tool("write_file", "write", {"path": "test.txt"})
    assert act == PermissionAction.ALLOW

    # Full-auto mode: still blocks privileged sudo
    full_mgr = PermissionManager(tmp_path, mode="full-auto")
    act, reason = full_mgr.evaluate_tool("run_command", "execute", {"command": "sudo rm -rf /"})
    assert act == PermissionAction.DENY
