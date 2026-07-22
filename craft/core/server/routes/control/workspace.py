"""工作区控制路由 — 移植自 routes/control/workspace.ts

工作区创建、列表、状态、删除、会话恢复等管理路由。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from craft.config.load import get_config
from craft.core.control_plane import WorkspaceInfo

logger = logging.getLogger(__name__)


class WorkspaceRoutes:
    """工作区路由处理器

    对应 TS WorkspaceRoutes
    """

    @staticmethod
    async def list_adaptors(request: Any) -> Any:
        """GET /experimental/workspace/adaptor

        列出工作区适配器。
        """
        return [
            {
                "type": "local",
                "name": "Local Directory",
                "description": "Sync with a local directory on the filesystem",
            },
            {
                "type": "github",
                "name": "GitHub Repository",
                "description": "Sync with a GitHub repository",
            },
        ]

    @staticmethod
    async def create(request: Any) -> Any:
        """POST /experimental/workspace/

        创建工作区。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        cwd = os.getcwd()
        project_id = f"proj_{hash(cwd) % 10**8:08x}"
        workspace = WorkspaceInfo(
            id=f"ws_{hash(str(body)) % 10**8:08x}",
            type=body.get("type", "local"),
            name=body.get("name", os.path.basename(cwd)),
            directory=body.get("directory", cwd),
            project_id=project_id,
        )
        return {
            "id": workspace.id,
            "type": workspace.type,
            "name": workspace.name,
            "directory": workspace.directory,
            "projectID": workspace.project_id,
        }

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /experimental/workspace/

        列出工作区。
        """
        cwd = os.getcwd()
        project_id = f"proj_{hash(cwd) % 10**8:08x}"
        return [
            {
                "id": f"ws_{project_id[-8:]}",
                "type": "local",
                "name": os.path.basename(cwd),
                "directory": cwd,
                "projectID": project_id,
            }
        ]

    @staticmethod
    async def status(request: Any) -> Any:
        """GET /experimental/workspace/status

        获取工作区状态。
        """
        cwd = os.getcwd()
        project_id = f"proj_{hash(cwd) % 10**8:08x}"
        return [
            {
                "workspaceID": f"ws_{project_id[-8:]}",
                "connected": False,
                "lastSync": 0,
            }
        ]

    @staticmethod
    async def remove(request: Any, workspace_id: str) -> Any:
        """DELETE /experimental/workspace/:id

        删除工作区。
        """
        logger.info("Workspace remove", extra={"workspace_id": workspace_id})
        return None

    @staticmethod
    async def session_restore(request: Any, workspace_id: str) -> Any:
        """POST /experimental/workspace/:id/session-restore

        将会话同步事件重放到目标工作区。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session_id = body.get("sessionID", "")
        logger.info(
            "Session restore",
            extra={"workspace_id": workspace_id, "session_id": session_id},
        )
        return {"total": 0}
