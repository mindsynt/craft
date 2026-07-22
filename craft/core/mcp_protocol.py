"""
MCP 协议 — 移植自 packages/opencode/src/mcp/
Model Context Protocol 服务器管理
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class MCPServer:
    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False

    @property
    def configured(self) -> bool:
        return bool(self.command)

    async def connect(self):
        if self._connected:
            return True
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**self.env} if self.env else None,
            )
            self._connected = True
            logger.info(f"[MCP] 已连接: {self.name}")
            return True
        except Exception as e:
            logger.error(f"[MCP] 连接失败 {self.name}: {e}")
            return False

    async def list_tools(self) -> list[dict]:
        if not self._connected:
            return []
        try:
            req = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list"})
            self._process.stdin.write(req.encode() + b"\n")
            await self._process.stdin.drain()
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=5)
            resp = json.loads(line)
            return resp.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"[MCP] 工具列表失败 {self.name}: {e}")
            return []

    async def call_tool(self, name: str, args: dict | None = None) -> dict:
        if not self._connected:
            return {"error": "未连接"}
        try:
            req = json.dumps({
                "jsonrpc": "2.0", "id": "2", "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            })
            self._process.stdin.write(req.encode() + b"\n")
            await self._process.stdin.drain()
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
            return json.loads(line).get("result", {})
        except Exception as e:
            return {"error": str(e)}

    async def disconnect(self):
        if self._process:
            self._process.terminate()
            self._connected = False


class MCPManager:
    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    def register(self, server: MCPServer):
        self._servers[server.name] = server

    def get(self, name: str) -> MCPServer | None:
        return self._servers.get(name)

    def list(self) -> list[dict]:
        return [{"name": s.name, "command": s.command, "connected": s._connected}
                for s in self._servers.values()]

    async def connect_all(self):
        for s in self._servers.values():
            await s.connect()

    async def disconnect_all(self):
        for s in self._servers.values():
            await s.disconnect()


mcp_manager = MCPManager()
