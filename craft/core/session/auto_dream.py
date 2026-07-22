"""Auto-Dream / Auto-Distill — 移植自 packages/opencode/src/session/auto-dream.ts

Per-project scheduled dream memory consolidation and distill passes.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

DAY_MS = 24 * 60 * 60 * 1000
DEFAULT_DREAM_INTERVAL_DAYS = 7
DEFAULT_DISTILL_INTERVAL_DAYS = 30
MIN_SPAWN_GAP_MS = 10_000

AUTO_DREAM_TITLE = "Auto Dream"
AUTO_DISTILL_TITLE = "Auto Distill"

SYSTEM_SESSION_TITLES: frozenset[str] = frozenset([AUTO_DREAM_TITLE, AUTO_DISTILL_TITLE])


def is_system_session(title: str) -> bool:
    """Check if a session title matches a known system session."""
    return title in SYSTEM_SESSION_TITLES


DREAM_TASK = (
    "Run one automatic dream memory consolidation pass for the current project.\n\n"
    "Use the memory files as the working index and the raw mimocode trajectory database as the source of truth.\n"
    "Use bash for read-only SQLite and filesystem inspection. Do not modify the database.\n"
    "Consolidate only durable, verified information into project memory."
)

DISTILL_TASK = (
    "Run one automatic distill pass for the current project.\n\n"
    "Review the past month of sessions and identify repeated manual workflows worth packaging.\n"
    "Use the raw mimocode trajectory database as the source of truth and memory files to spot cross-session patterns.\n"
    "Inventory existing skills, agents, and commands first so you reuse or extend instead of duplicating.\n"
    "Use bash for read-only SQLite and filesystem inspection. Do not modify the database.\n"
    "Produce a compact shortlist, then create only the high-confidence missing assets."
)

# Module-level rate-limit state
_last_dream_spawn_time: float = 0
_last_distill_spawn_time: float = 0


class AutoDream:
    """Auto-dream/distill scheduling logic — port of auto-dream.ts."""

    @staticmethod
    def should_auto_run(
        enabled: bool,
        interval_days: int,
        title: str,
        label: str,
        db_get_last_run_time,
        db_get_earliest_session_time,
    ) -> bool:
        """Check whether an auto-run should trigger.

        Args:
            enabled: Whether the feature is enabled in config.
            interval_days: How many days between runs.
            title: Session title to look up.
            label: Human label for logging ("dream" or "distill").
            db_get_last_run_time: Callable(title) → timestamp_ms or None.
            db_get_earliest_session_time: Callable() → timestamp_ms or None.

        Returns:
            True if the autodream should trigger.
        """
        if not enabled:
            return False

        interval_ms = interval_days * DAY_MS
        last_run = db_get_last_run_time(title)
        now = time.time() * 1000

        if last_run is None:
            # First time ever: check if the project is old enough
            earliest = db_get_earliest_session_time()
            if earliest is None or now - earliest < interval_ms:
                logger.info("auto-%s skipped — project too young", label)
                return False

        elapsed = now - last_run if last_run else float("inf")
        if elapsed < interval_ms:
            logger.info("auto-%s skipped — last run too recent", label)
            return False

        logger.info("auto-%s triggering", label)
        return True

    @staticmethod
    def should_auto_dream(
        cfg: dict | None,
        db_get_last_run_time,
        db_get_earliest_session_time,
    ) -> bool:
        """Check whether the auto-dream should trigger."""
        if cfg is None:
            return False
        enabled = cfg.get("dream", {}).get("auto", True)
        if not enabled:
            return False

        global _last_dream_spawn_time
        now = time.time() * 1000
        if now - _last_dream_spawn_time < MIN_SPAWN_GAP_MS:
            return False
        _last_dream_spawn_time = now

        interval_days = cfg.get("dream", {}).get("interval_days", DEFAULT_DREAM_INTERVAL_DAYS)
        return AutoDream.should_auto_run(
            enabled=True,
            interval_days=interval_days,
            title=AUTO_DREAM_TITLE,
            label="dream",
            db_get_last_run_time=db_get_last_run_time,
            db_get_earliest_session_time=db_get_earliest_session_time,
        )

    @staticmethod
    def should_auto_distill(
        cfg: dict | None,
        db_get_last_run_time,
        db_get_earliest_session_time,
    ) -> bool:
        """Check whether the auto-distill should trigger."""
        if cfg is None:
            return False
        enabled = cfg.get("distill", {}).get("auto", True)
        if not enabled:
            return False

        global _last_distill_spawn_time
        now = time.time() * 1000
        if now - _last_distill_spawn_time < MIN_SPAWN_GAP_MS:
            return False
        _last_distill_spawn_time = now

        interval_days = cfg.get("distill", {}).get("interval_days", DEFAULT_DISTILL_INTERVAL_DAYS)
        return AutoDream.should_auto_run(
            enabled=True,
            interval_days=interval_days,
            title=AUTO_DISTILL_TITLE,
            label="distill",
            db_get_last_run_time=db_get_last_run_time,
            db_get_earliest_session_time=db_get_earliest_session_time,
        )
