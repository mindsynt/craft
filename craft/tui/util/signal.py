"""
信号 — 移植自 util/signal.ts

Solid.js 响应式信号机制的 Python 模拟：防抖信号和淡入效果。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional


class DebouncedSignal:
    """防抖信号：值变化后延迟更新"""

    def __init__(self, initial: Any, delay_ms: float):
        self._value = initial
        self._delay = delay_ms / 1000.0
        self._timer: Optional[asyncio.TimerHandle] = None
        self._listeners: list[Callable] = []

    def get(self):
        return self._value

    def set(self, value: Any):
        self._schedule(value)

    def _schedule(self, value: Any):
        loop = asyncio.get_event_loop()

        async def _apply():
            self._value = value
            for listener in self._listeners:
                listener(value)

        if self._timer:
            self._timer.cancel()
        self._timer = loop.call_later(self._delay, lambda: asyncio.create_task(_apply()))

    def subscribe(self, listener: Callable):
        self._listeners.append(listener)

    def dispose(self):
        if self._timer:
            self._timer.cancel()


class FadeInSignal:
    """淡入信号：模拟 SolidJS createFadeIn 效果"""

    def __init__(self, show: bool, enabled: bool = True):
        self._alpha = 1.0 if show else 0.0
        self._revealed = show
        self._enabled = enabled
        self._listeners: list[Callable] = []
        self._timer: Optional[asyncio.TimerHandle] = None

    def set_visible(self, visible: bool):
        if not visible:
            self._alpha = 0.0
            self._notify()
            return

        if not self._enabled or self._revealed:
            self._revealed = True
            self._alpha = 1.0
            self._notify()
            return

        # Animate: ease-out cubic
        start = time.time()
        self._revealed = True
        self._alpha = 0.0

        async def _animate():
            nonlocal start
            duration = 0.16  # 160ms
            while True:
                elapsed = time.time() - start
                progress = min(elapsed / duration, 1.0)
                # ease-out cubic
                self._alpha = 1.0 - (1.0 - progress) ** 3
                self._notify()
                if progress >= 1.0:
                    break
                await asyncio.sleep(0.016)

        asyncio.create_task(_animate())

    def get_alpha(self) -> float:
        return self._alpha

    def subscribe(self, listener: Callable):
        self._listeners.append(listener)

    def _notify(self):
        for listener in self._listeners:
            listener(self._alpha)

    def dispose(self):
        if self._timer:
            self._timer.cancel()
        self._listeners.clear()
