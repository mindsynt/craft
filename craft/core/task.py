"""
任务管理 — 移植自 packages/opencode/src/task/
任务创建、分配、跟踪、归档、事件、门控
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from craft.config import CONFIG_DIR

# ═══════════════════════════════════════════════════════════
# 原有 Task / TaskManager（保留）
# ═══════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════
# Schema — 移植自 schema.ts
# ═══════════════════════════════════════════════════════════

TASK_ID_RE = re.compile(r"^T\d+(\.\d+)*$")


def is_valid_task_id(id_: str) -> bool:
    return bool(TASK_ID_RE.match(id_))


TASK_STATUSES = ("open", "in_progress", "blocked", "done", "abandoned")
TASK_EVENT_KINDS = (
    "created",
    "started",
    "unstarted",
    "blocked",
    "unblocked",
    "done",
    "abandoned",
    "renamed",
)

TERMINAL_STATUSES = ("done", "abandoned")
NON_TERMINAL_STATUSES = ("open", "in_progress", "blocked")


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_actionable_status(status: str) -> bool:
    return status in ("open", "in_progress")


@dataclass
class TaskData:
    """对应 TS Task 结构"""
    id: str
    session_id: str
    parent_task_id: str | None = None
    status: str = "open"
    summary: str = ""
    owner: str | None = None
    created_at: float = 0.0
    last_event_at: float = 0.0
    ended_at: float | None = None
    cleanup_after: float | None = None


@dataclass
class TaskEvent:
    """对应 TS TaskEvent 结构"""
    id: int
    task_id: str
    at: float
    kind: str
    summary: str | None = None


# ═══════════════════════════════════════════════════════════
# Task SQL — 移植自 task.sql.ts
# 适配 Craft 的 Database 层
# ═══════════════════════════════════════════════════════════

TASK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS task (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    parent_task_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    summary TEXT NOT NULL,
    owner TEXT,
    created_at INTEGER NOT NULL,
    last_event_at INTEGER NOT NULL,
    ended_at INTEGER,
    cleanup_after INTEGER,
    PRIMARY KEY (session_id, id)
);
CREATE INDEX IF NOT EXISTS task_session_idx ON task(session_id);
CREATE INDEX IF NOT EXISTS task_parent_idx ON task(session_id, parent_task_id);
CREATE INDEX IF NOT EXISTS task_status_idx ON task(status);

CREATE TABLE IF NOT EXISTS task_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    at INTEGER NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT,
    FOREIGN KEY (session_id, task_id) REFERENCES task(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS task_event_task_idx ON task_event(session_id, task_id, at);
"""


def _ensure_task_tables(db) -> None:
    """Ensure task tables exist."""
    from craft.core.storage import db as storage_db
    # Execute the schema
    for statement in TASK_SCHEMA_SQL.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            try:
                storage_db.execute(stmt)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# Events — 移植自 events.ts
# ═══════════════════════════════════════════════════════════


class TaskBusEvent:
    """Base class for task bus events."""

    def __init__(self, session_id: str, task: TaskData | dict):
        self.session_id = session_id
        self.task = task


class TaskCreated(TaskBusEvent):
    """Emitted when a task is created."""

    def __init__(self, session_id: str, task: TaskData | dict):
        super().__init__(session_id, task)


class TaskUpdated(TaskBusEvent):
    """Emitted when a task transitions.

    ``kind`` is one of TaskEventKind (excludes "created").
    """

    def __init__(self, session_id: str, task: TaskData | dict, kind: str):
        super().__init__(session_id, task)
        self.kind = kind


# ═══════════════════════════════════════════════════════════
# ID 生成 — 移植自 registry.ts
# ═══════════════════════════════════════════════════════════


def next_child_id(parent_id: str | None, siblings: list[str]) -> str:
    """Generate next task ID (e.g. T1, T1.1, T2, etc.)."""
    prefix = f"{parent_id}." if parent_id else "T"
    used = []
    for s in siblings:
        if parent_id:
            if s.startswith(prefix):
                tail = s[len(prefix):]
                if re.match(r"^\d+$", tail):
                    used.append(int(tail))
        else:
            if re.match(r"^T\d+$", s):
                used.append(int(s[1:]))
    nxt = max(used) + 1 if used else 1
    return f"{prefix}{nxt}"


# ═══════════════════════════════════════════════════════════
# Gate — 移植自 gate.ts
# ═══════════════════════════════════════════════════════════

MAX_TASK_GATE_SUBAGENT_REACT = 2


@dataclass
class Decision:
    need_reentry: bool = False
    cap_exceeded: bool = False
    reentry_text: str = ""
    incomplete_tasks: list[str] = field(default_factory=list)


@dataclass
class DecideInput:
    session_id: str
    owner: str | None = None
    react_count: int = 0
    max_react: int = MAX_TASK_GATE_SUBAGENT_REACT


def _build_reentry_text(incomplete: list[dict]) -> str:
    """Build system reminder for unfinished tasks."""
    lines = [
        "<system-reminder>",
        "You are about to finish, but these tasks you own are still unfinished:",
    ]
    for t in incomplete:
        lines.append(f"- {t['id']} ({t['status']}): {t['summary']}")
    lines.append(
        "For EACH: complete the work then `task done <id> <summary>`, "
        "or `task abandon <id> <reason>` if it is genuinely not needed."
    )
    lines.append("Then re-emit your final message starting with the **Status**/**Summary** header.")
    lines.append("</system-reminder>")
    return "\n".join(lines)


def decide(input_: DecideInput, tasks: list[TaskData]) -> Decision:
    """Pure decision: given non-terminal tasks for (session, owner), return the gate branch."""
    actionable = [t for t in tasks if is_actionable_status(t.status)]

    if not actionable:
        return Decision()

    if input_.react_count >= input_.max_react:
        return Decision(cap_exceeded=True, incomplete_tasks=[t.id for t in actionable])

    return Decision(
        need_reentry=True,
        reentry_text=_build_reentry_text(
            [{"id": t.id, "status": t.status, "summary": t.summary} for t in actionable]
        ),
        incomplete_tasks=[t.id for t in actionable],
    )


# ═══════════════════════════════════════════════════════════
# Registry — 移植自 registry.ts
# ═══════════════════════════════════════════════════════════

DAY_MS = 24 * 60 * 60 * 1000

_not_found_message = lambda id_: f"Task {id_} not found. Use `task list` to see valid task IDs, or `task create` to add one."


def _from_row(row: dict) -> TaskData:
    """Convert a DB row to TaskData."""
    return TaskData(
        id=row["id"],
        session_id=row["session_id"],
        parent_task_id=row.get("parent_task_id"),
        status=row["status"],
        summary=row["summary"],
        owner=row.get("owner"),
        created_at=row["created_at"],
        last_event_at=row["last_event_at"],
        ended_at=row.get("ended_at"),
        cleanup_after=row.get("cleanup_after"),
    )


def _from_event_row(row: dict) -> TaskEvent:
    """Convert a DB row to TaskEvent."""
    return TaskEvent(
        id=row["id"],
        task_id=row["task_id"],
        at=row["at"],
        kind=row["kind"],
        summary=row.get("summary"),
    )


class TaskRegistry:
    """Task persistence and eventing — port of TaskRegistry from registry.ts."""

    def __init__(self):
        from craft.core.storage import db
        self._db = db
        self._bus = None
        _ensure_task_tables(self._db)

    @property
    def bus(self):
        if self._bus is None:
            from craft.core.bus import bus
            self._bus = bus
        return self._bus

    def _insert_event(self, session_id: str, task_id: str, kind: str,
                      summary: str | None, now: float) -> None:
        self._db.execute(
            "INSERT INTO task_event (session_id, task_id, at, kind, summary) VALUES (?, ?, ?, ?, ?)",
            [session_id, task_id, int(now), kind, summary],
        )

    def _publish_created(self, task: TaskData) -> None:
        self.bus.emit("task.created", {"sessionID": task.session_id, "task": task})

    def _publish_updated(self, task: TaskData, kind: str) -> None:
        self.bus.emit("task.updated", {"sessionID": task.session_id, "task": task, "kind": kind})

    def create(
        self,
        session_id: str,
        summary: str,
        parent_id: str | None = None,
        owner: str | None = None,
    ) -> TaskData:
        """Create a new task and emit event."""
        now = time.time() * 1000
        siblings = self._db.fetch_all(
            "SELECT id FROM task WHERE session_id = ? AND "
            + ("parent_task_id = ?" if parent_id else "parent_task_id IS NULL"),
            [session_id] + ([parent_id] if parent_id else []),
        )
        id_ = next_child_id(parent_id, [s["id"] for s in siblings])

        self._db.execute(
            "INSERT INTO task (id, session_id, parent_task_id, status, summary, owner, "
            "created_at, last_event_at, ended_at, cleanup_after) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            [id_, session_id, parent_id, "open", summary, owner, int(now), int(now)],
        )
        self._insert_event(session_id, id_, "created", None, now)

        task = TaskData(
            id=id_, session_id=session_id, parent_task_id=parent_id,
            status="open", summary=summary, owner=owner,
            created_at=now, last_event_at=now,
        )
        self._publish_created(task)
        return task

    def list(
        self,
        session_id: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        include_terminal: bool = False,
        include_archived: bool = False,
    ) -> list[TaskData]:
        """List tasks with optional filters."""
        now = time.time() * 1000
        conditions = []
        params = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if owner:
            conditions.append("owner = ?")
            params.append(owner)
        if not include_terminal:
            non_term = ",".join(f"'{s}'" for s in NON_TERMINAL_STATUSES)
            conditions.append(f"status IN ({non_term})")
        if not include_archived:
            conditions.append("(cleanup_after IS NULL OR cleanup_after > ?)")
            params.append(int(now))

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM task WHERE {where} ORDER BY created_at"
        rows = self._db.fetch_all(sql, params)
        return [_from_row(r) for r in rows]

    def get(self, session_id: str, id_: str) -> TaskData | None:
        """Get a single task by session_id and id."""
        row = self._db.fetch_one(
            "SELECT * FROM task WHERE session_id = ? AND id = ?",
            [session_id, id_],
        )
        if not row:
            return None
        return _from_row(row)

    def _update_status(
        self,
        session_id: str,
        id_: str,
        status: str,
        event_kind: str,
        event_summary: str | None = None,
        extra: dict | None = None,
    ) -> TaskData:
        """Update task status, insert event, and emit bus event."""
        now = time.time() * 1000
        sets = {"status": status, "last_event_at": int(now)}
        if extra:
            sets.update(extra)
        set_clause = ", ".join(f"{k} = ?" for k in sets)
        values = list(sets.values()) + [session_id, id_]
        self._db.execute(
            f"UPDATE task SET {set_clause} WHERE session_id = ? AND id = ?",
            values,
        )
        self._insert_event(session_id, id_, event_kind, event_summary, now)
        updated = self.get(session_id, id_)
        if updated:
            self._publish_updated(updated, event_kind)
        return updated

    def block(self, session_id: str, id_: str, event_summary: str | None = None) -> TaskData:
        """Mark a task as blocked."""
        return self._update_status(session_id, id_, "blocked", "blocked", event_summary)

    def unblock(self, session_id: str, id_: str, event_summary: str | None = None) -> TaskData:
        """Mark a task as unblocked (reopen)."""
        return self._update_status(session_id, id_, "open", "unblocked", event_summary)

    def start(self, session_id: str, id_: str, owner: str | None = None,
              event_summary: str | None = None) -> TaskData:
        """Start a task (transition to in_progress)."""
        now = time.time() * 1000
        existing = self.get(session_id, id_)
        if not existing:
            raise ValueError(_not_found_message(id_))

        if existing.status in ("done", "abandoned"):
            return existing

        resolved_owner = owner or existing.owner
        if existing.status == "in_progress" and resolved_owner == existing.owner:
            return existing

        return self._update_status(
            session_id, id_, "in_progress", "started", event_summary,
            extra={"owner": resolved_owner},
        )

    def done(self, session_id: str, id_: str, event_summary: str | None = None) -> TaskData:
        """Mark a task as done."""
        now = time.time() * 1000
        cleanup = int(now + 7 * DAY_MS)
        return self._update_status(
            session_id, id_, "done", "done", event_summary,
            extra={"ended_at": int(now), "cleanup_after": cleanup},
        )

    def abandon(self, session_id: str, id_: str, event_summary: str | None = None) -> TaskData:
        """Mark a task as abandoned."""
        now = time.time() * 1000
        cleanup = int(now + 7 * DAY_MS)
        return self._update_status(
            session_id, id_, "abandoned", "abandoned", event_summary,
            extra={"ended_at": int(now), "cleanup_after": cleanup},
        )

    def rename(self, session_id: str, id_: str, summary: str) -> TaskData:
        """Rename a task."""
        now = time.time() * 1000
        self._db.execute(
            "UPDATE task SET summary = ?, last_event_at = ? WHERE session_id = ? AND id = ?",
            [summary, int(now), session_id, id_],
        )
        self._insert_event(session_id, id_, "renamed", summary, now)
        updated = self.get(session_id, id_)
        if updated:
            self._publish_updated(updated, "renamed")
        return updated

    def events(self, session_id: str, task_id: str) -> list[TaskEvent]:
        """Get all events for a task."""
        rows = self._db.fetch_all(
            "SELECT * FROM task_event WHERE session_id = ? AND task_id = ? ORDER BY at",
            [session_id, task_id],
        )
        return [_from_event_row(r) for r in rows]


# ═══════════════════════════════════════════════════════════
# 模块全局实例
# ═══════════════════════════════════════════════════════════

tasks = TaskManager()
registry = TaskRegistry()
