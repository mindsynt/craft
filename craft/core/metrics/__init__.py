"""Metrics package — ported from packages/opencode/src/metrics/

用量统计、事件追踪、性能监控。

Split into:
- client: HTTP event reporting
- subscriber: Event bus subscription
- util: Utility functions
- event: Event type definitions

Maintains backward compatibility:
  from craft.core.metrics import post_events  (still works)
"""
from __future__ import annotations

from .client import (
    METRICS_ENDPOINT,
    METRICS_APP_ID,
    build_metrics_header,
    post_events,
    send_metric,
    get_installation_id,
)
from .subscriber import MetricsSubscriber, get_subscriber, record_event
from .util import safe_serialize, truncate_string, hash_value, format_duration_ms, build_metric_tags

# Backward compatibility: old `metrics` singleton with summary()
class _MetricsCompat:
    """Backward-compatible metrics object (old metrics.py API)."""
    def summary(self) -> dict[str, float]:
        return {}

metrics = _MetricsCompat()

__all__ = [
    "METRICS_ENDPOINT",
    "METRICS_APP_ID",
    "build_metrics_header",
    "post_events",
    "send_metric",
    "get_installation_id",
    "MetricsSubscriber",
    "get_subscriber",
    "record_event",
    "safe_serialize",
    "truncate_string",
    "hash_value",
    "format_duration_ms",
    "build_metric_tags",
]
