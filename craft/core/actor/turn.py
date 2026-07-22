"""
回合 — 移植自 packages/opencode/src/actor/turn.ts
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from craft.core.actor.schema import ActorOutcome, ActorStatus
from craft.core.actor.registry import ActorRegistryInterface


async def run_turn(session_id: str, actor_id: str, work: Callable[[], Any],
                   registry: ActorRegistryInterface):
    """运行一个 turn — 移植自 turn.ts runTurn"""
    try:
        await registry.update_status(session_id, actor_id, ActorStatus.RUNNING)
        try:
            result = await work()
        except asyncio.CancelledError:
            await registry.update_status(
                session_id, actor_id, ActorStatus.IDLE,
                last_outcome=ActorOutcome.CANCELLED
            )
            raise
        except Exception as e:
            await registry.update_status(
                session_id, actor_id, ActorStatus.IDLE,
                last_outcome=ActorOutcome.FAILURE,
                last_error=str(e)
            )
            raise
        else:
            await registry.update_status(
                session_id, actor_id, ActorStatus.IDLE,
                last_outcome=ActorOutcome.SUCCESS
            )
            return result
    except Exception:
        # Re-raise but ensure status is written
        raise
