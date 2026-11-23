from pathlib import Path
import pytest
from Relay.context.builder import ContextBuilder
from Relay.context.tokenizer import TokenBudget
from Relay.providers.base import ModelMessage


def test_build_system_prompt(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Always write docstrings.", encoding="utf-8")
    builder = ContextBuilder(tmp_path)

    prompt = builder.build_system_prompt("You are a helpful coding agent.")
    assert "You are a helpful coding agent." in prompt
    assert "<project-instructions path=\"AGENTS.md\">" in prompt
    assert "Always write docstrings." in prompt
    assert "<environment>" in prompt


def test_fit_messages_within_budget(tmp_path):
    builder = ContextBuilder(tmp_path, budget=TokenBudget(max_context_tokens=1000))
    messages = [
        ModelMessage(role="user", content="Oldest message " + "a" * 500),
        ModelMessage(role="assistant", content="Medium message " + "b" * 500),
        ModelMessage(role="user", content="Recent message " + "c" * 20),
    ]

    fit = builder.fit_messages("System", messages, max_prompt_tokens=200)
    assert fit[0].role == "system"
    # Should drop older messages to strictly fit within budget
    assert len(fit) < len(messages) + 1
    assert "Recent message" in fit[-1].content
