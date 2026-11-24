"""Specialist subagents with bounded scopes and non-escalating permissions (Section 11.4)."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Relay.agent.messages import assistant_message, tool_result_message, user_message
from Relay.providers.base import LLMProvider, ModelMessage, ModelRequest, ToolCall
from Relay.security.permissions import PermissionManager
from Relay.tools.registry import ToolRegistry


@dataclass
class SubagentResult:
    """Structured output returned by a subagent upon task completion."""

    subagent_name: str
    role: str
    summary: str
    tool_calls_count: int
    findings: List[str]
    success: bool = True
    error: Optional[str] = None


class SpecialistSubagent:
    """A bounded subagent operating on an explicit tool subset with restricted permissions."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        allowed_tools: List[str],
        provider: LLMProvider,
        base_registry: ToolRegistry,
        permission_manager: Optional[PermissionManager] = None,
        max_iterations: int = 6,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.allowed_tools = set(allowed_tools)
        self.provider = provider
        self.permission_manager = permission_manager
        self.max_iterations = max_iterations

        # Build scoped registry restricted to allowed_tools
        self.scoped_registry = ToolRegistry(permission_manager=permission_manager)
        for t in base_registry.list_tools():
            if t.name in self.allowed_tools:
                self.scoped_registry.register(t)

    async def execute(self, task: str, model: str, context: Any) -> SubagentResult:
        """Run bounded task execution."""
        messages: List[ModelMessage] = [
            ModelMessage(role="system", content=self.system_prompt),
            user_message(task),
        ]
        tool_schemas = self.scoped_registry.get_schemas()
        total_tool_calls = 0
        findings: List[str] = []

        for _ in range(self.max_iterations):
            req = ModelRequest(
                model=model,
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=0.1,
            )

            try:
                res = await self.provider.generate(req)
            except Exception as e:
                return SubagentResult(
                    subagent_name=self.name,
                    role=self.role,
                    summary=f"Failed during execution: {e}",
                    tool_calls_count=total_tool_calls,
                    findings=findings,
                    success=False,
                    error=str(e),
                )

            messages.append(assistant_message(content=res.content, tool_calls=res.tool_calls))

            if not res.tool_calls:
                # Finished
                return SubagentResult(
                    subagent_name=self.name,
                    role=self.role,
                    summary=res.content or "Completed analysis.",
                    tool_calls_count=total_tool_calls,
                    findings=findings,
                    success=True,
                )

            # Execute allowed tools
            for tc in res.tool_calls:
                total_tool_calls += 1
                args = tc.parsed_arguments()
                tool_res = self.scoped_registry.execute(
                    name=tc.name,
                    arguments=args,
                    context=context,
                )
                if tool_res.content and len(tool_res.content) < 500:
                    findings.append(f"{tc.name}: {tool_res.content.strip()[:100]}")
                messages.append(tool_result_message(tc.id, tool_res))

        return SubagentResult(
            subagent_name=self.name,
            role=self.role,
            summary="Subagent reached iteration budget limit.",
            tool_calls_count=total_tool_calls,
            findings=findings,
            success=True,
        )


def create_analyst_subagent(provider: LLMProvider, registry: ToolRegistry, permissions: Optional[PermissionManager] = None) -> SpecialistSubagent:
    """Read-only repository analyst subagent."""
    return SpecialistSubagent(
        name="repository_analyst",
        role="Repository Analyst",
        system_prompt="You are a read-only repository analysis specialist. Inspect code, locate relevant symbols, and report concise findings.",
        allowed_tools=["list_files", "read_file", "search_code", "diagnose_project", "get_environment"],
        provider=provider,
        base_registry=registry,
        permission_manager=permissions,
    )


def create_test_subagent(provider: LLMProvider, registry: ToolRegistry, permissions: Optional[PermissionManager] = None) -> SpecialistSubagent:
    """Test verification specialist subagent."""
    return SpecialistSubagent(
        name="test_specialist",
        role="Test Specialist",
        system_prompt="You are a test verification specialist. Run and diagnose project tests. Report exact failure messages and causes.",
        allowed_tools=["run_tests", "run_command", "read_file"],
        provider=provider,
        base_registry=registry,
        permission_manager=permissions,
    )


def create_reviewer_subagent(provider: LLMProvider, registry: ToolRegistry, permissions: Optional[PermissionManager] = None) -> SpecialistSubagent:
    """Code reviewer subagent."""
    return SpecialistSubagent(
        name="code_reviewer",
        role="Reviewer",
        system_prompt="You are a strict code review specialist. Inspect diffs and code for bugs, style deviations, security risks, and test coverage.",
        allowed_tools=["git_diff", "git_status", "read_file"],
        provider=provider,
        base_registry=registry,
        permission_manager=permissions,
    )


def create_implementer_subagent(provider: LLMProvider, registry: ToolRegistry, permissions: Optional[PermissionManager] = None) -> SpecialistSubagent:
    """Implementation specialist subagent."""
    return SpecialistSubagent(
        name="implementation_specialist",
        role="Implementation Specialist",
        system_prompt="You are an implementation specialist. Apply targeted, precise code edits and patches.",
        allowed_tools=["edit_file", "write_file", "apply_patch", "read_file"],
        provider=provider,
        base_registry=registry,
        permission_manager=permissions,
    )
