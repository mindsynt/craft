"""
PTY 终端 — 移植自 packages/opencode/src/pty/
虚拟终端、命令执行、会话管理
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

logger = logging.getLogger(__name__)


class PTYProcess:
    def __init__(self, command: str, cwd: str | None = None, env: dict | None = None):
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._output = ""

    async def start(self):
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env={**os.environ, **self.env},
        )

    async def read_output(self) -> str:
        if not self._process:
            return ""
        stdout, stderr = await self._process.communicate()
        output = (stdout or b"").decode(errors="replace")
        if stderr:
            output += "\n" + stderr.decode(errors="replace")
        self._output = output
        return output

    @property
    def return_code(self) -> int | None:
        return self._process.returncode if self._process else None

    async def terminate(self):
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()


class TerminalManager:
    def __init__(self):
        self._sessions: dict[str, PTYProcess] = {}

    async def execute(self, command: str, cwd: str | None = None) -> dict:
        proc = PTYProcess(command, cwd)
        await proc.start()
        output = await proc.read_output()
        return {"output": output, "return_code": proc.return_code, "command": command}

    async def execute_shell(self, command: str, timeout: float = 30) -> dict:
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "output": (stdout or b"").decode(errors="replace"),
                "error": (stderr or b"").decode(errors="replace"),
                "return_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"output": "", "error": f"命令超时 ({timeout}s)", "return_code": -1}


terminal_manager = TerminalManager()
