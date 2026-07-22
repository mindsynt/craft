"""全局路由 — 移植自 routes/global.ts

健康检查、事件订阅、配置管理、升级等全局 API。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 事件队列容量
EVENT_QUEUE_CAPACITY = int(os.environ.get("CRAFT_EVENT_QUEUE_CAPACITY", "10000"))


class GlobalRoutes:
    """全局路由处理器

    对应 TS GlobalRoutes
    """

    @staticmethod
    async def health(request: Any) -> Any:
        """GET /global/health

        返回服务器健康状态和版本信息。
        """
        return {
            "healthy": True,
            "version": os.environ.get("CRAFT_VERSION", "0.1.0"),
        }

    @staticmethod
    async def event_stream(request: Any) -> Any:
        """GET /global/event

        SSE 事件流订阅。
        """
        logger.info("Global event connected")

        async def event_generator():
            # 发送连接事件
            yield _sse_json({"type": "server.connected", "properties": {}})

            # 每 10 秒发心跳
            while True:
                await asyncio.sleep(10)
                yield _sse_json({"type": "server.heartbeat", "properties": {}})

        return event_generator()

    @staticmethod
    async def get_config(request: Any) -> Any:
        """GET /global/config

        获取全局配置。
        """
        # TODO: 接入 Config.Service
        return {
            "config": {},
        }

    @staticmethod
    async def update_config(request: Any) -> Any:
        """PATCH /global/config

        更新全局配置。
        """
        # TODO: 接入 Config.Service
        return {}

    @staticmethod
    async def dispose(request: Any) -> Any:
        """POST /global/dispose

        销毁所有实例。
        """
        # TODO: 接入 Instance.disposeAll()
        return True

    @staticmethod
    async def upgrade(request: Any) -> Any:
        """POST /global/upgrade

        升级 craft。
        """
        # TODO: 接入 Installation
        return {
            "success": True,
            "version": os.environ.get("CRAFT_VERSION", "0.1.0"),
        }

    @staticmethod
    async def import_scan(request: Any) -> Any:
        """GET /global/import/scan

        扫描外部会话源。
        """
        # TODO: 接入 ExternalImport
        return {}

    @staticmethod
    async def import_run(request: Any) -> Any:
        """POST /global/import/run

        导入外部会话。
        """
        # TODO: 接入 ExternalImport
        return {}


def _sse_json(data: dict) -> str:
    """格式化为 SSE 数据"""
    return f"data: {json.dumps(data)}\n\n"
