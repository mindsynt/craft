"""PTY 路由 — 移植自 routes/instance/pty.ts

伪终端 (PTY) 会话 CRUD 和 WebSocket 连接。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.core.server.pty_ticket import issue as issue_ticket, consume as consume_ticket

logger = logging.getLogger(__name__)


class PtyRoutes:
    """PTY 路由处理器

    对应 TS PtyRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /pty
        
        列出 PTY 会话。
        """
        # TODO: 接入 Pty.Service
        return []

    @staticmethod
    async def create(request: Any) -> Any:
        """POST /pty
        
        创建 PTY 会话。
        """
        # TODO: 接入 Pty.Service
        return {}

    @staticmethod
    async def get(request: Any, pty_id: str) -> Any:
        """GET /pty/:ptyID
        
        获取 PTY 详情。
        """
        # TODO: 接入 Pty.Service
        return {}

    @staticmethod
    async def update(request: Any, pty_id: str) -> Any:
        """PUT /pty/:ptyID
        
        更新 PTY 会话。
        """
        # TODO: 接入 Pty.Service
        return {}

    @staticmethod
    async def remove(request: Any, pty_id: str) -> Any:
        """DELETE /pty/:ptyID
        
        删除 PTY 会话。
        """
        # TODO: 接入 Pty.Service
        return True

    @staticmethod
    async def connect_token(request: Any, pty_id: str) -> Any:
        """POST /pty/:ptyID/connect-token
        
        签发连接票据。
        """
        # 检查票据头
        token_header = getattr(request, "headers", {}).get("x-craft-ticket", "")
        if token_header != "1":
            return type("Response", (), {
                "status": 403,
                "body": '{"error": "Forbidden"}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()
        
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

        # TODO: 实现 WebSocket 升级
        logger.info("PTY connect requested", extra={"pty_id": pty_id})
        raise NotImplementedError("WebSocket connect not yet implemented")
