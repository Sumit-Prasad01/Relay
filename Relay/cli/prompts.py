"""Dark, sleek interactive CLI prompts for provider dropdown, API key box, and model input."""

import os
from typing import Dict, List, Optional, Tuple

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import ValidationError, Validator

from Relay.cli.display import WARNING, console
from Relay.config.secrets import ENV_KEY_MAP, SecretManager
from Relay.providers.registry import ProviderRegistry

PROVIDER_LABELS: Dict[str, str] = {
    "openrouter": "OpenRouter    · Unified multi-provider API gateway",
    "groq":       "Groq          · High-speed LPU inference cloud",
    "anthropic":  "Anthropic     · Native Claude Messages API",
    "openai":     "OpenAI        · Official OpenAI Platform API",
    "gemini":     "Google Gemini · Google AI Studio & Gemini API",
    "ollama":     "Ollama        · Local self-hosted inference engine",
}

# Sleek dark obsidian & electric-cyan prompt_toolkit theme
RELAY_PROMPT_STYLE = Style.from_dict(
    {
        "frame.border": "#334155",
        "frame.label": "bold #38bdf8",
        "selected-option": "bold #38bdf8 bg:#0f172a",
        "option": "#cbd5e1",
        "number": "#64748b",
        "input-selection": "",
        "placeholder": "#64748b italic",
        "bottom-toolbar": "bg:#0f172a #94a3b8",
        "bottom-toolbar.text": "#94a3b8",
        "validation-toolbar": "bg:#450a0a #fca5a5",
        "prompt-label": "bold #f8fafc",
        "prompt-hint": "#64748b",
    }
)


class _NonEmptyValidator(Validator):
    """Validator ensuring interactive input is non-empty when required."""

    def __init__(self, message: str):
        self.message = message

    def validate(self, document) -> None:
        if not document.text.strip():
            raise ValidationError(message=self.message, cursor_position=len(document.text))


def _get_provider_options() -> List[Tuple[str, str]]:
    """Build dropdown options dynamically from registered providers without demo model names."""
    registered = ProviderRegistry.list_providers()
    preferred_order = ["openrouter", "groq", "anthropic", "openai", "gemini", "ollama"]
    ordered = [p for p in preferred_order if p in registered] + [
        p for p in registered if p not in preferred_order
    ]
    return [(pid, PROVIDER_LABELS.get(pid, pid.capitalize())) for pid in ordered]


def save_provider_credential(provider: str, api_key: str) -> None:
    """Persist API key to keyring (when available) and export to current process env."""
    if not api_key or not api_key.strip():
        return

    clean_key = api_key.strip()
    provider_id = provider.lower().strip()
    ref = f"relay/{provider_id}"

    env_vars = ENV_KEY_MAP.get(ref, [f"{provider_id.upper()}_API_KEY"])
    os.environ[env_vars[0]] = clean_key

    try:
        SecretManager.set_credential(ref, clean_key)
    except Exception as e:
        console.print(
            f"[{WARNING}]Note: Could not store in OS keyring ({e}). "
            f"Active for this session via {env_vars[0]}.[/{WARNING}]"
        )


def prompt_provider_selection(default: str = "openrouter") -> str:
    """Render a sleek dark interactive dropdown for selecting a model provider."""
    options = _get_provider_options()
    valid_ids = [opt[0] for opt in options]
    initial_default = default.lower().strip() if default and default.lower().strip() in valid_ids else valid_ids[0]

    selected = choice(
        message=HTML(
            "<prompt-label>Select Model Provider</prompt-label> "
            "<prompt-hint>(↑/↓ navigate · Enter select)</prompt-hint>"
        ),
        options=options,
        default=initial_default,
        symbol="❯",
        show_frame=True,
        mouse_support=True,
        bottom_toolbar=HTML(" <b>↑/↓</b> Move   <b>1-6</b> Quick Pick   <b>Enter</b> Confirm   <b>Ctrl+C</b> Exit "),
        style=RELAY_PROMPT_STYLE,
    )
    return selected.strip().lower()


def prompt_api_key(provider: str, existing_key: Optional[str] = None) -> str:
    """Render a sleek dark framed input box for entering the provider API key."""
    provider_id = provider.lower().strip()
    ref = f"relay/{provider_id}"
    saved_key = existing_key if existing_key is not None else SecretManager.get_credential(ref)

    session = PromptSession()

    if provider_id == "ollama":
        entered = session.prompt(
            HTML(f"<prompt-label>API Key</prompt-label> <prompt-hint>({provider_id})</prompt-hint> ❯ "),
            is_password=True,
            show_frame=True,
            placeholder=HTML("<placeholder>Optional for local Ollama · Press Enter to skip</placeholder>"),
            bottom_toolbar=HTML(" <b>Enter</b> Continue   <b>Ctrl+C</b> Exit "),
            style=RELAY_PROMPT_STYLE,
        )
        return entered.strip()

    if saved_key:
        entered = session.prompt(
            HTML(f"<prompt-label>API Key</prompt-label> <prompt-hint>({provider_id})</prompt-hint> ❯ "),
            is_password=True,
            show_frame=True,
            placeholder=HTML("<placeholder>Saved key detected · Press Enter to keep or paste new key</placeholder>"),
            bottom_toolbar=HTML(" <b>Enter</b> Keep / Save Key   <b>Ctrl+C</b> Exit "),
            style=RELAY_PROMPT_STYLE,
        )
        return entered.strip() if entered.strip() else saved_key

    entered = session.prompt(
        HTML(f"<prompt-label>API Key</prompt-label> <prompt-hint>({provider_id})</prompt-hint> ❯ "),
        is_password=True,
        show_frame=True,
        placeholder=HTML(f"<placeholder>Enter your {provider_id.upper()} API key...</placeholder>"),
        validator=_NonEmptyValidator(f"API key is required for {provider_id}."),
        validate_while_typing=False,
        bottom_toolbar=HTML(" <b>Enter</b> Confirm API Key   <b>Ctrl+C</b> Exit "),
        style=RELAY_PROMPT_STYLE,
    )
    return entered.strip()


def prompt_model_selection(provider: str, default: Optional[str] = None) -> str:
    """Render a sleek dark framed input box for entering the model name (no demo models)."""
    provider_id = provider.lower().strip()
    initial_text = default.strip() if default else ""

    session = PromptSession()
    entered = session.prompt(
        HTML(f"<prompt-label>Model Name</prompt-label> <prompt-hint>({provider_id})</prompt-hint> ❯ "),
        default=initial_text,
        show_frame=True,
        placeholder=HTML(f"<placeholder>Enter model ID for {provider_id}...</placeholder>"),
        validator=_NonEmptyValidator(f"Model name is required for {provider_id}."),
        validate_while_typing=False,
        bottom_toolbar=HTML(" <b>Enter</b> Launch Session   <b>Ctrl+C</b> Exit "),
        style=RELAY_PROMPT_STYLE,
    )
    return entered.strip()


def prompt_credentials_interactive(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    default_provider: str = "openrouter",
) -> Tuple[str, str, Optional[str]]:
    """Gather provider (dropdown), API key (input box), and model name (input box) interactively."""
    selected_provider = (
        provider.strip().lower()
        if provider
        else prompt_provider_selection(default=default_provider)
    )

    selected_key = api_key
    if selected_key is None:
        selected_key = prompt_api_key(selected_provider)

    selected_model = (
        model.strip()
        if model
        else prompt_model_selection(selected_provider)
    )

    return selected_provider, selected_model, selected_key
