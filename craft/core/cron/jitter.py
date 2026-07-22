"""Cron 抖动算法 — 移植自 cron-jitter.ts"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from craft.core.cron.expr import compute_next_cron_run


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
EVERY_N_MIN_RE = re.compile(r"^\*/\d+ \* \* \* \*$")


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
