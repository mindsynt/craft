"""Session run state — ported from run-state.ts.

Manages concurrent session execution state, cancellation, and busy tracking.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


class BusyError(Exception):
    """Raised when a session is already busy."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session {session_id} is busy")


@dataclass
class RunnerState:
    session_id: str = ""
    agent_id: str = ""
    busy: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class RunStateManager:
    """Manages per-session run states."""

    def __init__(self):
        self._runners: dict[str, RunnerState] = {}

    def _key(self, session_id: str, agent_id: str) -> str:
        return f"{session_id}:{agent_id}"

    def assert_not_busy(self, session_id: str) -> None:
        """Raise BusyError if the main runner is busy."""
        key = self._key(session_id, "main")
        runner = self._runners.get(key)
        if runner and runner.busy:
            raise BusyError(session_id)

    def is_busy(self, session_id: str, agent_id: str = "main") -> bool:
        key = self._key(session_id, agent_id)
        runner = self._runners.get(key)
        return runner is not None and runner.busy

    def set_busy(self, session_id: str, agent_id: str = "main") -> RunnerState:
        key = self._key(session_id, agent_id)
        runner = self._runners.get(key)
        if not runner:
            runner = RunnerState(session_id=session_id, agent_id=agent_id)
            self._runners[key] = runner
        runner.busy = True
        runner.cancel_event.clear()
        return runner

    def set_idle(self, session_id: str, agent_id: str = "main") -> None:
        key = self._key(session_id, agent_id)
        runner = self._runners.get(key)
        if runner:
            runner.busy = False
            runner.task = None

    def cancel(self, session_id: str, agent_id: str = "main") -> None:
        key = self._key(session_id, agent_id)
        runner = self._runners.get(key)
        if runner:
            runner.cancel_event.set()
            if runner.task and not runner.task.done():
                runner.task.cancel()

    def cancel_actor(self, session_id: str, agent_id: str) -> None:
        self.cancel(session_id, agent_id)

    def list_busy(self) -> list[RunnerState]:
        return [r for r in self._runners.values() if r.busy]


run_state_manager = RunStateManager()
