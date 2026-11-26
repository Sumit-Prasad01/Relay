"""Normalized provider contracts and data models (Section 6.1)."""

import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from Relay.utils.logging import redact_secrets


MessageRole = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: str  # JSON string

    def parsed_arguments(self) -> Dict[str, Any]:
        try:
            return json.loads(self.arguments)
        except Exception:
            return {}

    def parse_arguments_strict(self) -> Dict[str, Any]:
        """Parse JSON tool-call arguments strictly, raising ValueError on malformed or non-object input."""
        if not isinstance(self.arguments, str) or not self.arguments.strip():
            raise ValueError("Tool call arguments are empty or not a JSON string.")
        try:
            parsed = json.loads(self.arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON arguments: {e.msg} (line {e.lineno}, col {e.colno})") from e
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object for tool arguments, got {type(parsed).__name__}.")
        return parsed


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ModelMessage(BaseModel):
    role: MessageRole
    content: str = ""
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None


class ModelRequest(BaseModel):
    model: str
    messages: List[ModelMessage]
    tools: Optional[List[ToolDefinition]] = None
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    timeout: float = 60.0
    structured_output: Optional[Dict[str, Any]] = None
    provider_options: Dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    content: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"  # stop, tool_calls, length, content_filter
    usage: Optional[UsageInfo] = None
    model: str = ""
    provider: str = ""
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)

    def sanitized_metadata(self) -> Dict[str, Any]:
        return {k: redact_secrets(str(v)) for k, v in self.raw_metadata.items()}


ModelEventType = Literal["text_delta", "tool_call_delta", "usage", "completion", "error"]


class ModelEvent(BaseModel):
    event_type: ModelEventType
    text_delta: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    usage: Optional[UsageInfo] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None


class ModelCapabilities(BaseModel):
    tool_calling: bool = False
    streaming: bool = True
    vision: bool = False
    structured_output: bool = False
    parallel_tool_calls: bool = False
    max_context_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    reasoning_controls: bool = False


class ModelInfo(BaseModel):
    id: str
    name: str
    context_length: Optional[int] = None
    capabilities: Optional[ModelCapabilities] = None
    description: Optional[str] = None


class ProviderHealth(BaseModel):
    healthy: bool
    provider: str
    message: str
    models: List[str] = Field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol defining internal contract for all LLM providers."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        ...

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        ...

    async def validate(self) -> ProviderHealth:
        ...

    async def list_models(self) -> List[ModelInfo]:
        ...

    def get_capabilities(self, model: str) -> ModelCapabilities:
        ...


class BaseProvider(ABC):
    """Abstract base class for provider adapters."""

    def __init__(self, name: str, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 60.0):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        pass

    @abstractmethod
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        pass

    @abstractmethod
    async def validate(self) -> ProviderHealth:
        pass

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        pass

    @abstractmethod
    def get_capabilities(self, model: str) -> ModelCapabilities:
        pass

    async def aclose(self) -> None:
        """Release any open network clients or connection pools."""
        return None
