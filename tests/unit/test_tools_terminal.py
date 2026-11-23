from pathlib import Path
import pytest
from Relay.tools.terminal import RunCommandTool


class MockContext:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root


def test_run_command_tool(tmp_path):
    ctx = MockContext(tmp_path)
    runner = RunCommandTool()

    # Simple echo
    res = runner.run({"command": "echo Hello Relay"}, ctx)
    assert res.success is True
    assert "Hello Relay" in res.content
    assert res.exit_code == 0
    assert res.duration_ms >= 0


def test_run_command_timeout(tmp_path):
    ctx = MockContext(tmp_path)
    runner = RunCommandTool()

    # Sleep longer than timeout
    res = runner.run({"command": "python -c \"import time; time.sleep(10)\"", "timeout": 1}, ctx)
    assert res.success is False
    assert "timed out" in res.content.lower()
    assert res.exit_code == 124
