"""Dark, sleek terminal UI utilities, animations, and tool-call renderers using Rich."""

from __future__ import annotations

import difflib
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from Relay import __version__
from Relay.providers.base import ToolCall

if TYPE_CHECKING:
    from Relay.tools.base import ToolResult

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

MAX_PREVIEW_LINES = 60
MAX_PREVIEW_CHARS = 4000
MAX_RESULT_LINES = 25

LANGUAGE_BY_EXTENSION: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".xml": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".diff": "diff",
    ".patch": "diff",
}

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

_ACTIVE_STATUS: Any = None


def set_active_status(status_obj: Any) -> None:
    """Track an active Rich Status spinner so interactive prompts can pause it cleanly."""
    global _ACTIVE_STATUS
    _ACTIVE_STATUS = status_obj


@contextmanager
def pause_active_status() -> Iterator[None]:
    """Temporarily pause any active spinner while requesting user approval input."""
    status_obj = _ACTIVE_STATUS
    if status_obj is not None:
        try:
            status_obj.stop()
        except Exception:
            pass
    try:
        yield
    finally:
        if status_obj is not None and _ACTIVE_STATUS is status_obj:
            try:
                status_obj.start()
            except Exception:
                pass


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
    with console.status(f"[{MUTED}]{escape(message)}[/{MUTED}]", spinner="dots2", spinner_style=ACCENT):
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


# ---------------------------------------------------------------------------
# Tool-call previews, diff renderers, and execution state outputs
# ---------------------------------------------------------------------------

def _truncate_preview(
    text: str,
    max_lines: int = MAX_PREVIEW_LINES,
    max_chars: int = MAX_PREVIEW_CHARS,
) -> Tuple[str, bool, int]:
    """Truncate display text for terminal readability without modifying execution args."""
    lines = text.splitlines()
    total_lines = len(lines)
    truncated = False

    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated = True

    preview = "\n".join(lines)
    if len(preview) > max_chars:
        preview = preview[:max_chars].rstrip()
        truncated = True

    return preview, truncated, total_lines


def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return LANGUAGE_BY_EXTENSION.get(ext, "text")


def render_write_file_preview(
    path: str,
    content: str,
    max_lines: int = MAX_PREVIEW_LINES,
    max_chars: int = MAX_PREVIEW_CHARS,
    target_console: Optional[Console] = None,
) -> None:
    """Display a proposed syntax-highlighted file write without executing it."""
    out = target_console or console
    language = _detect_language(path)
    preview_text, truncated, total_lines = _truncate_preview(
        content, max_lines=max_lines, max_chars=max_chars
    )

    title = Text()
    title.append(" WRITE FILE ", style=f"bold {ACCENT}")
    title.append(path, style=f"bold {SURFACE_TEXT}")

    subtitle = Text(f"{len(content):,} chars · {total_lines} lines", style=DIM)
    if truncated:
        shown = len(preview_text.splitlines())
        subtitle = Text(
            f"Preview truncated: showing {shown} of {total_lines} lines ({len(content):,} chars total)",
            style=WARNING,
        )

    if not preview_text:
        renderable: Any = Text("(empty file)", style=f"italic {DIM}")
    else:
        renderable = Syntax(
            preview_text,
            language,
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
            padding=(0, 1),
        )

    out.print()
    out.print(
        Panel(
            renderable,
            title=title,
            subtitle=subtitle,
            box=box.ROUNDED,
            border_style=BORDER,
            expand=True,
        )
    )


def render_diff_preview(
    path: str,
    diff_text: str,
    title_label: str = "DIFF PREVIEW",
    target_console: Optional[Console] = None,
) -> None:
    """Render a unified diff preview inside a sleek dark panel."""
    out = target_console or console
    preview_text, truncated, total_lines = _truncate_preview(diff_text)

    title = Text()
    title.append(f" {title_label} ", style=f"bold {ACCENT}")
    title.append(path, style=f"bold {SURFACE_TEXT}")

    subtitle = Text(
        f"Preview truncated ({total_lines} diff lines)" if truncated else f"{total_lines} diff lines",
        style=WARNING if truncated else DIM,
    )

    renderable: Any = (
        Syntax(preview_text, "diff", theme="monokai", line_numbers=True, word_wrap=True, padding=(0, 1))
        if preview_text.strip()
        else Text("(no textual differences)", style=f"italic {DIM}")
    )

    out.print()
    out.print(
        Panel(
            renderable,
            title=title,
            subtitle=subtitle,
            box=box.ROUNDED,
            border_style=BORDER,
            expand=True,
        )
    )


def render_edit_file_preview(
    path: str,
    old_str: str,
    new_str: str,
    allow_multi: bool = False,
    target_console: Optional[Console] = None,
) -> None:
    """Display proposed edit_file changes as a syntax-highlighted unified diff."""
    diff_lines = list(
        difflib.unified_diff(
            old_str.splitlines(keepends=True),
            new_str.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    diff_text = "\n".join(line.rstrip("\r\n") for line in diff_lines)
    label = "EDIT FILE (MULTI)" if allow_multi else "EDIT FILE"
    render_diff_preview(path=path, diff_text=diff_text, title_label=label, target_console=target_console)


def render_command_preview(
    command: str,
    timeout: Optional[int] = None,
    title_label: str = "RUN COMMAND",
    target_console: Optional[Console] = None,
) -> None:
    """Display a proposed shell/test command inside a clean dark panel."""
    out = target_console or console
    title = Text(f" {title_label} ", style=f"bold {ACCENT}")
    subtitle = Text(f"timeout: {timeout}s", style=DIM) if timeout else None

    out.print()
    out.print(
        Panel(
            Syntax(command, "bash", theme="monokai", word_wrap=True, padding=(0, 1)),
            title=title,
            subtitle=subtitle,
            box=box.ROUNDED,
            border_style=BORDER,
            expand=True,
        )
    )


def render_generic_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    target_console: Optional[Console] = None,
) -> None:
    """Render non-file/command tool calls cleanly without exposing raw escaped JSON blobs."""
    out = target_console or console
    out.print()
    if not arguments:
        out.print(f"[bold {ACCENT}]⚙ {escape(tool_name)}[/bold {ACCENT}]")
        return

    parts = []
    for k, v in arguments.items():
        val_str = str(v)
        if len(val_str) > 120:
            val_str = val_str[:117] + "..."
        parts.append(f"[{MUTED}]{escape(str(k))}[/{MUTED}]=[#f8fafc]{escape(val_str)}[/#f8fafc]")
    out.print(f"[bold {ACCENT}]⚙ {escape(tool_name)}[/bold {ACCENT}] " + " · ".join(parts))


def render_tool_error(
    tool_name: str,
    error: str,
    target_console: Optional[Console] = None,
) -> None:
    """Render an explicit tool validation or execution failure cleanly."""
    out = target_console or console
    out.print(f"[bold {ERROR}]✖ {escape(tool_name)} failed[/bold {ERROR}]")
    if error:
        out.print(f"  [{ERROR}]{escape(error.strip())}[/{ERROR}]")


def render_tool_denied(
    tool_name: str,
    reason: str = "",
    is_policy: bool = False,
    is_instruct: bool = False,
    target_console: Optional[Console] = None,
) -> None:
    """Distinguish user rejection, agent guidance redirect, and policy denial."""
    out = target_console or console
    if is_instruct:
        out.print(f"[{ACCENT}]↪ {escape(tool_name)} redirected:[/{ACCENT}] [{MUTED}]{escape(reason.strip())}[/{MUTED}]")
    elif is_policy:
        out.print(f"[bold {ERROR}]✖ {escape(tool_name)} blocked by policy[/bold {ERROR}]")
        if reason:
            out.print(f"  [{DIM}]{escape(reason.strip())}[/{DIM}]")
    else:
        out.print(f"[{WARNING}]⊘ {escape(tool_name)} cancelled by user[/{WARNING}]")


def render_tool_result(
    tool_name: str,
    result: ToolResult,
    target_console: Optional[Console] = None,
) -> None:
    """Render actual post-execution tool results concisely and safely."""
    out = target_console or console
    duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
    raw_content = (result.content or "").strip()

    # Compact headline for write/patch/git operations
    if tool_name in ("write_file", "apply_patch", "git_commit", "git_branch"):
        headline = raw_content.splitlines()[0] if raw_content else f"{tool_name} completed"
        out.print(f"[{SUCCESS}]✔ {escape(headline)}[/{SUCCESS}][{DIM}]{escape(duration)}[/{DIM}]")
        return

    if tool_name == "edit_file":
        headline = raw_content.splitlines()[0] if raw_content else "edit_file applied"
        out.print(f"[{SUCCESS}]✔ {escape(headline)}[/{SUCCESS}][{DIM}]{escape(duration)}[/{DIM}]")
        return

    out.print(f"[{SUCCESS}]✔ {escape(tool_name)} completed[/{SUCCESS}][{DIM}]{escape(duration)}[/{DIM}]")
    if raw_content:
        lines = raw_content.splitlines()
        if len(lines) > MAX_RESULT_LINES:
            shown = "\n".join(lines[:MAX_RESULT_LINES])
            out.print(f"[{DIM}]{escape(shown)}[/{DIM}]")
            out.print(f"[{DIM}]... ({len(lines) - MAX_RESULT_LINES} more lines omitted)[/{DIM}]")
        else:
            out.print(f"[{DIM}]{escape(raw_content)}[/{DIM}]")


def render_tool_call(
    tool_call: ToolCall,
    target_console: Optional[Console] = None,
) -> bool:
    """Parse completed ToolCall arguments once and render the appropriate preview.

    Returns True if arguments were valid and rendered, False on malformed/invalid payload.
    Never mutates tool_call.arguments.
    """
    out = target_console or console
    try:
        arguments = tool_call.parse_arguments_strict()
    except ValueError as e:
        render_tool_error(tool_call.name, str(e), target_console=out)
        return False

    name = tool_call.name

    if name == "write_file":
        path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
            render_tool_error(name, "Invalid write_file arguments: 'path' and 'content' must be strings.", target_console=out)
            return False
        render_write_file_preview(path, content, target_console=out)
        return True

    if name == "edit_file":
        path = arguments.get("path")
        old_str = arguments.get("old_str")
        new_str = arguments.get("new_str")
        if not isinstance(path, str) or not isinstance(old_str, str) or not isinstance(new_str, str):
            render_tool_error(name, "Invalid edit_file arguments: 'path', 'old_str', and 'new_str' must be strings.", target_console=out)
            return False
        render_edit_file_preview(
            path=path,
            old_str=old_str,
            new_str=new_str,
            allow_multi=bool(arguments.get("allow_multi_edit", False)),
            target_console=out,
        )
        return True

    if name == "apply_patch":
        path = arguments.get("path")
        patch_text = arguments.get("patch")
        if not isinstance(path, str) or not isinstance(patch_text, str):
            render_tool_error(name, "Invalid apply_patch arguments: 'path' and 'patch' must be strings.", target_console=out)
            return False
        render_diff_preview(path=path, diff_text=patch_text, title_label="APPLY PATCH", target_console=out)
        return True

    if name == "run_command":
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            render_tool_error(name, "Invalid run_command arguments: 'command' must be a non-empty string.", target_console=out)
            return False
        timeout = arguments.get("timeout")
        render_command_preview(
            command=command,
            timeout=timeout if isinstance(timeout, int) else None,
            target_console=out,
        )
        return True

    if name == "run_tests":
        cmd = arguments.get("command")
        if isinstance(cmd, str) and cmd.strip():
            render_command_preview(command=cmd, title_label="RUN TESTS", target_console=out)
        else:
            out.print(f"\n[bold {ACCENT}]⚙ run_tests[/bold {ACCENT}] [{DIM}](auto-detect suite)[/{DIM}]")
        return True

    if name == "read_file":
        path = arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            render_tool_error(name, "Invalid read_file arguments: 'path' must be a string.", target_console=out)
            return False
        offset = arguments.get("offset", 1)
        limit = arguments.get("limit", 500)
        out.print(
            f"\n[bold {ACCENT}]⚙ READ FILE[/bold {ACCENT}] [#f8fafc]{escape(path)}[/#f8fafc] "
            f"[{DIM}](offset={escape(str(offset))}, limit={escape(str(limit))})[/{DIM}]"
        )
        return True

    if name == "search_code":
        query = arguments.get("query")
        if not isinstance(query, str):
            render_tool_error(name, "Invalid search_code arguments: 'query' must be a string.", target_console=out)
            return False
        glob_str = f" · glob={escape(str(arguments['file_glob']))}" if arguments.get("file_glob") else ""
        out.print(
            f"\n[bold {ACCENT}]⚙ SEARCH CODE[/bold {ACCENT}] [#f8fafc]{escape(query)}[/#f8fafc]"
            f"[{DIM}]{glob_str}[/{DIM}]"
        )
        return True

    if name == "list_files":
        rel = arguments.get("path") or "."
        out.print(f"\n[bold {ACCENT}]⚙ LIST FILES[/bold {ACCENT}] [#f8fafc]{escape(str(rel))}[/#f8fafc]")
        return True

    render_generic_tool_call(name, arguments, target_console=out)
    return True


def extract_complete_markdown_blocks(buffer: str) -> Tuple[List[str], str]:
    """Split completed top-level Markdown blocks separated by blank lines outside code fences.

    Used during streaming so each paragraph, heading, table, or code block prints once
    without relying on multi-line Live cursor-up redraws that duplicate on Windows terminals.
    """
    if not buffer:
        return [], ""

    ready: List[str] = []
    cur_lines: List[str] = []
    open_fence: Optional[str] = None

    for line in buffer.splitlines(keepends=True):
        stripped = line.lstrip()
        fence_token = None
        if stripped.startswith("```"):
            fence_token = "```"
        elif stripped.startswith("~~~"):
            fence_token = "~~~"

        if fence_token:
            if open_fence is None:
                open_fence = fence_token
            elif fence_token == open_fence and stripped.strip() == fence_token:
                open_fence = None

        if open_fence is None and line.strip() == "" and line.endswith("\n"):
            if any(l.strip() for l in cur_lines):
                ready.append("".join(cur_lines).strip())
                cur_lines = []
            continue

        cur_lines.append(line)

    return ready, "".join(cur_lines)
