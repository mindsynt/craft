"""请求追踪 — 移植自 routes/instance/trace.ts

OTel 风格的请求追踪辅助工具。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


def param_to_attribute_key(key: str) -> str:
    """将路由参数名转换为 OTel 属性键

    对应 TS paramToAttributeKey()
    fooID → foo.id, 其他 → craft.<name>
    """
    m = re.match(r"^(.+)ID$", key)
    if m:
        return f"{m.group(1).lower()}.id"
    return f"craft.{key}"


def request_attributes(request: Any) -> dict[str, str]:
    """提取请求属性用于追踪

    对应 TS requestAttributes()
    """
    attributes: dict[str, str] = {
        "http.method": getattr(request, "method", "UNKNOWN"),
    }
    url_str = getattr(request, "url", "")
    try:
        from urllib.parse import urlparse
        attributes["http.path"] = urlparse(url_str).path
    except Exception:
        attributes["http.path"] = "/"

    # 添加路由参数
    params = getattr(request, "params", {}) or {}
    for key, value in params.items():
        attributes[param_to_attribute_key(key)] = str(value)

    return attributes


async def json_response(request: Any, data: Any) -> Any:
    """构造 JSON 响应

    对应 TS jsonRequest 的简化版本
    """
    import json
    body = json.dumps(data) if data is not None else ""
    return type("Response", (), {
        "status": 200,
        "body": body,
        "headers": {"Content-Type": "application/json"},
        "content_type": "application/json",
    })()
