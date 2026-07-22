"""Cron 分布式锁 — 移植自 cron-lock.ts"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

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
