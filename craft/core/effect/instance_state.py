"""实例状态管理 — InstanceRef, WorkspaceRef, InstanceState, Disposer"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    NamedTuple,
    TypeVar,
)

T = TypeVar("T")
B = TypeVar("B")


# =============================================================================
# instance-ref.ts — 实例引用 / 工作区引用 (Context Reference 等价)
# =============================================================================

# 全局状态: 用于在当前上下文中广播 instance / workspace
_current_instance: threading.local = threading.local()
_current_workspace: threading.local = threading.local()


class InstanceRef:
    """实例引用 — 类似 Effect-TS Context.Reference<InstanceContext>"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_instance, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_instance.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_instance, "value"):
            del _current_instance.value


class WorkspaceRef:
    """工作区引用 — 类似 Effect-TS Context.Reference<WorkspaceID>"""

    @staticmethod
    def get() -> str | None:
        return getattr(_current_workspace, "value", None)

    @staticmethod
    def set(value: str) -> None:
        _current_workspace.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_workspace, "value"):
            del _current_workspace.value


# =============================================================================
# instance-registry.ts — 实例处置器注册表
# =============================================================================


class Disposer(NamedTuple):
    fn: Callable[[str], Awaitable[None]]
    phase: str  # "normal" | "late"


_instance_disposers: set[Disposer] = set()
_disposers_lock = threading.Lock()


def register_disposer(
    fn: Callable[[str], Awaitable[None]],
    phase: str = "normal",
) -> Callable[[], None]:
    """注册一个实例释放回调"""
    entry = Disposer(fn=fn, phase=phase)
    with _disposers_lock:
        _instance_disposers.add(entry)

    def unregister() -> None:
        with _disposers_lock:
            _instance_disposers.discard(entry)

    return unregister


async def dispose_instance(directory: str) -> None:
    """释放指定目录下的所有实例资源"""
    normal: list[Disposer] = []
    late: list[Disposer] = []
    with _disposers_lock:
        for d in _instance_disposers:
            if d.phase == "late":
                late.append(d)
            else:
                normal.append(d)

    # 先 normal, 再 late
    results_normal = await asyncio.gather(
        *[d.fn(directory) for d in normal], return_exceptions=True
    )
    results_late = await asyncio.gather(
        *[d.fn(directory) for d in late], return_exceptions=True
    )
    # 静默吞掉所有异常 (Promise.allSettled 语义)
    for r in results_normal + results_late:
        if isinstance(r, Exception):
            logging.getLogger("effect.dispose").warning(
                "dispose_instance error: %s", r
            )


# =============================================================================
# instance-state.ts — 实例状态管理 (ScopedCache 等价)
# =============================================================================


class InstanceState(Generic[T]):
    """
    实例状态 — 基于目录的缓存管理器 (对应 instance-state.ts)
    类似于 Effect-TS ScopedCache<string, A>
    """

    def __init__(
        self,
        init: Callable[[Any], T | Awaitable[T]],
        phase: str = "normal",
    ):
        self._init = init
        self._cache: dict[str, T] = {}
        self._lock = asyncio.Lock()
        self._off = register_disposer(
            lambda d: self._invalidate(d), phase=phase
        )

    async def _invalidate(self, directory: str) -> None:
        async with self._lock:
            self._cache.pop(directory, None)

    async def get(self, ctx: Any = None) -> T:
        dir_key = str(ctx) if ctx is not None else "default"
        async with self._lock:
            if dir_key in self._cache:
                return self._cache[dir_key]
            value = self._init(ctx)
            if hasattr(value, "__await__"):
                value = await value  # type: ignore
            self._cache[dir_key] = value  # type: ignore
            return self._cache[dir_key]  # type: ignore

    async def has(self, ctx: Any = None) -> bool:
        dir_key = str(ctx) if ctx is not None else "default"
        async with self._lock:
            return dir_key in self._cache

    async def invalidate(self, ctx: Any = None) -> None:
        dir_key = str(ctx) if ctx is not None else "default"
        await self._invalidate(dir_key)

    @staticmethod
    def make(
        init: Callable[[Any], T | Awaitable[T]],
        phase: str = "normal",
    ) -> InstanceState[T]:
        return InstanceState(init, phase=phase)

    @staticmethod
    def use(state: InstanceState[T], select: Callable[[T], B], ctx: Any = None) -> Awaitable[B]:
        async def _use() -> B:
            value = await state.get(ctx)
            return select(value)
        return _use()


__all__ = [
    "InstanceRef",
    "WorkspaceRef",
    "Disposer",
    "register_disposer",
    "dispose_instance",
    "InstanceState",
]
