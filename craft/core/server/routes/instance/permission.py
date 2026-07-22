"""权限路由 — 移植自 routes/instance/permission.ts

权限请求列表、回复、skip-all 状态。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PermissionRoutes:
    """权限路由处理器

    对应 TS PermissionRoutes
    """

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /permission/:requestID/reply
        
        回复权限请求。
        """
        # TODO: 接入 Permission.Service
        return True

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /permission/
        
        列出待处理的权限请求。
        """
        # TODO: 接入 Permission.Service
        return []

    @staticmethod
    async def skip_all(request: Any) -> Any:
        """GET /permission/skip-all
        
        获取 skip-all 状态。
        """
        # TODO: 接入 Permission.Service
        return False

    @staticmethod
    async def set_skip_all(request: Any) -> Any:
        """POST /permission/skip-all
        
        设置 skip-all 状态。
        """
        # TODO: 接入 Permission.Service
        return False
