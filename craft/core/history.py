"""
历史记录 — 移植自 packages/opencode/src/history/
会话历史 FTS 索引、搜索、归档
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from craft.config import CONFIG_DIR

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
# Extract — 移植自 extract.ts
# ═══════════════════════════════════════════════════════════

KINDS = frozenset({
    "user_text",
    "assistant_text",
    "tool_input",
    "tool_error",
    "reasoning",
    "tool_output",
})

DEFAULT_KINDS = frozenset({
    "user_text",
    "assistant_text",
    "tool_input",
    "tool_error",
})


@dataclass
class Extracted:
    kind: str
    body: str
    tool_name: str | None = None


def extract(
    part_type: str,
    part_state: dict | None,
    part_text: str | None,
    part_tool: str | None,
    message_role: str,
    enabled_kinds: set[str],
) -> Extracted | None:
    """Extract searchable text from a message part.

    Args:
        part_type: 'text', 'reasoning', or 'tool'
        part_state: dict with 'status', 'input', 'output', 'error' keys
        part_text: text content (for text/reasoning parts)
        part_tool: tool name (for tool parts)
        message_role: 'user' or 'assistant'
        enabled_kinds: set of enabled kind strings

    Returns:
        Extracted object or None if the part should not be indexed.
    """
    if part_type == "text":
        kind = "user_text" if message_role == "user" else "assistant_text"
        if kind not in enabled_kinds or not part_text:
            return None
        return Extracted(kind=kind, body=part_text, tool_name=None)

    if part_type == "reasoning":
        if "reasoning" not in enabled_kinds or not part_text:
            return None
        return Extracted(kind="reasoning", body=part_text, tool_name=None)

    if part_type == "tool":
        state = part_state or {}
        status = state.get("status", "")
        if status in ("pending", "running"):
            return None

        if status == "error" and "tool_error" in enabled_kinds:
            return Extracted(
                kind="tool_error",
                body=f"{part_tool} {json.dumps(state.get('input', {}))} {state.get('error', '')}",
                tool_name=part_tool,
            )
        if status == "completed" and "tool_output" in enabled_kinds:
            return Extracted(
                kind="tool_output",
                body=f"{part_tool} {json.dumps(state.get('input', {}))} {json.dumps(state.get('output', ''))}",
                tool_name=part_tool,
            )
        if "tool_input" in enabled_kinds:
            return Extracted(
                kind="tool_input",
                body=f"{part_tool} {json.dumps(state.get('input', {}))}",
                tool_name=part_tool,
            )
        return None

    return None


# ═══════════════════════════════════════════════════════════
# FTS Query Builder — 移植自 fts-query.ts
# ═══════════════════════════════════════════════════════════


def build_fts_query(raw: str) -> str | None:
    """Build an FTS5 MATCH expression from a free-form user query.

    Tokenizes on non-word boundaries, wraps each token in phrase quotes, AND-joins.
    Returns None when no usable tokens.
    """
    tokens = re.findall(r"\w+", raw)
    tokens = [t.strip() for t in tokens if t.strip()]
    if not tokens:
        return None
    quoted = ['"' + t.replace('"', '') + '"' for t in tokens]
    return " AND ".join(quoted)


# ═══════════════════════════════════════════════════════════
# FTS SQL — 移植自 fts.sql.ts
# ═══════════════════════════════════════════════════════════

FTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS history_fts (
    part_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    tool_name TEXT,
    body TEXT NOT NULL,
    time_created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS history_fts_session_idx ON history_fts(session_id, time_created);
CREATE INDEX IF NOT EXISTS history_fts_project_idx ON history_fts(project_id, time_created);
CREATE INDEX IF NOT EXISTS history_fts_message_idx ON history_fts(message_id);
-- Virtual FTS5 table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS history_fts_idx USING fts5(
    body,
    content='history_fts',
    content_rowid='rowid',
    tokenize='unicode61'
);
-- Triggers to keep the FTS index in sync
CREATE TRIGGER IF NOT EXISTS history_fts_ai AFTER INSERT ON history_fts BEGIN
    INSERT INTO history_fts_idx(rowid, body) VALUES (new.rowid, new.body);
END;
CREATE TRIGGER IF NOT EXISTS history_fts_ad AFTER DELETE ON history_fts BEGIN
    INSERT INTO history_fts_idx(history_fts_idx, rowid, body) VALUES('delete', old.rowid, old.body);
END;
CREATE TRIGGER IF NOT EXISTS history_fts_au AFTER UPDATE ON history_fts BEGIN
    INSERT INTO history_fts_idx(history_fts_idx, rowid, body) VALUES('delete', old.rowid, old.body);
    INSERT INTO history_fts_idx(rowid, body) VALUES (new.rowid, new.body);
END;
"""


def _ensure_fts_tables() -> None:
    from craft.core.storage import db
    for statement in FTS_SCHEMA_SQL.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            try:
                db.execute(stmt)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# LRU Cache — 移植自 resolve.ts
# ═══════════════════════════════════════════════════════════


class LRU:
    """Simple LRU cache."""

    def __init__(self, maxsize: int = 1024):
        self._maxsize = maxsize
        self._cache: dict = {}
        self._order: list = []

    def get(self, key: Any) -> Any | None:
        if key not in self._cache:
            return None
        self._order.remove(key)
        self._order.append(key)
        return self._cache[key]

    def set(self, key: Any, value: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._order) >= self._maxsize:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)
        self._order.append(key)
        self._cache[key] = value


# ═══════════════════════════════════════════════════════════
# Resolver — 移植自 resolve.ts
# ═══════════════════════════════════════════════════════════


class Resolver:
    """Cached resolvers for message role and session project_id."""

    def __init__(self):
        self._role_cache = LRU(1024)
        self._project_cache = LRU(512)

    def resolve_role(self, message_id: str) -> str:
        """Resolve message role ('user' or 'assistant')."""
        cached = self._role_cache.get(message_id)
        if cached:
            return cached
        from craft.core.storage import db
        row = db.fetch_one("SELECT data FROM message WHERE id = ?", [message_id])
        role = "assistant"
        if row:
            data = row.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    data = {}
            if isinstance(data, dict) and data.get("role") == "user":
                role = "user"
        self._role_cache.set(message_id, role)
        return role

    def resolve_project_id(self, session_id: str) -> str:
        """Resolve project_id for a session."""
        cached = self._project_cache.get(session_id)
        if cached:
            return cached
        from craft.core.storage import db
        row = db.fetch_one("SELECT project_id FROM session WHERE id = ?", [session_id])
        project_id = row["project_id"] if row else ""
        self._project_cache.set(session_id, project_id)
        return project_id


# ═══════════════════════════════════════════════════════════
# History Writer Service — 移植自 writer.ts
# ═══════════════════════════════════════════════════════════

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
        except Exception as e:
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
        except Exception as e:
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


# ═══════════════════════════════════════════════════════════
# 模块全局实例
# ═══════════════════════════════════════════════════════════

history = HistoryStore()
writer = HistoryWriter()
backfill = HistoryBackfill()
service = HistoryService()
