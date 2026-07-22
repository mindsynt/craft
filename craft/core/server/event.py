"""服务事件定义 — 移植自 event.ts

定义服务器生命周期事件（连接、销毁等）。
"""

from __future__ import annotations

from typing import Any, Callable


class ServerEventDef:
    """事件定义 — 对应 TS BusEvent.define"""

    def __init__(self, type: str):
        self.type = type

    def __repr__(self) -> str:
        return f"ServerEventDef({self.type!r})"


# 预定义的服务事件
Event = type("Event", (), {
    "Connected": ServerEventDef("server.connected"),
    "Disposed": ServerEventDef("global.disposed"),
    "Heartbeat": ServerEventDef("server.heartbeat"),
})()


class EventBus:
    """简单事件总线 — 对应 TS Bus/EventBus

    用于服务器内部的事件发布/订阅。
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str | ServerEventDef, handler: Callable):
        """订阅事件"""
        key = event.type if isinstance(event, ServerEventDef) else event
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)

    def off(self, event: str | ServerEventDef, handler: Callable):
        """取消订阅"""
        key = event.type if isinstance(event, ServerEventDef) else event
        handlers = self._handlers.get(key, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: str | ServerEventDef, data: Any = None):
        """发布事件"""
        key = event.type if isinstance(event, ServerEventDef) else event
        for handler in self._handlers.get(key, []):
            try:
                handler(data)
            except Exception:
                pass


# 全局事件总线
global_bus = EventBus()
