"""同步路由 — 移植自 routes/instance/sync.ts

工作区同步启动、重放、历史查询。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from craft.config.load import get_config

logger = logging.getLogger(__name__)


class SyncRoutes:
    """同步路由处理器

    对应 TS SyncRoutes
    """

    @staticmethod
    async def start(request: Any) -> Any:
        """POST /sync/start

        启动工作区同步。
        """
        cfg = get_config()
        project_id = ""
        cwd = os.getcwd()
        if hasattr(cfg, "project") and cwd in cfg.project:
            project_id = cfg.project[cwd].id if hasattr(cfg.project[cwd], "id") else cwd
        else:
            project_id = cwd

        logger.info("Workspace sync start", extra={"project_id": project_id})
        return True

    @staticmethod
    async def replay(request: Any) -> Any:
        """POST /sync/replay

        重放同步事件。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        directory = body.get("directory", "")
        events = body.get("events", [])

        if events:
            source = events[0].get("aggregateID", "unknown")
            logger.info(
                "Sync replay",
                extra={
                    "session_id": source,
                    "events": len(events),
                    "directory": directory,
                },
            )
            return {"sessionID": source}

        return {"sessionID": ""}

    @staticmethod
    async def history(request: Any) -> Any:
        """POST /sync/history

        获取同步事件历史。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        # body is a dict of aggregate_id -> last_known_seq
        # Return events with seq > last_known_seq
        # Currently no DB-backed event store; return empty
        return []
