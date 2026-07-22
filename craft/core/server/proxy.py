"""HTTP/WebSocket 代理 — 移植自 proxy.ts

将请求和 WebSocket 连接代理到工作区实例。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from craft.core.server import fence

logger = logging.getLogger(__name__)

# 逐跳头（hop-by-hop headers）
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
}


def _filter_headers(headers: dict[str, str], extra: dict[str, str] | None = None) -> dict[str, str]:
    """过滤逐跳头并添加额外头

    对应 TS headers()
    """
    result = {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}
    # 移除 craft/mimocode 特定头
    result.pop("accept-encoding", None)
    result.pop("x-craft-directory", None)
    result.pop("x-craft-workspace", None)
    if extra:
        result.update(extra)
    return result


def _to_ws_url(url: str) -> str:
    """将 http(s) URL 转换为 ws(s) URL

    对应 TS socket()
    """
    if url.startswith("http://"):
        return "ws://" + url[7:]
    if url.startswith("https://"):
        return "wss://" + url[8:]
    return url


async def http_proxy(
    url: str,
    extra_headers: dict[str, str] | None,
    request: Any,
    workspace_id: str,
) -> Any:
    """HTTP 代理请求

    对应 TS http()
    """
    import httpx

    # 从 request 对象提取信息
    method = getattr(request, "method", "GET")
    headers = getattr(request, "headers", {})
    body = getattr(request, "body", None)

    filtered = _filter_headers(headers, extra_headers)

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=method,
            url=url,
            headers=filtered,
            content=body,
            follow_redirects=False,
        )

    # 处理 fence 同步头
    sync_state = fence.parse(dict(resp.headers))
    next_headers = dict(resp.headers)
    next_headers.pop("content-encoding", None)
    next_headers.pop("content-length", None)

    if sync_state:
        await fence.wait(workspace_id, sync_state)

    return type("Response", (), {
        "status": resp.status_code,
        "body": resp.content,
        "headers": next_headers,
    })()


async def websocket_proxy(
    target: str,
    extra_headers: dict[str, str] | None,
    request: Any,
) -> Any:
    """WebSocket 代理

    对应 TS websocket()
    """
    # TODO: 使用 websockets 库实现 WS 代理
    logger.info(
        "WebSocket proxy requested",
        extra={"target": target},
    )
    raise NotImplementedError("WebSocket proxy not yet implemented")
