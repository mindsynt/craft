"""通用运行时 — Runtime"""

from __future__ import annotations

import asyncio
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    TypeVar,
)

from .memo_map import MemoMap

T = TypeVar("T")


class Runtime:
    """
    通用运行时 — 对应 runtime.ts 的 makeRuntime
    封装 ManagedRuntime.runSync / runPromise / runFork 等价
    """

    def __init__(
        self,
        service_name: str,
        layers: list[Any] | None = None,
        memo_map: MemoMap | None = None,
    ):
        self._service_name = service_name
        self._layers = layers or []
        self._memo_map = memo_map or MemoMap()
        self._initialized = False

    def _ensure(self) -> None:
        if not self._initialized:
            self._initialized = True

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        self._ensure()
        return fn(*args, **kwargs)

    def run_promise(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        self._ensure()
        return fn(*args, **kwargs)

    def run_fork(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> asyncio.Task[T]:
        self._ensure()
        return asyncio.ensure_future(fn(*args, **kwargs))

    def run_callback(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        self._ensure()

        async def _wrapped() -> T:
            try:
                result = await fn(*args, **kwargs)
                if on_done:
                    on_done(result)
                return result
            except Exception as e:
                if on_error:
                    on_error(e)
                raise

        return asyncio.ensure_future(_wrapped())

    def dispose(self) -> None:
        self._initialized = False
        self._memo_map.clear()


__all__ = [
    "Runtime",
]
