"""
等待 — 移植自 packages/opencode/src/actor/waiter.ts
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from craft.core.actor.schema import (
    ActorInfo,
    ActorOutcome,
    ActorStatus,
    ActorTime,
    Lifecycle,
)
from craft.core.actor.return_header import (
    ReturnStatus,
    parse_return_header,
)
from craft.core.actor.registry import ActorRegistry


DEFAULT_TIMEOUT_MS = 600_000


def _is_wait_resolving(actor: ActorInfo) -> bool:
    """检查 actor 是否处于可解析状态 — 移植自 waiter.ts isWaitResolving"""
    return (
        actor.status == ActorStatus.IDLE and
        (actor.lifecycle == Lifecycle.EPHEMERAL or
         (actor.last_outcome is not None and actor.last_outcome != ActorOutcome.SUCCESS))
    )


@dataclass
class WaitResult:
    status: ActorStatus | str = "unknown"  # ActorStatus | "timeout" | "unknown"
    actor_id: str = ""
    description: str | None = None
    agent: str | None = None
    background: bool | None = None
    turn_count: int | None = None
    last_turn_time: float | None = None
    result: str | None = None
    error: str | None = None
    last_outcome: ActorOutcome | None = None
    reported_status: ReturnStatus | None = None  # noqa: F821
    reported_summary: str | None = None
    time: ActorTime | None = None


async def wait_actor(registry: ActorRegistry, session_id: str, actor_id: str,
                     timeout_ms: float = DEFAULT_TIMEOUT_MS) -> WaitResult:
    """等待 Actor 完成 — 移植自 waiter.ts wait"""
    entry = await registry.get(session_id, actor_id)
    if not entry:
        return WaitResult(status="unknown", actor_id=actor_id)
    if _is_wait_resolving(entry):
        return await _snapshot(registry, session_id, actor_id, entry)

    # TODO: 实现基于事件的等待（订阅 ActorStatusChanged）
    # 当前实现使用轮询
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        await asyncio.sleep(0.5)
        entry = await registry.get(session_id, actor_id)
        if not entry:
            return WaitResult(status="unknown", actor_id=actor_id)
        if _is_wait_resolving(entry):
            return await _snapshot(registry, session_id, actor_id, entry)
    return WaitResult(status="timeout", actor_id=actor_id)


async def _snapshot(registry: ActorRegistry, session_id: str, actor_id: str,
                    entry: ActorInfo) -> WaitResult:
    """Actor 快照 — 移植自 waiter.ts snapshot"""
    result = None
    if entry.status == ActorStatus.IDLE and entry.last_outcome == ActorOutcome.SUCCESS:
        # 尝试获取最后的消息（简化版）
        result = None  # messages 需要 session 服务
    reported = parse_return_header(result)
    return WaitResult(
        status=entry.status.value if isinstance(entry.status, ActorStatus) else entry.status,
        actor_id=entry.actor_id,
        description=entry.description,
        agent=entry.agent,
        background=entry.background,
        turn_count=entry.turn_count,
        last_turn_time=entry.last_turn_time,
        last_outcome=entry.last_outcome,
        error=entry.last_error,
        result=result,
        reported_status=reported.status,
        reported_summary=reported.summary,
        time=entry.time,
    )
