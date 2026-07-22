"""
Actor 运行时 — 移植自 packages/opencode/src/actor/
并发参与者模型, 包含: schema, events, registry, spawn, turn, waiter, group, return-header, spawn-ref
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


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
# Events (events.ts)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# Turn (turn.ts)
# ═══════════════════════════════════════════════════════════

class ActorRegistryInterface:
    """Actor Registry 接口"""
    async def get(self, session_id: str, actor_id: str) -> ActorInfo | None:
        raise NotImplementedError

    async def update_status(self, session_id: str, actor_id: str, status: ActorStatus,
                            last_outcome: ActorOutcome | None = None,
                            last_error: str | None = None):
        raise NotImplementedError


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


# ═══════════════════════════════════════════════════════════
# Spawn Ref (spawn-ref.ts)
# ═══════════════════════════════════════════════════════════

# 全局引用，用于避免 Actor Registry 和 Session 之间的循环依赖
_current_spawn_service: threading.local = threading.local()


class SpawnRef:
    """Spawn 引用 — 移植自 spawn-ref.ts"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_spawn_service, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_spawn_service.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_spawn_service, "value"):
            del _current_spawn_service.value


# ═══════════════════════════════════════════════════════════
# Registry (registry.ts)
# ═══════════════════════════════════════════════════════════

class ActorRegistry(ActorRegistryInterface):
    """Actor 注册表 — 移植自 registry.ts"""

    def __init__(self):
        self._actors: dict[str, Actor] = {}
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
                       tools: list[str] | str | None = None) -> Actor:
        """注册 Actor — 移植自 registry.ts register"""
        now = time.time() * 1000
        actor = Actor(
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

    async def get(self, session_id: str, actor_id: str) -> Actor | None:
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

    async def list_by_session(self, session_id: str) -> list[Actor]:
        """列出会话的所有 Actor"""
        async with self._lock:
            return [a for a in self._actors.values() if a.session_id == session_id]

    async def list_active(self) -> list[Actor]:
        """列出活跃 Actor"""
        async with self._lock:
            return [a for a in self._actors.values()
                    if a.background and a.status in (ActorStatus.PENDING, ActorStatus.RUNNING)]

    async def list_by_parent(self, session_id: str, parent_actor_id: str) -> list[Actor]:
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


# ═══════════════════════════════════════════════════════════
# Waiter (waiter.ts)
# ═══════════════════════════════════════════════════════════

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
    reported_status: ReturnStatus | None = None
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


# ═══════════════════════════════════════════════════════════
# Group (group.ts)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# 基础 Actor 类 (原始系统保留)
# ═══════════════════════════════════════════════════════════

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
        self.registry = ActorRegistry()

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
