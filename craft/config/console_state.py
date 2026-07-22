"""终端状态 — 对应 console-state.ts"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsoleState:
    """控制台状态"""
    console_managed_providers: list[str] = field(default_factory=list)
    active_org_name: str | None = None
    switchable_org_count: int = 0


def empty_console_state() -> ConsoleState:
    return ConsoleState(
        console_managed_providers=[],
        active_org_name=None,
        switchable_org_count=0,
    )
