"""Debug-and-repair and test-and-repair workflows (Section 11.1 C & E)."""

from typing import Any, Dict, List, Optional
from Relay.agent.messages import user_message
from Relay.providers.base import LLMProvider, ModelRequest
from Relay.tools.registry import ToolRegistry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.state import WorkflowState


class TestAndRepairWorkflow:
    """Discovers tests, runs them, diagnoses failures, applies bounded fixes, and verifies."""

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

    async def run(self, state: WorkflowState, context: Any) -> WorkflowState:
        """Run tests, iteratively repair failures up to max_repair_count, and report status."""
        run_tests_tool = self.tool_registry.get_tool("run_tests")
        if not run_tests_tool:
            state.add_error("run_tests tool not registered in registry.")
            state.is_completed = True
            return state

        while state.repair_count < state.max_repair_count:
            # 1. Run tests
            test_res = run_tests_tool.run({}, context)
            state.test_results = {"output": test_res.content, "success": test_res.success}

            if test_res.success:
                state.is_completed = True
                state.final_summary = (
                    f"All tests passing! Verified after {state.repair_count} repairs. "
                    f"Changed files: {', '.join(state.changed_files) if state.changed_files else 'None'}."
                )
                if self.checkpointer:
                    self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "test_pass", state, status="completed")
                return state

            # 2. Diagnose failure and generate repair
            state.repair_count += 1
            repair_prompt = (
                f"Project tests failed (attempt {state.repair_count}/{state.max_repair_count}).\n"
                f"Test failure output:\n```\n{test_res.content[:8000]}\n```\n\n"
                f"Diagnose the cause of failure and use edit_file or write_file to apply the minimal fix."
            )

            tool_schemas = self.tool_registry.get_schemas()
            req = ModelRequest(
                model=self.model,
                messages=[user_message(repair_prompt)],
                tools=tool_schemas if tool_schemas else None,
                temperature=0.1,
            )

            res = await self.provider.generate(req)
            if res.tool_calls:
                for tc in res.tool_calls:
                    args = tc.parsed_arguments()
                    t_res = self.tool_registry.execute(tc.name, args, context)
                    if tc.name in ("write_file", "edit_file", "apply_patch") and t_res.success:
                        p = args.get("path")
                        if p:
                            state.add_changed_file(p)

            if self.checkpointer:
                self.checkpointer.save_checkpoint(
                    state.workflow_id,
                    state.session_id,
                    f"repair_attempt_{state.repair_count}",
                    state,
                )

        # Re-run after max attempts
        final_test = run_tests_tool.run({}, context)
        state.test_results = {"output": final_test.content, "success": final_test.success}
        state.is_completed = True
        state.final_summary = (
            f"Test and repair finished: {'SUCCESS' if final_test.success else 'UNRESOLVED'}. "
            f"Attempted {state.repair_count} repairs. "
            f"Changed files: {', '.join(state.changed_files) if state.changed_files else 'None'}."
        )

        if self.checkpointer:
            self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "repair_finished", state, status="completed")

        return state
