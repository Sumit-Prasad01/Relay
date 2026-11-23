from pathlib import Path
import pytest
from Relay.context.instructions import InstructionLoader


def test_load_instructions_missing(tmp_path):
    loader = InstructionLoader(tmp_path)
    assert loader.load_instructions() is None


def test_load_instructions_existing(tmp_path):
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("Follow strict formatting.", encoding="utf-8")

    loader = InstructionLoader(tmp_path)
    loaded = loader.load_instructions()

    assert loaded is not None
    assert "<project-instructions path=\"AGENTS.md\">" in loaded
    assert "Follow strict formatting." in loaded
    assert "</project-instructions>" in loaded
