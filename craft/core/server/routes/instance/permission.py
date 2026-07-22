"""权限路由 — 移植自 routes/instance/permission.ts

权限请求列表、回复、skip-all 状态。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.core.inbox import Inbox

logger = logging.getLogger(__name__)

inbox = Inbox()
_skip_all_enabled = False


class PermissionRoutes:
    """权限路由处理器

    对应 TS PermissionRoutes
    """

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /permission/:requestID/reply

        回复权限请求。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        reply_value = body.get("reply", "allow")
        message = body.get("message", "")

        inbox.mark_read(request_id)
        logger.info(
            "Permission reply",
            extra={"request_id": request_id, "reply": reply_value, "message": message},
        )
        return True

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /permission/

        列出待处理的权限请求。
        """
        items = inbox.list(unread_only=True)
        permissions = []
        for item in items:
            if item.get("type") == "permission" or item.get("actionable", False):
                permissions.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "source": item.get("source", "system"),
                    "createdAt": item.get("created_at", 0),
                })
        return permissions

    @staticmethod
    async def skip_all(request: Any) -> Any:
        """GET /permission/skip-all

        获取 skip-all 状态。
        """
        return _skip_all_enabled

    @staticmethod
    async def set_skip_all(request: Any) -> Any:
        """POST /permission/skip-all

        设置 skip-all 状态。
        """
        global _skip_all_enabled
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass
        _skip_all_enabled = body.get("enabled", False)
        return _skip_all_enabled
