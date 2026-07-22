"""HTTP 错误定义 — 移植自 error.ts

定义 API 端点可能返回的标准错误响应。
"""

from __future__ import annotations

from typing import Any


# 标准错误响应定义
ERRORS: dict[int, dict[str, Any]] = {
    400: {
        "description": "Bad request",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "data": {},
                        "errors": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "success": {"type": "boolean", "const": False},
                    },
                },
            },
        },
    },
    404: {
        "description": "Not found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "data": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                        },
                    },
                },
            },
        },
    },
    409: {
        "description": "Conflict — session resource is busy",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "const": "UnknownError"},
                        "data": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                        },
                    },
                },
            },
        },
    },
}


def errors(*codes: int) -> dict[str, Any]:
    """获取指定状态码的错误响应定义

    对应 TS errors() 函数
    """
    result = {}
    for code in codes:
        if code in ERRORS:
            result[str(code)] = ERRORS[code]
    return result
