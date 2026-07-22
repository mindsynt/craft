"""工作区路由中间件 — 移植自 workspace.ts

根据工作区配置，将请求路由到本地实例或远程代理。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# 路由规则
_RULES: list[dict[str, Any]] = [
    {"path": "/session/status", "action": "forward"},
    {"method": "GET", "path": "/session", "action": "local"},
]


def _local(method: str, path: str) -> bool:
    """检查路径是否应该在本地处理

    对应 TS local()
    """
    for rule in _RULES:
        if rule.get("method") and rule["method"] != method:
            continue
        match = (
            path == rule["path"]
            or path.startswith(rule["path"] + "/")
        )
        if match:
            return rule["action"] == "local"
    return False


async def workspace_middleware(
    request: Any,
    next_handler: Callable[[Any], Awaitable[Any]],
) -> Any:
    """工作区路由中间件

    对应 TS WorkspaceRouterMiddleware
    根据请求的 session 信息，将请求路由到对应的工作区实例或代理。
    """
    from urllib.parse import urlparse, parse_qs

    url_str = getattr(request, "url", "")
    parsed = urlparse(url_str)
    path = parsed.path
    method = getattr(request, "method", "GET")

    # 检查是否是本地路径
    if _local(method, path):
        return await next_handler(request)

    # TODO: 实现工作区查找和路由逻辑
    return await next_handler(request)
