"""HTTP API 提供商路由 — 移植自 routes/instance/httpapi/provider.ts
"""

from __future__ import annotations

from typing import Any

from craft.config.load import get_config
from craft.core.provider.registry import PROVIDER_MAP


class ProviderApi:
    """提供商 API — 实验性 HttpApi 版本"""

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /provider

        列出所有提供商。
        """
        cfg = get_config()
        disabled = set(cfg.disabled_providers or [])
        enabled = set(cfg.enabled_providers) if cfg.enabled_providers else None

        all_providers = []
        for key in PROVIDER_MAP:
            if (enabled and key not in enabled) or key in disabled:
                continue
            all_providers.append({
                "id": key,
                "name": key.capitalize(),
                "models": cfg.provider.get(key, None),
            })

        connected = {}
        for pid, pcfg in cfg.provider.items():
            if pcfg.api_key:
                connected[pid] = {
                    "id": pid,
                    "name": pid.capitalize(),
                }

        default = {}
        for pid in PROVIDER_MAP:
            default[pid] = (
                cfg.provider.get(pid, type("", (), {"model": ""})).model
                if pid in cfg.provider
                else ""
            )

        return {
            "all": all_providers,
            "default": default,
            "connected": list(connected.keys()),
        }

    @staticmethod
    async def auth(request: Any) -> Any:
        """GET /provider/auth

        获取认证方法。
        """
        cfg = get_config()
        methods = {}
        for pid, pcfg in cfg.provider.items():
            has_key = bool(pcfg.api_key)
            methods[pid] = {"apiKey": has_key, "oauth": False}
        return methods

    @staticmethod
    async def authorize(request: Any, provider_id: str) -> Any:
        """POST /provider/:providerID/oauth/authorize

        发起 OAuth 授权。
        """
        return {"error": "OAuth not implemented", "status": 501}

    @staticmethod
    async def callback(request: Any, provider_id: str) -> Any:
        """POST /provider/:providerID/oauth/callback

        处理 OAuth 回调。
        """
        return True
