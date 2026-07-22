"""Layer 记忆映射 — MemoMap"""

from __future__ import annotations

import threading
from typing import Any, Callable


class MemoMap:
    """Layer 记忆映射 (对应 Layer.makeMemoMapUnsafe)"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str, factory: Callable[[], Any]) -> Any:
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


memo_map = MemoMap()


__all__ = [
    "MemoMap",
    "memo_map",
]
