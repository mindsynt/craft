"""
同步系统 — 移植自 packages/opencode/src/sync/
配置同步、状态持久化、跨设备同步
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


class SyncRecord:
    def __init__(self, key: str, value: Any, scope: str = "local"):
        self.id = uuid.uuid4().hex[:16]
        self.key = key
        self.value = value
        self.scope = scope
        self.version = int(time.time() * 1000)
        self.updated_at = time.time()


class SyncManager:
    def __init__(self):
        self._records: dict[str, SyncRecord] = {}
        self._db_path = CONFIG_DIR / "sync.json"
        self._load()

    def _load(self):
        try:
            if self._db_path.exists():
                data = json.loads(self._db_path.read_text())
                for item in data:
                    r = SyncRecord("", None)
                    r.__dict__.update(item)
                    self._records[r.key] = r
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(
            [r.__dict__ for r in self._records.values()], indent=2, default=str
        ))

    def set(self, key: str, value: Any, scope: str = "local"):
        self._records[key] = SyncRecord(key, value, scope)
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        r = self._records.get(key)
        return r.value if r else default

    def delete(self, key: str):
        self._records.pop(key, None)
        self._save()

    def list(self, scope: str | None = None) -> list[dict]:
        records = self._records.values()
        if scope:
            records = [r for r in records if r.scope == scope]
        return [{"key": r.key, "value": r.value, "scope": r.scope, "updated_at": r.updated_at}
                for r in records]


sync_manager = SyncManager()
