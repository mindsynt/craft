"""CLI Bootstrap — 移植自 packages/opencode/src/cli/bootstrap.ts"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def bootstrap(directory: str, cb):
    """Initialize and run a CLI bootstrap, then clean up.

    Provides the project instance, runs the callback, drains checkpoint writers,
    and disposes the instance.
    """
    from craft.core.project import instance_manager, bootstrap_project

    ctx = await bootstrap_project(directory)
    try:
        result = await cb()
        return result
    finally:
        # Allow pending background writers to drain
        await asyncio.sleep(0.5)
        instance_manager.reset()
