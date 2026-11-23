"""Base classes and execution contract for Relay tools (Section 8)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

ToolCategory = Literal["read", "write", "execute", "git"]


@dataclass
class ToolResult:
    content: str
    success: bool = True
    exit_code: Optional[int] = None
    duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "success": self.success,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]

    @abstractmethod
    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        """Execute the tool with validated arguments."""
        pass
