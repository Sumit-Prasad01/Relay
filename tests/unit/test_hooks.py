"""Tests for lifecycle hooks execution (Section 14.3)."""

from pathlib import Path
from Relay.integrations.hooks import HookConfig, HookManager, HookType


def test_hook_execution(tmp_path: Path):
    target_file = tmp_path / "hook_output.txt"
    command = f'echo hook_triggered > "{target_file}"'

    hook = HookConfig(
        hook_type=HookType.SESSION_START,
        command=command,
        timeout_seconds=5,
    )

    manager = HookManager(workspace_root=tmp_path, hooks=[hook])
    manager.execute_hook(HookType.SESSION_START, context={"turn": 1})

    assert target_file.is_file()
    assert "hook_triggered" in target_file.read_text(encoding="utf-8")
