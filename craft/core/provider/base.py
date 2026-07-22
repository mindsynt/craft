"""Base provider classes"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


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
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        ...
