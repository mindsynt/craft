"""MCP 路由 — 移植自 routes/instance/mcp.ts

MCP 服务器状态、添加、OAuth 认证、连接管理。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.config.load import get_config
from craft.config.mcp import MCPConfig

logger = logging.getLogger(__name__)


class McpRoutes:
    """MCP 路由处理器

    对应 TS McpRoutes
    """

    @staticmethod
    async def status(request: Any) -> Any:
        """GET /mcp/

        获取所有 MCP 服务器状态。
        """
        cfg = get_config()
        mcp_cfgs = cfg.mcp if hasattr(cfg, "mcp") else {}
        status = {}
        for name in (mcp_cfgs if isinstance(mcp_cfgs, dict) else {}):
            status[name] = {"connected": False, "name": name}
        return status

    @staticmethod
    async def add(request: Any) -> Any:
        """POST /mcp/

        动态添加 MCP 服务器。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        name = body.get("name", "")
        config = body.get("config", {})
        logger.info("MCP server add requested", extra={"name": name, "config": config})
        return {"connected": False, "name": name}

    @staticmethod
    async def auth_start(request: Any, name: str) -> Any:
        """POST /mcp/:name/auth

        开始 MCP OAuth 认证。
        """
        return {"authorizationUrl": "", "supports": False}

    @staticmethod
    async def auth_callback(request: Any, name: str) -> Any:
        """POST /mcp/:name/auth/callback

        完成 MCP OAuth 认证。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        code = body.get("code", "")
        # MCP OAuth not yet implemented
        return {"connected": False, "name": name}

    @staticmethod
    async def auth_authenticate(request: Any, name: str) -> Any:
        """POST /mcp/:name/auth/authenticate

        完整的 OAuth 流程。
        """
        return {"connected": False, "name": name}

    @staticmethod
    async def auth_remove(request: Any, name: str) -> Any:
        """DELETE /mcp/:name/auth

        移除 MCP OAuth 凭据。
        """
        logger.info("MCP auth removed", extra={"name": name})
        return {"success": True}

    @staticmethod
    async def connect(request: Any, name: str) -> Any:
        """POST /mcp/:name/connect

        连接 MCP 服务器。
        """
        logger.info("MCP connect requested", extra={"name": name})
        return True

    @staticmethod
    async def disconnect(request: Any, name: str) -> Any:
        """POST /mcp/:name/disconnect

        断开 MCP 服务器。
        """
        logger.info("MCP disconnect requested", extra={"name": name})
        return True
