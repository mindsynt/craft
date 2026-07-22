"""服务器认证 — 移植自 auth.ts

生成 Basic Auth 头用于客户端到服务器的认证。
"""

from __future__ import annotations

import base64
import os
from typing import Optional


def _get_env_password() -> Optional[str]:
    """获取环境变量中的服务器密码"""
    return os.environ.get("CRAFT_SERVER_PASSWORD") or os.environ.get("MIMOCODE_SERVER_PASSWORD")


def _get_env_username() -> str:
    """获取环境变量中的服务器用户名"""
    return (
        os.environ.get("CRAFT_SERVER_USERNAME")
        or os.environ.get("MIMOCODE_SERVER_USERNAME")
        or "craft"
    )


def server_auth_header(
    credentials: dict | None = None,
) -> str | None:
    """生成 Basic Auth 头值

    对应 TS serverAuthHeader()
    """
    password = (credentials or {}).get("password") or _get_env_password()
    if not password:
        return None
    username = (credentials or {}).get("username") or _get_env_username()
    raw = f"{username}:{password}"
    encoded = base64.b64encode(raw.encode()).decode()
    return f"Basic {encoded}"


def server_auth_headers(
    credentials: dict | None = None,
) -> dict[str, str] | None:
    """生成包含 Authorization 头的字典

    对应 TS serverAuthHeaders()
    """
    header = server_auth_header(credentials)
    if not header:
        return None
    return {"Authorization": header}
