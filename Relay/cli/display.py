"""Terminal display utilities using Rich."""

from typing import Any, Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
error_console = Console(stderr=True)

ACCENT = "bright_blue"
SUCCESS = "green"
WARNING = "yellow"
ERROR = "red"
MUTED = "dim"


def print_banner() -> None:
    title = Text(" Relay ", style=f"bold {ACCENT}")
    subtitle = Text("Local-First AI Coding Agent", style=MUTED)
    console.print(Panel(subtitle, title=title, border_style=ACCENT, expand=False))


def print_doctor_report(checks: List[Dict[str, Any]]) -> None:
    table = Table(title="System Diagnostics (Doctor)", border_style=MUTED)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details", style=MUTED)

    for c in checks:
        status_text = (
            Text("OK", style=f"bold {SUCCESS}")
            if c["status"] == "ok"
            else Text("WARN", style=f"bold {WARNING}")
            if c["status"] == "warn"
            else Text("FAIL", style=f"bold {ERROR}")
        )
        table.add_row(c["name"], status_text, c.get("details", ""))

    console.print(table)
