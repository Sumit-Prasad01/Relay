"""Interactive human approval handler with dropdown and custom agent feedback (Section 7.2 & 9.1)."""

import asyncio
import sys
from dataclasses import dataclass
from typing import Literal, Optional

from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from Relay.cli.display import ACCENT, DIM, WARNING, console, pause_active_status

ApprovalActionChoice = Literal["allow", "deny", "instruct"]


@dataclass
class ApprovalResult:
    """Structured result from an interactive user approval prompt."""

    approved: bool
    action: ApprovalActionChoice = "deny"
    instruction: Optional[str] = None


def _has_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class ApprovalHandler:
    """Interactively prompts user via a dropdown (Allow / Don't Allow / Tell agent)."""

    @staticmethod
    def _prompt_dropdown_tty() -> ApprovalActionChoice:
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.shortcuts.choice_input import ChoiceInput
        from Relay.cli.prompts import RELAY_PROMPT_STYLE

        in_thread = _has_running_loop()
        selector = ChoiceInput(
            message=HTML("<prompt-label>Action</prompt-label> <prompt-hint>(↑/↓ navigate · Enter select)</prompt-hint>"),
            options=[
                ("allow", "Allow                 · Execute this operation"),
                ("deny", "Don't Allow           · Reject and skip this action"),
                ("instruct", "Tell agent explicitly · Guide Relay and continue chat"),
            ],
            default="allow",
            symbol="❯",
            show_frame=True,
            mouse_support=True,
            bottom_toolbar=HTML(" <b>↑/↓</b> Move   <b>1-3</b> Quick Pick   <b>Enter</b> Confirm   <b>Ctrl+C</b> Deny "),
            style=RELAY_PROMPT_STYLE,
        )
        return selector._create_application().run(in_thread=in_thread)

    @staticmethod
    def _prompt_instruction_tty() -> str:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from Relay.cli.prompts import RELAY_PROMPT_STYLE

        in_thread = _has_running_loop()
        session = PromptSession()
        text = session.prompt(
            HTML("<prompt-label>Tell Relay what to do</prompt-label> ❯ "),
            show_frame=True,
            placeholder=HTML("<placeholder>Describe how you want Relay to proceed...</placeholder>"),
            bottom_toolbar=HTML(" <b>Enter</b> Send guidance to agent   <b>Ctrl+C</b> Cancel "),
            style=RELAY_PROMPT_STYLE,
            in_thread=in_thread,
        )
        return text.strip()

    @staticmethod
    def request_approval(reason: str, command_or_path: Optional[str] = None) -> ApprovalResult:
        """Display approval panel and prompt user to Allow, Don't Allow, or Tell agent explicitly."""
        with pause_active_status():
            console.print()
            title = Text(" ⚠ Approval Required ", style=f"bold {WARNING}")
            body = Text(f"{reason}", style="bold #f8fafc")
            if command_or_path:
                body.append(f"\nTarget: {command_or_path}", style=DIM)

            console.print(
                Panel(
                    body,
                    title=title,
                    box=box.ROUNDED,
                    border_style=WARNING,
                    padding=(0, 2),
                    expand=False,
                )
            )

            is_tty = bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())
            if is_tty:
                try:
                    action = ApprovalHandler._prompt_dropdown_tty()
                except (EOFError, KeyboardInterrupt):
                    action = "deny"

                if action == "allow":
                    console.print(f"[{DIM}]✓ Approved: {escape(command_or_path or reason)}[/{DIM}]")
                    return ApprovalResult(approved=True, action="allow")

                if action == "instruct":
                    try:
                        instruction = ApprovalHandler._prompt_instruction_tty()
                    except (EOFError, KeyboardInterrupt):
                        instruction = ""
                    if instruction:
                        console.print(f"[{ACCENT}]↪ Guidance captured for agent.[/{ACCENT}]")
                        return ApprovalResult(approved=False, action="instruct", instruction=instruction)
                    return ApprovalResult(approved=False, action="deny")

                return ApprovalResult(approved=False, action="deny")

            # Non-TTY fallback (piped input or simple line-buffered test harness)
            console.print(Text("[1] Allow  [2] Don't Allow  [3] Tell agent explicitly: ", style=WARNING), end="")
            try:
                raw = input().strip()
            except (EOFError, KeyboardInterrupt):
                return ApprovalResult(approved=False, action="deny")

            low = raw.lower()
            if low in ("1", "y", "yes", "allow"):
                return ApprovalResult(approved=True, action="allow")
            if low in ("3", "i", "instruct", "tell"):
                console.print(Text("Tell agent what to do: ", style=ACCENT), end="")
                try:
                    instruction = input().strip()
                except (EOFError, KeyboardInterrupt):
                    return ApprovalResult(approved=False, action="deny")
                if instruction:
                    return ApprovalResult(approved=False, action="instruct", instruction=instruction)
            return ApprovalResult(approved=False, action="deny")
