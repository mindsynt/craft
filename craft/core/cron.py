"""
定时任务系统 — 移植自 packages/opencode/src/cron/
基于 asyncio 的轻量调度器，支持 cron 表达式、一次性、重复任务
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


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


scheduler = CronScheduler()
