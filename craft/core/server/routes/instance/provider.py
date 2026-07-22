"""提供商路由 — 移植自 routes/instance/provider.ts

AI 提供商列表、认证、OAuth。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProviderRoutes:
    """提供商路由处理器

    对应 TS ProviderRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /provider
        
        列出所有提供商。
        """
        # TODO: 接入 Provider.Service
        return {"all": [], "default": {}, "connected": []}

    @staticmethod
    async def auth_methods(request: Any) -> Any:
        """GET /provider/auth
        
        获取认证方法。
        """
        # TODO: 接入 ProviderAuth
        return {}

    @staticmethod
    async def oauth_authorize(request: Any, provider_id: str) -> Any:
        """POST /provider/:providerID/oauth/authorize
        
        发起 OAuth 授权。
        """
        # TODO: 接入 ProviderAuth
        return {}

    @staticmethod
    async def oauth_callback(request: Any, provider_id: str) -> Any:
        """POST /provider/:providerID/oauth/callback
        
        处理 OAuth 回调。
        """
        # TODO: 接入 ProviderAuth
        return True
