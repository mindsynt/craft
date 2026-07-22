"""IIFE (立即执行函数) — 移植自 iife.ts

提供立即执行函数的工具，用于延迟求值或创建作用域。
"""

from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def iife(fn: Callable[[], T]) -> T:
    """立即执行函数

    对应 TS iife()。立即调用 fn 并返回其结果。
    用于创建独立作用域或延迟求值。
    """
    return fn()
