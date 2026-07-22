"""
任务管理 — 移植自 packages/opencode/src/task/
任务创建、分配、跟踪、归档
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


class Task:
    def __init__(self, title: str, description: str = "", agent_id: str = "",
                 parent_id: str = ""):
        self.id = uuid.uuid4().hex[:16]
        self.title = title
        self.description = description
        self.status = "pending"
        self.agent_id = agent_id
        self.parent_id = parent_id
        self.subtask_ids: list[str] = []
        self.result: Any = None
        self.created_at = time.time()
        self.updated_at = time.time()
        self.completed_at: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @property
    def is_completed(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._db_path = CONFIG_DIR / "tasks.json"
        self._load()

    def _load(self):
        try:
            if self._db_path.exists():
                data = json.loads(self._db_path.read_text())
                for item in data:
                    t = Task("")
                    t.__dict__.update(item)
                    self._tasks[t.id] = t
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(
            [t.to_dict() for t in self._tasks.values()], indent=2, default=str
        ))

    def create(self, title: str, description: str = "", agent_id: str = "",
               parent_id: str = "") -> Task:
        task = Task(title, description, agent_id, parent_id)
        self._tasks[task.id] = task
        if parent_id and parent_id in self._tasks:
            self._tasks[parent_id].subtask_ids.append(task.id)
        self._save()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: str, result: Any = None):
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            task.updated_at = time.time()
            if result is not None:
                task.result = result
            if status in ("completed", "failed", "cancelled"):
                task.completed_at = time.time()
            self._save()

    def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in tasks[:limit]]

    def tree(self, parent_id: str | None = None, indent: int = 0) -> str:
        lines = []
        for task in self._tasks.values():
            if task.parent_id == (parent_id or ""):
                prefix = "  " * indent
                status_map = {"pending": "⏳", "running": "🔄", "completed": "✅",
                             "failed": "❌", "cancelled": "⏹️"}
                icon = status_map.get(task.status, "📋")
                lines.append(f"{prefix}{icon} {task.title} ({task.status})")
                lines.append(task.id)
                for child_id in task.subtask_ids:
                    child = self._tasks.get(child_id)
                    if child:
                        lines.extend(self._tree_recursive(child, indent + 1))
        return "\n".join(lines)


tasks = TaskManager()
