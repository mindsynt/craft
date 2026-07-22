"""PTY 路由 — 移植自 routes/instance/pty.ts

伪终端 (PTY) 会话 CRUD 和 WebSocket 连接。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from craft.core.server.pty_ticket import issue as issue_ticket, consume as consume_ticket

logger = logging.getLogger(__name__)

# In-memory PTY session storage
_pty_sessions: dict[str, dict[str, Any]] = {}


class PtyRoutes:
    """PTY 路由处理器

    对应 TS PtyRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /pty

        列出 PTY 会话。
        """
        return list(_pty_sessions.values())

    @staticmethod
    async def create(request: Any) -> Any:
        """POST /pty

        创建 PTY 会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        pty_id = f"pty_{uuid.uuid4().hex[:12]}"
        session = {
            "id": pty_id,
            "title": body.get("title", f"PTY {pty_id[:8]}"),
            "command": body.get("command", "/bin/bash"),
            "cwd": body.get("cwd", "/"),
            "createdAt": 0,
            "status": "created",
        }
        _pty_sessions[pty_id] = session
        return session

    @staticmethod
    async def get(request: Any, pty_id: str) -> Any:
        """GET /pty/:ptyID

        获取 PTY 详情。
        """
        session = _pty_sessions.get(pty_id)
        if not session:
            return {"error": "Session not found", "status": 404}
        return session

    @staticmethod
    async def update(request: Any, pty_id: str) -> Any:
        """PUT /pty/:ptyID

        更新 PTY 会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = _pty_sessions.get(pty_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        session.update(body)
        return session

    @staticmethod
    async def remove(request: Any, pty_id: str) -> Any:
        """DELETE /pty/:ptyID

        删除 PTY 会话。
        """
        if pty_id in _pty_sessions:
            del _pty_sessions[pty_id]
            return True
        return False

    @staticmethod
    async def connect_token(request: Any, pty_id: str) -> Any:
        """POST /pty/:ptyID/connect-token

        签发连接票据。
        """
        # Check ticket header
        token_header = getattr(request, "headers", {}).get("x-craft-ticket", "")
        if token_header != "1":
            return type("Response", (), {
                "status": 403,
                "body": '{"error": "Forbidden"}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

        if pty_id not in _pty_sessions:
            return {"error": "Session not found", "status": 404}

        return issue_ticket(pty_id)

    @staticmethod
    async def connect(request: Any, pty_id: str) -> Any:
        """GET /pty/:ptyID/connect

        WebSocket 连接到 PTY 会话。
        """
        ticket = None
        if hasattr(request, "query_params"):
            ticket = request.query_params.get("ticket")

        if ticket and not consume_ticket(ticket, pty_id):
            return type("Response", (), {
                "status": 403,
                "body": '{"error": "Invalid or expired ticket"}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

        if pty_id not in _pty_sessions:
            return {"error": "Session not found", "status": 404}

        logger.info("PTY connect requested", extra={"pty_id": pty_id})
        return {"connected": True, "ptyID": pty_id}
