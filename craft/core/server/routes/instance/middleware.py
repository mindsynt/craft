"""实例中间件 — 移植自 routes/instance/middleware.ts

为请求提供实例上下文（目录解析、工作区提供）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable

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
        directory = os.getcwd()

    # URL 解码
    try:
        from urllib.parse import unquote
        directory = unquote(directory)
    except Exception:
        pass

    # 检查目录权限（仅在无密码时）
    password = os.environ.get("CRAFT_SERVER_PASSWORD")
    if not password:
        cwd = os.getcwd()
        # 检查目录是否在 cwd 内
        if not os.path.abspath(directory).startswith(os.path.abspath(cwd)):
            return type("Response", (), {
                "status": 403,
                "body": '{"error": "Access denied: directory must be within the server\'s working directory"}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

    # TODO: 设置 WorkspaceContext 和 Instance 上下文
    return await next_handler(request)
