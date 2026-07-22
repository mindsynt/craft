"""事件流路由 — 移植自 routes/instance/event.ts

SSE 事件订阅端点。
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


class EventRoutes:
    """事件路由处理器

    对应 TS EventRoutes
    """

    @staticmethod
    async def subscribe(request: Any) -> Any:
        """GET /event
        
        SSE 事件流。
        """
        logger.info("Event connected")

        async def event_generator():
            yield _sse_json({"type": "server.connected", "properties": {}})

            while True:
                await asyncio.sleep(10)
                yield _sse_json({"type": "server.heartbeat", "properties": {}})

        return event_generator()


def _sse_json(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
