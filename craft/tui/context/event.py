"""
Event 上下文 — 移植自 context/event.ts

事件订阅，过滤同步事件和工作区/目录特定事件。
"""

from __future__ import annotations

from typing import Any, Callable, Optional


class EventContext:
    """事件上下文 — 管理事件订阅和过滤"""

    def __init__(self, sdk_event: Any = None):
        self._sdk_event = sdk_event

    def subscribe(self, handler: Callable) -> Callable:
        """订阅所有事件（过滤 sync 事件）"""
        if self._sdk_event is None:
            return lambda: None  # no-op

        def _wrapped(event):
            payload = getattr(event, "payload", event) if hasattr(event, "payload") else event
            if isinstance(payload, dict) and payload.get("type") == "sync":
                return
            handler(payload)

        return self._sdk_event.on("event", _wrapped)

    def on(self, event_type: str, handler: Callable) -> Callable:
        """订阅特定类型的事件"""
        def _filtered(event):
            if event.get("type") != event_type:
                return
            handler(event)

        return self.subscribe(_filtered)
