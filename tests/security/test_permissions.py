import pytest
from Relay.security.permissions import PermissionAction, PermissionManager


def test_plan_mode_blocks_mutations(tmp_path):
    mgr = PermissionManager(tmp_path, mode="plan")

    # Read allowed
    act, _ = mgr.evaluate_tool("read_file", "read", {"path": "main.py"})
    assert act == PermissionAction.ALLOW

    # Write denied
    act, reason = mgr.evaluate_tool("write_file", "write", {"path": "main.py", "content": "..."})
    assert act == PermissionAction.DENY
    assert "plan" in reason

    # Execution denied
    act, reason = mgr.evaluate_tool("run_command", "execute", {"command": "ls"})
    assert act == PermissionAction.DENY


def test_path_traversal_blocked(tmp_path):
    mgr = PermissionManager(tmp_path, mode="auto-edit")

    # Path escaping workspace root
    escaped_path = "../../etc/passwd"
    act, reason = mgr.evaluate_tool("read_file", "read", {"path": escaped_path})
    assert act == PermissionAction.DENY
    assert "traversal blocked" in reason.lower()


def test_modes_evaluation(tmp_path):
    # Ask mode: prompts for writes and commands
    ask_mgr = PermissionManager(tmp_path, mode="ask")
    act, _ = ask_mgr.evaluate_tool("write_file", "write", {"path": "test.txt"})
    assert act == PermissionAction.ASK

    # Auto-edit mode: allows writes inside workspace
    edit_mgr = PermissionManager(tmp_path, mode="auto-edit")
    act, _ = edit_mgr.evaluate_tool("write_file", "write", {"path": "test.txt"})
    assert act == PermissionAction.ALLOW

    # Full-auto mode: still blocks privileged sudo
    full_mgr = PermissionManager(tmp_path, mode="full-auto")
    act, reason = full_mgr.evaluate_tool("run_command", "execute", {"command": "sudo rm -rf /"})
    assert act == PermissionAction.DENY


def test_approval_handler_dropdown_decisions(tmp_path):
    from unittest.mock import patch
    from Relay.security.approval import ApprovalHandler, ApprovalResult
    from Relay.tools.registry import create_default_registry

    class Ctx:
        def __init__(self, ws):
            self.workspace_root = ws

    perm_mgr = PermissionManager(tmp_path, mode="ask")
    registry = create_default_registry(permission_manager=perm_mgr)
    ctx = Ctx(tmp_path)

    # 1. User selects Don't Allow -> blocks execution
    with patch.object(ApprovalHandler, "request_approval", return_value=ApprovalResult(approved=False, action="deny")):
        res = registry.execute("write_file", {"path": "blocked.py", "content": "x = 1"}, ctx)
        assert res.success is False
        assert res.error == "user_denied"
        assert not (tmp_path / "blocked.py").exists()

    # 2. User selects "Tell agent explicitly" -> rejects current tool call and attaches instruction
    with patch.object(
        ApprovalHandler,
        "request_approval",
        return_value=ApprovalResult(approved=False, action="instruct", instruction="Use async def instead"),
    ):
        res_inst = registry.execute("write_file", {"path": "guided.py", "content": "def f(): pass"}, ctx)
        assert res_inst.success is False
        assert res_inst.error == "user_instructed"
        assert "Use async def instead" in res_inst.content
        assert not (tmp_path / "guided.py").exists()

    # 3. User selects Allow -> executes normally with exact original payload
    with patch.object(ApprovalHandler, "request_approval", return_value=ApprovalResult(approved=True, action="allow")):
        res_ok = registry.execute("write_file", {"path": "allowed.py", "content": "x = 42"}, ctx)
        assert res_ok.success is True
        assert (tmp_path / "allowed.py").read_text(encoding="utf-8") == "x = 42"


@pytest.mark.asyncio
async def test_tell_agent_explicitly_continues_chat_with_instruction(tmp_path):
    import json
    from unittest.mock import MagicMock, patch
    from Relay.agent.loop import AgentLoop
    from Relay.app import create_app_context
    from Relay.providers.base import ModelEvent, ToolCall
    from Relay.security.approval import ApprovalHandler, ApprovalResult

    app_ctx = create_app_context(workspace_root=tmp_path)
    perm_mgr = PermissionManager(mode="ask", workspace_root=tmp_path)
    from Relay.agent.runtime import AgentRuntime

    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_mgr)
    state = runtime.create_session(provider="groq", model="test-model")

    seen_messages = []
    call_idx = 0

    async def fake_stream(request):
        nonlocal call_idx
        call_idx += 1
        seen_messages.append(list(request.messages))
        if call_idx == 1:
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(
                    id="c1",
                    name="write_file",
                    arguments=json.dumps({"path": "calc.py", "content": "def add(a, b): return a + b"}),
                ),
            )
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Understood, updating approach as instructed.")

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

    with patch.object(
        ApprovalHandler,
        "request_approval",
        return_value=ApprovalResult(approved=False, action="instruct", instruction="Put it in math_utils.py instead"),
    ):
        events = [ev async for ev in loop.run_turn(state, "Create add function")]

    assert any(e.event_type == "tool_call_failed" and e.tool_result.error == "user_instructed" for e in events)
    assert any(e.event_type == "turn_completed" for e in events)
    # Second LLM call receives the user's explicit guidance in tool output
    assert len(seen_messages) == 2
    assert any("Put it in math_utils.py instead" in m.content for m in seen_messages[1] if m.role == "tool")
