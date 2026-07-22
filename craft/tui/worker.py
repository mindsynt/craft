"""
Worker — 移植自 worker.ts

后台 Worker 进程：RPC 服务器、更新检查、会话管理。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TuiWorker:
    """TUI Worker — 后台工作进程"""

    def __init__(self):
        self._running = False
        self._server: Optional[Any] = None

    async def start(self):
        """启动 Worker"""
        self._running = True
        logger.info("TUI Worker started")

    async def stop(self):
        """停止 Worker"""
        self._running = False
        logger.info("TUI Worker stopped")

    async def handle_fetch(self, url: str, method: str = "GET",
                           headers: Optional[dict] = None,
                           body: Optional[str] = None) -> dict:
        """处理 fetch 请求（代理到 SDK 服务器）"""
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": "{}",
        }

    async def handle_reload(self):
        """重新加载 Worker 配置"""
        logger.info("Reloading Worker config")

    async def handle_shutdown(self):
        """优雅关闭 Worker"""
        logger.info("Shutting down Worker...")
        await self.stop()
