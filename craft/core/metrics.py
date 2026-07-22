"""
指标收集 — 移植自 packages/opencode/src/metrics/
用量统计、事件追踪、性能监控

支持：client（HTTP 事件上报）、subscriber（事件总线订阅）、
util（工具函数）
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── HTTP Client for telemetry ─────────────────────────────────
# 对应 TS metrics/client.ts

METRICS_ENDPOINT = "https://tracking.miui.com/track/v4/o"
METRICS_APP_ID = "31000402765"


def build_metrics_header(
    event_type: str,
    instance_id: str | None = None,
    uid: str | None = None,
) -> dict[str, Any]:
    """Build a metrics header matching the MiMo-Code telemetry format."""
    import uuid
    header: dict[str, Any] = {
        "event": event_type,
        "app_id": METRICS_APP_ID,
        "instance_id": instance_id or str(uuid.uuid4()),
        "instance_id_type": "uuid",
        "e_ts": int(time.time() * 1000),
    }
    if uid:
        header["uid"] = uid
        header["uid_type"] = "session_id"
    return header


async def post_events(payload: list[dict]) -> None:
    """Post a batch of metric events to the telemetry endpoint.

    Silently ignores failures (fire-and-forget).
    """
    if not payload:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(
                METRICS_ENDPOINT,
                json=payload,
                headers={"content-type": "application/json"},
            )
    except Exception:
        pass  # Fire-and-forget


# ── Metric Event Types ───────────────────────────────────────
# 对应 TS metrics/event.ts

ModelCallEvent = {
    "type": "model_call",
    "properties": {
        "session_id": str,
        "model_id": str,
        "provider": str,
        "finish_reason": str,
        "ttft_ms": float,
        "latency_ms": float,
        "total_tokens_in": int,
        "total_tokens_out": int,
        "cached_read_tokens": int,
    },
}

ToolCallEvent = {
    "type": "tool_call",
    "properties": {
        "session_id": str,
        "tool_name": str,
        "tool_call_id": str,
        "tool_call_status": str,
        "input_bytes": int,
        "output_bytes": int,
    },
}

AgentRequestEvent = {
    "type": "agent_request",
    "properties": {
        "session_id": str,
        "phase": str,
        "task_type": str,
        "surface": str,
        "total_tokens_in": int,
        "total_tokens_out": int,
        "files_changed": int,
        "validation_status": str,
    },
}


# ── Subscriber ────────────────────────────────────────────────
# 对应 TS metrics/subscriber.ts

async def subscribe_metrics(instance_id: str | None = None):
    """Subscribe to local events and send metric events to the telemetry endpoint.

    Listens to model_call, tool_call, and agent_request events.
    """
    try:
        from craft.core.bus import Bus
    except ImportError:
        logger.warning("Bus not available, metrics subscription disabled")
        return

    async def _on_model_call(event):
        props = event.get("properties", {})
        header = build_metrics_header("model_call",
                                       instance_id=instance_id,
                                       uid=props.get("sessionID"))
        await post_events([{
            "H": header,
            "B": {
                "finish_reason": props.get("finish_reason"),
                "ttft_ms": props.get("ttft_ms"),
                "latency_ms": props.get("latency_ms"),
                "cached_read_tokens": props.get("cached_read_tokens"),
                "model_id": props.get("model_id"),
                "provider": props.get("provider"),
                "total_tokens_in": props.get("total_tokens_in"),
                "total_tokens_out": props.get("total_tokens_out"),
            },
        }])

    async def _on_tool_call(event):
        props = event.get("properties", {})
        header = build_metrics_header("tool_call",
                                       instance_id=instance_id,
                                       uid=props.get("sessionID"))
        await post_events([{
            "H": header,
            "B": {
                "tool_name": props.get("tool_name"),
                "input_bytes": props.get("input_bytes"),
                "output_bytes": props.get("output_bytes"),
                "tool_call_id": props.get("tool_call_id"),
                "tool_call_status": props.get("tool_call_status"),
            },
        }])

    async def _on_agent_request(event):
        props = event.get("properties", {})
        header = build_metrics_header("agent_request",
                                       instance_id=instance_id,
                                       uid=props.get("sessionID"))
        await post_events([{
            "H": header,
            "B": {
                "phase": props.get("phase"),
                "task_type": props.get("task_type"),
                "surface": props.get("surface"),
                "total_tokens_in": props.get("total_tokens_in"),
                "total_tokens_out": props.get("total_tokens_out"),
                "files_changed": props.get("files_changed"),
                "validation_status": props.get("validation_status"),
            },
        }])

    Bus.subscribe("model_call", _on_model_call)
    Bus.subscribe("tool_call", _on_tool_call)
    Bus.subscribe("agent_request", _on_agent_request)
    logger.info("metrics subscriber initialized")


# ── Utility Functions ────────────────────────────────────────
# 对应 TS metrics/util.ts

def json_byte_length(value: Any) -> int:
    """Calculate the byte length of a JSON-serialized value in UTF-8."""
    try:
        serialized = json.dumps(value, ensure_ascii=False)
        return len(serialized.encode("utf-8"))
    except (TypeError, ValueError):
        return 0


# ── Original MetricsCollector (preserved) ─────────────────────

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
        from craft.config import CONFIG_DIR
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
