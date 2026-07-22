"""配置路由 — 移植自 routes/instance/config.ts

获取和更新实例配置。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.config.load import load_config, get_config, reload_config
from craft.core.provider.registry import PROVIDER_MAP

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
        cfg = get_config()
        return cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.__dict__

    @staticmethod
    async def update(request: Any) -> Any:
        """PATCH /config

        更新配置。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        if body:
            cfg = get_config()
            for key, value in body.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)

        return body

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
            default[pid] = cfg.provider.get(pid, type("", (), {"model": ""})).model if pid in cfg.provider else ""

        return {
            "providers": providers,
            "default": default,
        }
