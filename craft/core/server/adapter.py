"""服务器适配器接口 — 移植自 adapter.ts

定义 Runtime 和 Adapter 接口，用于在不同运行时（Node/Bun）上启动 HTTP 服务。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ListenOpts:
    """监听选项"""
    port: int
    hostname: str


@dataclass
class Listener:
    """监听器 — 返回 port 和 stop 方法"""
    port: int
    stop: Any  # callable


class Runtime(ABC):
    """运行时抽象 — 对应 TS Runtime interface"""

    @abstractmethod
    def listen(self, opts: ListenOpts) -> Listener:
        """启动 HTTP 服务"""
        ...


class Adapter(ABC):
    """适配器抽象 — 对应 TS Adapter interface"""

    @abstractmethod
    def create(self, app: Any) -> Runtime:
        """从 ASGI 应用创建运行时"""
        ...
