"""项目路由 — 移植自 routes/instance/project.ts

项目列表、当前项目、git 初始化、项目更新。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from craft.config.load import get_config
from craft.core.share import ShareManager

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
        cfg = get_config()
        projects = []

        # Derive projects from config
        cwd = os.getcwd()
        projects.append({
            "id": f"proj_{hash(cwd) % 10**8:08x}",
            "name": os.path.basename(cwd),
            "directory": cwd,
            "vcs": _detect_vcs(cwd),
        })

        # Additional projects from managed config
        for name, pcfg in cfg.project.items() if hasattr(cfg, "project") else {}:
            pdir = getattr(pcfg, "directory", "")
            if pdir and os.path.isdir(pdir):
                projects.append({
                    "id": f"proj_{hash(pdir) % 10**8:08x}",
                    "name": getattr(pcfg, "name", os.path.basename(pdir)),
                    "directory": pdir,
                    "vcs": _detect_vcs(pdir),
                })

        return projects

    @staticmethod
    async def current(request: Any) -> Any:
        """GET /project/current

        获取当前项目。
        """
        cwd = os.getcwd()
        return {
            "id": f"proj_{hash(cwd) % 10**8:08x}",
            "name": os.path.basename(cwd),
            "directory": cwd,
            "vcs": _detect_vcs(cwd),
            "worktree": cwd,
        }

    @staticmethod
    async def init_git(request: Any) -> Any:
        """POST /project/git/init

        初始化 git 仓库。
        """
        cwd = os.getcwd()
        try:
            import subprocess
            result = subprocess.run(
                ["git", "init"],
                capture_output=True, text=True, timeout=30, cwd=cwd,
            )
            if result.returncode == 0:
                logger.info("Git init successful", extra={"directory": cwd})
            else:
                logger.warning("Git init failed", extra={"error": result.stderr})
        except Exception as e:
            logger.warning("Git init error", extra={"error": str(e)})

        return _project_info(cwd)

    @staticmethod
    async def update(request: Any, project_id: str) -> Any:
        """PATCH /project/:projectID

        更新项目。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        cwd = os.getcwd()
        info = _project_info(cwd)
        info.update(body)
        return info


def _detect_vcs(directory: str) -> str:
    """检测项目版本控制系统"""
    git_dir = os.path.join(directory, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=directory,
            )
            if result.returncode == 0:
                return f"git:{result.stdout.strip()}"
        except Exception:
            pass
        return "git"
    return "none"


def _project_info(directory: str) -> dict[str, Any]:
    """返回项目信息字典"""
    return {
        "id": f"proj_{hash(directory) % 10**8:08x}",
        "name": os.path.basename(directory),
        "directory": directory,
        "vcs": _detect_vcs(directory),
        "worktree": directory,
    }
