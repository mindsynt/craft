"""
项目管理 — 移植自 packages/opencode/src/project/
项目初始化、实例管理、配置发现
"""

from __future__ import annotations

import os
from pathlib import Path


class Project:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getcwd()).resolve()
        self._config = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_git_repo(self) -> bool:
        return (self.path / ".git").exists()

    @property
    def is_python_project(self) -> bool:
        return (self.path / "pyproject.toml").exists() or (self.path / "setup.py").exists()

    @property
    def is_node_project(self) -> bool:
        return (self.path / "package.json").exists()

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
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return self.path

    def files(self, pattern: str = "**/*") -> list[Path]:
        return list(self.path.glob(pattern))

    def __repr__(self):
        return f"Project({self.path})"


class ProjectInstance:
    def __init__(self, project: Project | None = None):
        self.project = project or Project()
        self.id = self.project.name.lower().replace(" ", "-")

    def init_gitignore(self):
        gitignore = self.project.path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Craft\n.craft/\n*.log\n.env\n__pycache__/\n.venv/\nnode_modules/\n"
            )

    def init_config(self):
        config_dir = self.project.path / ".craft"
        config_dir.mkdir(exist_ok=True)


def find_project_root(start: str | None = None) -> Path:
    cur = Path(start or os.getcwd()).resolve()
    for p in [cur] + list(cur.parents):
        if (p / ".git").exists():
            return p
    return cur
