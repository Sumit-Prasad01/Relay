import pytest
from Relay.context.compaction import ContextCompactor
from Relay.providers.base import ModelMessage


def test_needs_compaction():
    short_messages = [
        ModelMessage(role="system", content="System"),
        ModelMessage(role="user", content="Hello"),
    ]
    assert ContextCompactor.needs_compaction(short_messages, max_tokens=1000) is False

    long_messages = [
        ModelMessage(role="user", content="A" * 4000),
    ]
    assert ContextCompactor.needs_compaction(long_messages, max_tokens=1000) is True


def test_compact_preserves_boundaries():
    messages = [
        ModelMessage(role="system", content="System prompt"),
        ModelMessage(role="user", content="First user request: add feature X"),
        ModelMessage(role="assistant", content="I will add feature X"),
        ModelMessage(role="tool", content="Wrote file.py", tool_call_id="call_1"),
        ModelMessage(role="user", content="Now please test feature X"),
        ModelMessage(role="assistant", content="Running tests"),
    ]

    compacted = ContextCompactor.compact(messages, cut_index=3)
    assert len(compacted) < len(messages)
    assert compacted[0].role == "system"
    assert compacted[1].role == "user"
    assert "<summary>" in compacted[1].content
    assert "## Goal" in compacted[1].content
    assert "First user request: add feature X" in compacted[1].content
    assert compacted[-1].content == "Running tests"
