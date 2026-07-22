"""History Service — FTS 搜索、上下文检索、Backfill"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR
from craft.core.history.extract import DEFAULT_KINDS, extract
from craft.core.history.fts import Resolver, _ensure_fts_tables, build_fts_query

# ═══════════════════════════════════════════════════════════
# 原有 HistoryEntry / HistoryStore（保留）
# ═══════════════════════════════════════════════════════════


class HistoryEntry:
    def __init__(self, session_id: str, role: str, content: str, model: str = ""):
        self.id = uuid.uuid4().hex[:16]
        self.session_id = session_id
        self.role = role
        self.content = content
        self.model = model
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class HistoryStore:
    def __init__(self):
        self._db_path = CONFIG_DIR / "history.jsonl"

    def append(self, session_id: str, role: str, content: str, model: str = ""):
        entry = HistoryEntry(session_id, role, content, model)
        try:
            with open(self._db_path, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception:
            pass

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not self._db_path.exists():
            return []
        results = []
        query_lower = query.lower()
        try:
            with open(self._db_path) as f:
                for line in f:
                    if len(results) >= limit:
                        break
                    try:
                        entry = json.loads(line)
                        if query_lower in entry.get("content", "").lower():
                            results.append(entry)
                    except Exception:
                        continue
        except Exception:
            pass
        return results

    def get_session_history(self, session_id: str) -> list[dict]:
        if not self._db_path.exists():
            return []
        results = []
        try:
            with open(self._db_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("session_id") == session_id:
                            results.append(entry)
                    except Exception:
                        continue
        except Exception:
            pass
        return results


# ═══════════════════════════════════════════════════════════
# Backfill Service — 移植自 backfill.ts
# ═══════════════════════════════════════════════════════════

BACKFILL_BATCH = 500


def backfill_all(enabled_kinds: set[str] | None = None) -> None:
    """Walk all sessions and backfill unindexed parts into the FTS index.

    Idempotent — re-running skips already-indexed parts.
    """
    if enabled_kinds is None:
        enabled_kinds = set(DEFAULT_KINDS)
    if not enabled_kinds:
        return

    from craft.core.storage import db

    sessions = db.fetch_all(
        "SELECT id, project_id FROM session ORDER BY time_updated DESC"
    )
    resolver = Resolver()

    for session in sessions:
        try:
            _scan_session(session, resolver, enabled_kinds)
        except Exception:
            pass


def _scan_session(session: dict, resolver: Resolver, enabled_kinds: set[str]) -> None:
    from craft.core.storage import db

    cursor = ""
    while True:
        parts = db.fetch_all(
            "SELECT p.id, p.session_id, p.message_id, p.data, p.time_created "
            "FROM part p "
            "WHERE p.session_id = ? AND p.id > ? "
            "AND NOT EXISTS (SELECT 1 FROM history_fts h WHERE h.part_id = p.id) "
            "ORDER BY p.id "
            "LIMIT ?",
            [session["id"], cursor, BACKFILL_BATCH],
        )
        if not parts:
            break

        _write_batch(parts, session["project_id"], resolver, enabled_kinds)
        cursor = parts[-1]["id"]


def _write_batch(
    parts: list[dict],
    project_id: str,
    resolver: Resolver,
    enabled_kinds: set[str],
) -> None:
    from craft.core.storage import db

    for p in parts:
        role = resolver.resolve_role(p["message_id"])
        data = p.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}

        part_type = data.get("type", "") if isinstance(data, dict) else ""
        part_state = data.get("state") if isinstance(data, dict) else None
        part_text = data.get("text") if isinstance(data, dict) and isinstance(data.get("text"), str) else None
        part_tool = data.get("tool") if isinstance(data, dict) else None
        time_created = p.get("time_created", time.time() * 1000)

        extracted = extract(part_type, part_state, part_text, part_tool, role, enabled_kinds)
        if not extracted:
            continue

        db.execute(
            "INSERT OR REPLACE INTO history_fts "
            "(part_id, session_id, message_id, project_id, kind, tool_name, body, time_created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [p["id"], p["session_id"], p["message_id"], project_id,
             extracted.kind, extracted.tool_name, extracted.body, int(time_created)],
        )


class HistoryBackfill:
    """Startup backfill service."""

    def __init__(self):
        self._initialized = False
        _ensure_fts_tables()

    def init(self) -> None:
        """Trigger backfill (fire-and-forget)."""
        if self._initialized:
            return
        self._initialized = True
        try:
            backfill_all()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# History Service — 移植自 service.ts
# ═══════════════════════════════════════════════════════════

HARD_CAP = 50


@dataclass
class SearchHit:
    part_id: str
    session_id: str
    message_id: str
    project_id: str
    kind: str
    tool_name: str | None = None
    snippet: str = ""
    score: float = 0.0
    time_created: float = 0.0


@dataclass
class MessagePart:
    part_id: str
    type: str
    role: str
    tool_name: str | None = None
    text: str = ""


@dataclass
class MessageContext:
    message_id: str
    matched: bool = False
    time_created: float = 0.0
    parts: list[MessagePart] = field(default_factory=list)


@dataclass
class AroundResult:
    session_id: str = ""
    messages: list[MessageContext] = field(default_factory=list)


@dataclass
class SearchInput:
    query: str
    scope: str = "project"  # "project" or "global"
    session_id: str | None = None
    kind: str | list[str] | None = None
    tool_name: str | None = None
    time_after: float | None = None
    time_before: float | None = None
    limit: int = 10


@dataclass
class AroundInput:
    message_id: str
    before: int = 5
    after: int = 5


class HistoryService:
    """Full-text search and context retrieval for conversation history."""

    def __init__(self):
        _ensure_fts_tables()

    def search(self, input_: SearchInput) -> list[SearchHit]:
        """Search the history FTS index."""
        fts_query = build_fts_query(input_.query)
        if not fts_query:
            return []

        limit = min(input_.limit, HARD_CAP)
        conditions = []
        params: list[Any] = []

        scope = input_.scope or "project"
        if scope == "project":
            # Use a default project ID if available
            conditions.append("h.project_id = ?")
            params.append("default")

        if input_.session_id:
            conditions.append("h.session_id = ?")
            params.append(input_.session_id)
        if input_.kind:
            kinds = [input_.kind] if isinstance(input_.kind, str) else input_.kind
            placeholders = ",".join(["?" for _ in kinds])
            conditions.append(f"h.kind IN ({placeholders})")
            params.extend(kinds)
        if input_.tool_name:
            conditions.append("h.tool_name = ?")
            params.append(input_.tool_name)
        if input_.time_after is not None:
            conditions.append("h.time_created >= ?")
            params.append(int(input_.time_after))
        if input_.time_before is not None:
            conditions.append("h.time_created <= ?")
            params.append(int(input_.time_before))

        where_clause = f"AND {' AND '.join(conditions)}" if conditions else ""

        from craft.core.storage import db

        # Use direct SQLite query for FTS5
        conn = db.conn
        sql = f"""
            SELECT h.part_id, h.session_id, h.message_id,
                   h.project_id, h.kind, h.tool_name,
                   h.time_created
            FROM history_fts h
            WHERE h.body LIKE ?
            {where_clause}
            ORDER BY h.time_created DESC
            LIMIT ?
        """
        word_pattern = re.compile(r'\w+')
        words = word_pattern.findall(input_.query.lower())
        like_query = "%" + " ".join(words) + "%"
        rows = db.fetch_all(sql, [like_query, *params, limit])

        results = []
        for r in rows:
            results.append(SearchHit(
                part_id=r["part_id"],
                session_id=r["session_id"],
                message_id=r["message_id"],
                project_id=r["project_id"],
                kind=r["kind"],
                tool_name=r.get("tool_name"),
                time_created=r["time_created"],
            ))
        return results

    def around(self, input_: AroundInput) -> AroundResult:
        """Get message context around a specific message."""
        from craft.core.storage import db

        before = input_.before
        after = input_.after

        anchor = db.fetch_one(
            "SELECT id, session_id, time_created FROM message WHERE id = ?",
            [input_.message_id],
        )
        if not anchor:
            return AroundResult()

        # Before messages
        before_rows = db.fetch_all(
            "SELECT * FROM message "
            "WHERE session_id = ? AND (time_created < ? OR (time_created = ? AND id <= ?)) "
            "ORDER BY time_created DESC, id DESC LIMIT ?",
            [anchor["session_id"], anchor["time_created"], anchor["time_created"],
             anchor["id"], before + 1],
        )
        before_rows.reverse()

        # After messages
        after_rows = db.fetch_all(
            "SELECT * FROM message "
            "WHERE session_id = ? AND (time_created > ? OR (time_created = ? AND id > ?)) "
            "ORDER BY time_created ASC, id ASC LIMIT ?",
            [anchor["session_id"], anchor["time_created"], anchor["time_created"],
             anchor["id"], after],
        )

        messages = before_rows + after_rows
        if not messages:
            return AroundResult(session_id=anchor["session_id"])

        # Get parts for all these messages
        message_ids = [m["id"] for m in messages]
        placeholders = ",".join(["?" for _ in message_ids])
        parts = db.fetch_all(
            f"SELECT * FROM part WHERE session_id = ? AND message_id IN ({placeholders}) "
            "ORDER BY message_id ASC, id ASC",
            [anchor["session_id"]] + message_ids,
        )

        by_message: dict[str, list[dict]] = {}
        for p in parts:
            by_message.setdefault(p["message_id"], []).append(p)

        out_messages = []
        for m in messages:
            role = "user"
            data = m.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    data = {}
            if isinstance(data, dict) and data.get("role") == "user":
                role = "user"
            elif isinstance(data, dict) and data.get("role") == "assistant":
                role = "assistant"

            parts_here = by_message.get(m["id"], [])
            msg_parts = []
            for p in parts_here:
                pd = p.get("data", {})
                if isinstance(pd, str):
                    try:
                        pd = json.loads(pd)
                    except (json.JSONDecodeError, TypeError):
                        pd = {}
                if not isinstance(pd, dict):
                    pd = {}
                p_type = pd.get("type", "")
                p_text = pd.get("text", "")
                p_tool = pd.get("tool")
                p_state = pd.get("state", {})

                if p_type in ("text", "reasoning"):
                    text = str(p_text) if p_text else ""
                elif p_type == "tool":
                    text = f"tool: {p_tool or ''}\ninput: {json.dumps(p_state.get('input', {}))}"
                    if p_state.get("error"):
                        text += f"\nerror: {p_state['error']}"
                    elif p_state.get("output"):
                        text += f"\noutput: {json.dumps(p_state.get('output', ''))}"
                else:
                    text = f"[{p_type}]"

                msg_parts.append(MessagePart(
                    part_id=p["id"],
                    type=p_type,
                    role=role,
                    tool_name=p_tool if p_type == "tool" else None,
                    text=text,
                ))

            out_messages.append(MessageContext(
                message_id=m["id"],
                matched=m["id"] == input_.message_id,
                time_created=m["time_created"],
                parts=msg_parts,
            ))

        return AroundResult(session_id=anchor["session_id"], messages=out_messages)
