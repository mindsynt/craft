"""基础 Effect 类型 — EffectResult, Effect, Option, NodeInfo"""

from __future__ import annotations

import platform
import sys
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generic,
    TypeVar,
)

T = TypeVar("T")
E = TypeVar("E", bound=Exception)
B = TypeVar("B")


# =============================================================================
# 基础 Effect 类型 — node.ts / temporary.ts
# =============================================================================


class EffectResult(Generic[T]):
    """操作结果容器 (对应 Effect-TS's Exit)"""

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

    def map(self, fn: Callable[[T], B]) -> EffectResult[B]:
        if self.is_ok:
            return EffectResult(value=fn(self.value))
        return EffectResult(error=self.error)

    def flat_map(self, fn: Callable[[T], EffectResult[B]]) -> EffectResult[B]:
        if self.is_ok:
            return fn(self.value)
        return EffectResult(error=self.error)


class Effect:
    """函数式效果模式 (对应 Effect-TS's Effect module)"""

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

    @staticmethod
    def sync(fn: Callable[[], T]) -> EffectResult[T]:
        try:
            return EffectResult(value=fn())
        except Exception as e:
            return EffectResult(error=e)

    @staticmethod
    def try_except(fn: Callable[[], T], catch: Callable[[Exception], E]) -> EffectResult[T]:
        try:
            return EffectResult(value=fn())
        except Exception as e:
            return EffectResult(error=catch(e))

    @staticmethod
    def async_of(coro: Coroutine[Any, Any, T]) -> Awaitable[EffectResult[T]]:
        async def _run():
            try:
                r = await coro
                return EffectResult(value=r)
            except Exception as e:
                return EffectResult(error=e)

        return _run()

    @staticmethod
    def map(result: EffectResult[T], fn: Callable[[T], B]) -> EffectResult[B]:
        return result.map(fn)

    @staticmethod
    def flat_map(result: EffectResult[T], fn: Callable[[T], EffectResult[B]]) -> EffectResult[B]:
        return result.flat_map(fn)


class Option:
    """可选值模式 (对应 Effect-TS's Option)"""

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


class NodeInfo:
    """运行时环境信息 (对应 node.ts)"""

    @property
    def version(self) -> str:
        return f"python {sys.version.split()[0]}"

    @property
    def platform(self) -> str:
        return platform.system().lower()

    @property
    def arch(self) -> str:
        return platform.machine()


node_info = NodeInfo()


__all__ = [
    "EffectResult",
    "Effect",
    "Option",
    "NodeInfo",
    "node_info",
]
