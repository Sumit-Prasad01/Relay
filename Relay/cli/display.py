"""Dark, sleek terminal UI utilities and animations using Rich."""

import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from Relay import __version__

# Cohesive dark obsidian & sky-cyan palette
ACCENT = "#38bdf8"       # Crisp sky cyan
ACCENT_ALT = "#818cf8"   # Soft indigo
SUCCESS = "#34d399"      # Emerald mint
WARNING = "#fbbf24"      # Warm amber
ERROR = "#f87171"        # Muted coral red
MUTED = "#94a3b8"        # Slate 400
DIM = "#64748b"          # Slate 500
BORDER = "#334155"       # Slate 700
SURFACE_TEXT = "#f8fafc" # Slate 50

RELAY_THEME = Theme(
    {
        "relay.accent": ACCENT,
        "relay.alt": ACCENT_ALT,
        "relay.success": SUCCESS,
        "relay.warning": WARNING,
        "relay.error": ERROR,
        "relay.muted": MUTED,
        "relay.dim": DIM,
        # Sleek dark Markdown styling
        "markdown.h1": f"bold {ACCENT}",
        "markdown.h1.border": BORDER,
        "markdown.h2": "bold #7dd3fc",
        "markdown.h3": f"bold {ACCENT_ALT}",
        "markdown.h4": "bold #cbd5e1",
        "markdown.h5": "italic #94a3b8",
        "markdown.h6": DIM,
        "markdown.code": "bold #7dd3fc on #0f172a",
        "markdown.code_block": "#e2e8f0 on #0f172a",
        "markdown.block_quote": f"italic {MUTED}",
        "markdown.item.bullet": f"bold {ACCENT}",
        "markdown.item.number": f"bold {ACCENT_ALT}",
        "markdown.hr": BORDER,
        "markdown.link": f"{ACCENT} underline",
        "markdown.link_url": f"{DIM} underline",
        "markdown.table.border": BORDER,
        "markdown.table.header": f"bold {ACCENT}",
    }
)

console = Console(theme=RELAY_THEME)
error_console = Console(stderr=True, theme=RELAY_THEME)

LOGO_ASCII = [
    "██████╗ ███████╗██╗      █████╗ ██╗   ██╗",
    "██╔══██╗██╔════╝██║     ██╔══██╗╚██╗ ██╔╝",
    "██████╔╝█████╗  ██║     ███████║ ╚████╔╝ ",
    "██╔══██╗██╔══╝  ██║     ██╔══██║  ╚██╔╝  ",
    "██║  ██║███████╗███████╗██║  ██║   ██║   ",
    "╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ",
]

GRADIENT_COLORS = ["#38bdf8", "#38bdf8", "#60a5fa", "#818cf8", "#a78bfa", "#64748b"]


def _build_banner_panel(reveal_lines: int = len(LOGO_ASCII), subtitle_reveal: bool = True) -> Panel:
    """Build the dark sleek Relay banner panel."""
    content = Text()
    for idx, line in enumerate(LOGO_ASCII):
        color = GRADIENT_COLORS[min(idx, len(GRADIENT_COLORS) - 1)]
        if idx < reveal_lines:
            content.append(line + "\n", style=f"bold {color}")
        else:
            content.append(" " * len(line) + "\n", style=DIM)

    if subtitle_reveal:
        content.append("\n")
        content.append("  ◆ ", style=f"bold {ACCENT}")
        content.append("Local-First Autonomous Coding Agent", style=f"bold {SURFACE_TEXT}")
        content.append(f"  ·  v{__version__}", style=DIM)
    else:
        content.append("\n  ", style=DIM)

    return Panel(
        Align.left(content),
        box=box.ROUNDED,
        border_style=BORDER,
        padding=(1, 2),
        expand=False,
    )


def print_banner(animate: bool = True) -> None:
    """Render the dark Relay startup banner with optional smooth line-reveal animation."""
    is_tty = bool(sys.stdout and sys.stdout.isatty())
    if animate and is_tty:
        with Live(
            _build_banner_panel(reveal_lines=0, subtitle_reveal=False),
            console=console,
            refresh_per_second=30,
            transient=False,
        ) as live:
            for step in range(1, len(LOGO_ASCII) + 1):
                live.update(_build_banner_panel(reveal_lines=step, subtitle_reveal=False))
                time.sleep(0.035)
            live.update(_build_banner_panel(reveal_lines=len(LOGO_ASCII), subtitle_reveal=True))
            time.sleep(0.05)
    else:
        console.print(_build_banner_panel(reveal_lines=len(LOGO_ASCII), subtitle_reveal=True))


def print_session_card(
    provider: str,
    model: str,
    mode: str,
    workspace: str,
    session_id: str,
) -> None:
    """Render a sleek dark session status header card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=DIM, justify="right")
    grid.add_column(style=SURFACE_TEXT)

    grid.add_row("Provider", Text(provider, style=f"bold {ACCENT}"))
    grid.add_row("Model", Text(model, style=f"bold {ACCENT_ALT}"))
    grid.add_row("Mode", Text(mode, style=f"bold {WARNING}"))
    grid.add_row("Session", Text(session_id[:12], style=MUTED))
    grid.add_row("Workspace", Text(workspace, style=DIM))

    console.print(
        Panel(
            grid,
            title=Text(" Session Active ", style=f"bold {SUCCESS}"),
            box=box.ROUNDED,
            border_style=BORDER,
            padding=(0, 2),
            expand=False,
        )
    )
    console.print(
        f"[{DIM}]Enter a coding task, or type [/{DIM}][{ACCENT}]/help[/{ACCENT}][{DIM}] for commands · Ctrl+C or [/{DIM}][{ACCENT}]/quit[/{ACCENT}][{DIM}] to exit[/{DIM}]\n"
    )


@contextmanager
def pulse_status(message: str, min_duration: float = 0.0) -> Iterator[None]:
    """Show an animated sleek terminal spinner for setup or asynchronous work."""
    is_tty = bool(sys.stdout and sys.stdout.isatty())
    if not is_tty:
        yield
        return

    start = time.monotonic()
    with console.status(f"[{MUTED}]{message}[/{MUTED}]", spinner="dots2", spinner_style=ACCENT):
        yield
        elapsed = time.monotonic() - start
        if min_duration > elapsed:
            time.sleep(min_duration - elapsed)


def print_doctor_report(checks: List[Dict[str, Any]]) -> None:
    """Render diagnostics in a sleek dark slate table."""
    table = Table(
        title="System Diagnostics (Doctor)",
        title_style=f"bold {SURFACE_TEXT}",
        box=box.ROUNDED,
        border_style=BORDER,
        header_style=f"bold {ACCENT}",
    )
    table.add_column("Check", style=f"bold {SURFACE_TEXT}")
    table.add_column("Status", justify="center")
    table.add_column("Details", style=MUTED)

    for c in checks:
        status_text = (
            Text("● OK", style=f"bold {SUCCESS}")
            if c["status"] == "ok"
            else Text("▲ WARN", style=f"bold {WARNING}")
            if c["status"] == "warn"
            else Text("✖ FAIL", style=f"bold {ERROR}")
        )
        table.add_row(c["name"], status_text, c.get("details", ""))

    console.print(table)
