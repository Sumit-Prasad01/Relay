"""Core CLI commands implementation for Relay."""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer
from Relay.app import create_app_context
from Relay.cli.display import console, print_banner, print_doctor_report
from Relay.cli.prompts import prompt_credentials_interactive
from Relay.config.loader import load_config
from Relay.config.secrets import SecretManager
from Relay.providers.factory import create_provider
from Relay.utils.paths import get_default_config_path
from Relay.utils.platform import get_platform_name

config_app = typer.Typer(help="Manage configuration")
provider_app = typer.Typer(help="Manage providers and credentials")
models_app = typer.Typer(help="Manage models")
sessions_app = typer.Typer(help="Manage conversation sessions")


def init_command(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Initialize a workspace with .relay/ and AGENTS.md."""
    target_dir = (workspace or Path.cwd()).resolve()
    relay_dir = target_dir / ".relay"
    relay_dir.mkdir(parents=True, exist_ok=True)

    agents_md = target_dir / "AGENTS.md"
    if not agents_md.is_file():
        agents_md.write_text(
            "# Project Instructions\n\n"
            "This file contains instructions for AI coding assistants working in this repository.\n\n"
            "## Architecture\n\n"
            "## Development Workflow\n",
            encoding="utf-8",
        )
        console.print(f"[green]Created {agents_md}[/green]")
    else:
        console.print(f"[dim]{agents_md} already exists.[/dim]")

    console.print(f"[bold green]Workspace initialized at {target_dir}[/bold green]")


def doctor_command(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Check system compatibility, database, keyring, git, and configuration."""
    checks = []

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        checks.append({"name": "Python Version", "status": "ok", "details": py_ver})
    else:
        checks.append({"name": "Python Version", "status": "fail", "details": f"{py_ver} (>= 3.11 required)"})

    # 2. Platform
    checks.append({"name": "Operating System", "status": "ok", "details": get_platform_name()})

    # 3. Keyring
    if SecretManager.is_keyring_available():
        checks.append({"name": "Keyring Secure Storage", "status": "ok", "details": "Available"})
    else:
        checks.append({
            "name": "Keyring Secure Storage",
            "status": "warn",
            "details": "Unavailable; environment variables required for secrets",
        })

    # 4. Git
    git_bin = shutil.which("git")
    if git_bin:
        checks.append({"name": "Git Executable", "status": "ok", "details": git_bin})
    else:
        checks.append({"name": "Git Executable", "status": "warn", "details": "Not found in PATH"})

    # 5. Ripgrep
    rg_bin = shutil.which("rg")
    if rg_bin:
        checks.append({"name": "Ripgrep (rg)", "status": "ok", "details": rg_bin})
    else:
        checks.append({"name": "Ripgrep (rg)", "status": "warn", "details": "Not found; fallback python search used"})

    # 6. Database and migrations
    try:
        app_ctx = create_app_context(workspace_root=workspace)
        checks.append({
            "name": "SQLite Database",
            "status": "ok",
            "details": f"{app_ctx.config.storage.database_path} (migrations up to date)",
        })
    except Exception as e:
        checks.append({"name": "SQLite Database", "status": "fail", "details": str(e)})

    print_doctor_report(checks)


@config_app.command("show")
def config_show(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Display active configuration with credentials redacted."""
    cfg = load_config(workspace_root=workspace)
    data = cfg.model_dump()
    for p in data.get("providers", {}).values():
        if isinstance(p, dict) and p.get("credential_ref"):
            p["credential_ref"] = "***REDACTED***"
    console.print_json(data=data)


@provider_app.command("list")
def provider_list(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """List configured providers and their status."""
    cfg = load_config(workspace_root=workspace)
    from rich.table import Table
    table = Table(title="Configured Providers")
    table.add_column("Provider", style="bold")
    table.add_column("Enabled")
    table.add_column("Default Model")
    table.add_column("Base URL")

    for name, p in cfg.providers.items():
        is_default = " (default)" if name == cfg.default_provider else ""
        enabled_str = "[green]Yes[/green]" if p.enabled else "[dim]No[/dim]"
        table.add_row(f"{name}{is_default}", enabled_str, p.model or "(none)", p.base_url or "(default)")

    console.print(table)


@provider_app.command("add")
def provider_add(
    name: str = typer.Argument(..., help="Provider name (groq, openai, anthropic, gemini, openrouter, ollama)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Default model for this provider"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="API key for this provider"),
) -> None:
    """Configure or update a provider and save credentials securely."""
    provider_name = name.strip().lower()
    selected_provider, selected_model, selected_key = prompt_credentials_interactive(
        provider=provider_name,
        model=model,
        api_key=api_key,
    )

    if selected_key:
        ref = f"relay/{selected_provider}"
        try:
            SecretManager.set_credential(ref, selected_key)
            console.print(f"[green]API key for {selected_provider} saved securely to keyring ({ref}).[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not store in keyring ({e}). You can set {selected_provider.upper()}_API_KEY as an environment variable.[/yellow]")

    console.print(f"[bold green]Provider '{selected_provider}' configured with model '{selected_model}'.[/bold green]")


@provider_app.command("test")
def provider_test(
    name: str = typer.Argument(..., help="Provider name to test (groq, openai, anthropic, gemini, openrouter, ollama)"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Validate credentials and test connectivity to a provider."""
    cfg = load_config(workspace_root=workspace)
    provider_name = name.strip().lower()
    if provider_name not in cfg.providers:
        console.print(f"[red]Error: Provider '{provider_name}' is not configured.[/red]")
        raise typer.Exit(1)

    provider = create_provider(provider_name, cfg.providers[provider_name])
    console.print(f"Testing connectivity to [bold]{provider_name}[/bold]...")

    health = asyncio.run(provider.validate())
    if health.healthy:
        console.print(f"[bold green]PASS:[/bold green] {health.message}")
        if health.models:
            console.print(f"[dim]Available models: {', '.join(health.models[:8])}[/dim]")
    else:
        console.print(f"[bold red]FAIL:[/bold red] {health.message}")
        raise typer.Exit(1)


@models_app.command("list")
def models_list(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter models by provider"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """List models configured across providers."""
    cfg = load_config(workspace_root=workspace)
    from rich.table import Table

    if provider:
        p_name = provider.strip().lower()
        if p_name not in cfg.providers:
            console.print(f"[red]Unknown provider: {p_name}[/red]")
            raise typer.Exit(1)
        p_instance = create_provider(p_name, cfg.providers[p_name])
        models = asyncio.run(p_instance.list_models())

        table = Table(title=f"Models for {p_name}")
        table.add_column("Model ID", style="bold")
        table.add_column("Tool Calling")
        table.add_column("Context Window")

        for m in models:
            caps = m.capabilities or p_instance.get_capabilities(m.id)
            tools_str = "[green]Yes[/green]" if caps.tool_calling else "[dim]No[/dim]"
            ctx_str = f"{caps.max_context_tokens:,}" if caps.max_context_tokens else "(unknown)"
            table.add_row(m.id, tools_str, ctx_str)

        if not models:
            table.add_row(cfg.providers[p_name].model, "[green]Yes[/green]", "128,000")

        console.print(table)
        return

    table = Table(title="Available Default Models")
    table.add_column("Provider", style="bold")
    table.add_column("Default Model")

    for name, p in cfg.providers.items():
        table.add_row(name, p.model or "(none)")

    console.print(table)


@models_app.command("use")
def models_use(
    target: str = typer.Argument(..., help="Provider and model in format 'provider/model' (e.g. 'groq/llama-3.3-70b-versatile')"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Set the active default provider and model."""
    if "/" not in target:
        console.print("[red]Target must be formatted as 'provider/model', e.g. 'groq/llama-3.3-70b-versatile'[/red]")
        raise typer.Exit(1)

    provider_part, model_part = target.split("/", 1)
    provider_name = provider_part.strip().lower()
    model_name = model_part.strip()

    cfg = load_config(workspace_root=workspace)
    if provider_name not in cfg.providers:
        console.print(f"[red]Error: Unknown provider '{provider_name}'.[/red]")
        raise typer.Exit(1)

    # Save to user config.toml
    config_path = get_default_config_path()
    try:
        content = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    except Exception:
        content = ""

    # Append or rewrite default_provider and default_model
    lines = [line for line in content.splitlines() if not line.startswith("default_provider") and not line.startswith("default_model")]
    lines.insert(0, f'default_provider = "{provider_name}"')
    lines.insert(1, f'default_model = "{model_name}"')
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(f"[bold green]Switched active provider to '{provider_name}' and model to '{model_name}'.[/bold green]")


@sessions_app.command("list")
def sessions_list(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """List conversation sessions for workspace."""
    app_ctx = create_app_context(workspace_root=workspace)
    sessions = app_ctx.session_store.list_sessions(workspace=app_ctx.workspace_root)
    if not sessions:
        console.print("[dim]No sessions found for this workspace.[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Sessions ({app_ctx.workspace_root})")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Provider/Model")
    table.add_column("Updated At", style="dim")

    for s in sessions:
        table.add_row(s["id"][:8], s["title"], f"{s['provider']}/{s['model']}", s["updated_at"][:19])

    console.print(table)


@sessions_app.command("show")
def sessions_show(
    session_id: str = typer.Argument(..., help="Session ID (full or prefix)"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Display session details and message transcript."""
    app_ctx = create_app_context(workspace_root=workspace)
    # Match by ID or prefix
    target_id = session_id
    sessions = app_ctx.session_store.list_sessions(workspace=app_ctx.workspace_root)
    matching = [s for s in sessions if s["id"].startswith(session_id)]
    if matching:
        target_id = matching[0]["id"]

    session = app_ctx.session_store.get_session(target_id)
    if not session:
        console.print(f"[red]Error: Session '{session_id}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Session:[/bold cyan] {session['title']}")
    console.print(f"[dim]ID: {session['id']} | Provider: {session['provider']}/{session['model']}[/dim]")
    console.print(f"[dim]Created: {session['created_at']} | Updated: {session['updated_at']}[/dim]\n")

    messages = app_ctx.session_store.get_messages(target_id)
    for m in messages:
        role_color = {"user": "bold yellow", "assistant": "bold green", "system": "dim cyan", "tool": "dim magenta"}.get(m["role"], "bold")
        console.print(f"[{role_color}][{m['role'].upper()}][/{role_color}]")
        console.print(m["content"] or "*(no content)*")
        console.print()


@sessions_app.command("export")
def sessions_export(
    session_id: str = typer.Argument(..., help="Session ID (full or prefix)"),
    format: str = typer.Option("markdown", "--format", "-f", help="Export format: markdown or json"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="File to save exported transcript to"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Export session transcript with secrets redacted."""
    app_ctx = create_app_context(workspace_root=workspace)
    sessions = app_ctx.session_store.list_sessions(workspace=app_ctx.workspace_root)
    matching = [s for s in sessions if s["id"].startswith(session_id)]
    target_id = matching[0]["id"] if matching else session_id

    try:
        exported = app_ctx.session_store.export_session(target_id, export_format=format)
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        raise typer.Exit(1)

    if output:
        output.write_text(exported, encoding="utf-8")
        console.print(f"[green]Transcript saved to {output.resolve()}[/green]")
    else:
        console.print(exported)


@sessions_app.command("delete")
def sessions_delete(
    session_id: str = typer.Argument(..., help="Session ID (full or prefix)"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Delete a conversation session."""
    app_ctx = create_app_context(workspace_root=workspace)
    sessions = app_ctx.session_store.list_sessions(workspace=app_ctx.workspace_root)
    matching = [s for s in sessions if s["id"].startswith(session_id)]
    target_id = matching[0]["id"] if matching else session_id

    if app_ctx.session_store.delete_session(target_id):
        console.print(f"[green]Deleted session '{target_id}'.[/green]")
    else:
        console.print(f"[red]Error: Session '{session_id}' not found.[/red]")
        raise typer.Exit(1)


@sessions_app.command("resume")
def sessions_resume(
    session_id: str = typer.Argument(..., help="Session ID (full or prefix)"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Resume an existing session in interactive mode."""
    app_ctx = create_app_context(workspace_root=workspace)
    sessions = app_ctx.session_store.list_sessions(workspace=app_ctx.workspace_root)
    matching = [s for s in sessions if s["id"].startswith(session_id)]
    target_id = matching[0]["id"] if matching else session_id

    interactive_session(workspace=workspace, session_id=target_id)


def interactive_session(
    workspace: Optional[Path] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Run interactive terminal session with in-session slash commands (Section 13.2)."""
    from prompt_toolkit import PromptSession
    from Relay.agent.runtime import AgentRuntime
    from Relay.security.permissions import PermissionManager

    app_ctx = create_app_context(workspace_root=workspace, provider=provider, model=model)
    perm_manager = PermissionManager(mode=app_ctx.config.permission_mode, workspace_root=app_ctx.workspace_root)
    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_manager)

    if session_id:
        try:
            state = runtime.resume_session(session_id)
            console.print(f"[green]Resumed session {state.session_id[:8]} ({len(state.messages)} prior messages)[/green]")
        except Exception as e:
            console.print(f"[red]Could not resume session ({e}). Creating new session.[/red]")
            state = runtime.create_session(provider=provider, model=model)
    else:
        state = runtime.create_session(provider=provider, model=model)

    print_banner()
    console.print(f"Connected to [bold cyan]{state.provider_name}/{state.model_name}[/bold cyan] | Mode: [bold yellow]{perm_manager.mode}[/bold yellow]")
    console.print("Type your coding request, or [bold]/help[/bold] for commands. Ctrl+C or [bold]/quit[/bold] to exit.\n")

    prompt_session = PromptSession()

    while True:
        try:
            user_input = prompt_session.prompt("relay > ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Slash command handling (Section 13.2)
        if user_input.startswith("/"):
            parts = user_input.split()
            cmd = parts[0].lower()

            if cmd in ("/quit", "/exit"):
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "/help":
                console.print(
                    "[bold]Available Interactive Commands:[/bold]\n"
                    "  /help              Show this help reference\n"
                    "  /diff              Show working tree git diff\n"
                    "  /status            Show active provider, model, permissions, and stats\n"
                    "  /permissions [m]   Inspect or switch permission mode (plan, ask, auto-edit, full-auto)\n"
                    "  /sessions          List recent workspace sessions\n"
                    "  /export [format]   Export current session transcript (markdown or json)\n"
                    "  /clear             Clear the terminal screen\n"
                    "  /quit              Exit interactive session\n"
                )
                continue
            elif cmd == "/diff":
                diff = runtime.get_diff()
                if diff:
                    from rich.panel import Panel
                    from rich.syntax import Syntax
                    console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff"))
                else:
                    console.print("[dim]No working tree modifications.[/dim]")
                continue
            elif cmd == "/status":
                console.print(
                    f"Session: {state.session_id}\n"
                    f"Provider: {state.provider_name}\n"
                    f"Model: {state.model_name}\n"
                    f"Permission Mode: {perm_manager.mode}\n"
                    f"Turn count: {state.turn_count}\n"
                    f"Total tokens used: {state.total_tokens_used}\n"
                    f"Files modified: {', '.join(state.changed_files) if state.changed_files else 'None'}"
                )
                continue
            elif cmd == "/permissions":
                if len(parts) > 1 and parts[1] in ("plan", "ask", "auto-edit", "full-auto"):
                    perm_manager.mode = parts[1]
                    console.print(f"[green]Permission mode switched to '{parts[1]}'.[/green]")
                else:
                    console.print(f"Current mode: [bold yellow]{perm_manager.mode}[/bold yellow]. Use '/permissions [plan|ask|auto-edit|full-auto]' to change.")
                continue
            elif cmd == "/sessions":
                sessions_list(workspace=app_ctx.workspace_root)
                continue
            elif cmd == "/export":
                fmt = parts[1] if len(parts) > 1 else "markdown"
                console.print(app_ctx.session_store.export_session(state.session_id, export_format=fmt))
                continue
            elif cmd == "/clear":
                console.clear()
                continue
            else:
                console.print(f"[yellow]Unknown slash command '{cmd}'. Type /help for available commands.[/yellow]")
                continue

        # Normal prompt turn
        try:
            asyncio.run(_run_turn_stream(runtime, state, user_input))
        except KeyboardInterrupt:
            console.print("\n[yellow]Turn cancelled by user.[/yellow]")
            runtime.cancel(state)


async def _run_turn_stream(runtime, state, prompt: str) -> None:
    """Stream agent execution turn events to terminal."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    console.print(f"\n[bold cyan]Relay Agent[/bold cyan] ({state.provider_name}/{state.model_name})")
    console.print(f"[dim]Workspace: {state.workspace_root}[/dim]\n")

    current_text_line = []
    async for event in runtime.run_turn(state, prompt):
        if event.event_type == "text_delta" and event.text_delta:
            console.print(event.text_delta, end="", highlight=False)
            current_text_line.append(event.text_delta)
        elif event.event_type == "tool_call_requested" and event.tool_call:
            if current_text_line:
                console.print()
                current_text_line = []
            console.print(f"\n[bold blue]🛠️  Tool:[/bold blue] [cyan]{event.tool_call.name}[/cyan] [dim]{event.tool_call.arguments}[/dim]")
        elif event.event_type == "tool_call_completed" and event.tool_result:
            duration = f"{event.tool_result.duration_ms}ms" if event.tool_result.duration_ms else ""
            console.print(f"[green]✓ Completed {duration}[/green]")
            if event.tool_result.content and len(event.tool_result.content) < 300:
                console.print(f"[dim]{event.tool_result.content.strip()}[/dim]")
        elif event.event_type == "tool_call_failed" and event.tool_result:
            console.print(f"[bold red]✗ Failed:[/bold red] {event.tool_result.content.strip()}")
        elif event.event_type == "file_changed" and event.file_path:
            console.print(f"[bold yellow]📝 Modified file:[/bold yellow] [bold]{event.file_path}[/bold]")
        elif event.event_type == "error":
            console.print(f"\n[bold red]Error:[/bold red] {event.error}")
        elif event.event_type == "stop_condition_met":
            console.print(f"\n[dim magenta]⏹️  {event.message}[/dim magenta]")

    console.print("\n")
    summary = runtime.summarize_changes(state)
    if summary["changed_files"]:
        console.print("[bold green]Files Changed:[/bold green]")
        for f in summary["changed_files"]:
            console.print(f" - [bold]{f}[/bold]")
        if summary.get("diff"):
            console.print(Panel(Syntax(summary["diff"], "diff", theme="monokai", line_numbers=True), title="Diff"))

    console.print(f"[dim]Tokens used: {summary['tokens']['total']} (prompt: {summary['tokens']['prompt']}, completion: {summary['tokens']['completion']})[/dim]")


def ask_command(
    prompt: str = typer.Argument(..., help="Prompt or task instructions for Relay agent"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider override"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
    permission_mode: Optional[str] = typer.Option(None, "--mode", help="Permission mode (plan, ask, auto-edit, full-auto)"),
) -> None:
    """Execute a task autonomously using the agent runtime."""
    from Relay.agent.runtime import AgentRuntime
    from Relay.security.permissions import PermissionManager

    app_ctx = create_app_context(
        workspace_root=workspace,
        provider=provider,
        model=model,
    )
    p_mode = permission_mode or app_ctx.config.permission_mode
    perm_manager = PermissionManager(mode=p_mode, workspace_root=app_ctx.workspace_root)
    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_manager)

    state = runtime.create_session(
        title=prompt[:50],
        provider=provider or app_ctx.config.default_provider,
        model=model,
    )

    try:
        asyncio.run(_run_turn_stream(runtime, state, prompt))
    except KeyboardInterrupt:
        console.print("\n[yellow]Task cancelled by user (Ctrl+C).[/yellow]")
        runtime.cancel(state)


def plan_command(
    prompt: str = typer.Argument(..., help="Task to analyze and plan without executing mutations"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider override"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace path"),
) -> None:
    """Analyze the repository and create an execution plan in read-only mode."""
    ask_command(
        prompt=f"Please inspect the codebase and create a detailed implementation plan for: {prompt}. Do not modify any files.",
        provider=provider,
        model=model,
        workspace=workspace,
        permission_mode="plan",
    )
