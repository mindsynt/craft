"""
Actor 运行时 — 移植自 packages/opencode/src/actor/
并发参与者模型, 包含: schema, events, registry, spawn_ref, return_header,
spawn, turn, waiter, group
"""

from __future__ import annotations

from craft.core.actor.schema import (
    DEFAULT_LIVENESS_STALL_MS,
    ActorInfo,
    ActorOutcome,
    ActorStatus,
    ActorTime,
    ContextMode,
    Liveness,
    Lifecycle,
    SpawnMode,
    derive_liveness,
)
from craft.core.actor.events import (
    ActorRegistered,
    ActorStalled,
    ActorStatusChanged,
    ActorStuck,
)
from craft.core.actor.spawn_ref import (
    SpawnRef,
)
from craft.core.actor.return_header import (
    RETURN_STATUSES,
    ParsedReturnHeader,
    ReturnStatus,
    parse_return_header,
)
from craft.core.actor.spawn import (
    SpawnRef as _deprecated_spawnref,  # back-compat
)
from craft.core.actor.registry import (
    ActorRecord,
    ActorRegistry,
    ActorRegistryInterface,
)
from craft.core.actor.turn import (
    run_turn,
)
from craft.core.actor.waiter import (
    DEFAULT_TIMEOUT_MS,
    WaitResult,
    wait_actor,
)
from craft.core.actor.group import (
    GroupMember,
    JoinResult,
    join_group,
)
from craft.core.actor.core import (
    Actor,
    ActorMessage,
    ActorSystem,
    actor_system,
)

__all__ = [
    # schema
    "DEFAULT_LIVENESS_STALL_MS", "ActorInfo", "ActorOutcome", "ActorStatus",
    "ActorTime", "ContextMode", "Liveness", "Lifecycle", "SpawnMode",
    "derive_liveness",
    # events
    "ActorRegistered", "ActorStalled", "ActorStatusChanged", "ActorStuck",
    # spawn_ref
    "SpawnRef",
    # return_header
    "RETURN_STATUSES", "ParsedReturnHeader", "ReturnStatus", "parse_return_header",
    # spawn (back-compat)
    "SpawnRef",
    # registry
    "ActorRecord", "ActorRegistry", "ActorRegistryInterface",
    # turn
    "run_turn",
    # waiter
    "DEFAULT_TIMEOUT_MS", "WaitResult", "wait_actor",
    # group
    "GroupMember", "JoinResult", "join_group",
    # core
    "Actor", "ActorMessage", "ActorSystem", "actor_system",
]
