"""应用运行时 — AppRuntime"""

from __future__ import annotations

import asyncio
import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    TypeVar,
)

from .memo_map import memo_map
from .observability import Observability
from .run_service import attach
from .runtime import Runtime

T = TypeVar("T")


class AppRuntime:
    """
    应用运行时 — 对应 app-runtime.ts
    单例模式, 提供全局 runSync / runPromise / runFork 入口
    """

    _instance: AppRuntime | None = None
    _lock = threading.Lock()

    def __init__(self, layers: list[Any] | None = None):
        self._layers = layers or []
        # 使用 Observability 层包裹
        self._runtime = Runtime(
            service_name="app",
            layers=[Observability.layer(el) for el in self._layers],
            memo_map=memo_map,
        )

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        wrapped = attach(fn)
        return self._runtime.run_sync(wrapped, *args, **kwargs)

    def run_promise(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[T]:
        wrapped = attach(fn)
        return self._runtime.run_promise(wrapped, *args, **kwargs)

    def run_promise_exit(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        options: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[T]:
        wrapped = attach(fn)
        return self._runtime.run_promise(wrapped, *args, **kwargs)

    def run_fork(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        wrapped = attach(fn)
        return self._runtime.run_fork(wrapped, *args, **kwargs)

    def run_callback(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        wrapped = attach(fn)
        return self._runtime.run_callback(wrapped, on_done, on_error, *args, **kwargs)

    def dispose(self) -> None:
        self._runtime.dispose()

    @classmethod
    def get_instance(cls, layers: list[Any] | None = None) -> AppRuntime:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(layers=layers)
            return cls._instance


__all__ = [
    "AppRuntime",
]
