"""OpenAI-compatible chat model provider"""

from __future__ import annotations

import os
from typing import Any

from craft.core.provider.base import BaseProvider, ProviderError
from craft.core.provider.openai_config import OpenAICompatibleProviderOptions
from craft.core.provider.tools import prepare_tools
from craft.core.provider.transform import map_openai_finish_reason


class OpenAIProvider(BaseProvider):
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        supports_structured_outputs: bool = False,
    ):
        super().__init__("openai", model)
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._organization = organization
        self._project = project
        self._supports_structured_outputs = supports_structured_outputs
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
            kwargs: dict[str, Any] = {
                "api_key": key,
                "base_url": self._base_url,
            }
            if self._organization:
                kwargs["organization"] = self._organization
            if self._project:
                kwargs["project"] = self._project
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        try:
            # Parse provider options
            opts = OpenAICompatibleProviderOptions.from_dict(
                kwargs.pop("providerOptions", None)
            )

            # Prepare tools
            openai_tools, tool_choice, _ = prepare_tools(
                tools, kwargs.pop("tool_choice", None)
            )

            # Build request args
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": messages,
            }
            if openai_tools:
                api_kwargs["tools"] = openai_tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice

            # Standard params
            for param in (
                "max_tokens",
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "seed",
                "user",
            ):
                value = kwargs.pop(param, None) or getattr(opts, param, None)
                if value is not None:
                    api_kwargs[param] = value

            # Response format: support structured outputs
            response_format = kwargs.pop("response_format", None)
            if response_format and isinstance(response_format, dict):
                if self._supports_structured_outputs and response_format.get("schema"):
                    api_kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "schema": response_format["schema"],
                            "name": response_format.get("name", "response"),
                            "description": response_format.get("description"),
                        },
                    }
                elif response_format.get("type") == "json":
                    api_kwargs["response_format"] = {"type": "json_object"}

            # Reasoning effort
            if opts.reasoning_effort:
                api_kwargs["reasoning_effort"] = opts.reasoning_effort

            # Any extra kwargs
            api_kwargs.update(kwargs)

            resp = await self.client.chat.completions.create(**api_kwargs)

            choice = resp.choices[0]
            msg = choice.message

            # Build content with reasoning support (Copilot-style)
            content_parts: list[dict] = []
            if msg.content:
                content_parts.append({"type": "text", "text": msg.content})
            if getattr(msg, "reasoning_text", None):
                content_parts.append({
                    "type": "reasoning",
                    "text": msg.reasoning_text,
                })
            if getattr(msg, "reasoning_content", None):
                content_parts.append({
                    "type": "reasoning",
                    "text": msg.reasoning_content,
                })

            result: dict[str, Any] = {
                "content": msg.content or "",
                "content_parts": content_parts,
                "finish_reason": map_openai_finish_reason(
                    getattr(choice, "finish_reason", None)
                ),
                "tool_calls": self._extract_tools(msg),
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens
                    if resp.usage
                    else 0,
                },
                "metadata": {
                    "id": resp.id,
                    "model": resp.model,
                    "created": resp.created,
                },
            }

            # Detailed token info
            if resp.usage:
                if resp.usage.prompt_tokens_details:
                    result["usage"]["cached_tokens"] = (
                        resp.usage.prompt_tokens_details.cached_tokens
                    )
                if resp.usage.completion_tokens_details:
                    result["usage"]["reasoning_tokens"] = (
                        resp.usage.completion_tokens_details.reasoning_tokens
                    )

            return result

        except Exception as e:
            err_str = str(e).lower()
            if "api_key" in err_str or "missing credentials" in err_str:
                raise ProviderError(
                    "请设置 OPENAI_API_KEY 环境变量", 401, "openai"
                ) from e
            raise ProviderError(str(e), 500, "openai") from e

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        try:
            # Parse provider options
            opts = OpenAICompatibleProviderOptions.from_dict(
                kwargs.pop("providerOptions", None)
            )

            openai_tools, tool_choice, _ = prepare_tools(
                tools, kwargs.pop("tool_choice", None)
            )

            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if openai_tools:
                api_kwargs["tools"] = openai_tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice

            for param in (
                "max_tokens",
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "seed",
                "user",
            ):
                value = kwargs.pop(param, None) or getattr(opts, param, None)
                if value is not None:
                    api_kwargs[param] = value

            if opts.reasoning_effort:
                api_kwargs["reasoning_effort"] = opts.reasoning_effort

            api_kwargs.update(kwargs)

            stream = await self.client.chat.completions.create(**api_kwargs)

            is_first = True
            active_reasoning = False
            reasoning_opaque: str | None = None

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None and not getattr(chunk, "usage", None):
                    continue

                # response-metadata on first chunk
                if is_first:
                    is_first = False
                    yield {
                        "type": "response-metadata",
                        "id": chunk.id,
                        "model": chunk.model,
                        "created": chunk.created,
                    }

                # Emit reasoning via reasoning_text (Copilot-style)
                if delta:
                    rtext = getattr(delta, "reasoning_text", None) or getattr(
                        delta, "reasoning_content", None
                    )
                    if rtext:
                        if not active_reasoning:
                            yield {"type": "reasoning-start", "id": "reasoning-0"}
                            active_reasoning = True
                        yield {
                            "type": "reasoning-delta",
                            "id": "reasoning-0",
                            "delta": rtext,
                        }

                    # Capture reasoning_opaque for multi-turn
                    r_opaque = getattr(delta, "reasoning_opaque", None)
                    if r_opaque:
                        reasoning_opaque = r_opaque

                    # Content
                    if delta.content:
                        if active_reasoning:
                            yield {
                                "type": "reasoning-end",
                                "id": "reasoning-0",
                                "providerMetadata": (
                                    {"copilot": {"reasoningOpaque": reasoning_opaque}}
                                    if reasoning_opaque
                                    else None
                                ),
                            }
                            active_reasoning = False
                        yield {"type": "content", "content": delta.content}

                    # Tool calls
                    if getattr(delta, "tool_calls", None):
                        if active_reasoning:
                            yield {
                                "type": "reasoning-end",
                                "id": "reasoning-0",
                                "providerMetadata": (
                                    {"copilot": {"reasoningOpaque": reasoning_opaque}}
                                    if reasoning_opaque
                                    else None
                                ),
                            }
                            active_reasoning = False
                        for tc in delta.tool_calls:
                            yield {
                                "type": "tool-call-delta",
                                "index": tc.index,
                                "id": tc.id,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "",
                                },
                            }

                # Usage
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                    usage_data: dict[str, Any] = {
                        "type": "usage",
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                    }
                    if usage.prompt_tokens_details:
                        usage_data["cached_tokens"] = (
                            usage.prompt_tokens_details.cached_tokens
                        )
                    if usage.completion_tokens_details:
                        usage_data["reasoning_tokens"] = (
                            usage.completion_tokens_details.reasoning_tokens
                        )
                    yield usage_data

            # Flush active reasoning
            if active_reasoning:
                yield {
                    "type": "reasoning-end",
                    "id": "reasoning-0",
                    "providerMetadata": (
                        {"copilot": {"reasoningOpaque": reasoning_opaque}}
                        if reasoning_opaque
                        else None
                    ),
                }

        except Exception as e:
            err_str = str(e).lower()
            yield {
                "type": "error",
                "message": "请设置 OPENAI_API_KEY"
                if "api_key" in err_str or "missing credentials" in err_str
                else str(e),
            }

    def _extract_tools(self, msg) -> list[dict] | None:
        if not getattr(msg, "tool_calls", None):
            return None
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
