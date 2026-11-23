"""Instruction loader enforcing precedence hierarchy and untrusted data boundary (Section 10.2)."""

from pathlib import Path
from typing import Optional


class InstructionLoader:
    """Discovers and formats workspace project instructions (AGENTS.md)."""

    def __init__(self, workspace_root: Path, filename: str = "AGENTS.md"):
        self.workspace_root = workspace_root.resolve()
        self.filename = filename

    def load_instructions(self) -> Optional[str]:
        """Load root instructions with untrusted data fencing."""
        candidate = self.workspace_root / self.filename
        if not candidate.is_file():
            return None

        try:
            content = candidate.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                return None

            # Untrusted delimiter fencing per Section 9.4
            return (
                f"<project-instructions path=\"{self.filename}\">\n"
                f"{content}\n"
                "</project-instructions>"
            )
        except Exception:
            return None
