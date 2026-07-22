"""
事件总线 — 移植自 packages/opencode/src/bus/
组件间解耦通信：发布/订阅模式，支持 BusEvent 定义和全局事件
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── BusEvent 定义系统 ──────────────────────────────────────
# 对应 TS bus/bus-event.ts

_registry: dict[str, dict] = {}


def define_event(type_name: str, properties: dict[str, type]) -> dict:
    """定义总线事件类型

    类似于 TS 的 BusEvent.define()。注册事件类型到全局 registry。
    """
    definition = {
        "type": type_name,
        "properties": properties,
    }
    _registry[type_name] = definition
    return definition


def registered_events() -> list[dict]:
    """获取所有已注册的事件类型"""
    return list(_registry.values())


# ── 全局总线 ────────────────────────────────────────────────
# 对应 TS bus/global.ts

class GlobalEventBus:
    """全局事件发射器 — 跨实例通信"""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event_type: str, callback: Callable):
        self._listeners.setdefault(event_type, []).append(callback)

    def off(self, event_type: str, callback: Callable | None = None):
        if callback:
            try:
                self._listeners.get(event_type, []).remove(callback)
            except ValueError:
                pass
        else:
            self._listeners.pop(event_type, None)

    def emit(self, event_type: str, payload: Any):
        """发射全局事件"""
        for cb in self._listeners.get(event_type, []):
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"[GlobalBus] handler error {event_type}: {e}")


global_bus = GlobalEventBus()


# ── 事件总线 ──────────────────────────────────────────────────
# 对应 TS bus/index.ts

Handler = Callable[..., Any]


class BusEvent:
    """总线事件实例"""

    def __init__(self, type: str, data: dict | None = None):
        self.id = f"evt_{uuid.uuid4().hex[:8]}"
        self.type = type
        self.data = data or {}
        self._stopped = False

    def stop(self):
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped


class EventBus:
    """事件总线 — 发布/订阅模式

    支持:
    - 按事件类型订阅 (subscribe)
    - 通配订阅所有事件 (subscribe_all)
    - 中间件
    - 异步发射
    """
    _instance = None
    _subscribers: dict[str, list[Callable]]
    _wildcard_subscribers: list[Callable]
    _middleware: list[Handler]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers = {}
            cls._instance._wildcard_subscribers = []
            cls._instance._middleware = []
        return cls._instance

    def publish(self, event_type: str, properties: dict | None = None):
        """发布事件（同步）

        类似于 TS Bus.publish()。发送到类型化订阅者和通配订阅者。
        同时也会通过 GlobalBus 广播。
        """
        payload = {"type": event_type, "properties": properties or {}}

        # 类型化订阅
        for cb in self._subscribers.get(event_type, []):
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"[Bus] subscriber error {event_type}: {e}")

        # 通配订阅
        for cb in self._wildcard_subscribers:
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"[Bus] wildcard subscriber error: {e}")

        # 全局广播
        global_bus.emit("event", {
            "payload": payload,
        })

    def on(self, event_type: str):
        """注册事件监听器（装饰器）"""
        def decorator(fn: Handler):
            self._subscribers.setdefault(event_type, []).append(fn)
            return fn
        return decorator

    def off(self, event_type: str, handler: Handler | None = None):
        """移除监听器"""
        if handler:
            try:
                self._subscribers.get(event_type, []).remove(handler)
            except ValueError:
                pass
        else:
            self._subscribers.pop(event_type, None)

    async def emit(self, event_type: str, data: dict | None = None):
        """发射事件（异步）"""
        event = BusEvent(event_type, data)
        for mw in self._middleware:
            mw(event)
            if event.stopped:
                return
        for handler in self._subscribers.get(event_type, []):
            try:
                r = handler(event)
                if hasattr(r, "__await__"):
                    await r
            except Exception as e:
                logger.error(f"[Bus] handler error {event_type}: {e}")

    def use(self, middleware: Handler):
        """注册中间件"""
        self._middleware.append(middleware)

    def subscribe(self, event_type: str, callback: Callable) -> Callable:
        """订阅指定类型的事件 — 返回取消订阅函数"""
        self._subscribers.setdefault(event_type, []).append(callback)

        def unsubscribe():
            self.off(event_type, callback)
        return unsubscribe

    def subscribe_all(self, callback: Callable) -> Callable:
        """订阅所有事件 — 返回取消订阅函数"""
        self._wildcard_subscribers.append(callback)

        def unsubscribe():
            try:
                self._wildcard_subscribers.remove(callback)
            except ValueError:
                pass
        return unsubscribe

    def handlers(self, event_type: str) -> list[Handler]:
        return self._subscribers.get(event_type, [])

    def event_types(self) -> list[str]:
        return list(self._subscribers.keys())

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
        FILE_CHANGED = "file:changed"
        INSTANCE_DISPOSED = "server.instance.disposed"


bus = EventBus()
