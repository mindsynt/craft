"""
类型定义 — 移植自 packages/opencode/src/actor/schema.ts
"""

from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# Schema (schema.ts)
# ═══════════════════════════════════════════════════════════

class ActorStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    IDLE = "idle"


class ActorOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class Lifecycle(str, enum.Enum):
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class ContextMode(str, enum.Enum):
    NONE = "none"
    STATE = "state"
    FULL = "full"


class SpawnMode(str, enum.Enum):
    PEER = "peer"
    SUBAGENT = "subagent"
    MAIN = "main"


class Liveness(str, enum.Enum):
    PROGRESSING = "progressing"
    STALLED = "stalled"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    IDLE = "idle"


DEFAULT_LIVENESS_STALL_MS = 90_000


@dataclass
class ActorTime:
    created: float = 0.0
    updated: float = 0.0
    completed: float | None = None


@dataclass
class ActorInfo:
    session_id: str = ""
    actor_id: str = ""
    mode: SpawnMode = SpawnMode.SUBAGENT
    parent_actor_id: str | None = None
    status: ActorStatus = ActorStatus.PENDING
    last_outcome: ActorOutcome | None = None
    lifecycle: Lifecycle = Lifecycle.EPHEMERAL
    agent: str = ""
    description: str = ""
    context_mode: ContextMode = ContextMode.NONE
    context_watermark: str | None = None
    background: bool = False
    tools: list[str] | str | None = None  # list of strings or "INHERIT"
    last_turn_time: float = 0.0
    turn_count: int = 0
    last_error: str | None = None
    time: ActorTime = field(default_factory=ActorTime)


def derive_liveness(
    actor: ActorInfo,
    now: float | None = None,
    stall_ms: float = DEFAULT_LIVENESS_STALL_MS,
) -> Liveness:
    """派生活跃度 — 移植自 schema.ts deriveLiveness"""
    if now is None:
        now = time.time() * 1000

    if actor.status in (ActorStatus.RUNNING, ActorStatus.PENDING):
        if actor.turn_count == 0:
            return Liveness.PROGRESSING
        return Liveness.PROGRESSING if (now - actor.last_turn_time <= stall_ms) else Liveness.STALLED

    if actor.last_outcome == ActorOutcome.SUCCESS:
        return Liveness.SUCCESS
    if actor.last_outcome == ActorOutcome.FAILURE:
        return Liveness.FAILURE
    if actor.last_outcome == ActorOutcome.CANCELLED:
        return Liveness.CANCELLED
    return Liveness.IDLE


# ═══════════════════════════════════════════════════════════
# Return Header (return-header.ts)
# ═══════════════════════════════════════════════════════════

RETURN_STATUSES = ["success", "partial", "failed", "blocked"]
ReturnStatus = str  # "success" | "partial" | "failed" | "blocked"


@dataclass
class ParsedReturnHeader:
    status: ReturnStatus | None = None
    summary: str | None = None


STATUS_RE = re.compile(r"^\s*\*\*Status\*\*:\s*(success|partial|failed|blocked)\b", re.IGNORECASE | re.MULTILINE)
SUMMARY_RE = re.compile(r"\*\*Summary\*\*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def parse_return_header(final_text: str | None) -> ParsedReturnHeader:
    """解析 **Status**/**Summary** 头部 — 移植自 return-header.ts parseReturnHeader"""
    if not final_text:
        return ParsedReturnHeader()
    status_match = STATUS_RE.search(final_text)
    summary_match = SUMMARY_RE.search(final_text)
    return ParsedReturnHeader(
        status=status_match.group(1).lower() if status_match else None,
        summary=summary_match.group(1).strip() if summary_match else None,
    )
