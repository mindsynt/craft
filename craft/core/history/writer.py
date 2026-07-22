"""History Writer Service — 移植自 writer.ts"""

from __future__ import annotations

import time
from typing import Any

from craft.core.history.extract import DEFAULT_KINDS, extract
from craft.core.history.fts import Resolver, _ensure_fts_tables

_default_resolver = Resolver()


def _handle_write_job(
    session_id: str,
    message_id: str,
    part_id: str,
    part_type: str,
    part_state: dict | None,
    part_text: str | None,
    part_tool: str | None,
    time_created: float,
    enabled_kinds: set[str] | None = None,
) -> None:
    """Handle a single write job (upsert a part into the FTS index)."""
    if enabled_kinds is None:
        enabled_kinds = set(DEFAULT_KINDS)

    role = _default_resolver.resolve_role(message_id)
    extracted = extract(part_type, part_state, part_text, part_tool, role, enabled_kinds)
    if not extracted:
        return

    project_id = _default_resolver.resolve_project_id(session_id)
    from craft.core.storage import db

    db.execute(
        "INSERT OR REPLACE INTO history_fts "
        "(part_id, session_id, message_id, project_id, kind, tool_name, body, time_created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [part_id, session_id, message_id, project_id, extracted.kind,
         extracted.tool_name, extracted.body, int(time_created)],
    )


def _handle_delete_job(part_id: str) -> None:
    """Handle a delete job."""
    from craft.core.storage import db
    db.execute("DELETE FROM history_fts WHERE part_id = ?", [part_id])


class HistoryWriter:
    """Bus subscriber that writes message parts into the FTS index."""

    def __init__(self):
        self._initialized = False
        _ensure_fts_tables()

    def init(self) -> None:
        """Initialize the writer (start listening to bus events)."""
        if self._initialized:
            return
        self._initialized = True
        from craft.core.bus import bus

        @bus.on("part.updated")
        def on_part_updated(event):
            data = event.data if hasattr(event, "data") else {}
            self._handle_part_updated(data)

        @bus.on("part.removed")
        def on_part_removed(event):
            data = event.data if hasattr(event, "data") else {}
            if "partID" in data:
                _handle_delete_job(data["partID"])

    def _handle_part_updated(self, data: dict) -> None:
        """Handle a part.updated event."""
        part = data.get("part", {})
        time_created = data.get("time", time.time() * 1000)
        _handle_write_job(
            session_id=part.get("sessionID", ""),
            message_id=part.get("messageID", ""),
            part_id=part.get("id", ""),
            part_type=part.get("type", ""),
            part_state=part.get("state"),
            part_text=part.get("text") if isinstance(part.get("text"), str) else None,
            part_tool=part.get("tool"),
            time_created=time_created,
        )
