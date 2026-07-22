"""中止控制 — 移植自 abort.ts

提供超时中止控制器，支持单一信号及多信号组合。
"""

from __future__ import annotations

import signal as _signal
import threading
from typing import Any


class AbortController:
    """可超时自动中止的控制器

    对应 TS abortAfter()。创建后经过 timeout_seconds 秒自动触发中止。
    """

    def __init__(self, timeout_seconds: float):
        self._aborted = False
        self._reason: Any = None
        self._listeners: list[callable] = []
        self._timer: threading.Timer | None = None

        if timeout_seconds > 0:
            self._timer = threading.Timer(timeout_seconds, self._do_abort)
            self._timer.daemon = True
            self._timer.start()

    def _do_abort(self):
        self._aborted = True
        self._reason = TimeoutError(f"Aborted after timeout")
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass

    @property
    def aborted(self) -> bool:
        return self._aborted

    @property
    def signal(self) -> AbortController:
        """返回自身，与 TS AbortSignal 模式类似"""
        return self

    @property
    def reason(self) -> Any:
        return self._reason

    def add_listener(self, callback: callable):
        self._listeners.append(callback)

    def remove_listener(self, callback: callable):
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def cancel(self):
        """取消超时定时器"""
        if self._timer:
            self._timer.cancel()
            self._timer = None


def abort_after(seconds: float) -> AbortController:
    """创建超时中止控制器 — 移植自 abortAfter()"""
    return AbortController(seconds * 1000 if seconds < 1000 else seconds)


def abort_after_any(seconds: float, *signals: AbortController) -> AbortController:
    """组合多个中止信号 — 移植自 abortAfterAny()

    任一信号中止或超时则中止。
    """
    combined = AbortController(seconds)

    def on_child_abort():
        combined._do_abort()

    for sig in signals:
        sig.add_listener(on_child_abort)

    return combined
