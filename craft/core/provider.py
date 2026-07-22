"""
LLM 提供商系统 — 移植自 MiMo-Code packages/opencode/src/provider/
支持 OpenAI / Anthropic / Ollama / 自定义，流式 + 非流式
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from craft.config import get_config

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, code: int = 500, provider: str = ""):
        self.code = code
        self.provider = provider
        super().__init__(message)


class BaseProvider(ABC):
    def __init__(self, name: str, model: str = ""):
        self.name = name
        self.model = model

    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> dict[str, Any]:
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        ...


class OpenAIProvider(BaseProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, base_url: str | None = None):
        super().__init__("openai", model)
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
            self._client = AsyncOpenAI(api_key=key, base_url=self._base_url)
        return self._client

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> dict:
        try:
            resp = await self.client.chat.completions.create(
                model=self.model, messages=messages, tools=tools or [], **kwargs)
            msg = resp.choices[0].message
            return {"content": msg.content or "", "tool_calls": self._extract_tools(msg),
                    "usage": {"prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                              "completion_tokens": resp.usage.completion_tokens if resp.usage else 0}}
        except Exception as e:
            err = str(e).lower()
            if "api_key" in err or "missing credentials" in err:
                raise ProviderError("请设置 OPENAI_API_KEY 环境变量", 401, "openai") from e
            raise ProviderError(str(e), 500, "openai") from e

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None, **kwargs):
        try:
            stream = await self.client.chat.completions.create(
                model=self.model, messages=messages, tools=tools or [],
                stream=True, stream_options={"include_usage": True}, **kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield {"type": "content", "content": delta.content}
                if getattr(chunk, 'usage', None):
                    yield {"type": "usage", "prompt_tokens": chunk.usage.prompt_tokens,
                           "completion_tokens": chunk.usage.completion_tokens}
        except Exception as e:
            err = str(e).lower()
            yield {"type": "error", "message": "请设置 OPENAI_API_KEY" if "api_key" in err or "missing credentials" in err else str(e)}

    def _extract_tools(self, msg) -> list[dict] | None:
        if not getattr(msg, 'tool_calls', None):
            return None
        return [{"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]


class AnthropicProvider(BaseProvider):
    def __init__(self, model: str = "claude-sonnet-4", api_key: str | None = None):
        super().__init__("anthropic", model)
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self._api_key or os.environ.get("ANTHROPIC_API_KEY", ""))
        return self._client

    def _split(self, messages: list[dict]):
        system, msgs = None, []
        for m in messages:
            if m["role"] == "system": system = m["content"]
            else: msgs.append(m)
        return system, msgs

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> dict:
        system, msgs = self._split(messages)
        try:
            resp = await self.client.messages.create(
                model=self.model, messages=msgs, system=system, max_tokens=kwargs.get("max_tokens", 4096))
            return {"content": resp.content[0].text if resp.content else "",
                    "usage": {"input_tokens": resp.usage.input_tokens if resp.usage else 0,
                              "output_tokens": resp.usage.output_tokens if resp.usage else 0}}
        except Exception as e:
            raise ProviderError(str(e), 500, "anthropic") from e

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None, **kwargs):
        system, msgs = self._split(messages)
        try:
            async with self.client.messages.stream(
                model=self.model, messages=msgs, system=system, max_tokens=kwargs.get("max_tokens", 4096)) as stream:
                async for text in stream.text_stream:
                    yield {"type": "content", "content": text}
        except Exception as e:
            yield {"type": "error", "message": str(e)}


PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": lambda **kw: OpenAIProvider(base_url="http://localhost:11434/v1", **kw),
}


def get_provider(provider_name: str | None = None, model: str | None = None) -> BaseProvider:
    cfg = get_config()
    if model and "/" in model:
        provider_name, model = model.split("/", 1)
    provider_name = provider_name or "openai"
    defaults = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4", "ollama": "llama3"}
    model = model or defaults.get(provider_name, "")
    factory = PROVIDER_MAP.get(provider_name)
    if not factory:
        raise ProviderError(f"未知提供商: {provider_name}，可用: {', '.join(PROVIDER_MAP.keys())}", 400)
    return factory(model=model)
