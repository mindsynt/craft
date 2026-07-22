"""Session todo list — ported from todo.ts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TodoInfo:
    content: str = ""
    status: str = "pending"  # pending, in_progress, completed, cancelled


class TodoManager:
    """In-memory session todo list manager."""

    def __init__(self):
        self._todos: dict[str, list[TodoInfo]] = {}

    def update(self, session_id: str, todos: list[TodoInfo]) -> None:
        self._todos[session_id] = list(todos)

    def get(self, session_id: str) -> list[TodoInfo]:
        return list(self._todos.get(session_id, []))

    def delete_session(self, session_id: str) -> None:
        self._todos.pop(session_id, None)


todo_manager = TodoManager()
