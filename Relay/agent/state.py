"""Agent state maintained across session execution and turns (Section 7.1 & 11.2)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.providers.base import ModelMessage


@dataclass
class AgentState:
    """Serializable runtime state of an agent session."""

    session_id: str
    workspace_root: Path
    provider_name: str
    model_name: str
    messages: List[ModelMessage] = field(default_factory=list)
    iteration_count: int = 0
    turn_count: int = 0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    total_tokens_used: int = 0
    changed_files: List[str] = field(default_factory=list)
    is_cancelled: bool = False
    is_finished: bool = False
    finish_reason: Optional[str] = None
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_changed_file(self, path: str) -> None:
        if path not in self.changed_files:
            self.changed_files.append(path)

    def update_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens_used += prompt_tokens
        self.completion_tokens_used += completion_tokens
        self.total_tokens_used += prompt_tokens + completion_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workspace_root": str(self.workspace_root),
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "messages": [m.model_dump() for m in self.messages],
            "iteration_count": self.iteration_count,
            "turn_count": self.turn_count,
            "prompt_tokens_used": self.prompt_tokens_used,
            "completion_tokens_used": self.completion_tokens_used,
            "total_tokens_used": self.total_tokens_used,
            "changed_files": list(self.changed_files),
            "is_cancelled": self.is_cancelled,
            "is_finished": self.is_finished,
            "finish_reason": self.finish_reason,
            "last_error": self.last_error,
            "metadata": dict(self.metadata),
        }
