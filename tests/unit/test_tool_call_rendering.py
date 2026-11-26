"""Tests for readable tool-call previews, argument validation, and turn streaming UI."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from Relay.agent.loop import AgentLoop
from Relay.app import create_app_context
from Relay.cli.commands import _run_turn_stream
from Relay.cli.display import (
    _detect_language,
    console,
    render_tool_call,
    render_tool_denied,
    render_tool_error,
    render_tool_result,
    render_write_file_preview,
)
from Relay.providers.base import ModelEvent, ToolCall
from Relay.security.permissions import PermissionManager
from Relay.tools.base import ToolResult


def test_language_detection_for_extensions():
    assert _detect_language("add_numbers.py") == "python"
    assert _detect_language("config.json") == "json"
    assert _detect_language("app.tsx") == "tsx"
    assert _detect_language("README.md") == "markdown"
    assert _detect_language("script.ps1") == "powershell"
    assert _detect_language("unknown.customext") == "text"


def test_write_file_preview_preserves_newlines_quotes_and_truncation():
    code = (
        '"""Module docstring."""\n\n'
        'def greet(name: str) -> str:\n'
        '    path = "C:\\\\temp\\\\test"\n'
        '    return f"Hello, {name}!"\n'
    )
    with console.capture() as cap:
        render_write_file_preview("sample.py", code, target_console=console)
    output = cap.get()

    assert "WRITE FILE" in output
    assert "sample.py" in output
    assert 'def greet(name: str) -> str:' in output
    assert r'C:\\temp\\test' in output
    assert "\\n" not in output  # Actual newlines rendered, not escaped sequences

    # Empty content renders cleanly
    with console.capture() as cap_empty:
        render_write_file_preview("empty.txt", "", target_console=console)
    assert "(empty file)" in cap_empty.get()

    # Large content truncates preview only
    long_content = "\n".join(f"line_{i} = {i}" for i in range(100))
    with console.capture() as cap_trunc:
        render_write_file_preview("big.py", long_content, max_lines=10, target_console=console)
    trunc_out = cap_trunc.get()
    assert "Preview truncated" in trunc_out
    assert "line_0 = 0" in trunc_out
    assert "line_99 = 99" not in trunc_out


def test_untrusted_rich_markup_is_escaped():
    tc = ToolCall(
        id="c1",
        name="custom_tool",
        arguments=json.dumps({"note": "[red]danger[/red] [bold]fake[/bold]", "path": "[blue]x.py"}),
    )
    with console.capture() as cap:
        ok = render_tool_call(tc, target_console=console)
    assert ok is True
    out = cap.get()
    assert "[red]danger[/red]" in out
    assert "[blue]x.py" in out


def test_strict_parsing_rejects_malformed_and_invalid_write_file():
    bad_json = ToolCall(id="c_bad", name="write_file", arguments="{not valid json")
    with pytest.raises(ValueError, match="Malformed JSON"):
        bad_json.parse_arguments_strict()

    with console.capture() as cap:
        assert render_tool_call(bad_json, target_console=console) is False
    assert "write_file failed" in cap.get()

    non_dict = ToolCall(id="c_arr", name="write_file", arguments='["a", "b"]')
    with console.capture() as cap_arr:
        assert render_tool_call(non_dict, target_console=console) is False
    assert "JSON object" in cap_arr.get()

    missing_content = ToolCall(id="c_miss", name="write_file", arguments='{"path": "a.py", "content": 123}')
    with console.capture() as cap_miss:
        assert render_tool_call(missing_content, target_console=console) is False
    assert "Invalid write_file arguments" in cap_miss.get()


def test_renderers_for_edit_patch_command_and_distinct_states():
    edit_tc = ToolCall(
        id="c_edit",
        name="edit_file",
        arguments=json.dumps({"path": "calc.py", "old_str": "return a - b", "new_str": "return a + b"}),
    )
    cmd_tc = ToolCall(
        id="c_cmd",
        name="run_command",
        arguments=json.dumps({"command": "pytest -q", "timeout": 30}),
    )

    with console.capture() as cap:
        assert render_tool_call(edit_tc, target_console=console) is True
        assert render_tool_call(cmd_tc, target_console=console) is True
        render_tool_result("write_file", ToolResult(content="Successfully wrote 42 characters to a.py.", duration_ms=5), target_console=console)
        render_tool_denied("write_file", is_policy=False, target_console=console)
        render_tool_denied("write_file", reason="Outside workspace", is_policy=True, target_console=console)
        render_tool_denied("write_file", reason="Use pathlib instead", is_instruct=True, target_console=console)
        render_tool_error("write_file", "Disk full", target_console=console)

    out = cap.get()
    assert "EDIT FILE" in out
    assert "-return a - b" in out
    assert "+return a + b" in out
    assert "RUN COMMAND" in out
    assert "pytest -q" in out
    assert "✔ Successfully wrote 42 characters to a.py." in out
    assert "⊘ write_file cancelled by user" in out
    assert "✖ write_file blocked by policy" in out
    assert "↪ write_file redirected:" in out
    assert "✖ write_file failed" in out


@pytest.mark.asyncio
async def test_runtime_stream_renders_preview_and_passes_unmodified_args(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    perm_mgr = PermissionManager(mode="auto-edit", workspace_root=tmp_path)
    from Relay.agent.runtime import AgentRuntime

    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_mgr)
    state = runtime.create_session(provider="groq", model="test-model")

    original_content = 'def add(a, b):\n    return a + b\n'
    raw_args = json.dumps({"path": "add.py", "content": original_content})

    call_idx = 0

    async def fake_stream(request):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(id="call_w1", name="write_file", arguments=raw_args),
            )
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Created `add.py`.")

    mock_provider = MagicMock()
    mock_provider.stream = fake_stream

    loop = AgentLoop(
        provider=mock_provider,
        tool_registry=runtime.tool_registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    stream_runtime = SimpleNamespace(
        run_turn=lambda s, p: loop.run_turn(s, p),
        summarize_changes=runtime.summarize_changes,
    )

    with console.capture() as cap:
        await _run_turn_stream(stream_runtime, state, "Create add.py")

    out = cap.get()
    assert "WRITE FILE" in out
    assert "def add(a, b):" in out
    assert "✔ Successfully wrote" in out
    # Original content written verbatim to disk without mutation
    assert (tmp_path / "add.py").read_text(encoding="utf-8") == original_content


@pytest.mark.asyncio
async def test_agent_loop_handles_malformed_tool_json_without_executing(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    perm_mgr = PermissionManager(mode="auto-edit", workspace_root=tmp_path)
    from Relay.agent.runtime import AgentRuntime

    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_mgr)
    state = runtime.create_session(provider="groq", model="test-model")

    call_idx = 0

    async def fake_stream(request):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(id="bad_1", name="write_file", arguments='{"path": "oops.py", "content": '),
            )
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Corrected myself.")

    mock_provider = MagicMock()
    mock_provider.stream = fake_stream

    loop = AgentLoop(
        provider=mock_provider,
        tool_registry=runtime.tool_registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    events = [ev async for ev in loop.run_turn(state, "Write oops.py")]
    failed_events = [e for e in events if e.event_type == "tool_call_failed"]
    assert len(failed_events) == 1
    assert failed_events[0].tool_result.error == "invalid_arguments"
    assert not (tmp_path / "oops.py").exists()
