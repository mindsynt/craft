"""
指标收集 — 移植自 packages/opencode/src/metrics/
用量统计、事件追踪、性能监控
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


class MetricEvent:
    def __init__(self, name: str, value: float = 1.0, tags: dict | None = None):
        self.name = name
        self.value = value
        self.tags = tags or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "tags": self.tags, "ts": self.timestamp}


class MetricsCollector:
    def __init__(self):
        self._events: list[MetricEvent] = []
        self._db_path = CONFIG_DIR / "metrics.jsonl"

    def track(self, name: str, value: float = 1.0, **tags):
        event = MetricEvent(name, value, tags)
        self._events.append(event)
        try:
            with open(self._db_path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception:
            pass

    def count(self, name: str, **tags):
        self.track(name, 1.0, **tags)

    def timing(self, name: str, seconds: float, **tags):
        self.track(f"timing.{name}", seconds, **tags)

    def flush(self):
        self._events.clear()

    def summary(self) -> dict:
        counts = {}
        for e in self._events:
            counts[e.name] = counts.get(e.name, 0) + e.value
        return counts


metrics = MetricsCollector()
