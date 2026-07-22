"""
事件总线 — 移植自 packages/opencode/src/bus/
组件间解耦通信：发布/订阅模式
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]


class BusEvent:
    def __init__(self, type: str, data: dict | None = None):
        self.id = f"evt_{uuid.uuid4().hex[:8]}"
        self.type = type
        self.data = data or {}
        self.timestamp = None
        self._stopped = False

    def stop(self):
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped


class EventBus:
    _instance = None
    _handlers: dict[str, list[Handler]]
    _middleware: list[Handler]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
            cls._instance._middleware = []
        return cls._instance

    def on(self, event_type: str):
        """注册事件监听器（装饰器）"""
        def decorator(fn: Handler):
            self._handlers.setdefault(event_type, []).append(fn)
            return fn
        return decorator

    def off(self, event_type: str, handler: Handler | None = None):
        """移除监听器"""
        if handler:
            self._handlers.get(event_type, []).remove(handler)
        else:
            self._handlers.pop(event_type, None)

    async def emit(self, event_type: str, data: dict | None = None):
        """发射事件"""
        event = BusEvent(event_type, data)
        for mw in self._middleware:
            mw(event)
            if event.stopped:
                return
        for handler in self._handlers.get(event_type, []):
            try:
                r = handler(event)
                if hasattr(r, "__await__"):
                    await r
            except Exception as e:
                logger.error(f"[Bus] handler error {event_type}: {e}")

    def use(self, middleware: Handler):
        """注册中间件"""
        self._middleware.append(middleware)

    def handlers(self, event_type: str) -> list[Handler]:
        return self._handlers.get(event_type, [])

    def event_types(self) -> list[str]:
        return list(self._handlers.keys())

    # 标准事件类型
    class Types:
        CONFIG_CHANGED = "config:changed"
        SESSION_CREATED = "session:created"
        SESSION_DELETED = "session:deleted"
        AGENT_START = "agent:start"
        AGENT_RESPONSE = "agent:response"
        AGENT_ERROR = "agent:error"
        TOOL_CALL = "tool:call"
        TOOL_RESULT = "tool:result"
        MEMORY_ADDED = "memory:added"
        MEMORY_SEARCHED = "memory:searched"
        SYSTEM_ERROR = "system:error"
        WORKFLOW_START = "workflow:start"
        WORKFLOW_COMPLETE = "workflow:complete"


bus = EventBus()
