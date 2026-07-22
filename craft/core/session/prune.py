"""Session pruning — ported from prune.ts.

Context window management: checkpoint threshold calculation, soft-trimming,
and non-essential content stripping.
"""

from __future__ import annotations

import math
import time
from typing import Any

PRUNE_MINIMUM = 20_000
PRUNE_PROTECT = 40_000
PRUNE_PROTECTED_TOOLS = ["skill"]
SOFT_TRIM_THRESHOLD = 4096
SOFT_TRIM_KEEP_HEAD = 1536
SOFT_TRIM_KEEP_TAIL = 1536
DEFAULT_CACHE_TTL = 300_000
CHECKPOINT_RESERVED = 13_000
MAX_WRITER_FAILURES = 3


def _token_estimate(text: str) -> int:
    """Rough token estimation (~4 chars/token)."""
    return len(text) // 4


def default_thresholds_for(window: int) -> list[str]:
    """Default checkpoint thresholds by context window size."""
    if window < 25_000:
        return []
    if window <= 200_000:
        return ["20%", "40%", "60%", "80%"]
    if window <= 500_000:
        return ["10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%"]
    return [f"{(i + 1) * 5}%" for i in range(18)]


def parse_threshold(s: str, window_size: int) -> int:
    """Parse a checkpoint threshold string into a token count."""
    trimmed = s.strip()
    if trimmed.endswith("%"):
        pct = float(trimmed[:-1])
        if not math.isfinite(pct) or pct <= 0 or pct > 100:
            raise ValueError(f'Invalid checkpoint threshold percentage: "{s}"')
        return int((window_size * pct) / 100)

    import re
    match = re.match(r"^(\d+(?:\.\d+)?)([KkMm]?)$", trimmed)
    if not match:
        raise ValueError(f'Invalid checkpoint threshold format: "{s}"')
    n = float(match.group(1))
    suffix = match.group(2)
    if suffix in ("K", "k"):
        n *= 1_000
    elif suffix in ("M", "m"):
        n *= 1_000_000
    return int(n)


def resolve_thresholds(
    raw: list[str],
    window_size: int,
    reserved: int | None = None,
) -> list[int]:
    """Parse, validate, sort, and deduplicate checkpoint thresholds."""
    effective_reserved = reserved if reserved is not None else CHECKPOINT_RESERVED
    max_allowed = window_size - effective_reserved
    if max_allowed <= 0:
        raise ValueError(
            f"Model window size ({window_size}) is too small for checkpoints "
            f"(need > {effective_reserved} reserved tokens)"
        )

    parsed = [{"raw": s, "value": parse_threshold(s, window_size)} for s in raw]
    result: list[int] = []
    capped_already = False
    for p in parsed:
        if p["value"] <= max_allowed:
            result.append(p["value"])
            continue
        if not capped_already:
            result.append(max_allowed)
            capped_already = True
        # drop subsequent over-cap values

    values = sorted(result)
    deduped: list[int] = []
    for v in values:
        if not deduped or deduped[-1] != v:
            deduped.append(v)
    return deduped


class PruneState:
    """Per-session pruning state."""

    def __init__(self):
        self.crossed: dict[str, set[int]] = {}  # session_id -> set of crossed thresholds
        self.max_crossed: set[str] = set()
        self.writer_failures: dict[str, int] = {}


prune_state = PruneState()
