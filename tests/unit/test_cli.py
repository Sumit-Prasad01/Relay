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
