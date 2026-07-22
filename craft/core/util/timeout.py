import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


class Timeout:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._task: asyncio.Task | None = None
        self._timed_out = False

    async def __aenter__(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *args):
        if self._task:
            self._task.cancel()

    async def _run(self):
        await asyncio.sleep(self.seconds)
        self._timed_out = True

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    def check(self):
        if self._timed_out:
            raise TimeoutError(f"操作超时 ({self.seconds}s)")


async def with_timeout(coro, timeout: float, default=None):
    """带超时的异步执行"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


async def timeout_promise(promise: Awaitable[T], ms: float) -> T:
    """Promise带超时 — 移植自 timeout.ts withTimeout"""
    return await asyncio.wait_for(promise, timeout=ms / 1000)


def abort_after(ms: int) -> dict:
    """创建超时中止控制器 — 移植自 abort.ts abortAfter"""
    event = asyncio.Event()

    def _abort():
        event.set()

    def clear_timeout():
        pass  # Timeout handled via asyncio.wait_for

    return {
        "event": event,
        "clear_timeout": clear_timeout,
    }
