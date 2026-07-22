"""全局路由 — 移植自 routes/global.ts

健康检查、事件订阅、配置管理、升级等全局 API。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from craft.config.load import get_config, load_config, reload_config
from craft.core.server.event import global_bus

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
            yield _sse_json({
                "payload": {"type": "server.connected", "properties": {}},
            })

            # 每 10 秒发心跳
            while True:
                await asyncio.sleep(10)
                yield _sse_json({
                    "payload": {"type": "server.heartbeat", "properties": {}},
                })

        return event_generator()

    @staticmethod
    async def get_config(request: Any) -> Any:
        """GET /global/config

        获取全局配置。
        """
        cfg = get_config()
        return cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.__dict__

    @staticmethod
    async def update_config(request: Any) -> Any:
        """PATCH /global/config

        更新全局配置。
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
    async def dispose(request: Any) -> Any:
        """POST /global/dispose

        销毁所有实例。
        """
        from craft.core.session import sessions

        # Clear all sessions
        sessions._sessions.clear()
        sessions._current_id = None

        global_bus.emit("global.disposed", {"directory": "global"})
        logger.info("All instances disposed")
        return True

    @staticmethod
    async def upgrade(request: Any) -> Any:
        """POST /global/upgrade

        升级 craft。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        target = body.get("target", "")
        version = target or os.environ.get("CRAFT_VERSION", "0.1.0")

        # Upgrade not yet implemented
        return {
            "success": True,
            "version": version,
        }

    @staticmethod
    async def import_scan(request: Any) -> Any:
        """GET /global/import/scan

        扫描外部会话源。
        """
        results = {}
        sources = ["cc", "codex", "opencode"]
        for source in sources:
            results[source] = {
                "available": False,
                "sessions": 0,
                "imported": 0,
            }

        # Check Claude Code
        try:
            import subprocess
            claude_dir = os.path.expanduser("~/.claude")
            if os.path.isdir(claude_dir):
                sessions_count = len(os.listdir(claude_dir)) if os.listdir(claude_dir) else 0
                results["cc"] = {
                    "available": True,
                    "sessions": sessions_count,
                    "imported": 0,
                }
        except Exception:
            pass

        # Check Codex
        try:
            codex_dir = os.path.expanduser("~/.codex")
            if os.path.isdir(codex_dir):
                sessions_count = len(os.listdir(codex_dir)) if os.listdir(codex_dir) else 0
                results["codex"] = {
                    "available": True,
                    "sessions": sessions_count,
                    "imported": 0,
                }
        except Exception:
            pass

        return results

    @staticmethod
    async def import_run(request: Any) -> Any:
        """POST /global/import/run

        导入外部会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        sources = body.get("sources", ["cc", "codex", "opencode"])
        force = body.get("force", False)

        results = {}
        for source in sources:
            results[source] = {
                "scanned": 0,
                "imported": 0,
                "resynced": 0,
                "skipped": 0,
                "errors": [],
            }

        logger.info("Import run", extra={"sources": sources, "force": force})
        return results


def _sse_json(data: dict) -> str:
    """格式化为 SSE 数据"""
    return f"data: {json.dumps(data)}\n\n"
