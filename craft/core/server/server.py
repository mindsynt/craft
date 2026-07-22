"""核心服务器 — 移植自 server.ts

创建、启动、停止 HTTP 服务器。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from craft.core.server import mdns
from craft.core.server.adapter import Adapter, ListenOpts, Listener
from craft.core.server.adapter_node import adapter as default_adapter

logger = logging.getLogger(__name__)


class Server:
    """HTTP 服务器

    对应 TS create() + listen() 的功能整合
    """

    def __init__(self, adapter: Adapter | None = None):
        self._adapter = adapter or default_adapter
        self._runtime: Any = None
        self._listener: Listener | None = None
        self.url: str | None = None

    async def listen(
        self,
        hostname: str = "127.0.0.1",
        port: int = 17890,
        cors: list[str] | None = None,
        no_auth: bool = False,
        mdns_enabled: bool = False,
        mdns_domain: str | None = None,
    ) -> Listener:
        """启动服务器

        对应 TS listen()
        """
        # 检查非回环地址是否配置了密码
        is_loopback = hostname in ("127.0.0.1", "localhost", "::1")
        password = os.environ.get("CRAFT_SERVER_PASSWORD") or os.environ.get("MIMOCODE_SERVER_PASSWORD")
        if not is_loopback and not password and not no_auth:
            raise RuntimeError(
                "Refusing to bind to non-loopback address without CRAFT_SERVER_PASSWORD. "
                "Set the environment variable or pass no_auth to explicitly allow unauthenticated access."
            )

        # 创建应用
        app = self._create_app(cors=cors or [])

        # 启动运行时
        self._runtime = self._adapter.create(app)
        self._listener = self._runtime.listen(ListenOpts(hostname=hostname, port=port))

        if asyncio.iscoroutine(self._listener):
            self._listener = await self._listener

        # 设置 URL
        scheme = "http"
        self.url = f"{scheme}://{hostname}:{self._listener.port}"

        # mDNS 发布
        should_mdns = (
            mdns_enabled
            and self._listener.port
            and hostname not in ("127.0.0.1", "localhost", "::1")
        )
        if should_mdns:
            mdns.publish(self._listener.port, mdns_domain)
        elif mdns_enabled:
            logger.warning("mDNS enabled but hostname is loopback; skipping mDNS publish")

        return self._listener

    def _create_app(self, cors: list[str]) -> Any:
        """创建应用 — 对应 create()

        TODO: 返回 ASGI 应用
        """
        raise NotImplementedError("Subclasses must implement _create_app")

    async def stop(self, close: bool = False):
        """停止服务器

        对应 Listener.stop()
        """
        if self._listener and self._listener.stop:
            result = self._listener.stop(close)
            if asyncio.iscoroutine(result):
                await result

    @property
    def port(self) -> int | None:
        return self._listener.port if self._listener else None
