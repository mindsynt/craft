"""Loop File 和 Loop State — 移植自 loop-file.ts / loop-state.ts"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_LOOP_FILE_BYTES = 25_000
TRUNCATION_MARKER = (
    "\n\n> WARNING: loop.md was truncated to 25000 bytes. Keep the task list concise."
)

# ═══════════════════════════════════════════════════════════
# Loop File — 移植自 loop-file.ts
# ═══════════════════════════════════════════════════════════


async def read_loop_file(workspace_root: str) -> dict | None:
    """Read loop.md from project (.craft/loop.md) or home (~/loop.md)."""
    candidates = [
        Path(workspace_root) / ".craft" / "loop.md",
        Path.home() / "loop.md",
    ]
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        if len(content) > MAX_LOOP_FILE_BYTES:
            return {
                "path": str(path),
                "content": content[:MAX_LOOP_FILE_BYTES] + TRUNCATION_MARKER,
            }
        return {"path": str(path), "content": content}
    return None


# ═══════════════════════════════════════════════════════════
# Loop State — 移植自 loop-state.ts
# ═══════════════════════════════════════════════════════════


@dataclass
class LoopState:
    prompt: str
    started_at: float
    last_scheduled_for: float
    aged_out: bool = False
    keepalive_strikes: int = 0


_LOOP_STATES: dict[str, LoopState] = {}


def get_loop_state(prompt: str) -> LoopState | None:
    return _LOOP_STATES.get(prompt)


def set_loop_state(state: LoopState) -> None:
    _LOOP_STATES[state.prompt] = state


def delete_loop_state(prompt: str) -> None:
    _LOOP_STATES.pop(prompt, None)


def list_loop_states() -> list[LoopState]:
    return list(_LOOP_STATES.values())


def clear_all_loop_states() -> None:
    _LOOP_STATES.clear()


def reset_strikes(prompt: str) -> None:
    s = _LOOP_STATES.get(prompt)
    if s:
        s.keepalive_strikes = 0


def increment_strikes(prompt: str) -> int:
    s = _LOOP_STATES.get(prompt)
    if not s:
        return 0
    s.keepalive_strikes += 1
    return s.keepalive_strikes


def get_strikes(prompt: str) -> int:
    s = _LOOP_STATES.get(prompt)
    return s.keepalive_strikes if s else 0
