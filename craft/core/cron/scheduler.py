"""Cron 调度器 — 移植自 scheduler.ts"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from craft.core.cron.expr import compute_next_cron_run
from craft.core.cron.jitter import (
    DEFAULT_JITTER,
    JitterConfig,
    jittered_next_cron_run_ms,
    one_shot_jittered_next_cron_run_ms,
)
from craft.core.cron.lock import (
    release_scheduler_lock,
    try_acquire_scheduler_lock,
)
from craft.core.cron.loop import (
    delete_loop_state,
    get_loop_state,
    get_strikes,
    increment_strikes,
    reset_strikes,
    set_loop_state,
    LoopState,
)
from craft.core.cron.sentinel import resolve_at_fire_time
from craft.core.cron.task import (
    add_session_cron_task,
    find_missed_tasks,
    get_session_cron_tasks,
    mark_cron_tasks_fired,
    read_cron_tasks,
    remove_session_cron_tasks,
    write_cron_tasks,
)

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
