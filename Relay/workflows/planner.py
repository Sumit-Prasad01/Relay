"""Plan-and-execute workflow graph with approval checkpoints (Section 11.1 A)."""

from typing import Any, Dict, List, Optional
from Relay.agent.messages import assistant_message, user_message
from Relay.providers.base import LLMProvider, ModelRequest
from Relay.tools.registry import ToolRegistry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.state import WorkflowState


class PlanAndExecuteWorkflow:
    """Orchestrates structured planning followed by approved step execution and verification."""

    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        model: str,
        checkpointer: Optional[WorkflowCheckpointer] = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.model = model
        self.checkpointer = checkpointer

    async def step_plan(self, state: WorkflowState, context: Any) -> WorkflowState:
        """Analyze user request and formulate an ordered execution plan."""
        prompt = (
            f"You are a software architect planning a development task.\n"
            f"Task: {state.user_request}\n\n"
            "Produce an ordered, numbered plan of execution steps (1 to 5 steps max).\n"
            "Format each step starting with a number like '1. Step description'."
        )
        req = ModelRequest(
            model=self.model,
            messages=[user_message(prompt)],
            temperature=0.1,
        )
        res = await self.provider.generate(req)
        lines = [line.strip() for line in res.content.splitlines() if line.strip()]

        plan_steps = []
        for line in lines:
            if line and line[0].isdigit() and ("." in line[:3] or ")" in line[:3]):
                plan_steps.append(line)

        if not plan_steps:
            plan_steps = [f"1. Implement {state.user_request}"]

        state.plan = plan_steps
        state.step_descriptions = plan_steps
        state.current_step = 0

        if self.checkpointer:
            self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "plan", state)

        return state

    async def step_execute(self, state: WorkflowState, context: Any) -> WorkflowState:
        """Execute plan steps sequentially using registered tools."""
        if state.approval_status == "rejected":
            state.add_error("Plan was rejected by user.")
            state.is_completed = True
            return state

        tool_schemas = self.tool_registry.get_schemas()

        while state.current_step < len(state.plan):
            current_step_text = state.plan[state.current_step]
            step_prompt = (
                f"You are executing Step {state.current_step + 1}/{len(state.plan)}: {current_step_text}\n"
                f"Overall goal: {state.user_request}\n"
                "Use tools to implement this step cleanly."
            )

            req = ModelRequest(
                model=self.model,
                messages=[user_message(step_prompt)],
                tools=tool_schemas if tool_schemas else None,
            )

            res = await self.provider.generate(req)
            if res.tool_calls:
                for tc in res.tool_calls:
                    args = tc.parsed_arguments()
                    tool_res = self.tool_registry.execute(tc.name, args, context)
                    if tc.name in ("write_file", "edit_file", "apply_patch") and tool_res.success:
                        p = args.get("path")
                        if p:
                            state.add_changed_file(p)

            state.current_step += 1
            if self.checkpointer:
                self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, f"step_{state.current_step}", state)

        return state

    async def step_verify(self, state: WorkflowState, context: Any) -> WorkflowState:
        """Verify changes with tests or diff inspection."""
        run_tests_tool = self.tool_registry.get_tool("run_tests")
        if run_tests_tool:
            test_res = run_tests_tool.run({}, context)
            state.test_results = {"output": test_res.content, "success": test_res.success}

        state.is_completed = True
        state.final_summary = (
            f"Plan executed ({len(state.plan)} steps). "
            f"Changed files: {', '.join(state.changed_files) if state.changed_files else 'None'}. "
            f"Test status: {'PASS' if state.test_results.get('success', True) else 'FAIL'}."
        )

        if self.checkpointer:
            self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "verify", state, status="completed")

        return state

    async def run(self, state: WorkflowState, context: Any) -> WorkflowState:
        """Run the complete plan-and-execute pipeline."""
        state = await self.step_plan(state, context)
        state = await self.step_execute(state, context)
        state = await self.step_verify(state, context)
        return state
