"""Cloudflare Workers AI / AI Gateway 认证插件 — 移植自 cloudflare.ts"""

from __future__ import annotations

import os
from typing import Any


def make_cloudflare_workers_auth_plugin() -> dict[str, Any]:
    """Cloudflare Workers AI 认证插件"""
    prompts = []
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        prompts.append({
            "type": "text",
            "key": "accountId",
            "message": "Enter your Cloudflare Account ID",
            "placeholder": "e.g. 1234567890abcdef1234567890abcdef",
        })
    return {
        "name": "cloudflare-workers-auth",
        "provider": "cloudflare-workers-ai",
        "auth": {
            "provider": "cloudflare-workers-ai",
            "methods": [{"type": "api", "label": "API key", "prompts": prompts}],
        },
    }


def make_cloudflare_ai_gateway_auth_plugin() -> dict[str, Any]:
    """Cloudflare AI Gateway 认证插件"""
    prompts = []
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        prompts.append({
            "type": "text",
            "key": "accountId",
            "message": "Enter your Cloudflare Account ID",
            "placeholder": "e.g. 1234567890abcdef1234567890abcdef",
        })
    if not os.environ.get("CLOUDFLARE_GATEWAY_ID"):
        prompts.append({
            "type": "text",
            "key": "gatewayId",
            "message": "Enter your Cloudflare AI Gateway ID",
            "placeholder": "e.g. my-gateway",
        })
    return {
        "name": "cloudflare-ai-gateway-auth",
        "provider": "cloudflare-ai-gateway",
        "auth": {
            "provider": "cloudflare-ai-gateway",
            "methods": [{"type": "api", "label": "Gateway API token", "prompts": prompts}],
        },
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if output.get("model", {}).get("providerID") == "cloudflare-ai-gateway"
            and str(output.get("model", {}).get("api", {}).get("id", "")).lower().startswith("openai/")
            and output.get("model", {}).get("capabilities", {}).get("reasoning")
            else output
        ),
    }
