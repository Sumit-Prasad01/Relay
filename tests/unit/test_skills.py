"""Tests for skill discovery and prompt formatting (Section 14.2)."""

from pathlib import Path
from Relay.integrations.skills import SkillManager


def test_skill_discovery_and_parsing(tmp_path: Path):
    skills_dir = tmp_path / ".agents" / "skills" / "deploy-tool"
    skills_dir.mkdir(parents=True)

    skill_file = skills_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: deploy-helper\n"
        "description: Assists with container deployment\n"
        "---\n"
        "# Deploy instructions\n"
        "Run docker build and deploy cleanly.\n",
        encoding="utf-8",
    )

    manager = SkillManager(workspace_root=tmp_path)
    skills = manager.discover_skills()

    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "deploy-helper"
    assert skill.description == "Assists with container deployment"
    assert "docker build" in skill.instructions

    formatted = manager.format_skills_for_prompt()
    assert "<skills>" in formatted
    assert "deploy-helper" in formatted
