from typing import Callable, TypeVar

T = TypeVar("T")


def lazy(fn: Callable[[], T]) -> Callable[[], T]:
    """惰性求值 — 移植自 lazy.ts"""
    value: T = None  # type: ignore
    loaded = False

    def wrapper() -> T:
        nonlocal value, loaded
        if not loaded:
            value = fn()
            loaded = True
        return value

    def reset():
        nonlocal value, loaded
        loaded = False
        value = None  # type: ignore

    wrapper.reset = reset  # type: ignore
    return wrapper
