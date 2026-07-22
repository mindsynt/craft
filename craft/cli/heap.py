"""Heap monitoring — 移植自 packages/opencode/src/cli/heap.ts"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_AUTO_HEAP_SNAPSHOT = os.environ.get("CRAFT_AUTO_HEAP_SNAPSHOT", "").lower() in ("1", "true", "yes")
_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB
_MINUTE = 60.0

_timer: threading.Timer | None = None
_lock = False
_armed = True


def _get_rss() -> int:
    """Get RSS memory usage in bytes (Linux/macOS)."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except Exception:
        return 0


def _write_heap_snapshot():
    """Write a heap snapshot if available (CPython 3.11+ with tracemalloc)."""
    try:
        import tracemalloc
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        snapshot = tracemalloc.take_snapshot()
        log_dir = os.environ.get("CRAFT_LOG_DIR", "/tmp")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filepath = os.path.join(log_dir, f"heap-{os.getpid()}-{ts}.snapshot")
        snapshot.dump(filepath)
        logger.warning("heap snapshot written to %s", filepath)
    except ImportError:
        logger.warning("tracemalloc not available, skipping heap snapshot")


def _run():
    global _lock, _armed
    if _lock:
        return

    rss = _get_rss()
    if rss <= _LIMIT:
        _armed = True
        return
    if not _armed:
        return

    _lock = True
    _armed = False
    logger.warning("heap usage exceeded limit: rss=%d, limit=%d", rss, _LIMIT)
    _write_heap_snapshot()
    _lock = False


def start():
    """Start periodic heap monitoring (writes snapshot when RSS exceeds limit)."""
    if not _AUTO_HEAP_SNAPSHOT:
        return
    global _timer
    if _timer:
        return

    def loop():
        _run()
        global _timer
        _timer = threading.Timer(_MINUTE, loop)
        _timer.daemon = True
        _timer.start()

    _timer = threading.Timer(_MINUTE, loop)
    _timer.daemon = True
    _timer.start()
    logger.info("heap monitoring started (limit=%d)", _LIMIT)
