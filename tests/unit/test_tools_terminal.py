from pathlib import Path
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


def test_normalize_windows_paths_for_bash():
    from Relay.security.sandbox import normalize_windows_paths_for_bash

    assert (
        normalize_windows_paths_for_bash(r".venv\Scripts\python.exe -m pip install pandas")
        == ".venv/Scripts/python.exe -m pip install pandas"
    )
    assert (
        normalize_windows_paths_for_bash(r"cd C:\Users\sumit\OneDrive\Desktop\Test-Relay && .venv\Scripts\python.exe visualize_users.py")
        == "cd C:/Users/sumit/OneDrive/Desktop/Test-Relay && .venv/Scripts/python.exe visualize_users.py"
    )
    assert (
        normalize_windows_paths_for_bash(r'cd "C:\Program Files\My App\bin"')
        == 'cd "C:/Program Files/My App/bin"'
    )
    # Single-quoted literals and string escapes stay intact
    assert normalize_windows_paths_for_bash(r"echo 'C:\keep\single'") == r"echo 'C:\keep\single'"
    assert normalize_windows_paths_for_bash(r'python -c "print(\"a\nb\tc\")"') == r'python -c "print(\"a\nb\tc\")"'


def test_sandbox_prioritizes_workspace_venv(tmp_path):
    from unittest.mock import MagicMock, patch
    from Relay.security.sandbox import SandboxRunner
    from Relay.utils.platform import is_windows

    scripts_sub = "Scripts" if is_windows() else "bin"
    ws_scripts = tmp_path / ".venv" / scripts_sub
    ws_scripts.mkdir(parents=True)

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("ok", "")
    mock_proc.returncode = 0

    runner = SandboxRunner(tmp_path)
    with patch("Relay.security.sandbox.subprocess.Popen", return_value=mock_proc) as mock_popen:
        res = runner.run(r".venv\Scripts\python.exe visualize_users.py")

    assert res.exit_code == 0
    kwargs = mock_popen.call_args.kwargs
    env = kwargs["env"]
    assert env["VIRTUAL_ENV"] == str(tmp_path / ".venv")
    assert env["PATH"].startswith(str(ws_scripts))
    if is_windows() and mock_popen.call_args.args[0][0].lower().endswith("bash.exe"):
        assert mock_popen.call_args.args[0][-1] == ".venv/Scripts/python.exe visualize_users.py"
