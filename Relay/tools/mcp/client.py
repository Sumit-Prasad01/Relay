"""Model Context Protocol (MCP) stdio JSON-RPC client (Section 14.4)."""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.utils.logging import get_logger, redact_secrets
from Relay.utils.platform import terminate_process_tree

logger = get_logger(__name__)


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: int = 30


class MCPStdioClient:
    """Communicates with a local stdio MCP server using JSON-RPC 2.0."""

    def __init__(self, config: MCPServerConfig, workspace_root: Path):
        self.config = config
        self.workspace_root = workspace_root.resolve()
        self._proc: Optional[subprocess.Popen] = None
        self._msg_id = 0

    def start(self) -> None:
        """Launch the stdio MCP server process."""
        if self._proc is not None:
            return

        cmd = [self.config.command] + self.config.args
        env = dict(os.environ)
        env.update(self.config.env)

        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=self.workspace_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            # Perform initial handshake
            self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "Relay", "version": "0.1.0"},
                "capabilities": {},
            })
        except Exception as e:
            logger.error(f"Failed to start MCP server {self.config.name}: {e}")
            self.close()
            raise

    def close(self) -> None:
        """Terminate the server process."""
        if self._proc is not None:
            try:
                terminate_process_tree(self._proc.pid)
            except Exception:
                pass
            self._proc = None

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC 2.0 request and read response line."""
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError(f"MCP server '{self.config.name}' is not running.")

        req_id = self._next_id()
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(msg) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

        resp_line = self._proc.stdout.readline()
        if not resp_line:
            raise RuntimeError(f"MCP server '{self.config.name}' terminated unexpectedly.")

        resp = json.loads(resp_line)
        if "error" in resp:
            raise RuntimeError(f"MCP server error: {resp['error']}")
        return resp.get("result", {})

    def list_tools(self) -> List[Dict[str, Any]]:
        """Query tools available from this MCP server."""
        self.start()
        res = self._send_request("tools/list", {})
        return res.get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool call against the MCP server."""
        self.start()
        res = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        content_blocks = res.get("content", [])
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)

        result_text = "\n".join(text_parts) if text_parts else json.dumps(res)
        return redact_secrets(result_text)
