"""
剪贴板 — 移植自 util/clipboard.ts
复制/粘贴增强、多条目管理
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from typing import Any


class ClipboardEntry:
    def __init__(self, text: str, source: str = ""):
        self.text = text
        self.source = source
        self.timestamp = time.time()
        self.pinned = False


class Clipboard:
    def __init__(self, max_entries: int = 20):
        self._entries: list[ClipboardEntry] = []
        self._max = max_entries

    async def copy(self, text: str, source: str = "") -> bool:
        """复制到系统剪贴板"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pbcopy" if __import__("sys").platform == "darwin" else "xclip",
                stdin=asyncio.subprocess.PIPE,
            )
            proc.stdin.write(text.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.wait()
        except Exception:
            pass
        
        self._entries.insert(0, ClipboardEntry(text, source))
        if len(self._entries) > self._max:
            self._entries.pop()
        return True

    async def paste(self) -> str:
        """从系统剪贴板读取"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pbpaste" if __import__("sys").platform == "darwin" else "xclip", "-o",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode(errors="replace")
        except Exception:
            return ""

    def history(self) -> list[dict]:
        return [{"text": e.text[:60], "source": e.source, "pinned": e.pinned}
                for e in self._entries[:10]]

    def pin(self, index: int):
        if 0 <= index < len(self._entries):
            self._entries[index].pinned = True

    def clear(self):
        self._entries.clear()


clipboard = Clipboard()
