"""Cron 任务管理 — 移植自 cron-task.ts"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR
from craft.core.cron.expr import compute_next_cron_run

logger = logging.getLogger(__name__)

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
        anchor_dt = _datetime_from_ms(anchor_ms)
        nxt = compute_next_cron_run(t["cron"], anchor_dt)
        if nxt is None:
            continue
        if nxt.timestamp() * 1000 <= now_ms:
            missed.append(t)
    return missed


def _datetime_from_ms(ms: float):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def mark_cron_tasks_fired(ids: list[str], fired_at_ms: float, dir_path: str | None = None) -> None:
    """Update lastFiredAt for tasks by ID."""
    tasks = read_cron_tasks(dir_path)
    id_set = set(ids)
    updated = [
        {**t, "lastFiredAt": fired_at_ms} if t["id"] in id_set else t
        for t in tasks
    ]
    write_cron_tasks(updated, dir_path)
