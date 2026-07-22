"""
全局状态 — 移植自 packages/opencode/src/global/
应用路径、环境信息、运行时上下文
"""

from __future__ import annotations

import os
from pathlib import Path

from craft.config import CONFIG_DIR


class GlobalPaths:
    """全局路径"""
    config: Path = CONFIG_DIR
    data: Path = CONFIG_DIR / "data"
    cache: Path = CONFIG_DIR / "cache"
    plugins: Path = CONFIG_DIR / "plugins"
    logs: Path = CONFIG_DIR / "logs"
    memory: Path = CONFIG_DIR / "memory"

    @classmethod
    def ensure(cls):
        for p in [cls.config, cls.data, cls.cache, cls.plugins, cls.logs, cls.memory]:
            p.mkdir(parents=True, exist_ok=True)


GlobalPaths.ensure()


class GlobalState:
    """全局运行时状态"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.start_time = None
            cls._instance.work_dir = Path.cwd()
        return cls._instance

    @property
    def cwd(self) -> Path:
        return Path.cwd()

    @cwd.setter
    def cwd(self, path: str | Path):
        os.chdir(path)


global_state = GlobalState()
