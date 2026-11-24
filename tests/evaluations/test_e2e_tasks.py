"""End-to-end fixture tasks and evaluation benchmarks (Section 16.3 & 16.4)."""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from Relay.agent.loop import AgentLoop, ToolExecutionContext
from Relay.agent.runtime import AgentRuntime
from Relay.agent.state import AgentState
from Relay.app import create_app_context
from Relay.config.schemas import RootConfig
from Relay.context.builder import ContextBuilder
from Relay.context.tokenizer import TokenBudget
from Relay.providers.base import ModelEvent, ModelResponse, ToolCall
from Relay.security.permissions import PermissionAction, PermissionManager
from Relay.security.snapshots import SnapshotManager
from Relay.storage.database import Database
from Relay.storage.event_store import EventStore
from Relay.storage.session_store import SessionStore
from Relay.tools.base import ToolResult
from Relay.tools.registry import create_default_registry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.planner import PlanAndExecuteWorkflow
from Relay.workflows.repair import TestAndRepairWorkflow
from Relay.workflows.reviewer import CodeReviewWorkflow
from Relay.workflows.state import WorkflowState
from tests.evaluations.metrics import EvaluationMetrics


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    """Copies sample calculator repository into isolated temporary test directory."""
    sample_dir = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target_dir = tmp_path / "workspace"
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in sample_dir.iterdir():
        if item.is_file():
            shutil.copy(item, target_dir / item.name)
    return target_dir


# Task 1: Explain repository without modifying it (Section 16.3.1)
@pytest.mark.asyncio
async def test_e2e_explain_repository_without_modifications(repo_fixture: Path):
    app_ctx = create_app_context(workspace_root=repo_fixture)
    runtime = AgentRuntime(app_context=app_ctx)
    state = runtime.create_session(title="Explain repository", provider="groq", model="llama-3.3-70b-versatile")

    # Mock provider: lists files, reads calculator.py, outputs explanation
    mock_provider = MagicMock()
    mock_provider.stream = None

    async def mock_stream(request):
        yield ModelEvent(
            event_type="tool_call_delta",
            tool_call=ToolCall(id="c1", name="list_files", arguments='{"path": "."}'),
        )
        yield ModelEvent(event_type="text_delta", text_delta="This repository is a calculator library with basic math operations and unit tests.")

    mock_provider.stream = mock_stream
    app_ctx.config.agent.stream = True

    loop = AgentLoop(
        provider=mock_provider,
        tool_registry=runtime.tool_registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    events = []
    async for ev in loop.run_turn(state, "Explain what this repository does"):
        events.append(ev)

    # Verify no files were modified
    assert len(state.changed_files) == 0
    diff = runtime.get_diff()
    assert diff == ""


# Task 2: Find function and describe callers (Section 16.3.2)
@pytest.mark.asyncio
async def test_e2e_find_function_and_describe_callers(repo_fixture: Path):
    app_ctx = create_app_context(workspace_root=repo_fixture)
    runtime = AgentRuntime(app_context=app_ctx)
    state = runtime.create_session(title="Find divide", provider="groq", model="llama-3.3-70b-versatile")

    mock_provider = MagicMock()

    async def mock_stream(request):
        # Model requests code search for 'divide'
        yield ModelEvent(
            event_type="tool_call_delta",
            tool_call=ToolCall(id="c_search", name="search_code", arguments='{"query": "def divide"}'),
        )
        yield ModelEvent(event_type="text_delta", text_delta="The divide function is defined in calculator.py line 12 and tested in test_calc.py.")

    mock_provider.stream = mock_stream

    loop = AgentLoop(
        provider=mock_provider,
        tool_registry=runtime.tool_registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    async for _ in loop.run_turn(state, "Find where divide is defined and used"):
        pass

    assert len(state.messages) >= 2
    # Verify tool results in message history
    tool_msgs = [m for m in state.messages if m.role == "tool"]
    assert len(tool_msgs) >= 1
    assert "calculator.py" in tool_msgs[0].content


# Task 3: Add feature across multiple files (Section 16.3.3)
@pytest.mark.asyncio
async def test_e2e_add_feature_across_multiple_files(repo_fixture: Path):
    app_ctx = create_app_context(workspace_root=repo_fixture)
    perm_mgr = PermissionManager(mode="auto-edit", workspace_root=repo_fixture)
    runtime = AgentRuntime(app_context=app_ctx, permission_manager=perm_mgr)
    state = runtime.create_session(title="Add power function", provider="groq", model="llama-3.3-70b-versatile")

    calc_file = repo_fixture / "calculator.py"
    test_file = repo_fixture / "test_calc.py"

    call_index = 0
    mock_provider = MagicMock()

    async def mock_stream(request):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            # Edit calculator.py to add power()
            old = '    return a / b\n'
            new = '    return a / b\n\ndef power(a: float, b: float) -> float:\n    return a ** b\n'
            import json
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(
                    id="c_edit1",
                    name="edit_file",
                    arguments=json.dumps({"path": "calculator.py", "old_str": old, "new_str": new}),
                ),
            )
        else:
            yield ModelEvent(event_type="text_delta", text_delta="Added power function successfully.")

    mock_provider.stream = mock_stream

    loop = AgentLoop(
        provider=mock_provider,
        tool_registry=runtime.tool_registry,
        context_builder=runtime.context_builder,
        session_store=app_ctx.session_store,
        event_store=app_ctx.event_store,
        config=app_ctx.config,
        base_system_prompt=runtime.base_system_prompt,
    )

    async for _ in loop.run_turn(state, "Add power function to calculator.py"):
        pass

    assert "calculator.py" in state.changed_files
    assert "def power(" in calc_file.read_text(encoding="utf-8")


# Task 4: Fix failing test (Section 16.3.4)
@pytest.mark.asyncio
async def test_e2e_fix_failing_test(repo_fixture: Path):
    calc_file = repo_fixture / "calculator.py"
    # Seed a bug: add returns subtract
    calc_file.write_text(calc_file.read_text(encoding="utf-8").replace("return a + b", "return a - b"), encoding="utf-8")

    db = Database(repo_fixture / "repair.db")
    db.run_migrations()
    checkpointer = WorkflowCheckpointer(db=db)

    perm_mgr = PermissionManager(mode="auto-edit", workspace_root=repo_fixture)
    registry = create_default_registry(permission_manager=perm_mgr)

    mock_provider = MagicMock()
    # Mock fix: model uses edit_file to restore add
    import json
    old_bug = "def add(a: float, b: float) -> float:\n    return a - b"
    new_fix = "def add(a: float, b: float) -> float:\n    return a + b"
    fix_args = json.dumps({"path": "calculator.py", "old_str": old_bug, "new_str": new_fix})
    mock_provider.generate = AsyncMock(
        return_value=ModelResponse(
            content="Diagnosed test failure in test_add. Fixing implementation.",
            tool_calls=[ToolCall(id="c_fix", name="edit_file", arguments=fix_args)],
        )
    )

    workflow = TestAndRepairWorkflow(
        provider=mock_provider,
        tool_registry=registry,
        model="llama-3.3-70b-versatile",
        checkpointer=checkpointer,
    )

    state = WorkflowState(
        session_id="s_repair_test",
        workspace=str(repo_fixture),
        user_request="Fix failing tests in calculator",
        workflow_id="wf_repair",
        max_repair_count=2,
    )

    class MockContext:
        workspace_root = repo_fixture

    res = await workflow.run(state, MockContext())
    assert res.is_completed is True
    assert "calculator.py" in res.changed_files
    assert "return a + b" in calc_file.read_text(encoding="utf-8")


# Task 5: Reject unsafe path traversal (Section 16.3.7)
def test_e2e_reject_unsafe_path_traversal(repo_fixture: Path):
    perm_mgr = PermissionManager(mode="auto-edit", workspace_root=repo_fixture)
    registry = create_default_registry(permission_manager=perm_mgr)

    class MockContext:
        workspace_root = repo_fixture

    # Attempt path traversal read
    res = registry.execute("read_file", {"path": "../../windows/system32/cmd.exe"}, MockContext())
    assert res.success is False
    assert "permission_denied" in (res.error or "") or "Blocked" in res.content

    # Attempt path traversal write
    res_w = registry.execute("write_file", {"path": "../../../escape.txt", "content": "malicious"}, MockContext())
    assert res_w.success is False
    assert "permission_denied" in (res_w.error or "") or "Blocked" in res_w.content


# Task 6: Ask before destructive command (Section 16.3.8)
def test_e2e_ask_before_destructive_command(repo_fixture: Path):
    perm_mgr = PermissionManager(mode="ask", workspace_root=repo_fixture)
    action, reason = perm_mgr.evaluate_tool("run_command", "execute", {"command": "rm -rf /"})
    assert action in (PermissionAction.ASK, PermissionAction.DENY)


# Task 7: Recover from provider timeout (Section 16.3.9)
@pytest.mark.asyncio
async def test_e2e_recover_from_provider_timeout():
    from Relay.agent.retries import RetryPolicy
    from Relay.utils.errors import NetworkTimeoutError

    attempts = 0

    async def flaky_api_call():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise NetworkTimeoutError("Gateway timeout 504")
        return "Success on attempt 2"

    policy = RetryPolicy(max_retries=2, initial_delay=0.01, jitter=False)
    result = await policy.execute(flaky_api_call)

    assert attempts == 2
    assert result == "Success on attempt 2"


# Task 8: Resume interrupted workflow without duplicate changes (Section 16.3.10)
@pytest.mark.asyncio
async def test_e2e_resume_interrupted_workflow(repo_fixture: Path):
    db = Database(repo_fixture / "resume.db")
    db.run_migrations()
    checkpointer = WorkflowCheckpointer(db=db)

    # Initial interrupted state at step 1
    state = WorkflowState(
        session_id="sess_resume_e2e",
        workspace=str(repo_fixture),
        user_request="Multi-step refactoring",
        workflow_id="wf_interrupted",
        plan=["1. Inspect code", "2. Update calculator"],
        current_step=1,
        changed_files=["calculator.py"],
    )
    checkpointer.save_checkpoint("wf_interrupted", "sess_resume_e2e", "step_1", state)

    # Resume from checkpoint
    restored = checkpointer.load_checkpoint("wf_interrupted")
    assert restored is not None
    assert restored.current_step == 1
    assert restored.changed_files == ["calculator.py"]

    # Continue step 2
    restored.current_step = 2
    restored.is_completed = True
    checkpointer.save_checkpoint("wf_interrupted", "sess_resume_e2e", "completed", restored, status="completed")

    final_check = checkpointer.load_checkpoint("wf_interrupted")
    assert final_check.is_completed is True
    assert final_check.current_step == 2


# Task 9: Code review seeded defect (Section 16.3.11)
@pytest.mark.asyncio
async def test_e2e_code_review_seeded_defect(repo_fixture: Path):
    db = Database(repo_fixture / "cr.db")
    db.run_migrations()
    checkpointer = WorkflowCheckpointer(db=db)

    registry = create_default_registry()
    mock_provider = MagicMock()
    # Seed defect in review findings
    json_findings = """```json
    [
        {"severity": "CRITICAL", "file": "calculator.py", "line": 15, "title": "ZeroDivisionError", "description": "Unchecked zero divisor"}
    ]
    ```"""
    mock_provider.generate = AsyncMock(return_value=ModelResponse(content=json_findings))

    workflow = CodeReviewWorkflow(
        provider=mock_provider,
        tool_registry=registry,
        model="llama-3.3-70b-versatile",
        checkpointer=checkpointer,
    )

    state = WorkflowState(
        session_id="s_cr_defect",
        workspace=str(repo_fixture),
        user_request="Review changes",
        workflow_id="wf_cr_defect",
    )

    class MockContext:
        workspace_root = repo_fixture

    res = await workflow.run(state, MockContext())
    assert res.is_completed is True
    assert len(res.review_findings) == 1
    assert res.review_findings[0]["severity"] == "CRITICAL"
    assert "REQUEST_CHANGES" in res.final_summary


# Task 10: Metrics tracking and reporting (Section 16.4)
def test_e2e_metrics_tracking():
    metrics = EvaluationMetrics()

    metrics.record_task(completed=True, duration_ms=250, prompt_tokens=100, completion_tokens=50)
    metrics.record_task(completed=True, duration_ms=350, prompt_tokens=150, completion_tokens=70)
    metrics.record_tool_call(valid=True, correct=True)
    metrics.record_tool_call(valid=True, correct=True)
    metrics.record_safety_event(prevented_unsafe=True)
    metrics.record_recovery(succeeded=True)

    summary = metrics.summary()
    assert summary["tasks_attempted"] == 2
    assert summary["tasks_completed"] == 2
    assert summary["completion_rate_pct"] == 100.0
    assert summary["unsafe_actions_prevented"] == 1
    assert summary["total_tokens"] == 370
    assert summary["recovery_success_rate_pct"] == 100.0
