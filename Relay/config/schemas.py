"""Pydantic schemas for Relay configuration (Section 15)."""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


PermissionMode = Literal["plan", "ask", "auto-edit", "full-auto"]


class AgentConfig(BaseModel):
    max_iterations: int = Field(default=30, ge=1, le=500)
    max_tool_calls: int = Field(default=100, ge=1, le=1000)
    task_timeout_seconds: int = Field(default=1800, ge=10)
    max_parallel_tools: int = Field(default=4, ge=1, le=16)
    max_context_tokens: int = Field(default=64000, ge=1000)
    stream: bool = True


class ProviderConfig(BaseModel):
    enabled: bool = True
    model: str = ""
    credential_ref: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    timeout_seconds: int = 60
    options: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceConfig(BaseModel):
    ignore_file: str = ".relayignore"
    instruction_file: str = "AGENTS.md"
    snapshot_before_write: bool = True


class TerminalConfig(BaseModel):
    timeout_seconds: int = 120
    max_output_bytes: int = 200_000
    sandbox: Literal["restricted", "container", "none"] = "restricted"


class StorageConfig(BaseModel):
    database_path: str = ""
    session_retention_days: int = 90


class RootConfig(BaseModel):
    default_provider: str = "openrouter"
    default_model: str = "anthropic/claude-3.5-sonnet"
    permission_mode: PermissionMode = "ask"
    workspace_only: bool = True

    agent: AgentConfig = Field(default_factory=AgentConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
