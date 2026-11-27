"""Core CLI commands implementation for Relay."""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer
from Relay.app import create_app_context
from Relay.cli.display import (
    ACCENT,
    ACCENT_ALT,
    BORDER,
    DIM,
    ERROR,
    MUTED,
    SUCCESS,
    WARNING,
    console,
    extract_complete_markdown_blocks,
    print_banner,
    print_doctor_report,
    print_session_card,
    pulse_status,
    render_tool_call,
    render_tool_denied,
    render_tool_error,
    render_tool_result,
    set_active_status,
)
from Relay.cli.prompts import (
    RELAY_PROMPT_STYLE,
    prompt_api_key,
    prompt_credentials_interactive,
    save_provider_credential,
)
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
    from rich import box
    from rich.table import Table

    table = Table(
        title="Configured Providers",
        title_style="bold #f8fafc",
        box=box.ROUNDED,
        border_style=BORDER,
        header_style=f"bold {ACCENT}",
    )
    table.add_column("Provider", style="bold #f8fafc")
    table.add_column("Enabled", justify="center")
    table.add_column("Default Model", style=MUTED)
    table.add_column("Base URL", style=DIM)

    for name, p in cfg.providers.items():
        is_default = f" [{ACCENT}](default)[/{ACCENT}]" if name == cfg.default_provider else ""
        enabled_str = f"[{SUCCESS}]● Yes[/{SUCCESS}]" if p.enabled else f"[{DIM}]○ No[/{DIM}]"
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

    async def _run_validate():
        try:
            return await provider.validate()
        finally:
            if hasattr(provider, "aclose"):
                await provider.aclose()

    health = asyncio.run(_run_validate())
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
    from rich import box
    from rich.table import Table

    if provider:
        p_name = provider.strip().lower()
        if p_name not in cfg.providers:
            console.print(f"[{ERROR}]Unknown provider: {p_name}[/{ERROR}]")
            raise typer.Exit(1)
        p_instance = create_provider(p_name, cfg.providers[p_name])

        async def _fetch_models():
            try:
                return await p_instance.list_models()
            finally:
                if hasattr(p_instance, "aclose"):
                    await p_instance.aclose()

        with pulse_status(f"Fetching models from {p_name}..."):
            models = asyncio.run(_fetch_models())

        table = Table(
            title=f"Models for {p_name}",
            title_style="bold #f8fafc",
            box=box.ROUNDED,
            border_style=BORDER,
            header_style=f"bold {ACCENT}",
        )
        table.add_column("Model ID", style="bold #f8fafc")
        table.add_column("Tool Calling", justify="center")
        table.add_column("Context Window", style=MUTED, justify="right")

        for m in models:
            caps = m.capabilities or p_instance.get_capabilities(m.id)
            tools_str = f"[{SUCCESS}]✓ Yes[/{SUCCESS}]" if caps.tool_calling else f"[{DIM}]— No[/{DIM}]"
            ctx_str = f"{caps.max_context_tokens:,}" if caps.max_context_tokens else "(unknown)"
            table.add_row(m.id, tools_str, ctx_str)

        if not models:
            table.add_row(cfg.providers[p_name].model, f"[{SUCCESS}]✓ Yes[/{SUCCESS}]", "128,000")

        console.print(table)
        return

    table = Table(
        title="Available Default Models",
        title_style="bold #f8fafc",
        box=box.ROUNDED,
        border_style=BORDER,
        header_style=f"bold {ACCENT}",
    )
    table.add_column("Provider", style="bold #f8fafc")
    table.add_column("Default Model", style=MUTED)

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

    from rich import box
    from rich.table import Table
    table = Table(
        title=f"Sessions ({app_ctx.workspace_root})",
        title_style="bold #f8fafc",
        box=box.ROUNDED,
        border_style=BORDER,
        header_style=f"bold {ACCENT}",
    )
    table.add_column("ID", style=DIM)
    table.add_column("Title", style="bold #f8fafc")
    table.add_column("Provider/Model", style=ACCENT_ALT)
    table.add_column("Updated At", style=MUTED)

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
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    debug: bool = False,
) -> None:
    """Run interactive terminal session with startup provider/key/model prompts and slash commands (Section 13.2)."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from Relay.agent.runtime import AgentRuntime
    from Relay.security.permissions import PermissionManager

    print_banner(animate=True)

    selected_provider = provider
    selected_model = model
    selected_key = api_key

    if session_id is None and selected_provider is None:
        base_cfg = load_config(workspace_root=workspace)
        try:
            selected_provider, selected_model, selected_key = prompt_credentials_interactive(
                provider=selected_provider,
                model=selected_model,
                api_key=selected_key,
                default_provider=base_cfg.default_provider,
            )
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{DIM}]Setup cancelled. Goodbye![/{DIM}]")
            return

        if selected_key:
            save_provider_credential(selected_provider, selected_key)

    with pulse_status("Initializing workspace & agent runtime...", min_duration=0.25):
        app_ctx = create_app_context(
            workspace_root=workspace,
            provider=selected_provider,
            model=selected_model,
            api_key=selected_key,
            debug=debug,
        )
        perm_manager = PermissionManager(mode=app_ctx.config.permission_mode, workspace_root=app_ctx.workspace_root)
        runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_manager)

        if session_id:
            try:
                state = runtime.resume_session(session_id)
                resumed_note = f"Resumed session {state.session_id[:8]} ({len(state.messages)} prior messages)"
            except Exception as e:
                resumed_note = f"Could not resume session ({e}). Started new session."
                state = runtime.create_session(provider=selected_provider, model=selected_model)
        else:
            resumed_note = None
            state = runtime.create_session(provider=selected_provider, model=selected_model)

    if resumed_note:
        console.print(f"[{MUTED}]{resumed_note}[/{MUTED}]")

    print_session_card(
        provider=state.provider_name,
        model=state.model_name,
        mode=perm_manager.mode,
        workspace=str(state.workspace_root),
        session_id=state.session_id,
    )

    prompt_session = PromptSession()

    while True:
        try:
            toolbar = HTML(
                f" <b>{state.provider_name}</b>/{state.model_name}  ·  "
                f"mode: <b>{perm_manager.mode}</b>  ·  "
                "<b>/help</b> commands  ·  <b>/quit</b> exit "
            )
            user_input = prompt_session.prompt(
                HTML("<prompt-label>relay</prompt-label> <ansibrightcyan>❯</ansibrightcyan> "),
                bottom_toolbar=toolbar,
                style=RELAY_PROMPT_STYLE,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{DIM}]Goodbye![/{DIM}]")
            break

        if not user_input:
            continue

        # Slash command handling (Section 13.2)
        if user_input.startswith("/"):
            parts = user_input.split()
            cmd = parts[0].lower()

            if cmd in ("/quit", "/exit"):
                console.print(f"[{DIM}]Goodbye![/{DIM}]")
                break
            elif cmd == "/help":
                from rich import box
                from rich.panel import Panel
                help_text = (
                    f"[{ACCENT}]/help[/{ACCENT}]              Show this command reference\n"
                    f"[{ACCENT}]/model[/{ACCENT}]             Switch provider, API key, or model mid-session\n"
                    f"[{ACCENT}]/diff[/{ACCENT}]              Show working tree git diff\n"
                    f"[{ACCENT}]/status[/{ACCENT}]            Show active provider, model, permissions, and stats\n"
                    f"[{ACCENT}]/permissions [m][/{ACCENT}]   Inspect or switch mode (plan, ask, auto-edit, full-auto)\n"
                    f"[{ACCENT}]/sessions[/{ACCENT}]          List recent workspace sessions\n"
                    f"[{ACCENT}]/export [format][/{ACCENT}]   Export session transcript (markdown or json)\n"
                    f"[{ACCENT}]/clear[/{ACCENT}]             Clear the terminal screen\n"
                    f"[{ACCENT}]/quit[/{ACCENT}]              Exit interactive session"
                )
                console.print(Panel(help_text, title="Interactive Commands", box=box.ROUNDED, border_style=BORDER, expand=False))
                continue
            elif cmd in ("/model", "/models"):
                from Relay.providers.registry import ProviderRegistry

                try:
                    new_provider = state.provider_name
                    new_model = state.model_name
                    new_key: Optional[str] = None

                    if len(parts) == 1:
                        # Full interactive switcher: Provider dropdown -> API key box -> Model box
                        new_provider, new_model, new_key = prompt_credentials_interactive(
                            default_provider=state.provider_name,
                        )
                    elif len(parts) == 2:
                        arg = parts[1].strip()
                        arg_lower = arg.lower()
                        if ProviderRegistry.is_registered(arg_lower):
                            # Switch to selected registered provider, prompting for key & model
                            _, new_model, new_key = prompt_credentials_interactive(
                                provider=arg_lower,
                            )
                            new_provider = arg_lower
                        elif "/" in arg and state.provider_name != "openrouter":
                            cand_provider, cand_model = arg.split("/", 1)
                            if ProviderRegistry.is_registered(cand_provider.lower()):
                                new_provider = cand_provider.lower()
                                new_model = cand_model.strip()
                                if new_provider != "ollama" and not SecretManager.get_credential(f"relay/{new_provider}"):
                                    new_key = prompt_api_key(new_provider)
                            else:
                                new_model = arg
                        else:
                            new_model = arg
                    else:
                        # /model <provider> <model>
                        cand_provider = parts[1].strip().lower()
                        if not ProviderRegistry.is_registered(cand_provider):
                            console.print(
                                f"[{ERROR}]Unknown provider '{cand_provider}'. Available: {', '.join(ProviderRegistry.list_providers())}[/{ERROR}]"
                            )
                            continue
                        new_provider = cand_provider
                        new_model = " ".join(parts[2:]).strip()
                        if new_provider != "ollama" and not SecretManager.get_credential(f"relay/{new_provider}"):
                            new_key = prompt_api_key(new_provider)
                except (KeyboardInterrupt, EOFError):
                    console.print(f"\n[{DIM}]Model switch cancelled. Keeping {state.provider_name}/{state.model_name}.[/{DIM}]")
                    continue

                if new_key:
                    save_provider_credential(new_provider, new_key)

                state.provider_name = new_provider
                state.model_name = new_model
                if new_provider in app_ctx.config.providers:
                    app_ctx.config.providers[new_provider].model = new_model
                app_ctx.session_store.update_session_model(state.session_id, new_provider, new_model)
                app_ctx.event_store.record_event(
                    event_type="model_switched",
                    payload={"provider": new_provider, "model": new_model},
                    session_id=state.session_id,
                )
                console.print(
                    f"[{SUCCESS}]● Switched active model to [bold {ACCENT}]{new_provider}[/bold {ACCENT}]/[bold {ACCENT_ALT}]{new_model}[/bold {ACCENT_ALT}].[/{SUCCESS}]"
                )
                continue
            elif cmd == "/diff":
                diff = runtime.get_diff()
                if diff:
                    from rich import box
                    from rich.panel import Panel
                    from rich.syntax import Syntax
                    console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff", box=box.ROUNDED, border_style=BORDER))
                else:
                    console.print(f"[{DIM}]No working tree modifications.[/{DIM}]")
                continue
            elif cmd == "/status":
                from rich import box
                from rich.panel import Panel
                status_body = (
                    f"[{DIM}]Session:[/{DIM}]         {state.session_id}\n"
                    f"[{DIM}]Provider:[/{DIM}]        [{ACCENT}]{state.provider_name}[/{ACCENT}]\n"
                    f"[{DIM}]Model:[/{DIM}]           [{ACCENT_ALT}]{state.model_name}[/{ACCENT_ALT}]\n"
                    f"[{DIM}]Permission Mode:[/{DIM}] [{WARNING}]{perm_manager.mode}[/{WARNING}]\n"
                    f"[{DIM}]Turn Count:[/{DIM}]      {state.turn_count}\n"
                    f"[{DIM}]Total Tokens:[/{DIM}]    {state.total_tokens_used:,}\n"
                    f"[{DIM}]Files Modified:[/{DIM}]  {', '.join(state.changed_files) if state.changed_files else 'None'}"
                )
                console.print(Panel(status_body, title="Session Status", box=box.ROUNDED, border_style=BORDER, expand=False))
                continue
            elif cmd == "/permissions":
                if len(parts) > 1 and parts[1] in ("plan", "ask", "auto-edit", "full-auto"):
                    perm_manager.mode = parts[1]
                    console.print(f"[{SUCCESS}]● Permission mode switched to '{parts[1]}'.[/{SUCCESS}]")
                else:
                    console.print(f"Current mode: [bold {WARNING}]{perm_manager.mode}[/bold {WARNING}]. Use '/permissions [plan|ask|auto-edit|full-auto]' to change.")
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
                print_banner(animate=False)
                continue
            else:
                console.print(f"[{WARNING}]Unknown command '{cmd}'. Type /help for available commands.[/{WARNING}]")
                continue

        # Normal prompt turn
        try:
            asyncio.run(_run_turn_stream(runtime, state, user_input))
        except KeyboardInterrupt:
            console.print(f"\n[{WARNING}]Turn cancelled by user.[/{WARNING}]")
            runtime.cancel(state)


async def _run_turn_stream(runtime, state, prompt: str) -> None:
    """Stream agent execution turn events to terminal with live status and non-repeating Markdown blocks."""
    import sys
    from rich import box
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax

    console.print(
        f"\n[bold {ACCENT}]◆ Relay[/bold {ACCENT}] [{DIM}]·[/{DIM}] [{ACCENT_ALT}]{state.provider_name}/{state.model_name}[/{ACCENT_ALT}]"
    )
    console.print(f"[{DIM}]{state.workspace_root}[/{DIM}]\n")

    is_tty = bool(sys.stdout and sys.stdout.isatty())
    active_status = None
    active_label = ""
    md_buffer = ""
    last_render_valid = True

    def _start_spinner(label: str) -> None:
        nonlocal active_status, active_label
        if not is_tty:
            return
        if active_status is not None and active_label == label:
            return
        _stop_spinner()
        active_label = label
        active_status = console.status(f"[{MUTED}]{label}[/{MUTED}]", spinner="dots2", spinner_style=ACCENT)
        set_active_status(active_status)
        active_status.start()

    def _stop_spinner() -> None:
        nonlocal active_status, active_label
        if active_status is not None:
            set_active_status(None)
            active_status.stop()
            active_status = None
            active_label = ""

    def _emit_markdown_chunk(delta: str) -> None:
        nonlocal md_buffer
        md_buffer += delta
        completed, md_buffer = extract_complete_markdown_blocks(md_buffer)
        if completed:
            _stop_spinner()
            for block in completed:
                console.print(Markdown(block, code_theme="monokai", inline_code_theme="monokai"))
            if md_buffer.strip():
                _start_spinner("Streaming response...")
        elif md_buffer.strip():
            _start_spinner("Streaming response...")

    def _flush_markdown() -> None:
        nonlocal md_buffer
        if not md_buffer.strip():
            md_buffer = ""
            return
        console.print(Markdown(md_buffer.strip(), code_theme="monokai", inline_code_theme="monokai"))
        md_buffer = ""

    _start_spinner("Thinking...")
    try:
        async for event in runtime.run_turn(state, prompt):
            if event.event_type == "text_delta" and event.text_delta:
                _emit_markdown_chunk(event.text_delta)
            elif event.event_type == "tool_call_requested" and event.tool_call:
                _stop_spinner()
                _flush_markdown()
                last_render_valid = render_tool_call(event.tool_call, target_console=console)
            elif event.event_type == "tool_call_started" and event.tool_call:
                _start_spinner(f"Executing {event.tool_call.name}...")
            elif event.event_type == "tool_call_completed" and event.tool_result:
                _stop_spinner()
                tool_name = event.tool_call.name if event.tool_call else "tool"
                render_tool_result(tool_name, event.tool_result, target_console=console)
                _start_spinner("Thinking...")
            elif event.event_type == "tool_call_failed" and event.tool_result:
                _stop_spinner()
                tool_name = event.tool_call.name if event.tool_call else "tool"
                err_code = event.tool_result.error or ""
                if err_code == "user_instructed":
                    render_tool_denied(
                        tool_name,
                        reason=event.tool_result.content,
                        is_instruct=True,
                        target_console=console,
                    )
                elif err_code == "user_denied":
                    render_tool_denied(tool_name, is_policy=False, target_console=console)
                elif err_code == "permission_denied":
                    render_tool_denied(
                        tool_name,
                        reason=event.tool_result.content,
                        is_policy=True,
                        target_console=console,
                    )
                elif err_code == "invalid_arguments" and not last_render_valid:
                    # Validation error already rendered cleanly on tool_call_requested
                    pass
                else:
                    render_tool_error(
                        tool_name,
                        event.tool_result.content or event.error or "Execution failed",
                        target_console=console,
                    )
                _start_spinner("Thinking...")
            elif event.event_type == "file_changed" and event.file_path:
                _stop_spinner()
                _flush_markdown()
                console.print(f"[{WARNING}]◆ Modified:[/{WARNING}] [bold #f8fafc]{event.file_path}[/bold #f8fafc]")
            elif event.event_type == "error":
                _stop_spinner()
                _flush_markdown()
                render_tool_error("runtime", str(event.error or "Unknown error"), target_console=console)
            elif event.event_type == "stop_condition_met":
                _stop_spinner()
                _flush_markdown()
                console.print(f"\n[{MUTED}]⏹ {event.message}[/{MUTED}]")
    finally:
        _stop_spinner()
        _flush_markdown()

    console.print()
    summary = runtime.summarize_changes(state)
    if summary["changed_files"]:
        console.print(f"[bold {SUCCESS}]Files Changed:[/bold {SUCCESS}]")
        for f in summary["changed_files"]:
            console.print(f"  [{ACCENT}]•[/{ACCENT}] [bold #f8fafc]{f}[/bold #f8fafc]")
        if summary.get("diff"):
            console.print(
                Panel(
                    Syntax(summary["diff"], "diff", theme="monokai", line_numbers=True),
                    title="Diff",
                    box=box.ROUNDED,
                    border_style=BORDER,
                )
            )

    console.print(
        f"[{DIM}]Tokens: {summary['tokens']['total']:,} "
        f"(prompt {summary['tokens']['prompt']:,} · completion {summary['tokens']['completion']:,})[/{DIM}]"
    )


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
