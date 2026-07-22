"""
项目管理 — 移植自 packages/opencode/src/project/
项目初始化、实例管理、VCS 检测、工作区信任、项目 ID
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from craft.core.bus import define_event
from craft.core.id import ascending as id_ascending


# ── 事件 ────────────────────────────────────────────────────

ProjectCreated = define_event("project.created", {
    "id": str,
    "path": str,
})

ProjectConfigLoaded = define_event("project.config_loaded", {
    "id": str,
    "path": str,
})


# ── Schema ──────────────────────────────────────────────────

@dataclass
class ProjectID:
    """项目 ID — 带前缀的唯一标识"""
    value: str

    @staticmethod
    def generate(prefix: str = "prj") -> ProjectID:
        return ProjectID(f"{prefix}_{id_ascending('workspace')}")

    def __str__(self) -> str:
        return self.value


# ── VCS 检测 ────────────────────────────────────────────────

def detect_vcs(path: str | Path) -> str:
    """检测版本控制系统

    Returns: "git" | "hg" | "svn" | "unknown"
    """
    p = Path(path)
    if (p / ".git").exists() or (p / "HEAD").exists():
        return "git"
    if (p / ".hg").exists():
        return "hg"
    if (p / ".svn").exists():
        return "svn"
    # 检查父目录
    for parent in p.parents:
        if (parent / ".git").exists():
            return "git"
        if (parent / ".hg").exists():
            return "hg"
    return "unknown"


# ── 工作区信任 ──────────────────────────────────────────────
# 对应 TS project/workspace-trust.ts

class WorkspaceTrust:
    """工作区信任管理 — 防止对系统目录的意外操作"""

    # 系统级保护目录
    SYSTEM_PATHS: set[str] = {
        "/", "/etc", "/bin", "/sbin", "/usr", "/var",
        "/System", "/Library", "/Applications",
    }

    # HOME 下的保护目录名
    PROTECTED_HOME_DIRS: set[str] = {
        "Desktop", "Documents", "Downloads", "Pictures",
        "Music", "Movies", "Applications", "Library",
        "Public", ".ssh", ".gnupg",
    }

    @staticmethod
    def is_trusted(path: str | Path) -> bool:
        """检查路径是否受信任"""
        p = Path(path).resolve()
        # 永远不信任系统目录
        for sp in WorkspaceTrust.SYSTEM_PATHS:
            if str(p) == sp or str(p).startswith(sp + "/"):
                return False
        # 检查 HOME 下的保护目录
        home = Path.home()
        try:
            relative = p.relative_to(home)
            parts = relative.parts
            if parts and parts[0] in WorkspaceTrust.PROTECTED_HOME_DIRS:
                return False
        except ValueError:
            pass
        return True


# ── Project ──────────────────────────────────────────────────

class Project:
    """项目管理 — 对应 TS Project schema + project.ts"""

    def __init__(self, path: str | None = None, id: str | None = None):
        self.path = Path(path or os.getcwd()).resolve()
        self.id = id or f"prj_{self.path.name.lower().replace(' ', '-')}_{int(time.time())}"
        self._config: dict | None = None
        self._vcs: str | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def vcs(self) -> str:
        if self._vcs is None:
            self._vcs = detect_vcs(self.path)
        return self._vcs

    @property
    def is_git_repo(self) -> bool:
        return self.vcs == "git"

    @property
    def is_python_project(self) -> bool:
        return (self.path / "pyproject.toml").exists() or (self.path / "setup.py").exists()

    @property
    def is_node_project(self) -> bool:
        return (self.path / "package.json").exists()

    @property
    def is_trusted(self) -> bool:
        return WorkspaceTrust.is_trusted(self.path)

    def find_configs(self) -> list[Path]:
        configs = []
        for name in ["craft.jsonc", "craft.json", ".craft/config.jsonc",
                      "mimocode.jsonc", "mimocode.json", ".mimocode.jsonc"]:
            p = self.path / name
            if p.exists():
                configs.append(p)
        return configs

    def find_root(self) -> Path:
        """向上查找项目根目录（包含 .git 的目录）"""
        current = self.path
        for p in [current] + list(current.parents):
            if (p / ".git").exists():
                return p
            # 也检查 .git 文件（git submodule）
            git_path = p / ".git"
            if git_path.is_file():
                return p
        return self.path

    def worktree(self) -> Path:
        """获取工作树路径 — git worktree 或项目根"""
        return self.find_root()

    def files(self, pattern: str = "**/*") -> list[Path]:
        return list(self.path.glob(pattern))

    def init_gitignore(self):
        gitignore = self.path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Craft\n.craft/\\n*.log\\n.env\\n__pycache__/\\n.venv/\\nnode_modules/\\n"
            )

    def init_config(self):
        config_dir = self.path / ".craft"
        config_dir.mkdir(exist_ok=True)

    def __repr__(self):
        return f"Project({self.path})"


# ── 实例管理 ────────────────────────────────────────────────
# 对应 TS project/instance.ts

@dataclass
class InstanceContext:
    """实例上下文 — 存储运行时的项目实例信息"""
    project: Project = field(default_factory=Project)
    directory: str = ""
    worktree: str = ""

    def __post_init__(self):
        if not self.directory:
            self.directory = str(self.project.path)
        if not self.worktree:
            self.worktree = str(self.project.worktree())


class InstanceManager:
    """实例管理器 — 管理当前运行的项目实例"""

    def __init__(self):
        self._current: InstanceContext | None = None

    @property
    def current(self) -> InstanceContext:
        if self._current is None:
            self._current = InstanceContext()
        return self._current

    def set(self, ctx: InstanceContext):
        self._current = ctx

    def reset(self):
        self._current = None

    @property
    def directory(self) -> str | None:
        if self._current:
            return self._current.directory
        return None

    @property
    def project(self) -> Project | None:
        if self._current:
            return self._current.project
        return None


instance_manager = InstanceManager()


# ── 实例 Bootstrap ──────────────────────────────────────────
# 对应 TS project/bootstrap.ts

async def bootstrap_project(directory: str | None = None) -> InstanceContext:
    """初始化项目实例 — 检测 VCS、查找根目录、准备上下文"""
    project = Project(path=directory)
    root = project.find_root()

    ctx = InstanceContext(
        project=project,
        directory=str(project.path),
        worktree=str(root),
    )

    instance_manager.set(ctx)
    return ctx


# ── 顶层便捷函数 ───────────────────────────────────────────

def find_project_root(start: str | None = None) -> Path:
    cur = Path(start or os.getcwd()).resolve()
    for p in [cur] + list(cur.parents):
        if (p / ".git").exists():
            return p
    return cur
