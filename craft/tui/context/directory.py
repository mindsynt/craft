"""
Directory 上下文 — 移植自 context/directory.ts

显示当前工作目录，可选带 VCS 分支信息。
"""

from __future__ import annotations

import os


class DirectoryContext:
    """工作目录上下文"""

    def __init__(self, home_dir: str | None = None):
        self._home = home_dir or os.path.expanduser("~")

    def format(self, directory: str, branch: str | None = None) -> str:
        """格式化目录显示（~ 缩写 + 分支）"""
        result = directory.replace(self._home, "~")
        if branch:
            result += f":{branch}"
        return result

    def get(self, directory: str, branch: str | None = None) -> str:
        """获取当前目录显示字符串"""
        return self.format(directory or os.getcwd(), branch)
