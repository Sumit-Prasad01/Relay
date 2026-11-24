"""Runtime events emitted during agent execution (Section 7.1 & 17)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from Relay.providers.base import ToolCall, UsageInfo
from Relay.tools.base import ToolResult


AgentEventType = Literal[
    "session_started",
    "turn_started",
    "model_request_started",
    "text_delta",
    "tool_call_delta",
    "tool_call_requested",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_failed",
    "file_changed",
    "usage_update",
    "retry_attempt",
    "turn_completed",
    "stop_condition_met",
    "session_finished",
    "error",
]


@dataclass
class AgentEvent:
    """Represents a structured runtime event emitted to subscribers (CLI, TUI, audit)."""

    event_type: AgentEventType
    session_id: str
    turn: int = 0
    text_delta: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[ToolResult] = None
    usage: Optional[UsageInfo] = None
    file_path: Optional[str] = None
    diff: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "turn": self.turn,
            "text_delta": self.text_delta,
            "tool_call": self.tool_call.model_dump() if self.tool_call else None,
            "tool_result": self.tool_result.to_dict() if self.tool_result else None,
            "usage": self.usage.model_dump() if self.usage else None,
            "file_path": self.file_path,
            "diff": self.diff,
            "error": self.error,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
