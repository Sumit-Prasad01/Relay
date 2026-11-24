"""Tests for MCP tool wrapper and security policy (Section 14.4)."""

from pathlib import Path
from unittest.mock import MagicMock
from Relay.tools.mcp.manager import MCPToolWrapper
from Relay.tools.mcp.policy import MCPToolPolicy
from Relay.tools.registry import ToolRegistry


def test_mcp_policy_and_wrapper():
    policy = MCPToolPolicy(
        server_name="test_server",
        default_category="execute",
        tool_categories={"read_db": "read"},
        blocked_tools={"danger_tool"},
    )

    assert policy.is_allowed("read_db") is True
    assert policy.is_allowed("danger_tool") is False
    assert policy.get_category("read_db") == "read"
    assert policy.get_category("unknown_tool") == "execute"

    # Wrapper execution test
    mock_client = MagicMock()
    mock_client.call_tool.return_value = "Query result: 42"

    wrapper = MCPToolWrapper(
        server_name="db_server",
        original_name="query",
        description="Query external DB",
        parameters={"type": "object"},
        category="read",
        client=mock_client,
    )

    assert wrapper.name == "mcp__db_server__query"
    res = wrapper.run({"sql": "SELECT 1"}, context=None)
    assert res.success is True
    assert "Query result: 42" in res.content
    mock_client.call_tool.assert_called_once_with("query", {"sql": "SELECT 1"})
