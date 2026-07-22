"""本地上下文 — 移植自 local-context.ts

基于 AsyncLocalStorage 的上下文管理，支持依赖注入模式。
"""

from __future__ import annotations

import contextvars
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class LocalContextNotFoundError(Exception):
    """上下文未找到错误"""
    def __init__(self, name: str):
        self.context_name = name
        super().__init__(f"No context found for {name}")


class LocalContext(Generic[T]):
    """本地上下文

    对应 TS create<T>()。使用 Python contextvars 实现类似 AsyncLocalStorage 的功能。
    """

    def __init__(self, name: str):
        self._name = name
        self._var: contextvars.ContextVar[T | None] = contextvars.ContextVar(
            f"local_context_{name}",
            default=None,
        )

    def use(self) -> T:
        """获取当前上下文值

        对应 TS use()。如果未设置则抛出 NotFound。
        """
        value = self._var.get()
        if value is None:
            raise LocalContextNotFoundError(self._name)
        return value

    def provide(self, value: T, fn: Callable[[], T]) -> T:
        """在指定函数内提供上下文值

        对应 TS provide()。使用 contextvars 在调用栈中注入值。
        """
        token = self._var.set(value)
        try:
            return fn()
        finally:
            self._var.reset(token)

    async def provide_async(self, value: T, fn: Callable[[], T]) -> T:
        """异步版本的 provide"""
        token = self._var.set(value)
        try:
            result = fn()
            if hasattr(result, "__await__"):
                return await result  # type: ignore
            return result  # type: ignore
        finally:
            self._var.reset(token)

    @property
    def name(self) -> str:
        return self._name


def create_context(name: str) -> LocalContext:
    """创建本地上下文实例

    对应 TS create()。
    """
    return LocalContext(name)
