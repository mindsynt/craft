"""
IDE 集成 — 移植自 packages/opencode/src/ide/
VS Code / Cursor / Windsurf 编辑器协议支持
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_IDES = {
    "vscode": {"cmd": "code", "args": ["--reuse-window", "{file}:{line}"]},
    "cursor": {"cmd": "cursor", "args": ["--reuse-window", "{file}:{line}"]},
    "windsurf": {"cmd": "windsurf", "args": ["{file}:{line}"]},
    "vim": {"cmd": "vim", "args": ["+{line}", "{file}"]},
    "nvim": {"cmd": "nvim", "args": ["+{line}", "{file}"]},
}


class IDEManager:
    def __init__(self):
        self._preferred: str = self._detect()

    def _detect(self) -> str:
        for ide, info in SUPPORTED_IDES.items():
            try:
                subprocess.run([info["cmd"], "--version"],
                              capture_output=True, timeout=3)
                return ide
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return ""

    @property
    def available(self) -> list[str]:
        return [name for name, info in SUPPORTED_IDES.items()
                if self._which(info["cmd"])]

    def _which(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, timeout=3)
            return True
        except Exception:
            return False

    def set_preferred(self, ide: str):
        if ide in SUPPORTED_IDES:
            self._preferred = ide

    def open_file(self, filepath: str, line: int = 1, ide: str | None = None) -> bool:
        ide = ide or self._preferred
        if not ide or ide not in SUPPORTED_IDES:
            logger.warning(f"[IDE] 未找到可用编辑器")
            return False
        info = SUPPORTED_IDES[ide]
        cmd = [info["cmd"]]
        for arg in info["args"]:
            cmd.append(arg.format(file=filepath, line=line))
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"[IDE] 打开: {filepath}:{line} ({ide})")
            return True
        except Exception as e:
            logger.error(f"[IDE] 打开失败: {e}")
            return False

    def open_diff(self, title: str, old_content: str, new_content: str) -> bool:
        """用编辑器打开差异对比"""
        tmp_dir = Path(tempfile.mkdtemp())
        old_file = tmp_dir / f"{title}.old"
        new_file = tmp_dir / f"{title}.new"
        old_file.write_text(old_content)
        new_file.write_text(new_content)
        ide = self._preferred
        if ide in ("vscode", "cursor"):
            try:
                subprocess.Popen(
                    [SUPPORTED_IDES[ide]["cmd"], "--diff", str(old_file), str(new_file)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass
        return False


ide_manager = IDEManager()
