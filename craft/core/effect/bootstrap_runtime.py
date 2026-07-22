"""启动运行时 — BootstrapRuntime"""

from __future__ import annotations

import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    TypeVar,
)

from .memo_map import memo_map
from .runtime import Runtime

T = TypeVar("T")


class BootstrapRuntime:
    """
    启动运行时 — 对应 bootstrap-runtime.ts
    合并所有默认层并创建 ManagedRuntime
    """

    _instance: BootstrapRuntime | None = None
    _lock = threading.Lock()

    def __init__(self, layers: list[Any] | None = None):
        self._layers = layers or []
        self._runtime = Runtime(
            service_name="bootstrap",
            layers=self._layers,
            memo_map=memo_map,
        )

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return self._runtime.run_sync(fn, *args, **kwargs)

    def run_promise(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        return self._runtime.run_promise(fn, *args, **kwargs)

    def run_fork(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        return self._runtime.run_fork(fn, *args, **kwargs)

    @classmethod
    def get_instance(cls, layers: list[Any] | None = None) -> BootstrapRuntime:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(layers=layers)
            return cls._instance


__all__ = [
    "BootstrapRuntime",
]
