"""Security policy and permission checks for untrusted MCP tools (Section 14.4)."""

from typing import Dict, Literal, Optional, Set
from pydantic import BaseModel, Field

ToolCategory = Literal["read", "write", "execute", "git"]


class MCPToolPolicy(BaseModel):
    """Configures trust and permission categories for tools discovered from an MCP server."""

    server_name: str
    enabled: bool = True
    default_category: ToolCategory = "execute"
    tool_categories: Dict[str, ToolCategory] = Field(default_factory=dict)
    blocked_tools: Set[str] = Field(default_factory=set)

    def get_category(self, tool_name: str) -> ToolCategory:
        """Resolve the permission category for an MCP tool."""
        return self.tool_categories.get(tool_name, self.default_category)

    def is_allowed(self, tool_name: str) -> bool:
        """Check if tool is permitted by policy."""
        if not self.enabled:
            return False
        return tool_name not in self.blocked_tools
