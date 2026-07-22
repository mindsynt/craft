import asyncio


class Lock:
    """异步互斥锁"""

    def __init__(self):
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        self._lock.release()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *args):
        self._lock.release()


class RWLock:
    """读写锁 — 移植自 lock.ts (read/write keyed锁)"""

    def __init__(self):
        self._readers = 0
        self._writer = False
        self._waiting_readers: list[asyncio.Event] = []
        self._waiting_writers: list[asyncio.Event] = []
        self._lock = asyncio.Lock()

    async def read(self) -> "RWLock._ReadGuard":
        async with self._lock:
            if not self._writer and not self._waiting_writers:
                self._readers += 1
                return self._ReadGuard(self)

        event = asyncio.Event()
        async with self._lock:
            self._waiting_readers.append(event)
        await event.wait()
        async with self._lock:
            self._readers += 1
        return self._ReadGuard(self)

    async def write(self) -> "RWLock._WriteGuard":
        async with self._lock:
            if not self._writer and self._readers == 0:
                self._writer = True
                return self._WriteGuard(self)

        event = asyncio.Event()
        async with self._lock:
            self._waiting_writers.append(event)
        await event.wait()
        async with self._lock:
            self._writer = True
        return self._WriteGuard(self)

    async def _release_read(self):
        async with self._lock:
            self._readers -= 1
            self._process()

    async def _release_write(self):
        async with self._lock:
            self._writer = False
            self._process()

    def _process(self):
        if self._writer or self._readers > 0:
            return
        if self._waiting_writers:
            ev = self._waiting_writers.pop(0)
            ev.set()
            return
        while self._waiting_readers:
            ev = self._waiting_readers.pop(0)
            ev.set()

    class _ReadGuard:
        def __init__(self, rw: "RWLock"):
            self._rw = rw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self._rw._release_read()

    class _WriteGuard:
        def __init__(self, rw: "RWLock"):
            self._rw = rw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self._rw._release_write()
