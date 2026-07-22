"""
历史记录 — 移植自 packages/opencode/src/history/
会话历史 FTS 索引、搜索、归档
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


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


history = HistoryStore()
