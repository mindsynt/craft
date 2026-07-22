"""API 服务 — 移植自 packages/opencode/src/server/

HTTP 服务、路由、事件、会话管理
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ServerEvent:
    """服务事件 — 对应 TS Server Event"""

    def __init__(self, type: str, data: dict | None = None, session_id: str = ""):
        self.type = type
        self.data = data or {}
        self.session_id = session_id

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "data": self.data,
            "session_id": self.session_id,
        })


class ServerConfig:
    """服务器配置 — 对应 TS Server Config"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 17890,
        cors: list[str] | None = None,
        no_auth: bool = False,
        mdns: bool = False,
        mdns_domain: str | None = None,
    ):
        self.host = host
        self.port = port
        self.cors = cors or []
        self.no_auth = no_auth
        self.mdns = mdns
        self.mdns_domain = mdns_domain

    @classmethod
    def from_env(cls):
        """从环境变量创建默认配置"""
        import os

        return cls(
            host=os.environ.get("CRAFT_HOST", "127.0.0.1"),
            port=int(os.environ.get("CRAFT_PORT", "17890")),
            cors=os.environ.get("CRAFT_CORS", "").split(",") if os.environ.get("CRAFT_CORS") else [],
            no_auth=os.environ.get("CRAFT_NO_AUTH", "").lower() in ("1", "true"),
            mdns=os.environ.get("CRAFT_MDNS", "").lower() in ("1", "true"),
            mdns_domain=os.environ.get("CRAFT_MDNS_DOMAIN"),
        )


def create_server_config() -> ServerConfig:
    """创建默认服务器配置 (向后兼容)"""
    return ServerConfig.from_env()


# Re-export submodules (lazy imports for subpackages)
from craft.core.server import adapter
from craft.core.server import auth
from craft.core.server import error
from craft.core.server import event
from craft.core.server import fence
from craft.core.server import mdns
from craft.core.server import middleware
from craft.core.server import projectors
from craft.core.server import proxy
from craft.core.server import pty_ticket
from craft.core.server import rate_limit
from craft.core.server import server
from craft.core.server import workspace

__all__ = [
    "ServerEvent",
    "ServerConfig",
    "adapter",
    "auth",
    "error",
    "event",
    "fence",
    "mdns",
    "middleware",
    "projectors",
    "proxy",
    "pty_ticket",
    "rate_limit",
    "server",
    "workspace",
]
