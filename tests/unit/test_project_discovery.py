from pathlib import Path
import pytest
from Relay.context.project import ProjectDiscovery


def test_project_manifest_and_command_detection(tmp_path):
    # Setup mock project
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Test instructions", encoding="utf-8")

    discovery = ProjectDiscovery(tmp_path)
    info = discovery.discover()

    assert "Python" in info.languages
    assert "pyproject.toml" in info.manifests
    assert any("pytest" in cmd for cmd in info.test_commands)
    assert "ruff check ." in info.lint_commands
    assert "AGENTS.md" in info.instruction_files
