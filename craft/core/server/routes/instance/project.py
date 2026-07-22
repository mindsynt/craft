"""项目路由 — 移植自 routes/instance/project.ts

项目列表、当前项目、git 初始化、项目更新。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProjectRoutes:
    """项目路由处理器

    对应 TS ProjectRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /project/
        
        列出所有项目。
        """
        # TODO: 接入 Project.list
        return []

    @staticmethod
    async def current(request: Any) -> Any:
        """GET /project/current
        
        获取当前项目。
        """
        # TODO: 接入 Instance.project
        return {}

    @staticmethod
    async def init_git(request: Any) -> Any:
        """POST /project/git/init
        
        初始化 git 仓库。
        """
        # TODO: 接入 Project.Service.initGit
        return {}

    @staticmethod
    async def update(request: Any, project_id: str) -> Any:
        """PATCH /project/:projectID
        
        更新项目。
        """
        # TODO: 接入 Project.Service.update
        return {}
