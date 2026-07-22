"""Cron bridge — wires cron scheduler to session prompt injection.

移植自 MiMo-Code packages/opencode/src/session/cron-bridge.ts
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)


def is_cron_disabled() -> bool:
    """Check if cron is disabled via MIMOCODE_DISABLE_CRON env var."""
    v = os.environ.get("MIMOCODE_DISABLE_CRON", "")
    if not v:
        return False
    s = v.strip().lower()
    return s not in ("", "0", "false", "no", "off")


class CronBridge:
    """Bridges cron scheduler events to session prompt injection.

    Attributes:
        session_id: The session ID this bridge is mounted on.
        workspace_root: The workspace root path.
        loading: Whether the session is currently busy.
        armed_this_turn: Set of prompt strings re-armed this turn.
    """

    def __init__(
        self,
        session_id: str,
        workspace_root: str,
        on_fire: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.session_id = session_id
        self.workspace_root = workspace_root
        self.loading = False
        self.got_first_event = False
        self.armed_this_turn: set[str] = set()
        self._on_fire = on_fire
        self._subscriptions: list[Callable] = []
        self._started = False

    def set_loading(self, loading: bool) -> None:
        """Update loading state and trigger keepalive sweep on busy→idle edge."""
        was_loading = self.loading
        self.loading = loading
        self.got_first_event = True
        if was_loading and not loading:
            self._run_keepalive_sweep()

    def on_arm_loop(self, prompt: str) -> None:
        """Record a model-driven re-arm."""
        self.armed_this_turn.add(prompt)

    def _run_keepalive_sweep(self) -> None:
        """Run keepalive sweep for this session."""
        # In a real implementation, this would check loop states and
        # potentially re-arm keepalive timers.
        pass

    def start(self) -> None:
        """Start the bridge."""
        if self._started:
            return
        self._started = True
        logger.info("cron bridge started", extra={
            "session_id": self.session_id,
            "workspace_root": self.workspace_root,
        })

    def stop(self) -> None:
        """Stop the bridge and clean up subscriptions."""
        if not self._started:
            return
        self._started = False
        for unsub in self._subscriptions:
            try:
                unsub()
            except Exception:
                pass
        self._subscriptions.clear()
        logger.info("cron bridge stopped", extra={"session_id": self.session_id})

    def fire(self, task: dict[str, Any]) -> None:
        """Fire a cron task for this session."""
        if self._on_fire:
            self._on_fire(task)


def create_cron_bridge(
    session_id: str,
    workspace_root: str,
    on_fire: Callable[[dict[str, Any]], None] | None = None,
) -> CronBridge:
    """Create a CronBridge instance."""
    return CronBridge(
        session_id=session_id,
        workspace_root=workspace_root,
        on_fire=on_fire,
    )
