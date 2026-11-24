"""MCP tool registration, namespacing, and lifecycle manager (Section 14.4)."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.tools.base import BaseTool, ToolCategory, ToolResult
from Relay.tools.mcp.client import MCPServerConfig, MCPStdioClient
from Relay.tools.mcp.policy import MCPToolPolicy
from Relay.tools.registry import ToolRegistry
from Relay.utils.logging import get_logger

logger = get_logger(__name__)


class MCPToolWrapper(BaseTool):
    """Wraps an external MCP tool as an internal Relay BaseTool."""

    def __init__(
        self,
        server_name: str,
        original_name: str,
        description: str,
        parameters: Dict[str, Any],
        category: ToolCategory,
        client: MCPStdioClient,
    ):
        self.server_name = server_name
        self.original_name = original_name
        self.name = f"mcp__{server_name}__{original_name}"
        self.description = f"[{server_name}] {description}"
        self.parameters = parameters
        self.category = category
        self.client = client

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        """Forward invocation to the MCP server client."""
        try:
            output = self.client.call_tool(self.original_name, arguments)
            return ToolResult(content=output, success=True)
        except Exception as e:
            return ToolResult(content=f"MCP Error ({self.name}): {e}", success=False, error=str(e))


class MCPManager:
    """Manages MCP server discovery, connections, and tool registration into ToolRegistry."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.servers: Dict[str, MCPServerConfig] = {}
        self.policies: Dict[str, MCPToolPolicy] = {}
        self.clients: Dict[str, MCPStdioClient] = {}

    def register_server(
        self,
        config: MCPServerConfig,
        policy: Optional[MCPToolPolicy] = None,
    ) -> None:
        self.servers[config.name] = config
        self.policies[config.name] = policy or MCPToolPolicy(server_name=config.name)

    def attach_tools(self, registry: ToolRegistry) -> int:
        """Discover tools from all enabled MCP servers and register them into the registry."""
        count = 0
        for name, cfg in self.servers.items():
            if not cfg.enabled:
                continue

            policy = self.policies.get(name) or MCPToolPolicy(server_name=name)
            client = MCPStdioClient(cfg, self.workspace_root)
            self.clients[name] = client

            try:
                tools_data = client.list_tools()
                for t in tools_data:
                    tool_name = t.get("name", "")
                    if not policy.is_allowed(tool_name):
                        continue

                    category = policy.get_category(tool_name)
                    desc = t.get("description", "")
                    params = t.get("inputSchema", {})

                    wrapper = MCPToolWrapper(
                        server_name=name,
                        original_name=tool_name,
                        description=desc,
                        parameters=params,
                        category=category,
                        client=client,
                    )
                    registry.register(wrapper)
                    count += 1
            except Exception as e:
                logger.warning(f"Could not load tools from MCP server '{name}': {e}")

        return count

    def shutdown(self) -> None:
        """Close all open MCP client processes."""
        for client in self.clients.values():
            client.close()
