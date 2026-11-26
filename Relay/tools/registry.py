"""Tool registry and dispatcher with permission gates and audit logging (Section 7.5 & 8)."""

import time
from typing import Any, Dict, List, Optional

from Relay.providers.base import ToolDefinition
from Relay.security.approval import ApprovalHandler
from Relay.security.permissions import PermissionAction, PermissionManager
from Relay.tools.base import BaseTool, ToolResult
from Relay.utils.logging import redact_secrets


class ToolRegistry:
    """Manages tool registration, schema export, and execution with security controls."""

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self._tools: Dict[str, BaseTool] = {}
        self.permission_manager = permission_manager

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def get_schemas(self) -> List[ToolDefinition]:
        """Convert registered tools to provider ToolDefinitions."""
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: Dict[str, Any], context: Any) -> ToolResult:
        """Execute a tool call passing through permission policy and validation."""
        start_time = time.time()
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                content=f"Error: Unknown tool '{name}'. Available: {', '.join(self._tools.keys())}",
                success=False,
                error="tool_not_found",
            )

        # 1. Permission evaluation
        if self.permission_manager:
            action, reason = self.permission_manager.evaluate_tool(
                tool_name=name,
                category=tool.category,
                arguments=arguments,
            )
            if action == PermissionAction.DENY:
                return ToolResult(
                    content=f"Blocked by policy: {reason}",
                    success=False,
                    error="permission_denied",
                )
            if action == PermissionAction.ASK:
                target = arguments.get("command") or arguments.get("path")
                decision = ApprovalHandler.request_approval(reason or f"Approve {name}", target)
                if isinstance(decision, bool):
                    approved = decision
                    decision_action = "allow" if approved else "deny"
                    instruction = None
                else:
                    approved = decision.approved
                    decision_action = decision.action
                    instruction = decision.instruction

                if not approved:
                    if decision_action == "instruct" and instruction:
                        return ToolResult(
                            content=(
                                f"User declined '{name}' and gave explicit instructions to follow instead: "
                                f"{instruction}"
                            ),
                            success=False,
                            error="user_instructed",
                        )
                    return ToolResult(
                        content="User rejected this tool execution.",
                        success=False,
                        error="user_denied",
                    )

        # 2. Tool execution with exception bounding
        try:
            result = tool.run(arguments, context)
            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms
            result.content = redact_secrets(result.content)
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                content=f"Error executing {name}: {type(e).__name__}: {e}",
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )


def create_default_registry(
    permission_manager: Optional[PermissionManager] = None,
) -> ToolRegistry:
    """Create and populate registry with initial tool catalog (Section 8.1)."""
    from Relay.tools.diagnostics import DiagnoseProjectTool, GetEnvironmentTool
    from Relay.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool
    from Relay.tools.git import GitBranchTool, GitCommitTool, GitDiffTool, GitLogTool, GitStatusTool
    from Relay.tools.patch import ApplyPatchTool, EditFileTool
    from Relay.tools.search import SearchCodeTool
    from Relay.tools.terminal import RunCommandTool
    from Relay.tools.tests import RunTestsTool

    registry = ToolRegistry(permission_manager=permission_manager)
    for tool_cls in [
        ListFilesTool,
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ApplyPatchTool,
        SearchCodeTool,
        RunCommandTool,
        RunTestsTool,
        GitStatusTool,
        GitDiffTool,
        GitLogTool,
        GitBranchTool,
        GitCommitTool,
        DiagnoseProjectTool,
        GetEnvironmentTool,
    ]:
        registry.register(tool_cls())

    return registry
