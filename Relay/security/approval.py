"""Interactive human approval handler (Section 7.2 & 9.1)."""

from typing import Optional
from rich import box
from rich.panel import Panel
from rich.text import Text
from Relay.cli.display import BORDER, DIM, WARNING, console


class ApprovalHandler:
    """Interactively prompts user for confirmation when permission policy dictates."""

    @staticmethod
    def request_approval(reason: str, command_or_path: Optional[str] = None) -> bool:
        """Prompt user with risk explanation."""
        console.print()
        title = Text(" ▲ Approval Required ", style=f"bold {WARNING}")
        body = Text(f"{reason}\n", style="bold #f8fafc")
        if command_or_path:
            body.append(f"Target: {command_or_path}\n", style=DIM)
        body.append("\nProceed with this action? [y/N]: ", style=WARNING)

        console.print(Panel(body, title=title, box=box.ROUNDED, border_style=BORDER, padding=(0, 2), expand=False))

        try:
            choice = input().strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
