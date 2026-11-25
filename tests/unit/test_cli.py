from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from Relay.cli.app import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Relay version 0.1.0" in result.output


def test_cli_doctor(tmp_path):
    result = runner.invoke(app, ["doctor", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "System Diagnostics (Doctor)" in result.output
    assert "Python Version" in result.output


def test_cli_config_show(tmp_path):
    result = runner.invoke(app, ["config", "show", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "default_provider" in result.output
    assert "openrouter" in result.output


def test_cli_provider_list(tmp_path):
    result = runner.invoke(app, ["provider", "list", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "Configured Providers" in result.output
    assert "groq" in result.output


def test_cli_models_list(tmp_path):
    result = runner.invoke(app, ["models", "list", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "Available Default Models" in result.output
    assert "llama-3.3-70b-versatile" in result.output


def test_cli_models_use(tmp_path):
    result = runner.invoke(app, ["models", "use", "groq/llama-3.3-70b-versatile", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "Switched active provider to 'groq'" in result.output


def test_cli_provider_add_with_options(tmp_path):
    result = runner.invoke(
        app,
        ["provider", "add", "groq", "--model", "llama-3.1-8b-instant", "--api-key", "gsk-test-key"],
    )
    assert result.exit_code == 0
    assert "Provider 'groq' configured with model 'llama-3.1-8b-instant'" in result.output


def test_cli_ask_help():
    result = runner.invoke(app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "Execute an autonomous coding task" in result.output


def test_cli_plan_help():
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code == 0
    assert "Produce an inspection and execution plan" in result.output


def test_provider_dropdown_options_include_all_providers_without_demo_models():
    from Relay.cli.prompts import _get_provider_options

    options = _get_provider_options()
    provider_ids = [opt[0] for opt in options]
    for expected in ("openrouter", "groq", "anthropic", "openai", "gemini", "ollama"):
        assert expected in provider_ids

    labels_text = " ".join(opt[1] for opt in options)
    for demo_name in ("Llama 3.3", "Mixtral", "GPT-4o", "o3-mini", "Gemini 1.5", "Claude 3.5"):
        assert demo_name not in labels_text


def test_prompt_provider_selection_uses_dropdown():
    from Relay.cli.prompts import prompt_provider_selection

    with patch("Relay.cli.prompts.choice", return_value="openrouter") as mock_choice:
        selected = prompt_provider_selection(default="groq")

    assert selected == "openrouter"
    mock_choice.assert_called_once()
    kwargs = mock_choice.call_args.kwargs
    assert kwargs["show_frame"] is True
    option_ids = [opt[0] for opt in kwargs["options"]]
    assert "openrouter" in option_ids
    assert "ollama" in option_ids


def test_prompt_api_key_keeps_saved_or_accepts_new():
    from Relay.cli.prompts import prompt_api_key

    mock_session = MagicMock()
    mock_session.prompt.return_value = ""
    with patch("Relay.cli.prompts.PromptSession", return_value=mock_session), patch(
        "Relay.cli.prompts.SecretManager.get_credential", return_value="sk-existing"
    ):
        assert prompt_api_key("openai") == "sk-existing"
        assert mock_session.prompt.call_args.kwargs["is_password"] is True
        assert mock_session.prompt.call_args.kwargs["show_frame"] is True

    mock_session.prompt.return_value = "sk-new-key"
    with patch("Relay.cli.prompts.PromptSession", return_value=mock_session), patch(
        "Relay.cli.prompts.SecretManager.get_credential", return_value="sk-existing"
    ):
        assert prompt_api_key("openai") == "sk-new-key"

    mock_session.prompt.return_value = ""
    with patch("Relay.cli.prompts.PromptSession", return_value=mock_session):
        assert prompt_api_key("ollama") == ""


def test_prompt_model_selection_uses_empty_framed_input_no_demo_models():
    from Relay.cli.prompts import prompt_model_selection

    mock_session = MagicMock()
    mock_session.prompt.return_value = "custom-model-id"
    with patch("Relay.cli.prompts.PromptSession", return_value=mock_session):
        selected = prompt_model_selection("openrouter")

    assert selected == "custom-model-id"
    kwargs = mock_session.prompt.call_args.kwargs
    assert kwargs["show_frame"] is True
    assert kwargs["default"] == ""


def test_interactive_session_prompts_for_provider_key_and_model(tmp_path):
    from Relay.cli.commands import interactive_session

    mock_repl_session = MagicMock()
    mock_repl_session.prompt.side_effect = ["/quit"]

    with patch(
        "Relay.cli.commands.prompt_credentials_interactive",
        return_value=("openrouter", "my-custom-model", "sk-or-test"),
    ) as mock_creds, patch(
        "Relay.cli.commands.save_provider_credential"
    ) as mock_save, patch(
        "Relay.cli.commands.print_session_card"
    ) as mock_card, patch(
        "prompt_toolkit.PromptSession", return_value=mock_repl_session
    ):
        interactive_session(workspace=tmp_path)

    mock_creds.assert_called_once()
    mock_save.assert_called_once_with("openrouter", "sk-or-test")
    mock_card.assert_called_once()
    assert mock_card.call_args.kwargs["provider"] == "openrouter"
    assert mock_card.call_args.kwargs["model"] == "my-custom-model"


def test_dark_ui_banner_and_session_card_render():
    from Relay.cli.display import console, print_banner, print_session_card

    with console.capture() as cap:
        print_banner(animate=False)
        print_session_card("anthropic", "custom-model", "ask", "/tmp/ws", "abcdef1234567890")

    output = cap.get()
    assert "Local-First Autonomous Coding Agent" in output
    assert "Session Active" in output
    assert "anthropic" in output
    assert "custom-model" in output


def test_configure_logging_suppresses_httpx_info_by_default():
    import logging
    from Relay.utils.logging import configure_logging

    configure_logging(debug=False)
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpx2").level == logging.WARNING

    configure_logging(debug=True)
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx2").level == logging.DEBUG

    # Restore non-debug default
    configure_logging(debug=False)


def test_run_turn_stream_renders_markdown(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from Relay.agent.events import AgentEvent
    from Relay.cli.commands import _run_turn_stream
    from Relay.cli.display import console

    async def fake_run_turn(state, prompt):
        yield AgentEvent(session_id="s1", event_type="text_delta", text_delta="# Solution\n\n")
        yield AgentEvent(session_id="s1", event_type="text_delta", text_delta="- **Step 1**: Run `pytest`")

    runtime = SimpleNamespace(
        run_turn=fake_run_turn,
        summarize_changes=lambda s: {"changed_files": [], "tokens": {"total": 10, "prompt": 6, "completion": 4}},
    )
    state = SimpleNamespace(provider_name="groq", model_name="test-model", workspace_root=tmp_path)

    with console.capture() as cap:
        asyncio.run(_run_turn_stream(runtime, state, "Explain"))

    out = cap.get()
    assert "Solution" in out
    assert "Step 1" in out
    assert "# Solution" not in out


def test_interactive_session_slash_model_switch(tmp_path):
    from Relay.app import create_app_context
    from Relay.cli.commands import interactive_session

    mock_repl_session = MagicMock()
    # 1. Interactive /model switch, 2. Inline /model same provider, 3. /model <provider> <model>, 4. /quit
    mock_repl_session.prompt.side_effect = [
        "/model",
        "/model gemini-2.5-pro",
        "/model groq llama-3.3-70b-versatile",
        "/quit",
    ]

    with patch(
        "Relay.cli.commands.prompt_credentials_interactive",
        side_effect=[
            ("gemini", "gemini-2.5-flash", "AIza-initial"),
            ("gemini", "gemini-2.0-flash", "AIza-new"),
        ],
    ), patch("Relay.cli.commands.save_provider_credential") as mock_save, patch(
        "Relay.cli.commands.SecretManager.get_credential", return_value="gsk-existing"
    ), patch("Relay.cli.commands.print_session_card"), patch(
        "prompt_toolkit.PromptSession", return_value=mock_repl_session
    ):
        interactive_session(workspace=tmp_path)

    # Initial setup + /model switch saved credentials
    assert mock_save.call_count == 2
    mock_save.assert_any_call("gemini", "AIza-new")

    # Verify final switched provider & model were persisted in SQLite session store
    app_ctx = create_app_context(workspace_root=tmp_path)
    sessions = app_ctx.session_store.list_sessions(workspace=tmp_path)
    assert len(sessions) == 1
    assert sessions[0]["provider"] == "groq"
    assert sessions[0]["model"] == "llama-3.3-70b-versatile"
