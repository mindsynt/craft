"""xAI (Grok) OAuth + Device Code 认证插件 — 移植自 xai.ts"""

from __future__ import annotations

from typing import Any


def make_xai_auth_plugin() -> dict[str, Any]:
    """xAI (Grok) OAuth + Device Code 认证插件"""
    return {
        "name": "xai-auth",
        "provider": "xai",
        "auth": {
            "provider": "xai",
            "methods": [
                {
                    "label": "xAI Grok OAuth (SuperGrok Subscription)",
                    "type": "oauth",
                    "authorize_url": "https://auth.x.ai/oauth2/authorize",
                    "token_url": "https://auth.x.ai/oauth2/token",
                    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
                    "scope": "openid profile email offline_access grok-cli:access api:access",
                    "redirect_uri": "http://127.0.0.1:56121/callback",
                },
                {
                    "label": "xAI Grok OAuth (Headless / Remote / VPS)",
                    "type": "device_code",
                    "device_auth_url": "https://auth.x.ai/oauth2/device/code",
                    "token_url": "https://auth.x.ai/oauth2/token",
                    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
                    "scope": "openid profile email offline_access grok-cli:access api:access",
                },
                {
                    "label": "Manually enter API Key",
                    "type": "api",
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "User-Agent": "craft/0.1.0"}}
            if output.get("model", {}).get("providerID") == "xai"
            else output
        ),
    }
