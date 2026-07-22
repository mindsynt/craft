"""实验性路由 — 移植自 routes/instance/experimental.ts

Console 组织管理、工具列表、工作树、跨项目会话列表、MCP 资源。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExperimentalRoutes:
    """实验性路由处理器

    对应 TS ExperimentalRoutes
    """

    @staticmethod
    async def console_get(request: Any) -> Any:
        """GET /experimental/console
        
        获取 Console 提供商元数据。
        """
        # TODO: 接入 Config.getConsoleState / Account
        return {}

    @staticmethod
    async def console_list_orgs(request: Any) -> Any:
        """GET /experimental/console/orgs
        
        列出可切换的 Console 组织。
        """
        # TODO: 接入 Account.Service
        return {"orgs": []}

    @staticmethod
    async def console_switch(request: Any) -> Any:
        """POST /experimental/console/switch
        
        切换 Console 组织。
        """
        # TODO: 接入 Account.Service
        return True

    @staticmethod
    async def tool_ids(request: Any) -> Any:
        """GET /experimental/tool/ids
        
        列出工具 ID。
        """
        # TODO: 接入 ToolRegistry
        return []

    @staticmethod
    async def tool_list(request: Any) -> Any:
        """GET /experimental/tool
        
        列出工具（含参数 schema）。
        """
        # TODO: 接入 ToolRegistry
        return []

    @staticmethod
    async def worktree_create(request: Any) -> Any:
        """POST /experimental/worktree
        
        创建工作树。
        """
        # TODO: 接入 Worktree.Service
        return {}

    @staticmethod
    async def worktree_list(request: Any) -> Any:
        """GET /experimental/worktree
        
        列出工作树。
        """
        # TODO: 接入 Project.Service
        return []

    @staticmethod
    async def worktree_remove(request: Any) -> Any:
        """DELETE /experimental/worktree
        
        移除工作树。
        """
        # TODO: 接入 Worktree.Service
        return True

    @staticmethod
    async def worktree_reset(request: Any) -> Any:
        """POST /experimental/worktree/reset
        
        重置工作树。
        """
        # TODO: 接入 Worktree.Service
        return True

    @staticmethod
    async def session_list_global(request: Any) -> Any:
        """GET /experimental/session
        
        跨项目会话列表。
        """
        # TODO: 接入 Session.listGlobal
        return []

    @staticmethod
    async def resource_list(request: Any) -> Any:
        """GET /experimental/resource
        
        列出 MCP 资源。
        """
        # TODO: 接入 MCP.Service
        return {}
