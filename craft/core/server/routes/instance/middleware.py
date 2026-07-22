"""实例中间件 — 移植自 routes/instance/middleware.ts

为请求提供实例上下文（目录解析、工作区提供）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable

from craft.config.load import get_config

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[Any]]


async def instance_middleware(request: Any, next_handler: Handler, workspace_id: str | None = None) -> Any:
    """实例中间件

    对应 TS InstanceMiddleware()
    解析目录参数，提供 Instance 上下文。
    """
    # 从 query 或 header 获取目录
    directory = None
    if hasattr(request, "query_params"):
        directory = request.query_params.get("directory")
    if not directory and hasattr(request, "headers"):
        directory = request.headers.get("x-craft-directory")
        if not directory:
            directory = request.headers.get("x-mimocode-directory")
    if not directory:
        directory = os.getcwd()

    # URL 解码
    try:
        from urllib.parse import unquote
        directory = unquote(directory)
    except Exception:
        pass

    # 解析为绝对路径
    directory = os.path.abspath(directory)

    # 检查目录权限（仅在无密码时）
    password = os.environ.get("CRAFT_SERVER_PASSWORD") or os.environ.get("MIMOCODE_SERVER_PASSWORD")
    if not password:
        cwd = os.path.abspath(os.getcwd())
        # Allow Orchestrator directory
        orchestrator = os.path.join(os.path.expanduser("~"), ".craft", "data", "orchestrator")
        if not directory.startswith(cwd) and directory != orchestrator:
            return type("Response", (), {
                "status": 403,
                "body": '{"error": "Access denied: directory must be within the server\'s working directory"}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

    # Set workspace context
    if workspace_id:
        logger.debug("Setting workspace context", extra={"workspace_id": workspace_id})

    logger.debug("Instance middleware", extra={"directory": directory, "workspace_id": workspace_id})
    return await next_handler(request)
