"""
环境管理 — 移植自 packages/opencode/src/env/
环境变量、功能检测、运行时信息
"""

from __future__ import annotations

import os
import platform
from typing import Any


class Env:
    def __init__(self):
        self._cache: dict[str, Any] = {}

    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    def set(self, key: str, value: str):
        os.environ[key] = value

    def has(self, key: str) -> bool:
        return key in os.environ

    def is_set(self, key: str) -> bool:
        val = os.environ.get(key, "").lower()
        return val in ("1", "true", "yes", "y")

    @property
    def is_dev(self) -> bool:
        return self.is_set("CRAFT_DEV") or self.is_set("NODE_ENV") == "development"

    @property
    def platform(self) -> str:
        return platform.system().lower()

    @property
    def is_macos(self) -> bool:
        return self.platform == "darwin"

    @property
    def is_linux(self) -> bool:
        return self.platform == "linux"

    @property
    def is_windows(self) -> bool:
        return self.platform == "windows"

    @property
    def is_docker(self) -> bool:
        if self._cache.get("_is_docker") is not None:
            return self._cache["_is_docker"]
        result = os.path.exists("/.dockerenv")
        self._cache["_is_docker"] = result
        return result

    @property
    def is_ssh(self) -> bool:
        return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))

    @property
    def home(self) -> str:
        return os.path.expanduser("~")

    @property
    def shell(self) -> str:
        return os.environ.get("SHELL", "/bin/bash")

    @property
    def terminal(self) -> str:
        return os.environ.get("TERM", "xterm-256color")

    @property
    def editor(self) -> str:
        return os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))

    @property
    def cpu_count(self) -> int:
        return os.cpu_count() or 4

    @property
    def memory_total(self) -> int:
        try:
            import psutil
            return int(psutil.virtual_memory().total)
        except ImportError:
            return 0


env = Env()
