"""HTTP API 项目路由 — 移植自 routes/instance/httpapi/project.ts
"""

from __future__ import annotations

import os
from typing import Any


class ProjectApi:
    """项目 API — 实验性 HttpApi 版本"""

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /project

        列出所有项目。
        """
        cwd = os.getcwd()
        return [
            {
                "id": f"proj_{hash(cwd) % 10**8:08x}",
                "name": os.path.basename(cwd),
                "directory": cwd,
                "vcs": _detect_vcs(cwd),
            }
        ]

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
