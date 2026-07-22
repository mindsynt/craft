import asyncio
import time
from typing import Any, Awaitable, Callable


def memoize(fn: Callable) -> Callable:
    """记忆化"""
    cache = {}

    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = fn(*args, **kwargs)
        return cache[key]

    wrapper.cache = cache
    return wrapper


def debounce(fn: Callable, wait: float = 0.3):
    """防抖"""
    timer = [None]

    async def wrapper(*args, **kwargs):
        if timer[0]:
            timer[0].cancel()
        loop = asyncio.get_event_loop()
        timer[0] = loop.call_later(wait, lambda: asyncio.create_task(fn(*args, **kwargs)))

    return wrapper


def throttle(fn: Callable, interval: float = 1.0):
    """节流"""
    last = 0

    def wrapper(*args, **kwargs):
        nonlocal last
        now = time.time()
        if now - last >= interval:
            last = now
            return fn(*args, **kwargs)

    return wrapper


class Defer:
    """推迟执行 — 移植自 defer.ts"""

    def __init__(self, fn: Callable[[], None | Awaitable[None]]):
        self._fn = fn
        self._done = False

    def __del__(self):
        if not self._done:
            self._done = True
            result = self._fn()
            if hasattr(result, "__await__"):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(result)  # type: ignore
                except RuntimeError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def defer(fn: Callable[[], None | Awaitable[None]]) -> Defer:
    return Defer(fn)
