"""配置路由 — 移植自 routes/instance/config.ts

获取和更新实例配置。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConfigRoutes:
    """配置路由处理器

    对应 TS ConfigRoutes
    """

    @staticmethod
    async def get(request: Any) -> Any:
        """GET /config
        
        获取配置。
        """
        # TODO: 接入 Config.Service
        return {}

    @staticmethod
    async def update(request: Any) -> Any:
        """PATCH /config
        
        更新配置。
        """
        # TODO: 接入 Config.Service
        return {}

    @staticmethod
    async def providers(request: Any) -> Any:
        """GET /config/providers
        
        列出已配置的提供商。
        """
        # TODO: 接入 Provider.Service
        return {"providers": [], "default": {}}
