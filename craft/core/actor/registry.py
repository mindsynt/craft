"""
注册表 — 移植自 packages/opencode/src/actor/registry.ts
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from craft.core.actor.schema import (
    DEFAULT_LIVENESS_STALL_MS,
    ActorInfo,
    ActorOutcome,
    ActorStatus,
    ActorTime,
    ContextMode,
    Lifecycle,
    SpawnMode,
    derive_liveness,
)
from craft.core.actor.events import ActorRegistered, ActorStatusChanged

logger = logging.getLogger(__name__)


class ActorRegistryInterface:
    """Actor Registry 接口"""
    async def get(self, session_id: str, actor_id: str) -> ActorInfo | None:
        raise NotImplementedError

    async def update_status(self, session_id: str, actor_id: str, status: ActorStatus,
                            last_outcome: ActorOutcome | None = None,
                            last_error: str | None = None):
        raise NotImplementedError


class ActorRecord(ActorInfo):
    """Actor 记录（注册表中的完整记录）"""
    pass


class ActorRegistry(ActorRegistryInterface):
    """Actor 注册表 — 移植自 registry.ts"""

    def __init__(self):
        self._actors: dict[str, ActorRecord] = {}
        self._lock = asyncio.Lock()
        self._event_handlers: dict[str, list[Callable]] = {
            "registered": [],
            "status_changed": [],
            "stuck": [],
        }

    def on(self, event: str, handler: Callable):
        if event in self._event_handlers:
            self._event_handlers[event].append(handler)

    def _emit(self, event: str, data: Any):
        for handler in self._event_handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"[ActorRegistry] event handler error: {e}")

    async def register(self, session_id: str, actor_id: str, mode: SpawnMode = SpawnMode.SUBAGENT,
                       parent_actor_id: str | None = None, agent: str = "",
                       description: str = "", context_mode: ContextMode = ContextMode.NONE,
                       background: bool = False, lifecycle: Lifecycle = Lifecycle.EPHEMERAL,
                       tools: list[str] | str | None = None) -> ActorRecord:
        """注册 Actor — 移植自 registry.ts register"""
        now = time.time() * 1000
        actor = ActorRecord(
            session_id=session_id,
            actor_id=actor_id,
            mode=mode,
            parent_actor_id=parent_actor_id,
            status=ActorStatus.PENDING,
            lifecycle=lifecycle,
            agent=agent,
            description=description,
            context_mode=context_mode,
            background=background,
            tools=tools,
            last_turn_time=now,
            turn_count=0,
            time=ActorTime(created=now, updated=now),
        )
        async with self._lock:
            self._actors[actor_id] = actor
        self._emit("registered", ActorRegistered(
            session_id=session_id, actor_id=actor_id, mode=mode,
            parent_actor_id=parent_actor_id, description=description,
            agent=agent, background=background,
        ))
        return actor

    async def update_status(self, session_id: str, actor_id: str,
                            status: ActorStatus,
                            last_outcome: ActorOutcome | None = None,
                            last_error: str | None = None):
        """更新 Actor 状态 — 移植自 registry.ts updateStatus"""
        async with self._lock:
            actor = self._actors.get(actor_id)
            if not actor:
                return
            now = time.time() * 1000
            actor.status = status
            actor.time.updated = now
            if last_outcome is not None:
                actor.last_outcome = last_outcome
            if last_error is not None:
                actor.last_error = last_error
            elif last_outcome is not None and last_outcome != ActorOutcome.FAILURE:
                actor.last_error = None
            if status == ActorStatus.IDLE and last_outcome is not None:
                actor.time.completed = now
        self._emit("status_changed", ActorStatusChanged(
            session_id=session_id, actor_id=actor_id,
            status=status, last_outcome=last_outcome,
            turn_count=actor.turn_count, last_turn_time=actor.last_turn_time,
            error=actor.last_error,
        ))

    async def update_turn(self, session_id: str, actor_id: str):
        """更新 turn — 移植自 registry.ts updateTurn"""
        async with self._lock:
            actor = self._actors.get(actor_id)
            if not actor:
                return
            now = time.time() * 1000
            actor.last_turn_time = now
            actor.turn_count += 1
            actor.time.updated = now

    async def update_agent(self, session_id: str, actor_id: str, agent: str):
        """更新 agent 类型 — 移植自 registry.ts updateAgent"""
        async with self._lock:
            actor = self._actors.get(actor_id)
            if not actor:
                return
            actor.agent = agent
            actor.time.updated = time.time() * 1000

    async def get(self, session_id: str, actor_id: str) -> ActorRecord | None:
        """获取 Actor"""
        async with self._lock:
            return self._actors.get(actor_id)

    async def liveness(self, session_id: str, actor_id: str,
                       stall_ms: float = DEFAULT_LIVENESS_STALL_MS) -> dict | None:
        """获取活跃度 — 移植自 registry.ts liveness"""
        actor = await self.get(session_id, actor_id)
        if not actor:
            return None
        return {
            "liveness": derive_liveness(actor, time.time() * 1000, stall_ms),
            "actor": actor,
        }

    async def list_by_session(self, session_id: str) -> list[ActorRecord]:
        """列出会话的所有 Actor"""
        async with self._lock:
            return [a for a in self._actors.values() if a.session_id == session_id]

    async def list_active(self) -> list[ActorRecord]:
        """列出活跃 Actor"""
        async with self._lock:
            return [a for a in self._actors.values()
                    if a.background and a.status in (ActorStatus.PENDING, ActorStatus.RUNNING)]

    async def list_by_parent(self, session_id: str, parent_actor_id: str) -> list[ActorRecord]:
        """列出父 Actor 的子 Actor"""
        async with self._lock:
            return [a for a in self._actors.values()
                    if a.session_id == session_id and a.parent_actor_id == parent_actor_id]

    async def allocate_actor_id(self, session_id: str, agent_type: str) -> str:
        """分配 Actor ID — 移植自 registry.ts allocateActorID"""
        async with self._lock:
            prefix = f"{agent_type}-"
            existing = [a for a in self._actors.values()
                        if a.session_id == session_id and a.agent == agent_type
                        and a.actor_id.startswith(prefix)]
            max_num = 0
            for a in existing:
                n_str = a.actor_id[len(prefix):]
                try:
                    n = int(n_str)
                    if n > max_num:
                        max_num = n
                except ValueError:
                    pass
            return f"{prefix}{max_num + 1}"
