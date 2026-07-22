"""
文件补丁 — 移植自 packages/opencode/src/patch/
文件编辑、差异计算、补丁应用
"""

from __future__ import annotations

import difflib
from pathlib import Path


class Patch:
    def __init__(self, filepath: str, old_string: str, new_string: str):
        self.filepath = filepath
        self.old_string = old_string
        self.new_string = new_string

    def apply(self) -> bool:
        try:
            path = Path(self.filepath)
            content = path.read_text(encoding="utf-8")
            if self.old_string not in content:
                return False
            new_content = content.replace(self.old_string, self.new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            return True
        except Exception:
            return False

    def dry_run(self) -> bool:
        try:
            content = Path(self.filepath).read_text(encoding="utf-8")
            return self.old_string in content
        except Exception:
            return False

    def diff(self) -> str:
        try:
            content = Path(self.filepath).read_text(encoding="utf-8")
            return "".join(difflib.unified_diff(
                content.splitlines(keepends=True),
                content.replace(self.old_string, self.new_string).splitlines(keepends=True),
                fromfile="original", tofile="patched",
            ))
        except Exception:
            return ""


class PatchManager:
    def __init__(self):
        self._history: list[Patch] = []

    def apply(self, filepath: str, old_string: str, new_string: str) -> bool:
        patch = Patch(filepath, old_string, new_string)
        if patch.apply():
            self._history.append(patch)
            return True
        return False

    def undo_last(self) -> bool:
        if not self._history:
            return False
        patch = self._history.pop()
        return Patch(patch.filepath, patch.new_string, patch.old_string).apply()


patcher = PatchManager()
