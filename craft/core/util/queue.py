import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class AsyncQueue(Generic[T]):
    """异步队列 — 移植自 queue.ts AsyncQueue"""

    def __init__(self, capacity: int = 0):
        self._queue: list[T] = []
        self._resolvers: list[asyncio.Future] = []
        self._capacity = capacity if capacity > 0 else float("inf")  # type: ignore
        self.dropped = 0

    def push(self, item: T):
        if self._resolvers:
            fut = self._resolvers.pop(0)
            fut.set_result(item)
            return
        if len(self._queue) >= self._capacity:
            self._queue.pop(0)
            self.dropped += 1
        self._queue.append(item)

    @property
    def size(self) -> int:
        return len(self._queue)

    async def next(self) -> T:
        if self._queue:
            return self._queue.pop(0)
        fut = asyncio.get_event_loop().create_future()
        self._resolvers.append(fut)
        return await fut

    def __aiter__(self) -> AsyncIterator[T]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[T]:
        while True:
            yield await self.next()


async def work_parallel(concurrency: int, items: list[T], fn: Callable[[T], Awaitable[None]]):
    """并发执行 — 移植自 queue.ts work"""
    pending = list(reversed(items))

    async def worker():
        while True:
            try:
                item = pending.pop()
            except IndexError:
                return
            await fn(item)

    await asyncio.gather(*[worker() for _ in range(concurrency)])
