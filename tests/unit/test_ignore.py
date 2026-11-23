from pathlib import Path
import pytest
from Relay.context.ignore import IgnoreRules


def test_default_ignore_patterns(tmp_path):
    rules = IgnoreRules(tmp_path)

    assert rules.is_ignored(tmp_path / ".git") is True
    assert rules.is_ignored(tmp_path / ".git" / "config") is True
    assert rules.is_ignored(tmp_path / ".venv" / "bin" / "python") is True
    assert rules.is_ignored(tmp_path / "node_modules" / "express" / "index.js") is True
    assert rules.is_ignored(tmp_path / "__pycache__" / "app.pyc") is True
    assert rules.is_ignored(tmp_path / ".env") is True

    # Normal files are not ignored
    assert rules.is_ignored(tmp_path / "src" / "main.py") is False
    assert rules.is_ignored(tmp_path / "README.md") is False


def test_custom_gitignore(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("secrets/\n*.log\ntemp.txt", encoding="utf-8")

    rules = IgnoreRules(tmp_path)
    assert rules.is_ignored(tmp_path / "secrets" / "key.txt") is True
    assert rules.is_ignored(tmp_path / "app.log") is True
    assert rules.is_ignored(tmp_path / "temp.txt") is True
    assert rules.is_ignored(tmp_path / "app.py") is False
