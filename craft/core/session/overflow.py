"""Overflow detection — ported from overflow.ts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COMPACTION_BUFFER = 20_000
OUTPUT_CAP = 20_000


def max_output_tokens(model: dict[str, Any]) -> int:
    """Get max output tokens from a model dict."""
    limits = model.get("limit", {})
    output = limits.get("output", 0)
    return output or 4096


def usable(cfg: dict[str, Any], model: dict[str, Any]) -> int:
    """Calculate usable context window."""
    context = model.get("limit", {}).get("context", 0)
    if context == 0:
        return 0

    reserved = cfg.get("compaction", {}).get(
        "reserved",
        min(COMPACTION_BUFFER, max_output_tokens(model)),
    )
    output_reserve = min(max_output_tokens(model), OUTPUT_CAP)

    input_limit = model.get("limit", {}).get("input")
    if input_limit:
        return max(0, input_limit - reserved)
    return max(0, context - output_reserve - reserved)


def is_overflow(cfg: dict[str, Any], tokens: dict[str, Any], model: dict[str, Any]) -> bool:
    """Check if token usage overflows the usable window."""
    if cfg.get("compaction", {}).get("auto") is False:
        return False
    if model.get("limit", {}).get("context") == 0:
        return False

    count = (
        tokens.get("total")
        or tokens.get("input", 0)
        + tokens.get("output", 0)
        + tokens.get("cache", {}).get("read", 0)
        + tokens.get("cache", {}).get("write", 0)
    )
    return count >= usable(cfg, model)


def pressure_level(cfg: dict[str, Any], tokens: dict[str, Any], model: dict[str, Any]) -> int:
    """Calculate pressure level (0-3)."""
    if cfg.get("compaction", {}).get("auto") is False:
        return 0
    if model.get("limit", {}).get("context") == 0:
        return 0

    count = (
        tokens.get("total")
        or tokens.get("input", 0)
        + tokens.get("output", 0)
        + tokens.get("cache", {}).get("read", 0)
        + tokens.get("cache", {}).get("write", 0)
    )
    limit = usable(cfg, model)
    if limit == 0:
        return 0

    ratio = count / limit
    if ratio < 0.50:
        return 0
    if ratio < 0.70:
        return 1
    if ratio < 0.85:
        return 2
    return 3
