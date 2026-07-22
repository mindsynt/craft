"""Anthropic provider implementation"""

from __future__ import annotations

import os
from typing import Any

from craft.core.provider.base import BaseProvider, ProviderError
from craft.core.provider.openai_config import OpenAICompatibleProviderOptions


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        model: str = "claude-sonnet-4",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__("anthropic", model)
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key
                or os.environ.get("ANTHROPIC_API_KEY", ""),
                base_url=self._base_url,
            )
        return self._client

    def _split(self, messages: list[dict]):
        system, msgs = None, []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)
        return system, msgs

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        system, msgs = self._split(messages)
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        try:
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": msgs,
                "max_tokens": kwargs.pop("max_tokens", 4096),
            }
            if system:
                api_kwargs["system"] = system
            if tools:
                api_kwargs["tools"] = tools
            if opts.thinking_budget:
                api_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": opts.thinking_budget,
                }

            resp = await self.client.messages.create(**api_kwargs)
            content_parts = []
            text = ""
            for block in resp.content:
                if block.type == "text":
                    text += block.text
                    content_parts.append({"type": "text", "text": block.text})
                elif block.type == "thinking":
                    content_parts.append({
                        "type": "reasoning",
                        "text": block.thinking,
                    })

            return {
                "content": text,
                "content_parts": content_parts,
                "usage": {
                    "input_tokens": resp.usage.input_tokens if resp.usage else 0,
                    "output_tokens": resp.usage.output_tokens if resp.usage else 0,
                },
            }
        except Exception as e:
            raise ProviderError(str(e), 500, "anthropic") from e

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        system, msgs = self._split(messages)
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        try:
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": msgs,
                "max_tokens": kwargs.pop("max_tokens", 4096),
            }
            if system:
                api_kwargs["system"] = system
            if tools:
                api_kwargs["tools"] = tools
            if opts.thinking_budget:
                api_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": opts.thinking_budget,
                }

            async with self.client.messages.stream(**api_kwargs) as stream:
                async for text_delta in stream.text_stream:
                    yield {"type": "content", "content": text_delta}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
