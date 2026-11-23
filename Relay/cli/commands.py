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
