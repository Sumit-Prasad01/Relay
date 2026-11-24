"""Workflow graph factory and runner supporting all five Section 11 workflows."""

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from Relay.app import AppContext
from Relay.providers.base import LLMProvider
from Relay.providers.factory import create_provider
from Relay.security.permissions import PermissionManager
from Relay.tools.registry import ToolRegistry, create_default_registry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.planner import PlanAndExecuteWorkflow
from Relay.workflows.repair import TestAndRepairWorkflow
from Relay.workflows.reviewer import CodeReviewWorkflow
from Relay.workflows.state import WorkflowState
from Relay.workflows.subagents import (
    create_analyst_subagent,
    create_implementer_subagent,
    create_reviewer_subagent,
    create_test_subagent,
)

WorkflowType = Literal["plan_execute", "code_review", "test_repair", "parallel_specialist"]


class WorkflowRunner:
    """Factory and execution coordinator for advanced multi-step workflows."""

    def __init__(
        self,
        app_context: AppContext,
        provider: Optional[LLMProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        model: Optional[str] = None,
    ):
        self.app_context = app_context
        self.workspace_root = app_context.workspace_root
        self.config = app_context.config

        p_name = self.config.default_provider
        self.model = model or self.config.providers.get(p_name, self.config).model
        self.provider = provider or create_provider(p_name, self.config.providers.get(p_name))

        self.permission_manager = PermissionManager(
            mode=self.config.permission_mode,
            workspace_root=self.workspace_root,
        )
        self.tool_registry = tool_registry or create_default_registry(permission_manager=self.permission_manager)
        self.checkpointer = WorkflowCheckpointer(db=app_context.db)

    async def run(
        self,
        workflow_type: WorkflowType,
        user_request: str,
        session_id: Optional[str] = None,
    ) -> WorkflowState:
        """Run an explicit workflow graph."""
        sess_id = session_id or self.app_context.session_store.create_session(
            workspace=self.workspace_root,
            provider=self.config.default_provider,
            model=self.model,
            title=f"Workflow: {workflow_type}",
        )

        state = WorkflowState(
            session_id=sess_id,
            workspace=str(self.workspace_root),
            user_request=user_request,
            workflow_id=f"wf_{sess_id[:8]}_{workflow_type}",
        )

        # Execution context for tools
        from Relay.agent.loop import ToolExecutionContext
        from Relay.security.snapshots import SnapshotManager
        context = ToolExecutionContext(
            workspace_root=self.workspace_root,
            session_id=sess_id,
            session_store=self.app_context.session_store,
            snapshots=SnapshotManager(self.workspace_root),
        )

        if workflow_type == "plan_execute":
            workflow = PlanAndExecuteWorkflow(
                provider=self.provider,
                tool_registry=self.tool_registry,
                model=self.model,
                checkpointer=self.checkpointer,
            )
            return await workflow.run(state, context)

        elif workflow_type == "code_review":
            workflow = CodeReviewWorkflow(
                provider=self.provider,
                tool_registry=self.tool_registry,
                model=self.model,
                checkpointer=self.checkpointer,
            )
            return await workflow.run(state, context)

        elif workflow_type == "test_repair":
            workflow = TestAndRepairWorkflow(
                provider=self.provider,
                tool_registry=self.tool_registry,
                model=self.model,
                checkpointer=self.checkpointer,
            )
            return await workflow.run(state, context)

        elif workflow_type == "parallel_specialist":
            # 1. Analyst inspects repository
            analyst = create_analyst_subagent(self.provider, self.tool_registry, self.permission_manager)
            analyst_res = await analyst.execute(
                f"Analyze repository files relevant to: {user_request}",
                model=self.model,
                context=context,
            )

            # 2. Implementer applies changes
            implementer = create_implementer_subagent(self.provider, self.tool_registry, self.permission_manager)
            impl_prompt = (
                f"Task: {user_request}\n"
                f"Analysis findings: {analyst_res.summary}\n"
                "Implement the necessary changes with edit_file or write_file."
            )
            impl_res = await implementer.execute(impl_prompt, model=self.model, context=context)

            # 3. Test specialist tests
            tester = create_test_subagent(self.provider, self.tool_registry, self.permission_manager)
            test_res = await tester.execute("Run and verify project tests", model=self.model, context=context)

            # 4. Reviewer checks diff
            reviewer = create_reviewer_subagent(self.provider, self.tool_registry, self.permission_manager)
            rev_res = await reviewer.execute("Review current git diff", model=self.model, context=context)

            state.is_completed = True
            state.final_summary = (
                f"Parallel Specialist Pipeline Complete:\n"
                f"- Analyst: {analyst_res.summary[:150]}\n"
                f"- Implementation: {impl_res.summary[:150]}\n"
                f"- Tests: {test_res.summary[:150]}\n"
                f"- Review: {rev_res.summary[:150]}"
            )
            self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "specialists_complete", state, status="completed")
            return state

        else:
            state.add_error(f"Unknown workflow type: {workflow_type}")
            return state
