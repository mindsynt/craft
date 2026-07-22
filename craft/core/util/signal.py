import asyncio


def make_signal():
    """创建信号量 — 移植自 signal.ts (one-shot)"""
    future: asyncio.Future | None = None

    async def wait():
        nonlocal future
        if future is None:
            future = asyncio.get_running_loop().create_future()
        await future

    def trigger():
        nonlocal future
        if future is not None and not future.done():
            future.set_result(None)

    return {"trigger": trigger, "wait": wait}
