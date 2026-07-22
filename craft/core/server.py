"""
API 服务 — 移植自 packages/opencode/src/server/
HTTP 服务、路由、事件、会话管理
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ServerEvent:
    def __init__(self, type: str, data: dict | None = None, session_id: str = ""):
        self.type = type
        self.data = data or {}
        self.session_id = session_id

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data, "session_id": self.session_id})


class ServerConfig:
    def __init__(self, host: str = "127.0.0.1", port: int = 17890):
        self.host = host
        self.port = port


def create_server_config() -> ServerConfig:
    """创建默认服务器配置"""
    import os
    return ServerConfig(
        host=os.environ.get("CRAFT_HOST", "127.0.0.1"),
        port=int(os.environ.get("CRAFT_PORT", "17890")),
    )
