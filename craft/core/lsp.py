"""
LSP 集成 — 移植自 packages/opencode/src/lsp/
Language Server Protocol 客户端管理
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class LSPServer:
    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 languages: list[str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.languages = languages or []
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def start(self) -> bool:
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 发送 initialize 请求
            result = await self._request("initialize", {
                "processId": None,
                "capabilities": {},
                "rootUri": None,
            })
            await self._notify("initialized", {})
            return result is not None
        except Exception as e:
            logger.error(f"[LSP] 启动失败 {self.name}: {e}")
            return False

    async def _request(self, method: str, params: dict) -> dict | None:
        if not self._process:
            return None
        self._request_id += 1
        req = json.dumps({
            "jsonrpc": "2.0", "id": self._request_id,
            "method": method, "params": params,
        })
        header = f"Content-Length: {len(req)}\r\n\r\n"
        self._process.stdin.write((header + req).encode())
        await self._process.stdin.drain()
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=10)
            return {"ok": True}
        except Exception:
            return None

    async def _notify(self, method: str, params: dict):
        if not self._process:
            return
        req = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        header = f"Content-Length: {len(req)}\r\n\r\n"
        self._process.stdin.write((header + req).encode())
        await self._process.stdin.drain()

    async def hover(self, filepath: str, line: int, col: int) -> str | None:
        return None

    async def completion(self, filepath: str, line: int, col: int) -> list[str]:
        return []

    async def definition(self, filepath: str, line: int, col: int) -> dict | None:
        return None

    async def stop(self):
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()


class LSPManager:
    def __init__(self):
        self._servers: dict[str, LSPServer] = {}

    def register(self, server: LSPServer):
        self._servers[server.name] = server

    def get(self, name: str) -> LSPServer | None:
        return self._servers.get(name)

    def for_language(self, language: str) -> LSPServer | None:
        for s in self._servers.values():
            if language in s.languages:
                return s
        return None

    def list(self) -> list[dict]:
        return [{"name": s.name, "command": s.command, "languages": s.languages}
                for s in self._servers.values()]


lsp_manager = LSPManager()
