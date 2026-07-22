"""小米 MiMo 认证 + Anthropic 代理插件 — 移植自 mimo.ts"""

from __future__ import annotations

import os
from typing import Any


def make_mimo_auth_plugin() -> dict[str, Any]:
    """小米 MiMo 认证 + Anthropic 代理插件"""
    return {
        "name": "mimo-auth",
        "provider": "xiaomi",
        "auth": {
            "provider": "xiaomi",
            "methods": [
                {
                    "label": "Browser Login (小米登录)",
                    "type": "oauth",
                    "platform_url": os.environ.get("MIMO_PLATFORM_URL", "https://platform.xiaomimimo.com"),
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "X-Mimo-Source": "craft-cli"}}
            if output.get("model", {}).get("providerID") == "xiaomi"
            else output
        ),
    }


def make_anthropic_proxy_plugin() -> dict[str, Any]:
    """Anthropic 代理插件（移除 anthropic-beta 头）"""
    return {
        "name": "anthropic-proxy",
        "provider": "anthropic",
        "auth": {
            "provider": "anthropic",
            "methods": [],
        },
    }
