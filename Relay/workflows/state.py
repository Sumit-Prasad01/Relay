"""Serializable workflow state schemas for LangGraph workflows (Section 11.2)."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    severity: Literal["CRITICAL", "WARNING", "SUGGESTION"]
    file: str
    line: Optional[int] = None
    title: str
    description: str


class WorkflowState(BaseModel):
    """Unified serializable state object for multi-step agent workflows."""

    session_id: str
    workspace: str
    user_request: str
    workflow_id: str = "default"

    # Planning and execution steps
    plan: List[str] = Field(default_factory=list)
    current_step: int = 0
    step_descriptions: List[str] = Field(default_factory=list)

    # Context and history
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_files: List[str] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    changed_files: List[str] = Field(default_factory=list)

    # Verification and repair
    test_results: Dict[str, Any] = Field(default_factory=dict)
    review_findings: List[Dict[str, Any]] = Field(default_factory=list)
    approval_status: Literal["pending", "approved", "rejected", "auto_approved"] = "approved"

    # Control bounds
    errors: List[str] = Field(default_factory=list)
    iteration_count: int = 0
    max_repair_count: int = 3
    repair_count: int = 0
    is_completed: bool = False
    final_summary: str = ""

    def add_error(self, err: str) -> None:
        self.errors.append(err)

    def add_changed_file(self, path: str) -> None:
        if path not in self.changed_files:
            self.changed_files.append(path)

    def add_relevant_file(self, path: str) -> None:
        if path not in self.relevant_files:
            self.relevant_files.append(path)
