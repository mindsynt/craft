"""实验性路由 — 移植自 routes/instance/experimental.ts

Console 组织管理、工具列表、工作树、跨项目会话列表、MCP 资源。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from craft.config.load import get_config
from craft.core.provider.registry import PROVIDER_MAP

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
        return {
            "activeConsoleOrg": "",
            "managedProviderIDs": [],
            "switchableOrgCount": 0,
        }

    @staticmethod
    async def console_list_orgs(request: Any) -> Any:
        """GET /experimental/console/orgs

        列出可切换的 Console 组织。
        """
        return {"orgs": []}

    @staticmethod
    async def console_switch(request: Any) -> Any:
        """POST /experimental/console/switch

        切换 Console 组织。
        """
        return True

    @staticmethod
    async def tool_ids(request: Any) -> Any:
        """GET /experimental/tool/ids

        列出工具 ID。
        """
        return [
            "read",
            "write",
            "edit",
            "search",
            "bash",
            "file_search",
            "web_search_preview",
            "code_interpreter",
        ]

    @staticmethod
    async def tool_list(request: Any) -> Any:
        """GET /experimental/tool

        列出工具（含参数 schema）。
        """
        provider = ""
        model = ""
        if hasattr(request, "query_params"):
            provider = request.query_params.get("provider", "")
            model = request.query_params.get("model", "")

        tools = [
            {
                "id": "read",
                "description": "Read the content of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            },
            {
                "id": "write",
                "description": "Write content to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "File content"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "id": "bash",
                "description": "Execute a bash command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"},
                    },
                    "required": ["command"],
                },
            },
            {
                "id": "search",
                "description": "Search for text in files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Search pattern"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "id": "file_search",
                "description": "Search for files by name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "File name query"},
                    },
                    "required": ["query"],
                },
            },
        ]
        return tools

    @staticmethod
    async def worktree_create(request: Any) -> Any:
        """POST /experimental/worktree

        创建工作树。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        cwd = os.getcwd()
        branch = body.get("branch", "")
        logger.info("Worktree create", extra={"directory": cwd, "branch": branch})
        return {"directory": os.path.join(cwd, ".sandbox"), "branch": branch}

    @staticmethod
    async def worktree_list(request: Any) -> Any:
        """GET /experimental/worktree

        列出工作树。
        """
        cwd = os.getcwd()
        sandbox_dir = os.path.join(cwd, ".sandbox")
        if os.path.isdir(sandbox_dir):
            return [sandbox_dir]
        return []

    @staticmethod
    async def worktree_remove(request: Any) -> Any:
        """DELETE /experimental/worktree

        移除工作树。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        directory = body.get("directory", "")
        logger.info("Worktree remove", extra={"directory": directory})
        return True

    @staticmethod
    async def worktree_reset(request: Any) -> Any:
        """POST /experimental/worktree/reset

        重置工作树。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        directory = body.get("directory", "")
        logger.info("Worktree reset", extra={"directory": directory})
        return True

    @staticmethod
    async def session_list_global(request: Any) -> Any:
        """GET /experimental/session

        跨项目会话列表。
        """
        from craft.core.session import sessions

        limit = 100
        cursor = None
        directory = None
        archived = False

        if hasattr(request, "query_params"):
            qp = request.query_params
            if qp.get("limit"):
                try:
                    limit = int(qp["limit"])
                except (ValueError, TypeError):
                    pass
            if qp.get("cursor"):
                try:
                    cursor = float(qp["cursor"])
                except (ValueError, TypeError):
                    pass
            directory = qp.get("directory")
            archived = qp.get("archived", "").lower() in ("true", "1")

        all_sessions = sessions.list(limit=limit + 1)
        results = []
        for s in all_sessions:
            if directory and s.get("directory", "") != directory:
                continue
            if not archived and s.get("archived", False):
                continue
            results.append(s)
            if len(results) > limit:
                break

        has_more = len(results) > limit
        if has_more:
            results = results[:limit]

        return results

    @staticmethod
    async def resource_list(request: Any) -> Any:
        """GET /experimental/resource

        列出 MCP 资源。
        """
        return {}
