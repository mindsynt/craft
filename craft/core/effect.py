"""
Effect 适配 — 移植自 packages/opencode/src/effect/
Effect-TS 的 Python 等价模式
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class EffectResult:
    def __init__(self, value: T | None = None, error: Exception | None = None):
        self.value = value
        self.error = error

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def unwrap(self) -> T:
        if self.error:
            raise self.error
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value if self.is_ok else default


class Effect:
    @staticmethod
    def succeed(value: T) -> EffectResult[T]:
        return EffectResult(value=value)

    @staticmethod
    def fail(error: Exception) -> EffectResult:
        return EffectResult(error=error)

    @staticmethod
    def from_async(fn: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            try:
                r = fn(*args, **kwargs)
                if hasattr(r, "__await__"):
                    r = await r
                return EffectResult(value=r)
            except Exception as e:
                return EffectResult(error=e)
        return wrapper

    @staticmethod
    def all(results: list[EffectResult]) -> EffectResult[list]:
        values = []
        for r in results:
            if r.is_error:
                return EffectResult(error=r.error)
            values.append(r.value)
        return EffectResult(value=values)


class Option:
    @staticmethod
    def some(value: T) -> T | None:
        return value

    @staticmethod
    def none() -> None:
        return None

    @staticmethod
    def is_some(value: Any) -> bool:
        return value is not None

    @staticmethod
    def is_none(value: Any) -> bool:
        return value is None

    @staticmethod
    def get_or(value: T | None, default: T) -> T:
        return value if value is not None else default


# ─── index.ts / node.ts / temporary.ts ───

class NodeInfo:
    """运行时环境信息 (对应 node.ts)"""
    @property
    def version(self) -> str:
        import sys
        return f"python {sys.version.split()[0]}"

    @property
    def platform(self) -> str:
        import platform
        return platform.system().lower()

    @property
    def arch(self) -> str:
        import platform
        return platform.machine()


node_info = NodeInfo()
