"""
生成 — 移植自 packages/opencode/src/actor/spawn-ref.ts
"""

from __future__ import annotations

import threading
from typing import Any


_current_spawn_service: threading.local = threading.local()


class SpawnRef:
    """Spawn 引用 — 移植自 spawn-ref.ts"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_spawn_service, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_spawn_service.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_spawn_service, "value"):
            del _current_spawn_service.value
