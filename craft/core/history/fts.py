"""FTS 查询与索引基础设施 — 移植自 fts-query.ts / fts.sql.ts / resolve.ts"""

from __future__ import annotations

import json
import re
from typing import Any

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
