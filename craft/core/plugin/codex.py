"""OpenAI Codex 认证插件 — 移植自 codex.ts"""

from __future__ import annotations

from typing import Any


def make_codex_auth_plugin() -> dict[str, Any]:
    """OpenAI Codex 认证插件"""
    return {
        "name": "codex-auth",
        "provider": "openai",
        "auth": {
            "provider": "openai",
            "methods": [
                {
                    "label": "ChatGPT Pro/Plus (browser)",
                    "type": "oauth",
                    "issuer": "https://auth.openai.com",
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                    "scope": "openid profile email offline_access",
                    "redirect_path": "/auth/callback",
                    "port": 1455,
                },
                {
                    "label": "ChatGPT Pro/Plus (headless)",
                    "type": "device_code",
                    "issuer": "https://auth.openai.com",
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                },
                {
                    "label": "Manually enter API Key",
                    "type": "api",
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {
                **output,
                "headers": {
                    **output.get("headers", {}),
                    "originator": "craft",
                    "User-Agent": "craft/0.1.0",
                },
            }
            if output.get("model", {}).get("providerID") == "openai"
            else output
        ),
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if output.get("model", {}).get("providerID") == "openai"
            else output
        ),
    }
