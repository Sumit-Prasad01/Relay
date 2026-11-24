"""Tests for LangGraph advanced workflows, checkpoints, and specialist subagents (Section 11)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from Relay.app import create_app_context
from Relay.providers.base import ModelResponse, ToolCall
from Relay.storage.database import Database
from Relay.tools.base import BaseTool, ToolResult
from Relay.tools.registry import ToolRegistry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.graph_factory import WorkflowRunner
from Relay.workflows.planner import PlanAndExecuteWorkflow
from Relay.workflows.reviewer import CodeReviewWorkflow
from Relay.workflows.state import WorkflowState
from Relay.workflows.subagents import create_analyst_subagent


class MockEchoTool(BaseTool):
    name = "mock_echo"
    description = "Mock tool"
    category = "read"
    parameters = {"type": "object", "properties": {"msg": {"type": "string"}}}

    def run(self, arguments, context):
        return ToolResult(content=f"Echo: {arguments.get('msg')}", success=True)


class MockGitDiffTool(BaseTool):
    name = "git_diff"
    description = "Mock diff"
    category = "read"
    parameters = {"type": "object"}

    def run(self, arguments, context):
        return ToolResult(
            content="""diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,3 @@\n+print("secret = 123")\n""",
            success=True,
        )


def test_workflow_state_and_sqlite_checkpointer(tmp_path: Path):
    db_path = tmp_path / "wf_test.db"
    db = Database(db_path)
    db.run_migrations()

    checkpointer = WorkflowCheckpointer(db=db)
    state = WorkflowState(
        session_id="sess_abc",
        workspace=str(tmp_path),
        user_request="Refactor authentication",
        workflow_id="wf_123",
        plan=["1. Read files", "2. Edit auth.py"],
        changed_files=["auth.py"],
    )

    run_id = checkpointer.save_checkpoint("wf_123", "sess_abc", "plan_step", state)
    assert run_id == "wf_123"

    restored = checkpointer.load_checkpoint("wf_123")
    assert restored is not None
    assert restored.session_id == "sess_abc"
    assert restored.plan == ["1. Read files", "2. Edit auth.py"]
    assert restored.changed_files == ["auth.py"]

    runs = checkpointer.list_workflow_runs("sess_abc")
    assert len(runs) == 1
    assert runs[0]["id"] == "wf_123"


@pytest.mark.asyncio
async def test_plan_and_execute_workflow(tmp_path: Path):
    db_path = tmp_path / "planner.db"
    db = Database(db_path)
    db.run_migrations()
    checkpointer = WorkflowCheckpointer(db=db)

    registry = ToolRegistry()
    registry.register(MockEchoTool())

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock()

    # Call 1: Plan generation
    # Call 2: Step 1 execution
    # Call 3: Step 2 execution
    mock_provider.generate.side_effect = [
        ModelResponse(content="1. Inspect files\n2. Run echo"),
        ModelResponse(
            content="Running tool 1",
            tool_calls=[ToolCall(id="c1", name="mock_echo", arguments='{"msg": "step 1"}')],
        ),
        ModelResponse(
            content="Running tool 2",
            tool_calls=[ToolCall(id="c2", name="mock_echo", arguments='{"msg": "step 2"}')],
        ),
    ]

    workflow = PlanAndExecuteWorkflow(
        provider=mock_provider,
        tool_registry=registry,
        model="mock_model",
        checkpointer=checkpointer,
    )

    state = WorkflowState(
        session_id="s_plan",
        workspace=str(tmp_path),
        user_request="Test plan execution",
        workflow_id="wf_plan",
    )

    class MockContext:
        workspace_root = tmp_path

    res = await workflow.run(state, MockContext())
    assert res.is_completed is True
    assert len(res.plan) == 2
    assert "Plan executed" in res.final_summary


@pytest.mark.asyncio
async def test_code_review_workflow(tmp_path: Path):
    db_path = tmp_path / "review.db"
    db = Database(db_path)
    db.run_migrations()
    checkpointer = WorkflowCheckpointer(db=db)

    registry = ToolRegistry()
    registry.register(MockGitDiffTool())

    mock_provider = MagicMock()
    json_findings = """```json
    [
        {"severity": "CRITICAL", "file": "app.py", "line": 2, "title": "Hardcoded secret", "description": "Found secret in diff"}
    ]
    ```"""
    mock_provider.generate = AsyncMock(return_value=ModelResponse(content=json_findings))

    workflow = CodeReviewWorkflow(
        provider=mock_provider,
        tool_registry=registry,
        model="mock_model",
        checkpointer=checkpointer,
    )

    state = WorkflowState(
        session_id="s_rev",
        workspace=str(tmp_path),
        user_request="Review changes",
        workflow_id="wf_rev",
    )

    class MockContext:
        workspace_root = tmp_path

    res = await workflow.run(state, MockContext())
    assert res.is_completed is True
    assert len(res.review_findings) == 1
    assert res.review_findings[0]["severity"] == "CRITICAL"
    assert "REQUEST_CHANGES" in res.final_summary


@pytest.mark.asyncio
async def test_subagent_tool_bounding(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(MockEchoTool())

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(return_value=ModelResponse(content="Analysis complete"))

    analyst = create_analyst_subagent(mock_provider, registry)
    # Analyst only has read tools, not write tools
    assert "write_file" not in analyst.allowed_tools
    assert "read_file" in analyst.allowed_tools

    res = await analyst.execute("Inspect", model="mock_model", context=None)
    assert res.success is True
    assert res.role == "Repository Analyst"
