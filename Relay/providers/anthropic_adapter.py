"""Anthropic Messages API provider adapter (Section 6.2)."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from Relay.providers.base import (
    BaseProvider,
    ModelCapabilities,
    ModelEvent,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
    ToolCall,
    UsageInfo,
)
from Relay.providers.capabilities import CapabilityRegistry
from Relay.utils.errors import AuthenticationError, RateLimitError, NetworkTimeoutError, RelayError


class AnthropicProvider(BaseProvider):
    """Adapter for native Anthropic Messages API."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 60.0):
        super().__init__(name="anthropic", base_url=base_url or self.DEFAULT_BASE_URL, api_key=api_key, timeout=timeout)
        self.capabilities_registry = CapabilityRegistry()

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def _convert_request(self, request: ModelRequest) -> Dict[str, Any]:
        system_prompts = []
        messages_payload: List[Dict[str, Any]] = []

        for m in request.messages:
            if m.role == "system":
                system_prompts.append(m.content)
            elif m.role == "tool":
                messages_payload.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "",
                            "content": m.content,
                        }
                    ],
                })
            elif m.role == "assistant" and m.tool_calls:
                content_blocks: List[Dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.parsed_arguments(),
                    })
                messages_payload.append({"role": "assistant", "content": content_blocks})
            else:
                messages_payload.append({"role": m.role, "content": m.content})

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages_payload,
            "max_tokens": request.max_output_tokens or 4096,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in request.tools
            ]

        return payload

    async def generate(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url.rstrip('/')}/messages"
        payload = self._convert_request(request)

        async with httpx.AsyncClient(timeout=request.timeout or self.timeout) as client:
            try:
                res = await client.post(url, headers=self._headers(), json=payload)
            except httpx.TimeoutException as e:
                raise NetworkTimeoutError(f"Timeout calling Anthropic: {e}")
            except Exception as e:
                raise RelayError(f"Error connecting to Anthropic: {e}")

            if res.status_code != 200:
                self._handle_http_error(res.status_code, res.text)

            data = res.json()

        content_parts = []
        tool_calls: List[ToolCall] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=json.dumps(block.get("input", {})),
                    )
                )

        usage = None
        if "usage" in data:
            usage = UsageInfo(
                prompt_tokens=data["usage"].get("input_tokens", 0),
                completion_tokens=data["usage"].get("output_tokens", 0),
                total_tokens=data["usage"].get("input_tokens", 0) + data["usage"].get("output_tokens", 0),
            )

        return ModelResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "stop"),
            usage=usage,
            model=request.model,
            provider="anthropic",
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        url = f"{self.base_url.rstrip('/')}/messages"
        payload = self._convert_request(request)
        payload["stream"] = True

        async with httpx.AsyncClient(timeout=request.timeout or self.timeout) as client:
            try:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        self._handle_http_error(response.status_code, err_body.decode())

                    current_tool_id = ""
                    current_tool_name = ""
                    tool_arg_chunks: List[str] = []

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        raw_data = line[6:].strip()
                        if raw_data == "[DONE]":
                            break
                        try:
                            event = json.loads(raw_data)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type")

                        if event_type == "content_block_start":
                            block = event.get("content_block", {})
                            if block.get("type") == "tool_use":
                                current_tool_id = block.get("id", "")
                                current_tool_name = block.get("name", "")
                                tool_arg_chunks = []

                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield ModelEvent(event_type="text_delta", text_delta=delta.get("text", ""))
                            elif delta.get("type") == "input_json_delta":
                                tool_arg_chunks.append(delta.get("partial_json", ""))

                        elif event_type == "content_block_stop":
                            if current_tool_name:
                                yield ModelEvent(
                                    event_type="tool_call_delta",
                                    tool_call=ToolCall(
                                        id=current_tool_id,
                                        name=current_tool_name,
                                        arguments="".join(tool_arg_chunks) or "{}",
                                    ),
                                )
                                current_tool_name = ""
                                current_tool_id = ""
                                tool_arg_chunks = []

                        elif event_type == "message_delta":
                            usage_data = event.get("usage")
                            if usage_data:
                                yield ModelEvent(
                                    event_type="usage",
                                    usage=UsageInfo(
                                        prompt_tokens=0,
                                        completion_tokens=usage_data.get("output_tokens", 0),
                                        total_tokens=usage_data.get("output_tokens", 0),
                                    ),
                                )
            except httpx.TimeoutException as e:
                raise NetworkTimeoutError(f"Timeout streaming from Anthropic: {e}")

        yield ModelEvent(event_type="completion", finish_reason="stop")

    async def validate(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(healthy=False, provider="anthropic", message="API key is missing.")
        # Minimal probe
        try:
            req = ModelRequest(
                model="claude-3-5-haiku-20241022",
                messages=[ModelMessage(role="user", content="ping")],
                max_output_tokens=1,
            )
            res = await self.generate(req)
            return ProviderHealth(
                healthy=True,
                provider="anthropic",
                message="Anthropic API credentials verified.",
                models=["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
            )
        except Exception as e:
            return ProviderHealth(healthy=False, provider="anthropic", message=str(e))

    async def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet", capabilities=self.get_capabilities("claude-3-5-sonnet-20241022")),
            ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku", capabilities=self.get_capabilities("claude-3-5-haiku-20241022")),
            ModelInfo(id="claude-3-opus-20240229", name="Claude 3 Opus", capabilities=self.get_capabilities("claude-3-opus-20240229")),
        ]

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return self.capabilities_registry.get_capabilities(model)

    def _handle_http_error(self, status: int, text: str) -> None:
        if status in (401, 403):
            raise AuthenticationError(f"Anthropic authentication failed ({status}): {text}")
        if status == 429:
            raise RateLimitError(f"Anthropic rate limit reached ({status}): {text}")
        raise RelayError(f"Anthropic API returned error ({status}): {text}")
