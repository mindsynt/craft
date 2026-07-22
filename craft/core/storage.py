"""
数据库层 — 移植自 packages/opencode/src/storage/
SQLite 数据库管理、迁移、查询

支持：DB 连接、JSON→SQLite 迁移、只读查询
"""

from __future__ import annotations

import json as _json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Read-Only SQLite Helpers ─────────────────────────────────
# 对应 TS storage/read-sqlite.ts

@dataclass
class ReadonlyDb:
    """A read-only SQLite database connection."""
    _conn: sqlite3.Connection | None = None
    _path: str = ""

    @staticmethod
    def open(path: str) -> ReadonlyDb:
        """Open a read-only SQLite database."""
        db = ReadonlyDb()
        db._path = path
        db._conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db._conn.row_factory = sqlite3.Row
        return db

    def all(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        if self._conn is None:
            raise RuntimeError("Database not open")
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get(self, sql: str, *params: Any) -> dict[str, Any] | None:
        """Execute a query and return the first row as a dict, or None."""
        if self._conn is None:
            raise RuntimeError("Database not open")
        cursor = self._conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self):
        """Close the read-only database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ── JSON Migration ───────────────────────────────────────────
# 对应 TS storage/json-migration.ts

@dataclass
class MigrationProgress:
    """Progress report during JSON migration."""
    current: int = 0
    total: int = 0
    label: str = ""


@dataclass
class MigrationStats:
    """Statistics from a completed JSON migration."""
    projects: int = 0
    sessions: int = 0
    messages: int = 0
    parts: int = 0
    todos: int = 0
    permissions: int = 0
    shares: int = 0
    errors: list[str] = field(default_factory=list)


async def run_json_migration(
    db: sqlite3.Connection,
    storage_dir: str | None = None,
    progress_callback: Any = None,
) -> MigrationStats:
    """Migrate JSON storage files into a SQLite database.

    Reads from ``storage_dir`` (default: ``~/.craft/storage/``) and writes
    into the provided SQLite connection.
    """
    if storage_dir is None:
        storage_dir = str(Path.home() / ".craft" / "storage")

    stats = MigrationStats()
    if not os.path.exists(storage_dir):
        logger.info("storage directory does not exist, skipping migration")
        return stats

    logger.info("starting json to sqlite migration from %s", storage_dir)

    # Optimize SQLite for bulk inserts
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = OFF")
    db.execute("PRAGMA cache_size = 10000")
    db.execute("PRAGMA temp_store = MEMORY")

    errs = stats.errors
    batch_size = 1000
    now = time.time()

    def _report(label: str, count: int, total: int):
        if progress_callback:
            progress_callback(MigrationProgress(current=count, total=total, label=label))

    async def _scan(pattern: str) -> list[str]:
        """Scan for files matching a glob pattern."""
        import glob
        return glob.glob(os.path.join(storage_dir, pattern), recursive=True)

    async def _read_files(files: list[str]) -> list[Any]:
        """Read multiple JSON files in parallel."""
        import asyncio
        async def _read_one(filepath: str) -> Any:
            try:
                with open(filepath) as f:
                    return _json.load(f)
            except Exception as e:
                errs.append(f"failed to read {filepath}: {e}")
                return None

        tasks = [_read_one(f) for f in files]
        return await asyncio.gather(*tasks)

    def _insert(table: str, values: list[dict]) -> int:
        if not values:
            return 0
        try:
            cols = ", ".join(values[0].keys())
            placeholders = ", ".join(["?"] * len(values[0]))
            sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
            for v in values:
                db.execute(sql, list(v.values()))
            return len(values)
        except Exception as e:
            errs.append(f"failed to migrate {table} batch: {e}")
            return 0

    # Pre-scan all files
    logger.info("scanning files...")
    project_files = await _scan("project/*.json")
    session_files = await _scan("session/*/*.json")
    message_files = await _scan("message/*/*.json")
    part_files = await _scan("part/*/*.json")
    todo_files = await _scan("todo/*.json")
    perm_files = await _scan("permission/*.json")
    share_files = await _scan("session_share/*.json")

    total = max(1, len(project_files) + len(session_files) + len(message_files)
                + len(part_files) + len(todo_files) + len(perm_files) + len(share_files))
    current = 0

    db.execute("BEGIN TRANSACTION")
    try:
        # Migrate projects
        project_ids: set[str] = set()
        project_values: list[dict] = []
        for i in range(0, len(project_files), batch_size):
            batch = project_files[i:i + batch_size]
            data_batch = await _read_files(batch)
            project_values.clear()
            for j, data in enumerate(data_batch):
                if not data:
                    continue
                pid = Path(batch[j]).stem
                project_ids.add(pid)
                project_values.append({
                    "id": pid,
                    "worktree": data.get("worktree", "/"),
                    "vcs": data.get("vcs"),
                    "name": data.get("name"),
                    "time_created": data.get("time", {}).get("created", now),
                    "time_updated": data.get("time", {}).get("updated", now),
                })
            stats.projects += _insert("project", project_values)
            current += len(batch)
            _report("projects", current, total)

        # Migrate sessions
        session_ids: set[str] = set()
        session_values: list[dict] = []
        for i in range(0, len(session_files), batch_size):
            batch = session_files[i:i + batch_size]
            data_batch = await _read_files(batch)
            session_values.clear()
            for j, data in enumerate(data_batch):
                if not data:
                    continue
                sid = Path(batch[j]).stem
                project_id = Path(batch[j]).parent.name
                if project_id not in project_ids:
                    continue
                session_ids.add(sid)
                session_values.append({
                    "id": sid,
                    "project_id": project_id,
                    "directory": data.get("directory", ""),
                    "title": data.get("title", ""),
                    "time_created": data.get("time", {}).get("created", now),
                    "time_updated": data.get("time", {}).get("updated", now),
                })
            stats.sessions += _insert("session", session_values)
            current += len(batch)
            _report("sessions", current, total)

        # Migrate messages
        message_values: list[dict] = []
        for i in range(0, len(message_files), batch_size):
            batch = message_files[i:i + batch_size]
            data_batch = await _read_files(batch)
            message_values.clear()
            for j, data in enumerate(data_batch):
                if not data:
                    continue
                mid = Path(batch[j]).stem
                session_id = Path(batch[j]).parent.name
                if session_id not in session_ids:
                    continue
                rest = {k: v for k, v in data.items() if k not in ("id", "sessionID")}
                message_values.append({
                    "id": mid,
                    "session_id": session_id,
                    "time_created": data.get("time", {}).get("created", now),
                    "time_updated": data.get("time", {}).get("updated", now),
                    "data": _json.dumps(rest),
                })
            stats.messages += _insert("message", message_values)
            current += len(batch)
            _report("messages", current, total)

        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    _report("complete", total, total)
    logger.info("json migration complete: %d projects, %d sessions, %d messages",
                stats.projects, stats.sessions, stats.messages)
    return stats


# ── Original Database class (preserved) ─────────────────────

class Database:
    def __init__(self, db_path: str | None = None):
        from craft.config import CONFIG_DIR
        self.db_path = db_path or str(CONFIG_DIR / "craft.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def execute(self, sql: str, params: list | None = None) -> sqlite3.Cursor:
        return self.conn.execute(sql, params or [])

    def fetch_all(self, sql: str, params: list | None = None) -> list[dict]:
        cursor = self.conn.execute(sql, params or [])
        return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: list | None = None) -> dict | None:
        cursor = self.conn.execute(sql, params or [])
        row = cursor.fetchone()
        return dict(row) if row else None

    def insert(self, table: str, data: dict) -> int:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        cursor = self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def update(self, table: str, data: dict, where: str, where_params: list | None = None):
        set_clause = ", ".join(f"{k} = ?" for k in data)
        self.conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where}",
            list(data.values()) + (where_params or []),
        )
        self.conn.commit()

    def delete(self, table: str, where: str, params: list | None = None):
        self.conn.execute(f"DELETE FROM {table} WHERE {where}", params or [])
        self.conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


db = Database()


class Migration:
    def __init__(self):
        self._create_migrations_table()

    def _create_migrations_table(self):
        db.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at REAL NOT NULL
            )
        """)

    def apply(self, name: str, sql: str):
        existing = db.fetch_one("SELECT id FROM _migrations WHERE name = ?", [name])
        if existing:
            return False
        db.execute(sql)
        db.insert("_migrations", {"name": name, "applied_at": time.time()})
        return True

    def pending(self) -> list[str]:
        return []


migration = Migration()
