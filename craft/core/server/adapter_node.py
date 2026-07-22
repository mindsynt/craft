"""Node.js 适配器 — 移植自 adapter.node.ts

使用 aiohttp 实现 HTTP/WebSocket 服务。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from craft.core.server.adapter import Adapter, ListenOpts, Listener, Runtime

logger = logging.getLogger(__name__)


class AioHttpRuntime(Runtime):
    """基于 aiohttp 的运行时实现"""

    def __init__(self, app: Any):
        self._app = app
        self._runner: Any = None
        self._site: Any = None

    async def listen(self, opts: ListenOpts) -> Listener:
        """启动 aiohttp 服务"""
        from aiohttp import web

        # 如果传入的是 ASGI/WSGI 应用，将其包装为 aiohttp 处理器
        # 这里假设 app 是一个 web.Application 或者可调用的处理器
        if isinstance(self._app, web.Application):
            app = self._app
        elif callable(self._app):
            app = web.Application()
            app.router.add_route("*", "/{tail:.*}", self._app)
        else:
            app = self._app

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, opts.hostname, opts.port)
        await site.start()

        self._runner = runner
        self._site = site

        # 获取实际绑定的端口
        port = opts.port
        for site_item in runner.sites:
            if hasattr(site_item, "_server") and site_item._server:
                sockets = site_item._server.sockets
                if sockets:
                    port = sockets[0].getsockname()[1]
                    break

        logger.info(
            "Server listening",
            extra={"host": opts.hostname, "port": port},
        )

        return Listener(
            port=port,
            stop=lambda close: self._stop(close),
        )

    async def _stop(self, close: bool = False):
        if self._runner:
            await self._runner.cleanup()


class AioHttpAdapter(Adapter):
    """aiohttp 适配器"""

    def create(self, app: Any) -> Runtime:
        return AioHttpRuntime(app)


# 默认适配器实例
adapter = AioHttpAdapter()
