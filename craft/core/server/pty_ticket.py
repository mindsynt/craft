"""PTY 连接票据 — 移植自 pty-ticket.ts

为 PTY WebSocket 连接提供一次性认证票据。
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

# 查询参数名
PTY_CONNECT_TICKET_QUERY = "ticket"
PTY_CONNECT_TOKEN_HEADER = "x-craft-ticket"
PTY_CONNECT_TOKEN_HEADER_VALUE = "1"

# PTY 连接路径匹配
PTY_CONNECT_PATH = re.compile(r"^/pty/[^/]+/connect$")

# 默认 TTL (60 秒)
DEFAULT_TTL_MS = 60_000

# 票据存储
_store: dict[str, dict[str, Any]] = {}


def _gc():
    """清理过期票据"""
    now = time.time() * 1000
    expired = [k for k, v in _store.items() if v["expires_at"] <= now]
    for k in expired:
        _store.pop(k, None)


def is_pty_connect_path(pathname: str) -> bool:
    """检查路径是否为 PTY 连接路径"""
    return bool(PTY_CONNECT_PATH.match(pathname))


def issue(pty_id: str, ttl: int = DEFAULT_TTL_MS) -> dict[str, Any]:
    """签发一次性连接票据

    对应 TS issue()
    """
    _gc()
    ticket = str(uuid.uuid4())
    _store[ticket] = {
        "pty_id": pty_id,
        "expires_at": (time.time() * 1000) + ttl,
    }
    return {
        "ticket": ticket,
        "expires_in": round(ttl / 1000),
    }


def consume(ticket: str, pty_id: str) -> bool:
    """消费票据（验证并删除）

    对应 TS consume()
    """
    record = _store.get(ticket)
    if not record:
        return False
    _store.pop(ticket, None)
    if record["expires_at"] <= (time.time() * 1000):
        return False
    return record["pty_id"] == pty_id
