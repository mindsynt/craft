"""HTTP API 权限路由 — 移植自 routes/instance/httpapi/permission.ts
"""

from __future__ import annotations

from typing import Any

from craft.core.inbox import Inbox

inbox = Inbox()


class PermissionApi:
    """权限 API — 实验性 HttpApi 版本"""

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /permission

        列出待处理的权限请求。
        """
        items = inbox.list(unread_only=True)
        permissions = []
        for item in items:
            if item.get("actionable", False):
                permissions.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "createdAt": item.get("created_at", 0),
                })
        return permissions

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
        return True
