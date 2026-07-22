"""
Temporary storage — ported from MiMo-Code temporary module.

Provides ephemeral, session-scoped storage for transient data
that doesn't need to persist across sessions or survives only
for the duration of a single task.

In MiMo-Code this was the cli entry point (temporary.ts), which
bootstraps the application. Here we provide the storage utility.
"""

from __future__ import annotations

import time
import uuid
from typing import Any


class TemporaryStore:
    """Ephemeral, in-memory key-value store for session-scoped data.

    Data stored here does not persist across process restarts.
    Items can have an optional TTL (time-to-live in seconds).
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value with optional TTL (seconds)."""
        self._data[key] = (value, time.time() + ttl if ttl else None)

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key. Returns None if missing or expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and time.time() > expiry:
            del self._data[key]
            return None
        return value

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        return self.get(key) is not None

    def clear(self) -> None:
        """Clear all stored data."""
        self._data.clear()

    def keys(self) -> list[str]:
        """Return all non-expired keys."""
        now = time.time()
        return [
            k for k, (_, expiry) in self._data.items()
            if expiry is None or now < expiry
        ]


class TempFile:
    """Represents a temporary file reference for the duration of a session.

    In MiMo-Code, temporary file paths are used for checkpoint data,
    extracted bundles, and other ephemeral artifacts.
    """

    def __init__(self, path: str, cleanup: bool = True):
        self.path = path
        self._cleanup = cleanup
        self._id = uuid.uuid4().hex[:12]

    @property
    def id(self) -> str:
        return self._id

    def mark_for_cleanup(self) -> None:
        """Mark this temp file for cleanup on session end."""
        self._cleanup = True

    def __repr__(self) -> str:
        return f"TempFile(id={self._id}, path={self.path})"


# Global temporary store instance
_temp_store = TemporaryStore()


def temp_store() -> TemporaryStore:
    """Get the global temporary store."""
    return _temp_store


def set_temp(key: str, value: Any, ttl: float | None = None) -> None:
    """Convenience: set a value in the global temp store."""
    _temp_store.set(key, value, ttl)


def get_temp(key: str) -> Any | None:
    """Convenience: get a value from the global temp store."""
    return _temp_store.get(key)
