"""GitHub Copilot 认证插件 + Copilot Models — 移植自 copilot.ts, github-copilot/models.ts"""

from __future__ import annotations

import json as _json
from typing import Any


async def copilot_models_fetch(
    base_url: str,
    headers: dict[str, str] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """获取 GitHub Copilot 模型列表"""
    import urllib.request

    req = urllib.request.Request(f"{base_url}/models")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch models: {e}") from e

    result = dict(existing or {})
    raw_items = data.get("data", [])
    remote_map: dict[str, Any] = {}
    for m in raw_items:
        if m.get("model_picker_enabled") and m.get("policy", {}).get("state") != "disabled":
            remote_map[m["id"]] = m

    # Prune existing models not in the response
    for key in list(result.keys()):
        mid = result[key].get("api", {}).get("id")
        if mid and mid not in remote_map:
            del result[key]

    # Add / update from remote
    for mid, m in remote_map.items():
        caps = m.get("capabilities", {})
        limits = caps.get("limits", {})
        supports = caps.get("supports", {})
        vision = limits.get("vision", {})
        reasoning = (
            supports.get("adaptive_thinking", False)
            or bool(supports.get("reasoning_effort", []))
            or supports.get("max_thinking_budget") is not None
            or supports.get("min_thinking_budget") is not None
        )
        has_image = supports.get("vision", False) or any(
            t.startswith("image/") for t in vision.get("supported_media_types", [])
        )
        supported_endpoints = m.get("supported_endpoints", [])
        is_msg_api = "/v1/messages" in supported_endpoints

        prev = result.get(mid)
        result[mid] = {
            "id": mid,
            "providerID": "github-copilot",
            "api": {
                "id": m["id"],
                "url": f"{base_url}/v1" if is_msg_api else base_url,
                "npm": "@ai-sdk/anthropic" if is_msg_api else "@ai-sdk/github-copilot",
            },
            "status": "active",
            "limit": {
                "context": limits.get("max_context_window_tokens", 0),
                "input": limits.get("max_prompt_tokens", 0),
                "output": limits.get("max_output_tokens", 0),
            },
            "capabilities": {
                "temperature": prev.get("capabilities", {}).get("temperature", True) if prev else True,
                "reasoning": prev.get("capabilities", {}).get("reasoning", reasoning) if prev else reasoning,
                "attachment": prev.get("capabilities", {}).get("attachment", True) if prev else True,
                "toolcall": supports.get("tool_calls", False),
                "input": {"text": True, "audio": False, "image": has_image, "video": False, "pdf": False},
                "output": {"text": True, "audio": False, "image": False, "video": False, "pdf": False},
                "interleaved": False,
            },
            "family": prev.get("family", caps.get("family", "")) if prev else caps.get("family", ""),
            "name": prev.get("name", m.get("name", "")) if prev else m.get("name", ""),
            "cost": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
            "options": prev.get("options", {}) if prev else {},
            "headers": prev.get("headers", {}) if prev else {},
            "release_date": prev.get("release_date", "") if prev else "",
        }

    return result


def make_copilot_auth_plugin() -> dict[str, Any]:
    """GitHub Copilot 认证插件"""
    return {
        "name": "copilot-auth",
        "provider": "github-copilot",
        "auth": {
            "provider": "github-copilot",
            "methods": [
                {
                    "type": "oauth",
                    "label": "Login with GitHub Copilot",
                    "client_id": "Ov23li8tweQw6odWQebz",
                    "device_code_url": "https://github.com/login/device/code",
                    "access_token_url": "https://github.com/login/oauth/access_token",
                    "scope": "read:user",
                },
            ],
        },
        "provider.models": lambda provider, ctx: (
            copilot_models_fetch(
                "https://api.githubcopilot.com",
                {"Authorization": f"Bearer {ctx.get('auth', {}).get('refresh', '')}"},
                provider.get("models", {}),
            )
        ),
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if "github-copilot" in str(output.get("model", {}).get("providerID", ""))
            and "gpt" in str(output.get("model", {}).get("api", {}).get("id", ""))
            else output
        ),
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "anthropic-beta": "interleaved-thinking-2025-05-14"}}
            if "github-copilot" in str(output.get("model", {}).get("providerID", ""))
            and output.get("model", {}).get("api", {}).get("npm") == "@ai-sdk/anthropic"
            else output
        ),
    }
