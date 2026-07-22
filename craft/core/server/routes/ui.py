"""UI 路由 — 移植自 routes/ui.ts

静态 Web UI 文件服务。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class UIRoutes:
    """UI 路由处理器

    对应 TS UIRoutes
    """

    @staticmethod
    async def serve_ui(request: Any) -> Any:
        """GET /*

        服务 Web UI 静态文件或返回错误。
        """
        # 检查是否有嵌入的 Web UI
        ui_disabled = os.environ.get("CRAFT_DISABLE_EMBEDDED_WEB_UI", "").lower() in ("1", "true")
        if ui_disabled:
            return type("Response", (), {
                "status": 503,
                "body": '{"error": "Web UI is temporarily unavailable."}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

        # TODO: 从嵌入式资源或 dist 目录加载 UI
        return type("Response", (), {
            "status": 404,
            "body": '{"error": "Not Found"}',
            "headers": {"Content-Type": "application/json"},
            "content_type": "application/json",
        })()
