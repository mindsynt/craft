"""Effect Bridge — 上下文恢复"""

from __future__ import annotations

import asyncio
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    TypeVar,
)

from .instance_state import InstanceRef, WorkspaceRef

R = TypeVar("R")
A = TypeVar("A")


class EffectBridge:
    """
    Effect Bridge — 提供 promise/fork 功能, 自动恢复实例/工作区上下文
    对应 bridge.ts 的 Shape
    """

    def __init__(
        self,
        instance: Any = None,
        workspace: str | None = None,
    ):
        self._instance = instance
        self._workspace = workspace

    def _restore_context(self, fn: Callable[[], R]) -> R:
        """在保存的上下文中执行函数"""
        prev_instance = InstanceRef.get()
        prev_workspace = WorkspaceRef.get()
        try:
            if self._instance is not None:
                InstanceRef.set(self._instance)
            if self._workspace is not None:
                WorkspaceRef.set(self._workspace)
            return fn()
        finally:
            if self._instance is not None:
                InstanceRef.set(prev_instance)
            if self._workspace is not None:
                WorkspaceRef.set(prev_workspace)

    def promise(self, coro_factory: Callable[[], Coroutine[Any, Any, A]]) -> Awaitable[A]:
        """在恢复的上下文中运行协程"""
        return self._restore_context(coro_factory)

    def fork(self, coro_factory: Callable[[], Coroutine[Any, Any, A]]) -> asyncio.Task[A]:
        """在恢复的上下文中派生子任务"""
        coro = self._restore_context(coro_factory)
        return asyncio.ensure_future(coro)

    @staticmethod
    async def make(
        instance: Any = None,
        workspace: str | None = None,
    ) -> EffectBridge:
        return EffectBridge(instance=instance, workspace=workspace)


__all__ = [
    "EffectBridge",
]
