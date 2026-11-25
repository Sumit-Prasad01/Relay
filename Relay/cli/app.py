"""Main Typer CLI entry point for Relay."""

from pathlib import Path
from typing import Optional

import typer
from Relay import __version__
from Relay.cli.commands import (
    ask_command,
    config_app,
    doctor_command,
    init_command,
    interactive_session,
    models_app,
    plan_command,
    provider_app,
    sessions_app,
)
from Relay.cli.display import console, print_banner

app = typer.Typer(
    name="relay",
    help="Relay: A provider-agnostic, local-first AI coding agent.",
    no_args_is_help=False,
)

# Register command groups
app.add_typer(config_app, name="config")
app.add_typer(provider_app, name="provider")
app.add_typer(models_app, name="models")
app.add_typer(sessions_app, name="sessions")

# Direct commands
app.command("init", help="Initialize workspace with .relay/ and AGENTS.md")(init_command)
app.command("doctor", help="Run system diagnostics and verify environment")(doctor_command)
app.command("ask", help="Execute an autonomous coding task")(ask_command)
app.command("plan", help="Produce an inspection and execution plan in read-only mode")(plan_command)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider to use (e.g. groq, openai, openrouter)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Provider API key"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Target workspace path"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    if version:
        console.print(f"Relay version {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        import sys
        if sys.stdin and sys.stdin.isatty():
            interactive_session(
                workspace=workspace,
                provider=provider,
                model=model,
                api_key=api_key,
                debug=debug,
            )
        else:
            print_banner()
            console.print("Run [bold cyan]relay --help[/bold cyan] to see available commands.")
            console.print("Run [bold cyan]relay doctor[/bold cyan] to verify system configuration.")
            console.print("Configure a provider using [bold cyan]relay provider add <name>[/bold cyan].")
