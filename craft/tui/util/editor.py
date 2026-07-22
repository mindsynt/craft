"""
编辑器集成 — 移植自 util/editor.ts

通过 $VISUAL/$EDITOR 打开临时文件编辑，返回编辑结果。
"""

from __future__ import annotations

import asyncio
import os
import platform
import tempfile
from pathlib import Path


async def open_editor(value: str) -> str | None:
    """打开外部编辑器编辑文本"""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        return None

    filepath = Path(tempfile.gettempdir()) / f"{os.urandom(4).hex()}.md"
    try:
        filepath.write_text(value, encoding="utf-8")
        parts = editor.split()
        proc = await asyncio.create_subprocess_exec(
            *parts, str(filepath),
            stdin=asyncio.subprocess.DEVNULL if platform.system() == "Windows" else None,
        )
        await proc.wait()
        content = filepath.read_text(encoding="utf-8")
        return content if content else None
    finally:
        filepath.unlink(missing_ok=True)
