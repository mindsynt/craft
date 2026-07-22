"""Checkpoint splitover plugin — validates checkpoint content quality.

移植自 MiMo-Code packages/opencode/src/plugin/checkpoint-splitover.ts

Runs validation on checkpoint-writer agent stop events to ensure
checkpoint quality, triggering retries or reflection when needed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def checkpoint_splitover_hook(
    session_id: str,
    project_id: str,
    actor_id: str,
    prior_titles: set[str] | None = None,
    expected_revisions: list[str] | None = None,
) -> dict[str, Any]:
    """Run the checkpoint splitover validation hook.

    Checks for content violations and returns a reason for retry
    if the checkpoint quality is insufficient.

    Args:
        session_id: The parent session ID.
        project_id: The project ID.
        actor_id: The checkpoint-writer actor ID.
        prior_titles: Titles already used in prior checkpoints.
        expected_revisions: Expected file revisions.

    Returns:
        {"continue": bool, "reason": str | None} — if continue is True,
        the checkpoint should be retried with the given reason.
    """
    if prior_titles is None:
        prior_titles = set()
    if expected_revisions is None:
        expected_revisions = []

    try:
        violations = await _run_validators_for_checkpoint(
            session_id=session_id,
            prior_titles=prior_titles,
            expected_revisions=expected_revisions,
            project_id=project_id,
        )

        if not violations:
            return {"continue": False, "reason": None}

        extract_required = [v for v in violations if v.get("severity") == "extract-required"]
        if extract_required:
            return {
                "continue": True,
                "reason": _build_extraction_reflection(extract_required),
            }

        errors = [v for v in violations if v.get("severity") == "error"]
        if errors:
            return {
                "continue": True,
                "reason": _build_reflection_message(errors, session_id, project_id),
            }

        # warn-only — fall through
        return {"continue": False, "reason": None}

    except Exception as e:
        logger.error("checkpoint-splitover hook failed", extra={
            "err": str(e),
            "session_id": session_id,
            "actor_id": actor_id,
        })
        return {"continue": False, "reason": None}


async def _run_validators_for_checkpoint(
    session_id: str,
    prior_titles: set[str],
    expected_revisions: list[str],
    project_id: str,
) -> list[dict[str, Any]]:
    """Run checkpoint validators and return any violations found.

    In a full implementation, this would check:
    - Title uniqueness against prior checkpoints
    - File revision expectations
    - Content quality heuristics
    """
    violations: list[dict[str, Any]] = []
    # Validate title uniqueness
    # (simplified — real implementation would query checkpoint store)

    return violations


def _build_extraction_reflection(violations: list[dict[str, Any]]) -> str:
    """Build a reflection message for extract-required violations."""
    parts = ["I need to extract more complete information for the following aspects:"]
    for v in violations:
        parts.append(f"- {v.get('detail', 'Missing required detail')}")
    parts.append("\nPlease retry with more thorough analysis.")
    return "\n".join(parts)


def _build_reflection_message(
    errors: list[dict[str, Any]],
    session_id: str,
    project_id: str,
) -> str:
    """Build a reflection message for error-severity violations."""
    parts = ["I found critical issues in the checkpoint content:"]
    for e in errors:
        parts.append(f"- [{e.get('rule', 'unknown')}] {e.get('detail', '')}")
    parts.append("\nPlease fix these issues and retry.")
    return "\n".join(parts)
