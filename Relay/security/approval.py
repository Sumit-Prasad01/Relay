"""Interactive human approval handler (Section 7.2 & 9.1)."""

from typing import Optional
from rich.panel import Panel
from rich.text import Text
from Relay.cli.display import console, WARNING


class ApprovalHandler:
    """Interactively prompts user for confirmation when permission policy dictates."""

    @staticmethod
    def request_approval(reason: str, command_or_path: Optional[str] = None) -> bool:
        """Prompt user with risk explanation."""
        console.print()
        title = Text("Approval Required", style=f"bold {WARNING}")
        body = Text(f"{reason}\n", style="bold")
        if command_or_path:
            body.append(f"Target: {command_or_path}\n", style="dim")
        body.append("Do you want to proceed? [y/N]: ", style="yellow")

        console.print(Panel(body, title=title, border_style=WARNING, expand=False))

        try:
            choice = input().strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
