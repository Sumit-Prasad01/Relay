"""OpenAI-compatible base adapter used by Groq, OpenRouter, OpenAI, and Gemini."""

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
from openai import AsyncOpenAI
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


class OpenAICompatibleProvider(BaseProvider):
    """Base provider handling any endpoint conforming to the OpenAI Chat Completions API."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
    ):
        super().__init__(name=name, base_url=base_url, api_key=api_key, timeout=timeout)
        self.default_headers = default_headers or {}
        self.capabilities_registry = CapabilityRegistry()
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "missing-key",
                default_headers=self.default_headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    async def aclose(self) -> None:
        """Close the AsyncOpenAI httpx pool while the active event loop is still running."""
        if self._client is not None:
            client = self._client
            self._client = None
            try:
                await client.close()
                # Allow Windows ProactorEventLoop TLS transport callbacks to finish before loop teardown
                await asyncio.sleep(0.05)
            except Exception:
                pass

    def _convert_messages(self, messages: List[ModelMessage]) -> List[Dict[str, Any]]:
        payload = []
        for m in messages:
            msg_dict: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.role == "tool" and m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.role == "assistant" and m.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in m.tool_calls
                ]
            payload.append(msg_dict)
        return payload

    def _convert_tools(self, tools: Optional[List[Any]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        client = self._get_client()
        messages = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)

        kwargs: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "timeout": request.timeout or self.timeout,
        }
        if tools:
            kwargs["tools"] = tools
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        try:
            res = await client.chat.completions.create(**kwargs)
        except Exception as e:
            self._handle_api_error(e)

        choice = res.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id or "",
                        name=tc.function.name,
                        arguments=tc.function.arguments or "{}",
                    )
                )

        usage = None
        if getattr(res, "usage", None):
            usage = UsageInfo(
                prompt_tokens=res.usage.prompt_tokens,
                completion_tokens=res.usage.completion_tokens,
                total_tokens=res.usage.total_tokens,
                cached_tokens=getattr(getattr(res.usage, "prompt_tokens_details", None), "cached_tokens", None),
                reasoning_tokens=getattr(getattr(res.usage, "completion_tokens_details", None), "reasoning_tokens", None),
            )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            model=request.model,
            provider=self.name,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        client = self._get_client()
        messages = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)

        kwargs: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": request.timeout or self.timeout,
        }
        if tools:
            kwargs["tools"] = tools
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        try:
            stream = await client.chat.completions.create(**kwargs)
        except Exception as e:
            self._handle_api_error(e)

        # Buffers for accumulating streaming tool call arguments
        accumulated_tools: Dict[int, Dict[str, str]] = {}
        finish_reason = "stop"

        try:
            async for chunk in stream:
                # Check for usage in chunk
                if getattr(chunk, "usage", None):
                    yield ModelEvent(
                        event_type="usage",
                        usage=UsageInfo(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                        ),
                    )

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta
                if delta.content:
                    yield ModelEvent(event_type="text_delta", text_delta=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in accumulated_tools:
                            accumulated_tools[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name or "" if tc_delta.function else "",
                                "arguments": "",
                            }
                        else:
                            if tc_delta.id:
                                accumulated_tools[idx]["id"] += tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                accumulated_tools[idx]["name"] += tc_delta.function.name

                        if tc_delta.function and tc_delta.function.arguments:
                            accumulated_tools[idx]["arguments"] += tc_delta.function.arguments
        finally:
            if hasattr(stream, "close"):
                await stream.close()

        # Emit assembled tool calls
        for idx in sorted(accumulated_tools.keys()):
            tool_data = accumulated_tools[idx]
            yield ModelEvent(
                event_type="tool_call_delta",
                tool_call=ToolCall(
                    id=tool_data["id"] or f"call_{idx}",
                    name=tool_data["name"],
                    arguments=tool_data["arguments"] or "{}",
                ),
            )

        yield ModelEvent(event_type="completion", finish_reason=finish_reason)

    async def validate(self) -> ProviderHealth:
        """Validate connectivity and authentication."""
        client = self._get_client()
        try:
            # Simple non-destructive models probe
            models = await client.models.list()
            model_ids = [m.id for m in models.data][:10] if models and models.data else []
            return ProviderHealth(
                healthy=True,
                provider=self.name,
                message="Provider credentials and connectivity verified.",
                models=model_ids,
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                provider=self.name,
                message=f"Validation failed: {e}",
            )

    async def list_models(self) -> List[ModelInfo]:
        client = self._get_client()
        try:
            models = await client.models.list()
            return [
                ModelInfo(
                    id=m.id,
                    name=m.id,
                    capabilities=self.get_capabilities(m.id),
                )
                for m in (models.data or [])
            ]
        except Exception:
            return []

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return self.capabilities_registry.get_capabilities(model)

    def _handle_api_error(self, e: Exception) -> None:
        err_msg = str(e).lower()
        if "auth" in err_msg or "unauthorized" in err_msg or "api key" in err_msg or "401" in err_msg:
            raise AuthenticationError(f"Authentication failed for {self.name}: {e}")
        if "rate limit" in err_msg or "429" in err_msg:
            raise RateLimitError(f"Rate limit exceeded for {self.name}: {e}")
        if "timeout" in err_msg:
            raise NetworkTimeoutError(f"Network timeout contacting {self.name}: {e}")
        raise RelayError(f"Error calling {self.name} provider: {e}")
