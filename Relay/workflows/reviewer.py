"""Automated code review workflow for inspection of working tree diffs (Section 11.1 D)."""

import json
from typing import Any, Dict, List, Optional
from Relay.agent.messages import user_message
from Relay.providers.base import LLMProvider, ModelRequest
from Relay.tools.registry import ToolRegistry
from Relay.workflows.checkpoints import WorkflowCheckpointer
from Relay.workflows.state import WorkflowState


class CodeReviewWorkflow:
    """Performs rigorous code review over git diffs without modifying code."""

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
        """Inspect diff, detect issues, and generate structured review findings."""
        git_diff_tool = self.tool_registry.get_tool("git_diff")
        diff_content = ""
        if git_diff_tool:
            diff_res = git_diff_tool.run({}, context)
            diff_content = diff_res.content

        if not diff_content or "(no changes)" in diff_content:
            state.final_summary = "Code Review: Working tree clean. No changes to review."
            state.is_completed = True
            if self.checkpointer:
                self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "review", state, status="completed")
            return state

        review_prompt = (
            "You are a principal engineer conducting a code review on the following git diff.\n"
            "Examine for correctness, security, performance, and edge cases.\n"
            "Return a JSON list of findings, where each finding has:\n"
            '{"severity": "CRITICAL" | "WARNING" | "SUGGESTION", "file": "<path>", "line": <num or null>, "title": "<title>", "description": "<details>"}\n\n'
            f"Git Diff:\n```diff\n{diff_content[:15000]}\n```\n"
            "Reply strictly with the JSON list inside a ```json ``` block."
        )

        req = ModelRequest(
            model=self.model,
            messages=[user_message(review_prompt)],
            temperature=0.1,
        )

        res = await self.provider.generate(req)
        content = res.content or ""

        # Parse JSON findings
        findings: List[Dict[str, Any]] = []
        if "```json" in content:
            raw_json = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            raw_json = content.split("```")[1].split("```")[0].strip()
        else:
            raw_json = content.strip()

        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                findings = parsed
        except Exception:
            # Fallback text summary
            findings = [{"severity": "SUGGESTION", "file": "general", "title": "Summary", "description": content[:300]}]

        state.review_findings = findings
        state.is_completed = True

        critical_count = len([f for f in findings if f.get("severity") == "CRITICAL"])
        warning_count = len([f for f in findings if f.get("severity") == "WARNING"])
        state.final_summary = (
            f"Code Review Complete: {len(findings)} findings "
            f"({critical_count} critical, {warning_count} warnings). "
            f"Verdict: {'REQUEST_CHANGES' if critical_count > 0 else 'APPROVE'}."
        )

        if self.checkpointer:
            self.checkpointer.save_checkpoint(state.workflow_id, state.session_id, "review", state, status="completed")

        return state
