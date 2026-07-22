"""
Actor 运行时 — 移植自 packages/opencode/src/actor/
并发参与者模型
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ActorMessage:
    def __init__(self, type: str, payload: dict | None = None, sender: str = ""):
        self.id = uuid.uuid4().hex[:8]
        self.type = type
        self.payload = payload or {}
        self.sender = sender


class Actor:
    def __init__(self, name: str = ""):
        self.id = f"actor_{uuid.uuid4().hex[:8]}"
        self.name = name or self.id
        self._mailbox: asyncio.Queue[ActorMessage] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"[Actor] 启动: {self.name}")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def send(self, msg: ActorMessage):
        await self._mailbox.put(msg)

    async def _run(self):
        while self._running:
            try:
                msg = await asyncio.wait_for(self._mailbox.get(), timeout=1.0)
                await self.handle(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Actor] 错误 {self.name}: {e}")

    async def handle(self, msg: ActorMessage):
        raise NotImplementedError


class ActorSystem:
    def __init__(self):
        self._actors: dict[str, Actor] = {}

    def register(self, actor: Actor):
        self._actors[actor.id] = actor

    def get(self, actor_id: str) -> Actor | None:
        return self._actors.get(actor_id)

    async def send(self, target: str, msg: ActorMessage):
        actor = self._actors.get(target)
        if actor:
            await actor.send(msg)

    async def broadcast(self, msg: ActorMessage):
        for actor in self._actors.values():
            await actor.send(msg)

    async def start_all(self):
        for actor in self._actors.values():
            await actor.start()

    async def stop_all(self):
        for actor in self._actors.values():
            await actor.stop()

    def list(self) -> list[dict]:
        return [{"id": a.id, "name": a.name, "running": a._running}
                for a in self._actors.values()]


actor_system = ActorSystem()
