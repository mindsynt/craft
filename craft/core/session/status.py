"""Session status — ported from status.ts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StatusIdle:
    type: Literal["idle"] = "idle"


@dataclass
class StatusRetry:
    type: Literal["retry"] = "retry"
    attempt: int = 0
    message: str = ""
    next: float = 0.0  # unix ms


@dataclass
class StatusBusy:
    type: Literal["busy"] = "busy"
    message: str | None = None


SessionStatusInfo = StatusIdle | StatusRetry | StatusBusy


class SessionStatusManager:
    """In-memory session status manager (port of status.ts)."""

    def __init__(self):
        self._states: dict[str, SessionStatusInfo] = {}

    def get(self, session_id: str) -> SessionStatusInfo:
        return self._states.get(session_id, StatusIdle())

    def list(self) -> dict[str, SessionStatusInfo]:
        return dict(self._states)

    def set(self, session_id: str, status: SessionStatusInfo) -> None:
        if status.type == "idle":
            self._states.pop(session_id, None)
        else:
            self._states[session_id] = status


session_status = SessionStatusManager()
