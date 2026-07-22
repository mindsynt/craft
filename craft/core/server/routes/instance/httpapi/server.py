"""实验性 HTTP API 路由 — 移植自 routes/instance/httpapi/server.ts

基于 Effect HttpApi 的实验性 API 服务器。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExperimentalHttpApiServer:
    """实验性 HTTP API 服务器

    对应 TS ExperimentalHttpApiServer
    """

    @staticmethod
    def web_handler() -> Any:
        """获取 Web 处理器

        对应 TS webHandler
        """
        # TODO: 实现 Effect HttpApi 风格的 Web 处理器
        logger.info("Experimental HttpApi web handler requested (not yet implemented)")
        return type("WebHandler", (), {"handler": None})()
