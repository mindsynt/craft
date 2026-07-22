"""速率限制中间件 — 移植自 rate-limit.ts

基于内存窗口的请求速率限制。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from craft.core.server.middleware import Handler, Middleware


class _WindowEntry:
    def __init__(self, window_ms: int):
        self.count = 0
        self.reset_at = (time.time() * 1000) + window_ms


_windows: dict[str, _WindowEntry] = {}
_last_sweep = time.time() * 1000
_SWEEP_INTERVAL = 60_000


def _sweep():
    """清理过期窗口"""
    global _last_sweep
    now = time.time() * 1000
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    expired = [k for k, v in _windows.items() if now >= v.reset_at]
    for k in expired:
        _windows.pop(k, None)


def rate_limit_middleware(
    window_ms: int,
    max_requests: int,
    key_prefix: str | None = None,
) -> Middleware:
    """速率限制中间件工厂

    对应 TS RateLimitMiddleware()
    """
    async def middleware(request: Any, next_handler: Handler) -> Any:
        _sweep()

        path = getattr(request, "path", "/")
        forward_for = ""
        if hasattr(request, "headers"):
            forward_for = request.headers.get("x-forwarded-for", "local")
        key = f"{key_prefix or path}:{forward_for}"

        now = time.time() * 1000
        entry = _windows.get(key)

        if not entry or now >= entry.reset_at:
            entry = _WindowEntry(window_ms)
            _windows[key] = entry

        entry.count += 1

        if entry.count > max_requests:
            retry_after = int((entry.reset_at - now) / 1000)
            response = type("Response", (), {
                "status": 429,
                "body": '{"error": "Too many requests"}',
                "headers": {"Retry-After": str(retry_after), "Content-Type": "application/json"},
                "content_type": "application/json",
            })()
            # 如果 response 有 set_header 方法
            if hasattr(response, "set_header"):
                response.set_header("Retry-After", str(retry_after))
            return response

        return await next_handler(request)

    return middleware
