"""Metrics utility functions.

移植自 MiMo-Code packages/opencode/src/metrics/util.ts
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def hash_value(value: Any) -> str:
    """Hash an arbitrary value to a hex string for anonymization."""
    serialized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def format_duration_ms(start_ms: int, end_ms: int | None = None) -> float:
    """Format a duration in milliseconds."""
    if end_ms is None:
        end_ms = int(time.time() * 1000)
    return float(end_ms - start_ms)


def truncate_string(s: str, max_len: int = 1000) -> str:
    """Truncate a string to max_len characters for metric payloads."""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def safe_serialize(obj: Any) -> dict[str, Any]:
    """Safely serialize an object for metric payloads, handling non-serializable values."""
    try:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return {"value": str(obj)}
    except Exception:
        return {"error": "serialization_failed"}


def build_metric_tags(
    tags: dict[str, str | None],
) -> dict[str, str]:
    """Build metric tags, filtering out None values."""
    return {k: v for k, v in tags.items() if v is not None}
