"""Metrics subscriber — subscribes to events and forwards them to the metrics system.

移植自 MiMo-Code packages/opencode/src/metrics/subscriber.ts
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MetricsSubscriber:
    """Subscribes to internal events and forwards them as telemetry events.

    Listens on the event bus for metric-relevant events (model calls,
    tool usage, session activity) and forwards them to the metrics
    client for telemetry reporting.
    """

    def __init__(self):
        self._subscriptions: list[Callable] = []
        self._running = False
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the subscriber worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("metrics subscriber started")

    async def stop(self) -> None:
        """Stop the subscriber worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        for unsub in self._subscriptions:
            try:
                unsub()
            except Exception:
                pass
        self._subscriptions.clear()
        logger.info("metrics subscriber stopped")

    async def enqueue(self, event: dict[str, Any]) -> None:
        """Enqueue a metric event for processing."""
        if self._running:
            await self._event_queue.put(event)

    async def _worker_loop(self) -> None:
        """Process events from the queue."""
        from craft.core.metrics import post_events

        batch: list[dict[str, Any]] = []
        last_flush = 0.0

        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=10.0,
                )
                batch.append(event)
                import time
                now = time.time()
                if len(batch) >= 10 or (now - last_flush) >= 5.0:
                    if batch:
                        try:
                            await post_events(batch)
                        except Exception:
                            pass
                        batch = []
                    last_flush = now
            except asyncio.TimeoutError:
                if batch:
                    try:
                        await post_events(batch)
                    except Exception:
                        pass
                    batch = []
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("metrics subscriber error", extra={"error": str(e)})

        # Flush remaining
        if batch:
            try:
                await post_events(batch)
            except Exception:
                pass


# Singleton subscriber
_subscriber: MetricsSubscriber | None = None


def get_subscriber() -> MetricsSubscriber:
    """Get the global metrics subscriber instance."""
    global _subscriber
    if _subscriber is None:
        _subscriber = MetricsSubscriber()
    return _subscriber


async def record_event(
    event_type: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Record a metric event (fire-and-forget).

    Args:
        event_type: The event type name.
        properties: Event properties dict.
    """
    import time

    event = {
        "event": event_type,
        "properties": properties or {},
        "timestamp": int(time.time() * 1000),
    }
    sub = get_subscriber()
    await sub.enqueue(event)
