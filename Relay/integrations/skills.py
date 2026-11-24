"""Skill discovery and loading from project .agents/skills/ (Section 14.2)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import yaml


@dataclass
class Skill:
    """Represents a discovered skill instruction module."""

    name: str
    description: str
    instructions: str
    path: Path


class SkillManager:
    """Discovers, parses, and formats project skills for injection into model prompt."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def discover_skills(self) -> List[Skill]:
        """Discover skills in .agents/skills/ and .relay/skills/."""
        skill_dirs = [
            self.workspace_root / ".agents" / "skills",
            self.workspace_root / ".relay" / "skills",
        ]
        skills: List[Skill] = []

        for base_dir in skill_dirs:
            if not base_dir.is_dir():
                continue

            for skill_folder in sorted(base_dir.iterdir()):
                if not skill_folder.is_dir():
                    continue

                skill_md = skill_folder / "SKILL.md"
                if not skill_md.is_file():
                    continue

                parsed = self._parse_skill_file(skill_md, skill_folder.name)
                if parsed:
                    skills.append(parsed)

        return skills

    def _parse_skill_file(self, path: Path, folder_name: str) -> Optional[Skill]:
        """Extract metadata and instructions from SKILL.md with optional YAML frontmatter."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        name = folder_name
        description = ""
        instructions = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                instructions = parts[2].strip()
                try:
                    meta = yaml.safe_load(frontmatter)
                    if isinstance(meta, dict):
                        name = meta.get("name", name)
                        description = meta.get("description", "")
                except Exception:
                    pass

        return Skill(
            name=name,
            description=description,
            instructions=instructions,
            path=path,
        )

    def format_skills_for_prompt(self) -> str:
        """Format discovered skills into a concise reference for system prompt injection."""
        skills = self.discover_skills()
        if not skills:
            return ""

        lines = ["<skills>"]
        for s in skills:
            desc = f": {s.description}" if s.description else ""
            lines.append(f"- **{s.name}**{desc}")
            lines.append(f"  {s.instructions[:300].strip()}...")
        lines.append("</skills>")

        return "\n".join(lines)
