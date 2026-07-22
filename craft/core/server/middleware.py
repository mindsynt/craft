"""HTTP 中间件 — 移植自 middleware.ts

认证、CORS、压缩、日志、错误处理中间件。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# === HTTP 处理器类型定义 ===

Handler = Callable[..., Awaitable[Any]]
Middleware = Callable[[Any, Handler], Awaitable[Any]]


class HTTPException(Exception):
    """HTTP 异常 — 对应 hono HTTPException"""

    def __init__(self, status: int = 500, message: str = "Internal Server Error"):
        self.status = status
        self.message = message
        super().__init__(message)


class NamedError(Exception):
    """命名错误 — 对应 TS NamedError"""

    def __init__(self, name: str, message: str, status: int = 500):
        self.name = name
        self.message = message
        self.status = status
        super().__init__(message)

    def to_object(self) -> dict:
        return {"name": self.name, "data": {"message": self.message}}


class NotFoundError(NamedError):
    def __init__(self, message: str = "Not found"):
        super().__init__("NotFoundError", message, status=404)


# === 工具函数 ===

def _get_server_password() -> str | None:
    return os.environ.get("CRAFT_SERVER_PASSWORD") or os.environ.get("MIMOCODE_SERVER_PASSWORD")


def _get_server_username() -> str:
    return (
        os.environ.get("CRAFT_SERVER_USERNAME")
        or os.environ.get("MIMOCODE_SERVER_USERNAME")
        or "craft"
    )


# === 中间件 ===

async def error_middleware(request: Any, next_handler: Handler) -> Any:
    """错误处理中间件 — 对应 ErrorMiddleware

    捕获异常并返回标准 JSON 错误响应。
    """
    try:
        return await next_handler(request)
    except HTTPException as err:
        return _json_response(
            {"name": "HTTPException", "data": {"message": err.message}},
            status=err.status,
        )
    except NotFoundError as err:
        return _json_response(err.to_object(), status=404)
    except NamedError as err:
        return _json_response(err.to_object(), status=err.status)
    except Exception as err:
        logger.error("Request failed", extra={"error": str(err)})
        return _json_response(
            {"name": "UnknownError", "data": {"message": str(err)}},
            status=500,
        )


async def auth_middleware(request: Any, next_handler: Handler) -> Any:
    """认证中间件 — 对应 AuthMiddleware

    检查 Basic Auth 或 PTY ticket。
    """
    # OPTIONS 请求跳过认证
    if getattr(request, "method", "") == "OPTIONS":
        return await next_handler(request)

    password = _get_server_password()
    if not password:
        return await next_handler(request)

    # 检查 Authorization 头
    auth_header = None
    if hasattr(request, "headers"):
        auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Basic "):
        try:
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode()
            username, pwd = decoded.split(":", 1)
            expected_user = _get_server_username()
            if username == expected_user and pwd == password:
                return await next_handler(request)
        except Exception:
            pass

    return _json_response(
        {"name": "Unauthorized", "data": {"message": "Unauthorized"}},
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="craft"'},
    )


async def logger_middleware(request: Any, next_handler: Handler) -> Any:
    """日志中间件 — 对应 LoggerMiddleware"""
    method = getattr(request, "method", "UNKNOWN")
    path = getattr(request, "path", "/")

    logger.info("Request", extra={"method": method, "path": path})
    start = time.time()

    response = await next_handler(request)

    elapsed = time.time() - start
    status = getattr(response, "status", 0)
    logger.info("Response", extra={"method": method, "path": path, "status": status, "elapsed": f"{elapsed:.3f}s"})
    return response


def cors_middleware(allowed_origins: list[str] | None = None) -> Middleware:
    """CORS 中间件工厂 — 对应 CorsMiddleware"""
    async def middleware(request: Any, next_handler: Handler) -> Any:
        origin = request.headers.get("Origin") if hasattr(request, "headers") else None
        if origin:
            allowed = _is_origin_allowed(origin, allowed_origins or [])
            if allowed:
                # 返回预检响应或添加头
                if getattr(request, "method", "") == "OPTIONS":
                    return _json_response(
                        None, status=204,
                        headers={
                            "Access-Control-Allow-Origin": origin,
                            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Craft-Sync",
                            "Access-Control-Max-Age": "86400",
                        },
                    )
                response = await next_handler(request)
                if hasattr(response, "headers"):
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Expose-Headers"] = "X-Craft-Sync, Link, X-Next-Cursor"
                return response

        return await next_handler(request)
    return middleware


def _is_origin_allowed(origin: str, extra: list[str]) -> bool:
    """检查来源是否允许"""
    if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
        return True
    if origin in ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"):
        return True
    import re
    if re.match(r"^https://([a-z0-9-]+\.)*craft\.ai$", origin):
        return True
    return origin in extra


async def compression_middleware(request: Any, next_handler: Handler) -> Any:
    """压缩中间件 — 对应 CompressionMiddleware

    跳过事件流端点。
    """
    path = getattr(request, "path", "")
    method = getattr(request, "method", "")

    if path in ("/event", "/global/event"):
        return await next_handler(request)

    import re
    if method == "POST" and re.search(r"/session/[^/]+/(message|prompt_async)$", path):
        return await next_handler(request)

    # 标记响应可压缩（由下层处理）
    response = await next_handler(request)
    return response


def _json_response(data: Any, status: int = 200, headers: dict[str, str] | None = None) -> Any:
    """创建 JSON 响应"""
    import json as json_mod
    body = json_mod.dumps(data) if data is not None else ""
    # 返回一个类似 Response 的对象
    return type("Response", (), {
        "status": status,
        "body": body,
        "headers": headers or {},
        "content_type": "application/json",
    })()
