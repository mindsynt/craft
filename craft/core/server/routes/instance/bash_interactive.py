"""交互式 Bash 路由 — 移植自 routes/instance/bash-interactive.ts

交互式 Bash 请求列表和回复。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BashInteractiveRoutes:
    """交互式 Bash 路由处理器

    对应 TS BashInteractiveRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /bash-interactive/
        
        列出待处理的交互式 Bash 请求。
        """
        # TODO: 接入 BashInteractive.Service
        return []

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /bash-interactive/:id/reply
        
        回复交互式 Bash 请求。
        """
        # TODO: 接入 BashInteractive.Service
        return True
