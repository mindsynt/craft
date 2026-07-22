"""
数据库层 — 移植自 packages/opencode/src/storage/
SQLite 数据库管理、迁移、查询
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


class Database:
    def __init__(self, db_path: str | None = None):
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
