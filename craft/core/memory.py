"""持久化记忆系统 — SQLite FTS5"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from craft.config import CONFIG_DIR


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(CONFIG_DIR / "memory.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY, path TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL DEFAULT 'project', scope_id TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT 'note', content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}', created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mem_scope ON memory_entries(scope, scope_id);
            CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_entries(type);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts_idx USING fts5(
                content, path, scope, scope_id, type, content=memory_entries, content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_fts_idx(rowid, content, path, scope, scope_id, type)
                VALUES (new.rowid, new.content, new.path, new.scope, new.scope_id, new.type);
            END;
            CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memory_entries BEGIN
                INSERT INTO memory_fts_idx(memory_fts_idx, rowid, content, path, scope, scope_id, type)
                VALUES ('delete', old.rowid, old.content, old.path, old.scope, old.scope_id, old.type);
            END;
        """)
        self._conn.commit()

    def add(self, content: str, path: str = "", scope: str = "project", scope_id: str = "", type: str = "note") -> str:
        mem_id = uuid.uuid4().hex[:16]; now = time.time()
        self._conn.execute("INSERT INTO memory_entries VALUES (?,?,?,?,?,?,?,?,?)",
                          (mem_id, path, scope, scope_id, type, content, "{}", now, now))
        self._conn.commit(); return mem_id

    def search(self, query: str, limit: int = 10) -> list[dict]:
        import re
        tokens = re.findall(r"[a-zA-Z0-9_]+", query)
        if not tokens:
            cursor = self._conn.execute(
                "SELECT id, path, scope, scope_id, type, substr(content,1,200) AS snippet "
                "FROM memory_entries WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", min(limit * 3, 50)),
            )
            rows = cursor.fetchall()
            if not rows: return []
            return [{"id": r[0], "path": r[1], "scope": r[2], "scope_id": r[3],
                     "type": r[4], "snippet": r[5], "score": 1.0} for r in rows][:limit]
        fts = " OR ".join(f'"{t}"' for t in tokens)
        cursor = self._conn.execute("""
            SELECT m.id, m.path, m.scope, m.scope_id, m.type,
                   snippet(memory_fts_idx, 0, '<<', '>>', '...', 32) AS snippet,
                   bm25(memory_fts_idx, 0.0, 0.0, 0.0, 0.0, 1.0) AS score
            FROM memory_fts_idx 
            JOIN memory_entries m ON m.rowid = memory_fts_idx.rowid
            WHERE memory_fts_idx MATCH ? ORDER BY score LIMIT ?
        """, (fts, min(limit * 3, 50)))
        rows = cursor.fetchall()
        if not rows: return []
        mapped = [{"id": r[0], "path": r[1], "scope": r[2], "scope_id": r[3], "type": r[4],
                   "snippet": r[5], "score": -r[6]} for r in rows]
        top = mapped[0]["score"]
        return [m for i, m in enumerate(mapped) if i == 0 or m["score"] >= top * 0.15][:limit]

    def list(self, limit: int = 50) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT id, type, substr(content,1,200) FROM memory_entries ORDER BY created_at DESC LIMIT ?", (limit,))
        return [{"id": r[0], "type": r[1], "content": r[2]} for r in cursor]

    def delete(self, mem_id: str) -> bool:
        c = self._conn.execute("DELETE FROM memory_entries WHERE id=?", (mem_id,))
        self._conn.commit(); return c.rowcount > 0

    def close(self):
        self._conn.close()


memory = MemoryStore()
