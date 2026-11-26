import os
from Relay.config.loader import load_config
from Relay.config.schemas import RootConfig


def test_default_config(tmp_path):
    empty_cfg = tmp_path / "empty.toml"
    empty_cfg.touch()
    cfg = load_config(config_path=empty_cfg)
    assert isinstance(cfg, RootConfig)
    assert cfg.default_provider in ("openrouter", "groq")
    assert "groq" in cfg.providers
    assert "openai" in cfg.providers
    assert "ollama" in cfg.providers
    assert cfg.providers["groq"].model == "llama-3.3-70b-versatile"
    assert cfg.agent.max_iterations == 30
    assert cfg.agent.max_context_tokens == 128000
    assert cfg.permission_mode == "ask"


def test_cli_overrides(tmp_path):
    empty_cfg = tmp_path / "empty.toml"
    empty_cfg.touch()
    cfg = load_config(config_path=empty_cfg, cli_provider="groq", cli_model="llama-3.1-8b-instant", cli_api_key="gsk-test")
    assert cfg.default_provider == "groq"
    assert cfg.default_model == "llama-3.1-8b-instant"
    assert cfg.providers["groq"].model == "llama-3.1-8b-instant"
    assert os.environ.get("GROQ_API_KEY") == "gsk-test"


def test_env_overrides(tmp_path, monkeypatch):
    empty_cfg = tmp_path / "empty.toml"
    empty_cfg.touch()
    monkeypatch.setenv("RELAY_DEFAULT_PROVIDER", "groq")
    monkeypatch.setenv("RELAY_DEFAULT_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("RELAY_PERMISSION_MODE", "plan")

    cfg = load_config(config_path=empty_cfg)
    assert cfg.default_provider == "groq"
    assert cfg.default_model == "llama-3.3-70b-versatile"
    assert cfg.permission_mode == "plan"


def test_workspace_config_override(tmp_path):
    empty_cfg = tmp_path / "empty.toml"
    empty_cfg.touch()
    relay_dir = tmp_path / ".relay"
    relay_dir.mkdir()
    cfg_file = relay_dir / "config.toml"
    cfg_file.write_text(
        """
        default_provider = "groq"
        default_model = "mixtral-8x7b-32768"
        permission_mode = "auto-edit"

        [agent]
        max_iterations = 50
        """,
        encoding="utf-8",
    )

    cfg = load_config(workspace_root=tmp_path, config_path=empty_cfg)
    assert cfg.default_provider == "groq"
    assert cfg.default_model == "mixtral-8x7b-32768"
    assert cfg.permission_mode == "auto-edit"
    assert cfg.agent.max_iterations == 50
