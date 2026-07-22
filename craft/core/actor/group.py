"""
分组 — 移植自 packages/opencode/src/actor/group.ts
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from craft.core.actor.schema import ActorInfo, ActorOutcome, ActorStatus
from craft.core.actor.registry import ActorRegistry
from craft.core.actor.waiter import DEFAULT_TIMEOUT_MS


@dataclass
class GroupMember:
    session_id: str = ""
    actor_id: str = ""
    description: str | None = None
    agent: str | None = None
    outcome: str = "unknown"  # "success" | "failure" | "cancelled" | "unknown"
    result: str | None = None
    error: str | None = None
    reported_status: str | None = None
    reported_summary: str | None = None


@dataclass
class JoinResult:
    status: str = "complete"  # "complete" | "timeout"
    total: int = 0
    counts: dict = field(default_factory=lambda: {"success": 0, "failure": 0, "cancelled": 0, "unknown": 0})
    members: list[GroupMember] = field(default_factory=list)


async def join_group(registry: ActorRegistry, members: list[dict],
                     timeout_ms: float = DEFAULT_TIMEOUT_MS) -> JoinResult:
    """加入 Actor 组 — 移植自 group.ts joinGroup"""
    # 去重
    seen = set()
    deduped = []
    for m in members:
        key = f"{m['session_id']}:{m['actor_id']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)

    if not deduped:
        return JoinResult(total=0, counts={"success": 0, "failure": 0, "cancelled": 0, "unknown": 0})

    def _terminal_outcome(entry: ActorInfo | None) -> str | None:
        if not entry:
            return None
        if entry.status != ActorStatus.IDLE:
            return None
        return entry.last_outcome.value if entry.last_outcome else None

    # 快照检查
    snapshots = []
    all_settled = True
    for m in deduped:
        entry = await registry.get(m["session_id"], m["actor_id"])
        outcome = _terminal_outcome(entry)
        resolved = outcome if outcome else ("unknown" if not entry else None)
        snapshots.append({"m": m, "entry": entry, "settled": resolved is not None, "outcome": resolved or "unknown"})
        if resolved is None:
            all_settled = False

    if all_settled:
        return _aggregate(snapshots, "complete")

    # 轮询等待所有成员完成（简化版）
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        snapshots = []
        all_settled = True
        for m in deduped:
            entry = await registry.get(m["session_id"], m["actor_id"])
            outcome = _terminal_outcome(entry)
            resolved = outcome if outcome else ("unknown" if not entry else None)
            snapshots.append({
                "m": m, "entry": entry, "settled": resolved is not None,
                "outcome": resolved or "unknown"
            })
            if resolved is None:
                all_settled = False
        if all_settled:
            return _aggregate(snapshots, "complete")
        await asyncio.sleep(0.5)

    # 超时
    return _aggregate(snapshots, "timeout")


def _aggregate(snapshots: list[dict], status: str) -> JoinResult:
    members = []
    for s in snapshots:
        m = s["m"]
        entry = s["entry"]
        outcome = s["outcome"]
        members.append(GroupMember(
            session_id=m["session_id"],
            actor_id=m["actor_id"],
            description=entry.description if entry else None,
            agent=entry.agent if entry else None,
            outcome=outcome,
        ))
    counts = {
        "success": sum(1 for m in members if m.outcome == "success"),
        "failure": sum(1 for m in members if m.outcome == "failure"),
        "cancelled": sum(1 for m in members if m.outcome == "cancelled"),
        "unknown": sum(1 for m in members if m.outcome == "unknown"),
    }
    return JoinResult(status=status, total=len(members), counts=counts, members=members)
