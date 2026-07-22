"""HTTP metrics client — event reporting to telemetry endpoint.

移植自 MiMo-Code packages/opencode/src/metrics/client.ts, installation.ts, event.ts
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

METRICS_ENDPOINT = "https://tracking.miui.com/track/v4/o"
METRICS_APP_ID = "31000402765"
INSTALLATION_FILE = "installation.json"


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


async def send_metric(
    event_type: str,
    session_id: str,
    body: dict[str, Any],
) -> None:
    """Send a single metric event (fire-and-forget).

    Combines header building and posting in one call.
    """
    header = build_metrics_header(event_type, session_id)
    await post_events([{"H": header, "B": body}])


async def get_installation_id() -> str:
    """Get or create a persistent installation ID (port of installation.ts)."""
    import uuid
    path = Path.home() / ".craft" / INSTALLATION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if data.get("id"):
                return data["id"]
        except (json.JSONDecodeError, OSError):
            pass
    uid = str(uuid.uuid4())
    try:
        path.write_text(json.dumps({"id": uid}))
    except OSError:
        pass
    return uid
