"""Cron 表达式解析 — 移植自 cron-expr.ts"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
