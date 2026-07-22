"""
事件 — 移植自 packages/opencode/src/actor/events.ts
"""

from __future__ import annotations

from dataclasses import dataclass

from craft.core.actor.schema import ActorOutcome, ActorStatus, SpawnMode


@dataclass
class ActorRegistered:
    session_id: str = ""
    actor_id: str = ""
    mode: SpawnMode = SpawnMode.SUBAGENT
    parent_actor_id: str | None = None
    description: str = ""
    agent: str = ""
    background: bool = False


@dataclass
class ActorStatusChanged:
    session_id: str = ""
    actor_id: str = ""
    status: ActorStatus = ActorStatus.PENDING
    last_outcome: ActorOutcome | None = None
    turn_count: int = 0
    last_turn_time: float = 0.0
    error: str | None = None


@dataclass
class ActorStuck:
    session_id: str = ""
    actor_id: str = ""
    description: str = ""
    last_turn_time: float = 0.0
    stuck_duration: float = 0.0


@dataclass
class ActorStalled:
    session_id: str = ""
    actor_id: str = ""
    description: str = ""
    last_turn_time: float = 0.0
    stalled_duration: float = 0.0
