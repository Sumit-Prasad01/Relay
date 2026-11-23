"""Interactive CLI prompts for model, provider, and secret input."""

from typing import Optional, Tuple
import typer
from rich.prompt import Prompt
from Relay.cli.display import console
from Relay.config.defaults import DEFAULT_PROVIDERS


def prompt_provider_selection(default: str = "groq") -> str:
    """Prompt user to select or enter a provider."""
    console.print("[bold]Available providers:[/bold] groq, openrouter, openai, anthropic, gemini, ollama")
    choice = Prompt.ask("Select provider", default=default)
    return choice.strip().lower()


def prompt_model_selection(provider: str, default: Optional[str] = None) -> str:
    """Prompt user for model name, providing provider default as suggestion."""
    suggested = default or (DEFAULT_PROVIDERS.get(provider).model if provider in DEFAULT_PROVIDERS else "")
    model = Prompt.ask(f"Model for {provider}", default=suggested)
    return model.strip()


def prompt_api_key(provider: str) -> str:
    """Prompt user for API key with masked input."""
    if provider.lower() == "ollama":
        return ""
    key = typer.prompt(f"Enter API key for {provider}", hide_input=True)
    return key.strip()


def prompt_credentials_interactive(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, str, Optional[str]]:
    """Ensure provider, model, and api key are gathered interactively if not already supplied."""
    selected_provider = provider or prompt_provider_selection()
    selected_model = model or prompt_model_selection(selected_provider)
    selected_key = api_key
    if not selected_key and selected_provider != "ollama":
        selected_key = prompt_api_key(selected_provider)

    return selected_provider, selected_model, selected_key
