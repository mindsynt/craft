"""
定时任务系统 — 移植自 packages/opencode/src/cron/
基于 asyncio 的轻量调度器，支持 cron 表达式、一次性、重复任务
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 原 CronParser / CronJob / CronScheduler（保留）
# ═══════════════════════════════════════════════════════════


@dataclass
class CronJob:
    id: str
    name: str
    enabled: bool = True
    interval_seconds: float = 0
    cron_expr: str = ""
    last_run: float = 0
    next_run: float = 0
    run_count: int = 0
    max_runs: int = 0
    handler: Callable | None = None
    one_shot: bool = False
    # 新增字段（与 TS CronTask 对应）
    created_at: float = 0
    last_fired_at: float | None = None
    recurring: bool | None = None
    permanent: bool | None = None
    kind: str | None = None
    created_by_session_id: str | None = None
    created_by_pid: int | None = None
    created_by_proc_start: float | None = None
    durable: bool | None = None
    agent_id: str | None = None


class CronParser:
    """简易 cron 表达式解析器"""
    @staticmethod
    def next_time(expr: str) -> float | None:
        now = datetime.now()
        parts = expr.strip().split()
        if len(parts) == 5:
            minute = parts[0]
            hour = parts[1]
            if minute == "*" and hour == "*":
                return (now + timedelta(minutes=1)).timestamp()
            if minute == "*":
                h = int(hour)
                next_dt = now.replace(hour=h, minute=0, second=0)
                if next_dt <= now:
                    next_dt += timedelta(days=1)
                return next_dt.timestamp()
            if hour == "*":
                m = int(minute)
                next_dt = now.replace(minute=m, second=0)
                if next_dt <= now:
                    next_dt += timedelta(hours=1)
                return next_dt.timestamp()
        return None


# ═══════════════════════════════════════════════════════════
# 增强 Cron 表达式 — 移植自 cron-expr.ts
# ═══════════════════════════════════════════════════════════

FIELD_RANGES = [
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 6),
]


@dataclass
class CronFields:
    minute: list[int]
    hour: list[int]
    dom: list[int]
    month: list[int]
    dow: list[int]
    dom_star: bool = False
    dow_star: bool = False


def _expand_field(token: str, lo: int, hi: int) -> list[int] | None:
    out: set[int] = set()
    for part in token.split(","):
        range_part, _, step_str = part.partition("/")
        step = int(step_str) if step_str else 1
        if step < 1:
            return None
        if range_part == "*":
            start_str, end_str = str(lo), str(hi)
        elif "-" in range_part:
            start_str, _, end_str = range_part.partition("-")
        else:
            start_str, end_str = range_part, ""

        start = int(start_str)
        end = int(end_str) if end_str else (hi if step_str else start)
        if start < lo or end > hi or start > end:
            return None
        for n in range(start, end + 1, step):
            out.add(n)
    return sorted(out)


def _is_star(token: str) -> bool:
    return token == "*" or token == "*/1"


def parse_cron_expression(expr: str) -> CronFields | None:
    """解析标准 5 字段 cron 表达式"""
    parts = expr.strip().split()
    if len(parts) != 5:
        return None
    fields_list = []
    for i, p in enumerate(parts):
        lo, hi = FIELD_RANGES[i]
        f = _expand_field(p, lo, hi)
        if f is None:
            return None
        fields_list.append(f)
    return CronFields(
        minute=fields_list[0],
        hour=fields_list[1],
        dom=fields_list[2],
        month=fields_list[3],
        dow=fields_list[4],
        dom_star=_is_star(parts[2]),
        dow_star=_is_star(parts[4]),
    )


def compute_next_cron_run(expr: str, from_dt: datetime | None = None) -> datetime | None:
    """计算下一次 cron 触发时间"""
    f = parse_cron_expression(expr)
    if not f:
        return None
    if from_dt is None:
        from_dt = datetime.now(timezone.utc)
    limit = from_dt + timedelta(days=365)
    d = from_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while d <= limit:
        day_matches: bool
        if f.dom_star or f.dow_star:
            day_matches = d.day in f.dom and d.weekday() in f.dow
        else:
            day_matches = d.day in f.dom or d.weekday() in f.dow
        if (
            d.month in f.month
            and day_matches
            and d.hour in f.hour
            and d.minute in f.minute
        ):
            return d
        d += timedelta(minutes=1)
    return None


def cron_to_human(expr: str) -> str:
    """将 cron 表达式转为可读文本"""
    import re
    m = re.match(r"^\*/(\d+) \* \* \* \*$", expr)
    if m:
        return f"every {m.group(1)} minutes"
    if expr == "0 * * * *":
        return "hourly"
    day_map = {"1-5": "weekdays", "0,6": "weekends"}
    wd = re.match(r"^(\d+) (\d+) \* \* (.+)$", expr)
    if wd and wd.group(3) in day_map:
        return f"{day_map[wd.group(3)]} at {wd.group(2)}:{wd.group(1).zfill(2)}"
    pinned = re.match(r"^(\d+) (\d+) (\d+) (\d+) \*$", expr)
    if pinned:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{months[int(pinned.group(4)) - 1]} {pinned.group(3)} {pinned.group(2)}:{pinned.group(1).zfill(2)}"
    return expr


# ═══════════════════════════════════════════════════════════
# Jitter — 移植自 cron-jitter.ts
# ═══════════════════════════════════════════════════════════

@dataclass
class JitterConfig:
    recurring_frac: float = 0.5
    recurring_cap_ms: float = 1_800_000
    one_shot_max_ms: float = 90_000
    one_shot_floor_ms: float = 0
    one_shot_minute_mod: int = 30
    recurring_max_age_ms: float = 7 * 24 * 60 * 60 * 1000
    cache_lead_ms: float = 15_000


DEFAULT_JITTER = JitterConfig()

CACHE_CLIFF_MINUTES = 5
EVERY_N_MIN_RE = __import__("re").compile(r"^\*/\d+ \* \* \* \*$")


def _hash_unit(s: str) -> float:
    h = 0
    for ch in s:
        h = ((h * 31) + ord(ch)) & 0xFFFFFFFF
    return ((h % 1_000_000) / 1_000_000)


def _next_run_ms(cron: str, from_ms: float) -> float | None:
    from_dt = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc)
    d = compute_next_cron_run(cron, from_dt)
    if d is None:
        return None
    return d.timestamp() * 1000


def jittered_next_cron_run_ms(
    cron: str, from_ms: float, task_id: str, cfg: JitterConfig | None = None
) -> float | None:
    if cfg is None:
        cfg = DEFAULT_JITTER
    first = _next_run_ms(cron, from_ms)
    if first is None:
        return None
    on_cache_cliff = (
        bool(EVERY_N_MIN_RE.match(cron))
        and cfg.cache_lead_ms > 0
        and int(datetime.fromtimestamp(first / 1000, tz=timezone.utc).minute) % CACHE_CLIFF_MINUTES == 0
    )
    if on_cache_cliff:
        pull = _hash_unit(task_id) * cfg.cache_lead_ms
        target = first if first - cfg.cache_lead_ms >= from_ms else _next_run_ms(cron, first)
        if target is None:
            return first
        return target - pull
    following_ms = _next_run_ms(cron, first)
    if following_ms is None:
        return first
    period_ms = following_ms - first
    j = min(_hash_unit(task_id) * cfg.recurring_frac * period_ms, cfg.recurring_cap_ms)
    return first + j


def one_shot_jittered_next_cron_run_ms(
    cron: str, created_at_ms: float, task_id: str, cfg: JitterConfig | None = None
) -> float | None:
    if cfg is None:
        cfg = DEFAULT_JITTER
    nxt = _next_run_ms(cron, created_at_ms)
    if nxt is None:
        return None
    if int(datetime.fromtimestamp(nxt / 1000, tz=timezone.utc).minute) % cfg.one_shot_minute_mod != 0:
        return nxt
    pull = cfg.one_shot_floor_ms + _hash_unit(task_id) * (cfg.one_shot_max_ms - cfg.one_shot_floor_ms)
    return max(nxt - pull, created_at_ms)


# ═══════════════════════════════════════════════════════════
# Cron Lock — 移植自 cron-lock.ts
# ═══════════════════════════════════════════════════════════

PROC_STARTED_AT = time.time() * 1000  # approximate epoch ms


@dataclass
class LockInfo:
    pid: int
    started_at: float
    identity: str | None = None


def get_lock_file_path(dir_path: str | None = None) -> str:
    base = Path(dir_path) if dir_path else Path.cwd()
    return str(base / ".craft" / ".cron-lock")


def _parse_lock_info(raw: str) -> LockInfo | None:
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    pid = obj.get("pid")
    started_at = obj.get("startedAt")
    if not isinstance(pid, int) or not isinstance(started_at, (int, float)):
        return None
    info = LockInfo(pid=pid, started_at=started_at)
    if isinstance(obj.get("identity"), str):
        info.identity = obj["identity"]
    return info


def _is_pid_alive(pid: int, lock_started_at_ms: float) -> bool:
    """Check if a PID is still alive (Unix-only)"""
    try:
        os.kill(pid, 0)
    except OSError as e:
        # EPERM = alive but can't signal; treat as alive
        if e.errno == 1:  # EPERM
            return True
        return False
    return True


def _write_lock_exclusive(path: str, info: LockInfo) -> str:
    """Returns 'created', 'exists', or 'error'."""
    try:
        flag = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(path, flag, 0o644)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({
                "pid": info.pid,
                "startedAt": info.started_at,
                "identity": info.identity,
            }))
        return "created"
    except FileExistsError:
        return "exists"
    except OSError:
        return "error"


def _overwrite_lock(path: str, info: LockInfo) -> bool:
    """Atomic overwrite via temp file + rename."""
    import tempfile
    tmp = f"{path}.tmp.{info.pid}"
    try:
        with open(tmp, "w") as f:
            f.write(json.dumps({
                "pid": info.pid,
                "startedAt": info.started_at,
                "identity": info.identity,
            }))
        os.replace(tmp, path)
        with open(path) as f:
            raw = f.read()
        parsed = _parse_lock_info(raw)
        return parsed is not None and parsed.pid == info.pid and parsed.started_at == info.started_at
    except OSError:
        return False


def _read_lock_file(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return None


def try_acquire_scheduler_lock(dir_path: str | None = None, lock_identity: str | None = None) -> bool:
    """Try to acquire the scheduler lock. Returns True if we are the owner."""
    path = get_lock_file_path(dir_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    self_info = LockInfo(
        pid=os.getpid(),
        started_at=PROC_STARTED_AT,
        identity=lock_identity,
    )

    result = _write_lock_exclusive(path, self_info)
    if result == "created":
        logger.debug("[CronLock] acquired (fresh)")
        return True
    if result == "error":
        logger.debug("[CronLock] acquire failed (unexpected fs error)")
        return False

    raw = _read_lock_file(path)
    if raw is None:
        own = _overwrite_lock(path, self_info)
        return own

    existing = _parse_lock_info(raw)
    if existing is None:
        logger.debug("[CronLock] malformed lock; taking over")
        return _overwrite_lock(path, self_info)

    if existing.pid == self_info.pid and existing.started_at == self_info.started_at:
        logger.debug("[CronLock] already owned by self (idempotent)")
        return True

    if not _is_pid_alive(existing.pid, existing.started_at):
        logger.debug("[CronLock] previous owner dead; taking over")
        return _overwrite_lock(path, self_info)

    logger.debug("[CronLock] lock held by live process")
    return False


def release_scheduler_lock(dir_path: str | None = None) -> None:
    """Release the scheduler lock if we own it."""
    path = get_lock_file_path(dir_path)
    raw = _read_lock_file(path)
    if raw is None:
        return
    existing = _parse_lock_info(raw)
    if existing is None or existing.pid != os.getpid():
        return
    try:
        os.unlink(path)
        logger.debug("[CronLock] released")
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════
# CronTask Persistence — 移植自 cron-task.ts
# ═══════════════════════════════════════════════════════════

CRON_TASKS_DIR = CONFIG_DIR
CRON_TASKS_FILE = CRON_TASKS_DIR / "scheduled_tasks.json"


def _get_cron_file_path(dir_path: str | None = None) -> Path:
    if dir_path:
        return Path(dir_path) / ".craft" / "scheduled_tasks.json"
    return CRON_TASKS_FILE


def _is_valid_task(t: Any) -> bool:
    if not isinstance(t, dict):
        return False
    if not isinstance(t.get("id"), str):
        return False
    if not isinstance(t.get("cron"), str):
        return False
    if not isinstance(t.get("prompt"), str):
        return False
    if not isinstance(t.get("createdAt"), (int, float)):
        return False
    return True


def _strip_runtime(t: dict) -> dict:
    out = dict(t)
    out.pop("agentId", None)
    return out


def read_cron_tasks(dir_path: str | None = None) -> list[dict]:
    """读取持久化的 cron 任务"""
    path = _get_cron_file_path(dir_path)
    try:
        raw = path.read_text()
        data = json.loads(raw)
        tasks = data.get("tasks", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        valid = []
        for t in tasks:
            if _is_valid_task(t):
                valid.append(t)
            else:
                logger.debug(f"[CronTask] dropped malformed task on read")
        return valid
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_cron_tasks(tasks: list[dict], dir_path: str | None = None) -> None:
    """写入持久化的 cron 任务"""
    path = _get_cron_file_path(dir_path)
    valid = [t for t in tasks if _is_valid_task(t)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tasks": [_strip_runtime(t) for t in valid]}, indent=2))


# 会话内任务存储（内存）
_SESSION_TASK_STORE: dict[str, dict] = {}


def add_session_cron_task(t: dict) -> None:
    t["durable"] = False
    _SESSION_TASK_STORE[t["id"]] = t


def get_session_cron_tasks() -> list[dict]:
    return list(_SESSION_TASK_STORE.values())


def remove_session_cron_tasks(ids: list[str]) -> None:
    for id_ in ids:
        _SESSION_TASK_STORE.pop(id_, None)


def find_missed_tasks(tasks: list[dict], now_ms: float) -> list[dict]:
    """Find one-shot tasks that were due before now but never fired."""
    missed = []
    for t in tasks:
        if t.get("recurring"):
            continue
        if t.get("createdAt", 0) > now_ms:
            continue
        anchor_ms = t.get("lastFiredAt") or t.get("createdAt")
        anchor_dt = datetime.fromtimestamp(anchor_ms / 1000, tz=timezone.utc)
        nxt = compute_next_cron_run(t["cron"], anchor_dt)
        if nxt is None:
            continue
        if nxt.timestamp() * 1000 <= now_ms:
            missed.append(t)
    return missed


def mark_cron_tasks_fired(ids: list[str], fired_at_ms: float, dir_path: str | None = None) -> None:
    """Update lastFiredAt for tasks by ID."""
    tasks = read_cron_tasks(dir_path)
    id_set = set(ids)
    updated = [
        {**t, "lastFiredAt": fired_at_ms} if t["id"] in id_set else t
        for t in tasks
    ]
    write_cron_tasks(updated, dir_path)


# ═══════════════════════════════════════════════════════════
# Sentinel — 移植自 sentinel.ts
# ═══════════════════════════════════════════════════════════

LOOP_FILE_SENTINEL = "<<loop.md>>"
LOOP_FILE_DYNAMIC_SENTINEL = "<<loop.md-dynamic>>"
AUTONOMOUS_LOOP_SENTINEL = "<<autonomous-loop>>"
AUTONOMOUS_LOOP_DYNAMIC_SENTINEL = "<<autonomous-loop-dynamic>>"

SENTINELS = {
    LOOP_FILE_SENTINEL,
    LOOP_FILE_DYNAMIC_SENTINEL,
    AUTONOMOUS_LOOP_SENTINEL,
    AUTONOMOUS_LOOP_DYNAMIC_SENTINEL,
}


def is_sentinel(s: str) -> bool:
    return s in SENTINELS


def _is_autonomous(s: str) -> bool:
    return s in (AUTONOMOUS_LOOP_SENTINEL, AUTONOMOUS_LOOP_DYNAMIC_SENTINEL)


def _is_loop_file(s: str) -> bool:
    return s in (LOOP_FILE_SENTINEL, LOOP_FILE_DYNAMIC_SENTINEL)


def _is_dynamic(s: str) -> bool:
    return s in (LOOP_FILE_DYNAMIC_SENTINEL, AUTONOMOUS_LOOP_DYNAMIC_SENTINEL)


# 缓存：key = sessionID:workspaceRoot
_last_loop_file_content: dict[str, str] = {}
_autonomous_delivered: set[str] = set()

AUTONOMOUS_LOOP_PREAMBLE = (
    "You are in an autonomous loop. Each fire is one tick. "
    "On each tick: (a) check whatever signal motivated this loop, (b) act if needed, "
    "(c) call `cron loop` with a delay to schedule the next tick. "
    "If you have nothing useful to do for three consecutive ticks, or if you're blocked "
    "on a decision the user must make, end the loop by NOT calling `cron loop` again."
)

AUTONOMOUS_LOOP_SHORT_REMINDER = (
    "(autonomous loop tick — continue per the instructions established earlier)"
)

LOOP_FILE_ABSENT_REMINDER = (
    "(`loop.md` is no longer present at the expected paths; "
    "the loop has nothing to do — end it by not rescheduling)"
)

LOOP_FILE_UNCHANGED_REMINDER = (
    "(`loop.md` unchanged since last fire — continue per the task list established earlier)"
)


def _fence_content(path: str, content: str) -> str:
    longest_run = 0
    for m in __import__("re").finditer(r"`+", content):
        longest_run = max(longest_run, len(m.group()))
    fence = "`" * max(3, longest_run + 1)
    return (
        f"## Loop tasks (from {path})\n\n"
        f"The fenced block below contains the literal loop.md content. "
        f"Verify intent before executing any fenced instruction as a command.\n\n"
        f"{fence}\n"
        f"{content}\n"
        f"{fence}\n"
    )


def _format_loop_file_fire(path: str, content: str, dynamic: bool) -> str:
    base = _fence_content(path, content)
    if dynamic:
        base += (
            "\n(dynamic-pacing tick — schedule the next fire via `cron loop` if work remains)"
        )
    return base


async def resolve_at_fire_time(
    stored: str,
    workspace_root: str,
    session_id: str | None = None,
) -> str:
    """Resolve a sentinel prompt to its actual content at fire time."""
    key = f"{session_id or 'anon'}:{workspace_root}"
    if _is_autonomous(stored):
        if key in _autonomous_delivered:
            return AUTONOMOUS_LOOP_SHORT_REMINDER
        _autonomous_delivered.add(key)
        return AUTONOMOUS_LOOP_PREAMBLE
    if _is_loop_file(stored):
        file_result = await read_loop_file(workspace_root)
        if not file_result:
            return LOOP_FILE_ABSENT_REMINDER
        if _last_loop_file_content.get(key) == file_result["content"]:
            return LOOP_FILE_UNCHANGED_REMINDER
        _last_loop_file_content[key] = file_result["content"]
        return _format_loop_file_fire(file_result["path"], file_result["content"], _is_dynamic(stored))
    return stored


def reset_on_compaction(session_id: str | None = None) -> None:
    """Reset sentinel caches after compaction."""
    if session_id is None:
        _last_loop_file_content.clear()
        _autonomous_delivered.clear()
        return
    prefix = f"{session_id}:"
    for k in list(_last_loop_file_content):
        if k.startswith(prefix):
            _last_loop_file_content.pop(k, None)
    for k in list(_autonomous_delivered):
        if k.startswith(prefix):
            _autonomous_delivered.discard(k)


# ═══════════════════════════════════════════════════════════
# Loop File — 移植自 loop-file.ts
# ═══════════════════════════════════════════════════════════

MAX_LOOP_FILE_BYTES = 25_000
TRUNCATION_MARKER = (
    "\n\n> WARNING: loop.md was truncated to 25000 bytes. Keep the task list concise."
)


async def read_loop_file(workspace_root: str) -> dict | None:
    """Read loop.md from project (.craft/loop.md) or home (~/loop.md)."""
    candidates = [
        Path(workspace_root) / ".craft" / "loop.md",
        Path.home() / "loop.md",
    ]
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        if len(content) > MAX_LOOP_FILE_BYTES:
            return {
                "path": str(path),
                "content": content[:MAX_LOOP_FILE_BYTES] + TRUNCATION_MARKER,
            }
        return {"path": str(path), "content": content}
    return None


# ═══════════════════════════════════════════════════════════
# Loop State — 移植自 loop-state.ts
# ═══════════════════════════════════════════════════════════

@dataclass
class LoopState:
    prompt: str
    started_at: float
    last_scheduled_for: float
    aged_out: bool = False
    keepalive_strikes: int = 0


_LOOP_STATES: dict[str, LoopState] = {}


def get_loop_state(prompt: str) -> LoopState | None:
    return _LOOP_STATES.get(prompt)


def set_loop_state(state: LoopState) -> None:
    _LOOP_STATES[state.prompt] = state


def delete_loop_state(prompt: str) -> None:
    _LOOP_STATES.pop(prompt, None)


def list_loop_states() -> list[LoopState]:
    return list(_LOOP_STATES.values())


def clear_all_loop_states() -> None:
    _LOOP_STATES.clear()


def reset_strikes(prompt: str) -> None:
    s = _LOOP_STATES.get(prompt)
    if s:
        s.keepalive_strikes = 0


def increment_strikes(prompt: str) -> int:
    s = _LOOP_STATES.get(prompt)
    if not s:
        return 0
    s.keepalive_strikes += 1
    return s.keepalive_strikes


def get_strikes(prompt: str) -> int:
    s = _LOOP_STATES.get(prompt)
    return s.keepalive_strikes if s else 0


# ═══════════════════════════════════════════════════════════
# 增强 Scheduler — 移植自 scheduler.ts
# ═══════════════════════════════════════════════════════════

class LoopEndedReason:
    GATE_OFF = "gate_off"
    MODEL_STOPPED = "model_stopped"
    AGED_OUT = "aged_out"
    USER_ABORT = "user_abort"
    BUDGET = "budget"
    ERROR = "error"


@dataclass
class LoopEndedEvent:
    reason: str
    prompt: str
    via_keepalive: bool | None = None


@dataclass
class StartOpts:
    workspace_root: str
    session_id: str
    is_loading: Callable[[], bool]
    is_killed: Callable[[], bool]
    on_fire: Callable[[dict], None]
    on_loop_ended: Callable[[LoopEndedEvent], None]
    on_arm_loop: Callable[[str], None] | None = None
    dir_path: str | None = None
    jitter_config: JitterConfig | None = None


@dataclass
class NewCronTask:
    session_id: str
    cron: str
    prompt: str
    recurring: bool
    durable: bool
    kind: str | None = None


@dataclass
class ArmLoopInput:
    prompt: str
    delay_seconds: int
    reason_length: int
    via_keepalive: bool = False


@dataclass
class ArmLoopResult:
    scheduled_for: float
    clamped_delay_seconds: int
    was_clamped: bool
    superseded_count: int


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class SchedulerInterface:
    """Interface matching the TS Scheduler Interface."""

    async def start(self, opts: StartOpts) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def add(self, task: NewCronTask) -> dict:
        raise NotImplementedError

    async def remove(self, id_: str, opts: dict | None = None) -> bool:
        raise NotImplementedError

    async def rename(self, id_: str, prompt: str, opts: dict | None = None) -> bool:
        raise NotImplementedError

    async def list(self, filter_: dict | None = None) -> list[dict]:
        raise NotImplementedError

    async def get(self, id_: str, opts: dict | None = None) -> dict | None:
        raise NotImplementedError

    async def arm_loop(self, input_: ArmLoopInput) -> ArmLoopResult | None:
        raise NotImplementedError

    async def reset_keepalive_strikes(self, prompt: str) -> None:
        raise NotImplementedError

    async def increment_keepalive_strikes(self, prompt: str) -> None:
        raise NotImplementedError

    async def end_loop(self, prompt: str, reason: str, opts: dict | None = None) -> None:
        raise NotImplementedError

    async def next_fire_time(self) -> float | None:
        raise NotImplementedError

    async def tick_once(self) -> None:
        raise NotImplementedError


class EnhancedScheduler:
    """Full-featured scheduler ported from scheduler.ts"""

    def __init__(self):
        self._opts: StartOpts | None = None
        self._cfg: JitterConfig | None = None
        self._interval_handle: asyncio.TimerHandle | None = None
        self._in_flight: set[str] = set()
        self._next_fire_at: dict[str, float] = {}
        self._is_owner: bool = False
        self._running: bool = False
        self._loop_task: asyncio.Task | None = None

    def _compute_next_fire_for(self, task: dict, anchor_ms: float, cfg: JitterConfig) -> float:
        if task.get("recurring"):
            fn = jittered_next_cron_run_ms
        else:
            fn = one_shot_jittered_next_cron_run_ms
        result = fn(task["cron"], anchor_ms, task["id"], cfg)
        return result if result is not None else float("inf")

    async def start(self, opts: StartOpts) -> None:
        if self._opts:
            return
        self._cfg = opts.jitter_config or DEFAULT_JITTER
        self._is_owner = try_acquire_scheduler_lock(opts.dir_path)
        self._opts = opts
        logger.info(f"[Scheduler] start session={opts.session_id} isOwner={self._is_owner}")

        # Surface missed tasks
        if self._is_owner:
            all_tasks = read_cron_tasks(opts.dir_path)
            missed = find_missed_tasks(all_tasks, time.time() * 1000)
            for task in missed:
                opts.on_fire(task)
                remaining = [t for t in read_cron_tasks(opts.dir_path) if t["id"] != task["id"]]
                write_cron_tasks(remaining, opts.dir_path)
            if missed:
                logger.info(f"[Scheduler] surfaced {len(missed)} missed tasks")

        self._running = True
        self._loop_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        if self._is_owner:
            release_scheduler_lock(self._opts.dir_path if self._opts else None)
        logger.info("[Scheduler] stopped")

    async def _tick_loop(self) -> None:
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Scheduler] tick error: {e}")
            await asyncio.sleep(1)

    async def _tick_once(self) -> None:
        opts = self._opts
        if not opts:
            return
        if opts.is_killed():
            return
        if opts.is_loading():
            return

        session_tasks = get_session_cron_tasks()
        session_ids = {t["id"] for t in session_tasks}
        file_tasks = read_cron_tasks(opts.dir_path) if self._is_owner else []
        tasks = file_tasks + session_tasks
        now_ms = time.time() * 1000

        fired_this_tick = False
        for task in tasks:
            if fired_this_tick:
                break
            if opts.is_loading():
                break
            if opts.is_killed():
                break
            if task["id"] in self._in_flight:
                continue

            if task["id"] not in self._next_fire_at:
                anchor_ms = task.get("lastFiredAt") or task.get("createdAt", now_ms)
                self._next_fire_at[task["id"]] = self._compute_next_fire_for(task, anchor_ms, self._cfg or DEFAULT_JITTER)

            due = self._next_fire_at.get(task["id"], float("inf"))
            if now_ms < due:
                continue

            recurring = task.get("recurring", False)
            permanent = task.get("permanent", False)
            created_at = task.get("createdAt", 0)
            aged = (
                recurring is True
                and permanent is not True
                and now_ms - created_at >= (self._cfg or DEFAULT_JITTER).recurring_max_age_ms
            )

            is_file_task = task["id"] not in session_ids
            opts.on_fire(task)
            fired_this_tick = True

            if recurring is True and not aged:
                self._next_fire_at[task["id"]] = self._compute_next_fire_for(task, now_ms, self._cfg or DEFAULT_JITTER)
                if is_file_task:
                    self._in_flight.add(task["id"])
                    try:
                        mark_cron_tasks_fired([task["id"]], now_ms, opts.dir_path)
                    except Exception:
                        pass
                    self._in_flight.discard(task["id"])
                continue

            self._in_flight.add(task["id"])
            self._next_fire_at.pop(task["id"], None)
            if is_file_task:
                try:
                    current = read_cron_tasks(opts.dir_path)
                    write_cron_tasks([t for t in current if t["id"] != task["id"]], opts.dir_path)
                except Exception:
                    pass
            else:
                remove_session_cron_tasks([task["id"]])
            self._in_flight.discard(task["id"])

            if aged:
                opts.on_loop_ended(LoopEndedEvent(reason=LoopEndedReason.AGED_OUT, prompt=task.get("prompt", "")))

    async def add(self, input_: NewCronTask) -> dict:
        id_ = _new_id()
        created = {
            "id": id_,
            "cron": input_.cron,
            "prompt": input_.prompt,
            "createdAt": time.time() * 1000,
            "recurring": input_.recurring,
            "durable": input_.durable,
        }
        if input_.kind:
            created["kind"] = input_.kind
        if input_.session_id:
            created["createdBySessionId"] = input_.session_id

        if input_.durable:
            dir_ = self._opts.dir_path if self._opts else None
            existing = read_cron_tasks(dir_)
            write_cron_tasks([*existing, created], dir_)
            return created

        add_session_cron_task(created)
        return created

    async def _find_by_id(self, id_: str, session_id: str | None = None) -> dict | None:
        dir_ = self._opts.dir_path if self._opts else None
        session_tasks = get_session_cron_tasks()
        file_tasks = read_cron_tasks(dir_) if self._opts else []
        all_tasks = file_tasks + session_tasks
        for t in all_tasks:
            if t["id"] == id_:
                if session_id and t.get("createdBySessionId") and t["createdBySessionId"] != session_id:
                    return None
                return t
        return None

    async def _remove_by(self, id_: str, session_id: str | None = None) -> bool:
        target = await self._find_by_id(id_, session_id)
        if not target:
            return False
        dir_ = self._opts.dir_path if self._opts else None
        session = get_session_cron_tasks()
        in_session = any(t["id"] == id_ for t in session)
        if in_session:
            remove_session_cron_tasks([id_])
            self._next_fire_at.pop(id_, None)
            return True
        file_tasks = read_cron_tasks(dir_)
        next_tasks = [t for t in file_tasks if t["id"] != id_]
        if len(next_tasks) == len(file_tasks):
            return False
        write_cron_tasks(next_tasks, dir_)
        self._next_fire_at.pop(id_, None)
        return True

    async def remove(self, id_: str, opts: dict | None = None) -> bool:
        return await self._remove_by(id_, opts.get("session_id") if opts else None)

    async def rename(self, id_: str, prompt: str, opts: dict | None = None) -> bool:
        target = await self._find_by_id(id_, opts.get("session_id") if opts else None)
        if not target:
            return False
        dir_ = self._opts.dir_path if self._opts else None
        session = get_session_cron_tasks()
        found = next((t for t in session if t["id"] == id_), None)
        if found:
            remove_session_cron_tasks([id_])
            updated = {**found, "prompt": prompt}
            add_session_cron_task(updated)
            return True
        file_tasks = read_cron_tasks(dir_)
        idx = next((i for i, t in enumerate(file_tasks) if t["id"] == id_), -1)
        if idx < 0:
            return False
        next_tasks = list(file_tasks)
        next_tasks[idx] = {**next_tasks[idx], "prompt": prompt}
        write_cron_tasks(next_tasks, dir_)
        return True

    async def list(self, filter_: dict | None = None) -> list[dict]:
        if filter_ is None:
            filter_ = {}
        dir_ = self._opts.dir_path if self._opts else None
        file_tasks = read_cron_tasks(dir_)
        session = get_session_cron_tasks()
        all_tasks = [
            *[dict(t, durable=True) for t in file_tasks],
            *[dict(t, durable=False) for t in session],
        ]

        session_id_filter = filter_.get("session_id")
        kind_filter = filter_.get("kind")
        durable_only = filter_.get("durable_only")

        def matches(t: dict) -> bool:
            if session_id_filter and t.get("createdBySessionId") != session_id_filter:
                return False
            if kind_filter == "loop" and t.get("kind") != "loop":
                return False
            if kind_filter == "cron" and t.get("kind") == "loop":
                return False
            if durable_only and t.get("durable") is not True:
                return False
            return True

        return [t for t in all_tasks if matches(t)]

    async def get(self, id_: str, opts: dict | None = None) -> dict | None:
        return await self._find_by_id(id_, opts.get("session_id") if opts else None)

    async def arm_loop(self, input_: ArmLoopInput) -> ArmLoopResult | None:
        opts = self._opts
        if not opts or opts.is_killed():
            return None
        cfg = self._cfg or DEFAULT_JITTER
        now_ms = time.time() * 1000
        existing = get_loop_state(input_.prompt)

        if existing and now_ms - existing.started_at >= cfg.recurring_max_age_ms:
            stale_prior = [t for t in get_session_cron_tasks()
                           if t.get("kind") == "loop" and t.get("prompt") == input_.prompt]
            if stale_prior:
                remove_session_cron_tasks([p["id"] for p in stale_prior])
                for p in stale_prior:
                    self._next_fire_at.pop(p["id"], None)
            delete_loop_state(input_.prompt)
            opts.on_loop_ended(LoopEndedEvent(reason=LoopEndedReason.AGED_OUT, prompt=input_.prompt))
            return None

        clamped = max(60, min(3600, input_.delay_seconds))
        was_clamped = clamped != input_.delay_seconds

        target_dt = datetime.fromtimestamp((now_ms + clamped * 1000) / 1000, tz=timezone.utc)
        target_dt = target_dt.replace(second=0, microsecond=0)
        if target_dt.timestamp() * 1000 <= now_ms:
            target_dt += timedelta(minutes=1)
        target_ms = target_dt.timestamp() * 1000

        prior = [t for t in get_session_cron_tasks()
                 if t.get("kind") == "loop" and t.get("prompt") == input_.prompt]
        if prior:
            remove_session_cron_tasks([p["id"] for p in prior])
            for p in prior:
                self._next_fire_at.pop(p["id"], None)

        id_ = _new_id()
        cron = f"{target_dt.minute} {target_dt.hour} * * *"
        add_session_cron_task({
            "id": id_,
            "cron": cron,
            "prompt": input_.prompt,
            "createdAt": now_ms,
            "kind": "loop",
            "recurring": False,
        })

        self._next_fire_at[id_] = target_ms

        set_loop_state(LoopState(
            prompt=input_.prompt,
            started_at=existing.started_at if existing else now_ms,
            last_scheduled_for=target_ms,
            keepalive_strikes=existing.keepalive_strikes if existing else 0,
        ))

        if not input_.via_keepalive and opts.on_arm_loop:
            opts.on_arm_loop(input_.prompt)

        return ArmLoopResult(
            scheduled_for=target_ms,
            clamped_delay_seconds=clamped,
            was_clamped=was_clamped,
            superseded_count=len(prior),
        )

    async def reset_keepalive_strikes(self, prompt: str) -> None:
        reset_strikes(prompt)

    async def increment_keepalive_strikes(self, prompt: str) -> None:
        increment_strikes(prompt)

    async def end_loop(self, prompt: str, reason: str, opts: dict | None = None) -> None:
        prior = [t for t in get_session_cron_tasks()
                 if t.get("kind") == "loop" and t.get("prompt") == prompt]
        if prior:
            remove_session_cron_tasks([p["id"] for p in prior])
            for p in prior:
                if self._opts:
                    self._next_fire_at.pop(p["id"], None)
        delete_loop_state(prompt)
        if self._opts:
            evt = LoopEndedEvent(reason=reason, prompt=prompt)
            if opts and "via_keepalive" in opts:
                evt.via_keepalive = opts["via_keepalive"]
            self._opts.on_loop_ended(evt)

    async def next_fire_time(self) -> float | None:
        if not self._next_fire_at:
            return None
        return min(self._next_fire_at.values())

    async def tick_once(self) -> None:
        await self._tick_once()


# ═══════════════════════════════════════════════════════════
# 原 CronScheduler（保留，用于兼容）
# ═══════════════════════════════════════════════════════════


class CronScheduler:
    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def add(self, name: str, interval_seconds: float = 0, cron_expr: str = "",
            handler: Callable | None = None, max_runs: int = 0, one_shot: bool = False) -> str:
        job_id = f"cron_{uuid.uuid4().hex[:8]}"
        now = time.time()
        next_run = now + (interval_seconds if interval_seconds > 0 else 60)
        if cron_expr:
            n = CronParser.next_time(cron_expr)
            if n:
                next_run = n

        job = CronJob(
            id=job_id, name=name, interval_seconds=interval_seconds,
            cron_expr=cron_expr, next_run=next_run, handler=handler,
            max_runs=max_runs, one_shot=one_shot,
        )
        self._jobs[job_id] = job
        logger.info(f"[Cron] 添加任务: {name} ({job_id})")
        return job_id

    def remove(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        return [{
            "id": j.id, "name": j.name, "enabled": j.enabled,
            "interval": j.interval_seconds, "cron": j.cron_expr,
            "last_run": j.last_run, "next_run": j.next_run,
            "run_count": j.run_count, "max_runs": j.max_runs,
        } for j in self._jobs.values()]

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[Cron] 调度器已启动")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[Cron] 调度器已停止")

    async def _loop(self):
        while self._running:
            now = time.time()
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if job.next_run <= now:
                    if job.max_runs > 0 and job.run_count >= job.max_runs:
                        job.enabled = False
                        continue
                    try:
                        if job.handler:
                            r = job.handler()
                            if hasattr(r, "__await__"):
                                await r
                        job.run_count += 1
                        job.last_run = now
                        logger.info(f"[Cron] 执行: {job.name}")
                    except Exception as e:
                        logger.error(f"[Cron] 失败: {job.name}: {e}")
                    finally:
                        if job.one_shot and job.run_count >= 1:
                            job.enabled = False
                        else:
                            interval = job.interval_seconds
                            if job.cron_expr:
                                n = CronParser.next_time(job.cron_expr)
                                interval = (n - now) if n else interval
                            job.next_run = now + (interval if interval > 0 else 60)
            await asyncio.sleep(5)


# ═══════════════════════════════════════════════════════════
# 模块全局实例（保留原实例以保持兼容）
# ═══════════════════════════════════════════════════════════

scheduler = CronScheduler()
enhanced_scheduler = EnhancedScheduler()
