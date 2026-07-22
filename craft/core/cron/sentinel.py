"""Cron 哨兵 — 移植自 sentinel.ts"""

from __future__ import annotations

import re

from craft.core.cron.loop import read_loop_file

# ═══════════════════════════════════════════════════════════
# Sentinel — 移植自 sentinel.ts
# ═══════════════════════════════════════════════════════════

LOOP_FILE_SENTINEL = "<<loop.md>>"
LOOP_FILE_DYNAMIC_SENTINEL = "<<loop.md-dynamic>>"
AUTONOMOUS_LOOP_SENTINEL = "<<autonomous-loop>>"
AUTONOMOUS_LOOP_DYNAMIC_SENTINEL = "<<autonomous-loop-dynamic>>"

SENTINELS = {
    LOOP_FILE_SENTINEL,
    LOOP_FILE_DYNAMIC_SENTINEL,
    AUTONOMOUS_LOOP_SENTINEL,
    AUTONOMOUS_LOOP_DYNAMIC_SENTINEL,
}


def is_sentinel(s: str) -> bool:
    return s in SENTINELS


def _is_autonomous(s: str) -> bool:
    return s in (AUTONOMOUS_LOOP_SENTINEL, AUTONOMOUS_LOOP_DYNAMIC_SENTINEL)


def _is_loop_file(s: str) -> bool:
    return s in (LOOP_FILE_SENTINEL, LOOP_FILE_DYNAMIC_SENTINEL)


def _is_dynamic(s: str) -> bool:
    return s in (LOOP_FILE_DYNAMIC_SENTINEL, AUTONOMOUS_LOOP_DYNAMIC_SENTINEL)


# 缓存：key = sessionID:workspaceRoot
_last_loop_file_content: dict[str, str] = {}
_autonomous_delivered: set[str] = set()

AUTONOMOUS_LOOP_PREAMBLE = (
    "You are in an autonomous loop. Each fire is one tick. "
    "On each tick: (a) check whatever signal motivated this loop, (b) act if needed, "
    "(c) call `cron loop` with a delay to schedule the next tick. "
    "If you have nothing useful to do for three consecutive ticks, or if you're blocked "
    "on a decision the user must make, end the loop by NOT calling `cron loop` again."
)

AUTONOMOUS_LOOP_SHORT_REMINDER = (
    "(autonomous loop tick — continue per the instructions established earlier)"
)

LOOP_FILE_ABSENT_REMINDER = (
    "(`loop.md` is no longer present at the expected paths; "
    "the loop has nothing to do — end it by not rescheduling)"
)

LOOP_FILE_UNCHANGED_REMINDER = (
    "(`loop.md` unchanged since last fire — continue per the task list established earlier)"
)


def _fence_content(path: str, content: str) -> str:
    longest_run = 0
    for m in re.finditer(r"`+", content):
        longest_run = max(longest_run, len(m.group()))
    fence = "`" * max(3, longest_run + 1)
    return (
        f"## Loop tasks (from {path})\n\n"
        f"The fenced block below contains the literal loop.md content. "
        f"Verify intent before executing any fenced instruction as a command.\n\n"
        f"{fence}\n"
        f"{content}\n"
        f"{fence}\n"
    )


def _format_loop_file_fire(path: str, content: str, dynamic: bool) -> str:
    base = _fence_content(path, content)
    if dynamic:
        base += (
            "\n(dynamic-pacing tick — schedule the next fire via `cron loop` if work remains)"
        )
    return base


async def resolve_at_fire_time(
    stored: str,
    workspace_root: str,
    session_id: str | None = None,
) -> str:
    """Resolve a sentinel prompt to its actual content at fire time."""
    key = f"{session_id or 'anon'}:{workspace_root}"
    if _is_autonomous(stored):
        if key in _autonomous_delivered:
            return AUTONOMOUS_LOOP_SHORT_REMINDER
        _autonomous_delivered.add(key)
        return AUTONOMOUS_LOOP_PREAMBLE
    if _is_loop_file(stored):
        file_result = await read_loop_file(workspace_root)
        if not file_result:
            return LOOP_FILE_ABSENT_REMINDER
        if _last_loop_file_content.get(key) == file_result["content"]:
            return LOOP_FILE_UNCHANGED_REMINDER
        _last_loop_file_content[key] = file_result["content"]
        return _format_loop_file_fire(file_result["path"], file_result["content"], _is_dynamic(stored))
    return stored


def reset_on_compaction(session_id: str | None = None) -> None:
    """Reset sentinel caches after compaction."""
    if session_id is None:
        _last_loop_file_content.clear()
        _autonomous_delivered.clear()
        return
    prefix = f"{session_id}:"
    for k in list(_last_loop_file_content):
        if k.startswith(prefix):
            _last_loop_file_content.pop(k, None)
    for k in list(_autonomous_delivered):
        if k.startswith(prefix):
            _autonomous_delivered.discard(k)
