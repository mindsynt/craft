"""
文件快照系统 — 移植自 packages/opencode/src/snapshot/
跟踪文件变更、撤销/恢复操作
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from craft.config import CONFIG_DIR

SNAPSHOT_DB = CONFIG_DIR / "snapshots.json"


class Snapshot:
    def __init__(self, filepath: str, content: str = "", operation: str = ""):
        self.id = f"snap_{uuid.uuid4().hex[:12]}"
        self.filepath = filepath
        self.content = content
        self.hash = hashlib.md5(content.encode()).hexdigest()
        self.operation = operation
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class SnapshotManager:
    def __init__(self):
        self._snapshots: list[Snapshot] = []
        self._max_per_file = 20
        self._load()

    def _load(self):
        try:
            if SNAPSHOT_DB.exists():
                data = json.loads(SNAPSHOT_DB.read_text())
                for item in data:
                    snap = Snapshot("")
                    snap.__dict__.update(item)
                    self._snapshots.append(snap)
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_DB.write_text(json.dumps(
            [s.to_dict() for s in self._snapshots[-500:]], indent=2, default=str
        ))

    def capture(self, filepath: str, operation: str = "edit") -> Snapshot | None:
        """捕获文件快照"""
        if not os.path.isfile(filepath):
            return None
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except Exception:
            return None
        snap = Snapshot(filepath, content, operation)
        self._snapshots.append(snap)

        # 限制每个文件最大快照数
        file_snaps = [s for s in self._snapshots if s.filepath == filepath]
        while len(file_snaps) > self._max_per_file:
            oldest = file_snaps.pop(0)
            self._snapshots.remove(oldest)

        self._save()
        return snap

    def restore(self, snap_id: str) -> bool:
        """恢复到指定快照"""
        for s in self._snapshots:
            if s.id == snap_id:
                try:
                    Path(s.filepath).write_text(s.content, encoding="utf-8")
                    return True
                except Exception:
                    return False
        return False

    def list(self, filepath: str | None = None, limit: int = 50) -> list[dict]:
        snaps = self._snapshots
        if filepath:
            snaps = [s for s in snaps if s.filepath == filepath]
        return [s.to_dict() for s in snaps[-limit:]]

    def diff(self, snap_id: str) -> str | None:
        """显示与当前文件的差异"""
        for s in self._snapshots:
            if s.id == snap_id and os.path.isfile(s.filepath):
                try:
                    current = Path(s.filepath).read_text(encoding="utf-8")
                    if current == s.content:
                        return "(无差异)"
                    import difflib
                    diff = difflib.unified_diff(
                        s.content.splitlines(keepends=True),
                        current.splitlines(keepends=True),
                        fromfile=f"snapshot/{snap_id[:8]}",
                        tofile="current",
                    )
                    return "".join(diff)
                except Exception:
                    return "(无法读取)"
        return None

    def clear(self, filepath: str | None = None):
        if filepath:
            self._snapshots = [s for s in self._snapshots if s.filepath != filepath]
        else:
            self._snapshots.clear()
        self._save()


snapshots = SnapshotManager()
