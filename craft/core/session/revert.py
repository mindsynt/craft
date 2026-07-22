"""Session revert/unrevert — ported from revert.ts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RevertState:
    message_id: str = ""
    part_id: str | None = None
    snapshot: str | None = None
    diff: str | None = None


class SessionRevertManager:
    """Manages session revert state."""

    def __init__(self):
        self._reverts: dict[str, RevertState] = {}
        self._cleanup_states: dict[str, dict] = {}

    def get(self, session_id: str) -> RevertState | None:
        return self._reverts.get(session_id)

    def set(self, session_id: str, state: RevertState) -> None:
        self._reverts[session_id] = state

    def clear(self, session_id: str) -> None:
        self._reverts.pop(session_id, None)
        self._cleanup_states.pop(session_id, None)

    def set_cleanup(self, session_id: str, state: dict) -> None:
        self._cleanup_states[session_id] = state

    def get_cleanup(self, session_id: str) -> dict | None:
        return self._cleanup_states.get(session_id)


revert_manager = SessionRevertManager()
