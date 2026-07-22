"""Checkpoint context (in-memory store) — ported from checkpoint-context.ts."""

import copy
from typing import TypedDict


class CheckpointContext(TypedDict, total=False):
    prior_titles: set[str]
    expected_revisions: list[dict]


_store: dict[str, CheckpointContext] = {}


def _key(session_id: str, actor_id: str) -> str:
    return f"{session_id}:{actor_id}"


def set_context(session_id: str, actor_id: str, ctx: CheckpointContext) -> None:
    _store[_key(session_id, actor_id)] = ctx


def get_context(session_id: str, actor_id: str) -> CheckpointContext | None:
    ctx = _store.get(_key(session_id, actor_id))
    if ctx is None:
        return None
    return copy.deepcopy(ctx)


def remove_context(session_id: str, actor_id: str) -> None:
    _store.pop(_key(session_id, actor_id), None)


def reset() -> None:
    """Test-only escape hatch."""
    _store.clear()


def size() -> int:
    """Test-only: returns total entry count."""
    return len(_store)
