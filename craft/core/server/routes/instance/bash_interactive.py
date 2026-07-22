"""交互式 Bash 路由 — 移植自 routes/instance/bash-interactive.ts

交互式 Bash 请求列表和回复。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from craft.core.inbox import Inbox

logger = logging.getLogger(__name__)

inbox = Inbox()
_bash_requests: dict[str, dict[str, Any]] = {}


class BashInteractiveRoutes:
    """交互式 Bash 路由处理器

    对应 TS BashInteractiveRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /bash-interactive/

        列出待处理的交互式 Bash 请求。
        """
        return list(_bash_requests.values())

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /bash-interactive/:id/reply

        回复交互式 Bash 请求。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        output = body.get("output", "")
        exit_code = body.get("exitCode", 0)

        req = _bash_requests.pop(request_id, None)
        if req:
            inbox.mark_read(request_id)

        logger.info(
            "Bash interactive reply",
            extra={"request_id": request_id, "exit_code": exit_code},
        )
        return True
