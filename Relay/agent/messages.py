"""Message conversion and history normalization between SQLite and provider contract (Section 7.1)."""

import json
from typing import Any, Dict, List, Optional

from Relay.providers.base import ModelMessage, ToolCall
from Relay.tools.base import ToolResult


def user_message(content: str) -> ModelMessage:
    """Create a normalized user message."""
    return ModelMessage(role="user", content=content)


def assistant_message(content: str = "", tool_calls: Optional[List[ToolCall]] = None) -> ModelMessage:
    """Create a normalized assistant message with optional tool calls."""
    return ModelMessage(role="assistant", content=content, tool_calls=tool_calls or None)


def tool_result_message(tool_call_id: str, result: ToolResult) -> ModelMessage:
    """Create a normalized tool message from an executed ToolResult."""
    return ModelMessage(
        role="tool",
        content=result.content,
        tool_call_id=tool_call_id,
    )


def system_message(content: str) -> ModelMessage:
    """Create a normalized system message."""
    return ModelMessage(role="system", content=content)


def serialize_for_storage(msg: ModelMessage) -> Dict[str, Any]:
    """Extract fields for SQLite storage via SessionStore."""
    raw_payload: Dict[str, Any] = {}
    if msg.tool_calls:
        raw_payload["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
    if msg.tool_call_id:
        raw_payload["tool_call_id"] = msg.tool_call_id

    return {
        "role": msg.role,
        "content": msg.content,
        "raw_payload": raw_payload if raw_payload else None,
    }


def deserialize_from_storage(row: Dict[str, Any]) -> ModelMessage:
    """Reconstruct a ModelMessage from a SQLite database row."""
    role = row.get("role", "user")
    content = row.get("content", "")
    raw_json = row.get("raw_payload")

    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None

    if raw_json:
        try:
            payload = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            if "tool_calls" in payload and isinstance(payload["tool_calls"], list):
                tool_calls = [ToolCall(**tc) for tc in payload["tool_calls"]]
            if "tool_call_id" in payload:
                tool_call_id = payload["tool_call_id"]
        except Exception:
            pass

    return ModelMessage(
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    )
