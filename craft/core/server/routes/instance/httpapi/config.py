"""HTTP API 配置路由 — 移植自 routes/instance/httpapi/config.ts
"""

from __future__ import annotations

from typing import Any

from craft.config.load import get_config
from craft.core.provider.registry import PROVIDER_MAP


class ConfigApi:
    """配置 API — 实验性 HttpApi 版本"""

    @staticmethod
    async def providers(request: Any) -> Any:
        """GET /config/providers

        列出已配置的提供商。
        """
        cfg = get_config()
        providers = []
        for pid, pcfg in cfg.provider.items():
            providers.append({
                "id": pid,
                "model": pcfg.model if hasattr(pcfg, "model") else "",
                "apiKey": bool(pcfg.api_key) if hasattr(pcfg, "api_key") else False,
            })

        default = {}
        for pid in PROVIDER_MAP:
            default[pid] = (
                cfg.provider.get(pid, type("", (), {"model": ""})).model
                if pid in cfg.provider
                else ""
            )

        return {
            "providers": providers,
            "default": default,
        }
