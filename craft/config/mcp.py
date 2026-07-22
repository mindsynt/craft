"""MCP 配置 — 对应 mcp.ts"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MCPLocalConfig(BaseModel):
    """本地 MCP 服务器配置"""
    type: str = "local"
    command: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout: int | None = None


class MCPRemoteConfig(BaseModel):
    """远程 MCP 服务器配置"""
    type: str = "remote"
    url: str = ""
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: dict[str, str] | bool | None = None
    timeout: int | None = None


class MCPConfig(BaseModel):
    """MCP 服务器配置"""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    # 扩充
    type: str = "local"
    url: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    command_list: list[str] = Field(default_factory=list)
    timeout: int | None = None


MCP_SENSITIVE_KEYS = [
    "authorization", "token", "api_key", "apikey", "key", "secret", "password", "credential",
]


def mcp_redact_string(text: str) -> str:
    """脱敏 MCP 配置中的敏感信息"""
    text = re.sub(r'(Bearer\s+)[^\s]+', r'\1****', text, flags=re.IGNORECASE)
    return text


def mcp_redact_command(command: list[str]) -> list[str]:
    """脱敏命令中的敏感参数"""
    result = []
    for i, item in enumerate(command):
        if i > 0 and any(k in command[i - 1].lower() for k in MCP_SENSITIVE_KEYS):
            result.append("****")
        else:
            result.append(mcp_redact_string(item))
    return result


def mcp_from_claude(name: str, data: Any) -> dict:
    """从 Claude Code 格式转换 MCP 配置"""
    if not isinstance(data, dict):
        return {"warning": f'skipped Claude Code MCP server "{name}"; server config is not an object.'}

    if data.get("type") == "sse":
        return {"warning": f'skipped Claude Code MCP server "{name}"; unsupported transport "sse".'}

    args = data.get("args")
    if args is not None and not isinstance(args, list):
        return {"warning": f'skipped Claude Code MCP server "{name}"; args is not an array.'}

    args_list = args if isinstance(args, list) else []
    if not all(isinstance(a, str) for a in args_list):
        return {"warning": f'skipped Claude Code MCP server "{name}"; args must contain only strings.'}

    enabled = not data.get("disabled", False)
    environment = data.get("environment") or data.get("env")
    if isinstance(environment, dict):
        environment = {k: str(v) for k, v in environment.items() if isinstance(v, str)}
    else:
        environment = None

    timeout = data.get("timeout") if isinstance(data.get("timeout"), (int, float)) else None
    transport_type = data.get("type")

    local_types = {"stdio", "local"}
    remote_types = {"http", "streamable-http", "remote"}

    if isinstance(data.get("command"), str) and (not transport_type or transport_type in local_types):
        command = [data["command"]] + args_list
        config = {
            "type": "local",
            "command": command,
            "enabled": enabled,
        }
        if environment:
            config["environment"] = environment
        if timeout is not None:
            config["timeout"] = timeout
        return {"config": config}

    if data.get("command") is not None:
        return {"warning": f'skipped Claude Code MCP server "{name}"; command is not a string.'}

    if isinstance(data.get("url"), str) and (not transport_type or transport_type in remote_types):
        config = {
            "type": "remote",
            "url": data["url"],
            "enabled": enabled,
        }
        headers = data.get("headers")
        if isinstance(headers, dict):
            config["headers"] = {k: str(v) for k, v in headers.items() if isinstance(v, str)}
        oauth_data = data.get("oauth")
        if oauth_data is not None and oauth_data is not False:
            if isinstance(oauth_data, dict):
                oauth_result = {}
                for ok in ("clientId", "clientSecret", "scope", "redirectUri"):
                    if ok in oauth_data and isinstance(oauth_data[ok], str):
                        oauth_result[ok] = oauth_data[ok]
                if oauth_result:
                    config["oauth"] = oauth_result
        elif oauth_data is False:
            config["oauth"] = False
        if environment:
            config["environment"] = environment
        if timeout is not None:
            config["timeout"] = timeout
        return {"config": config}

    if data.get("url") is not None:
        return {"warning": f'skipped Claude Code MCP server "{name}"; url is not a string.'}

    if transport_type and transport_type not in local_types and transport_type not in remote_types:
        return {"warning": f'skipped Claude Code MCP server "{name}"; unsupported transport "{transport_type}".'}

    return {"warning": f'skipped Claude Code MCP server "{name}"; missing command or url.'}
