"""
Debug workspace plugin — ported from MiMo-Code control-plane/dev/debug-workspace-plugin.ts

Creates a debugging server workspace for development/testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEV_DATA_DIR = Path(tempfile.gettempdir()) / "craft-workspace-dev-data.json"
DEV_DATA_TEMP = Path(str(DEV_DATA_DIR) + ".tmp")


async def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    """Wait for the debug server to become healthy."""
    import urllib.request

    url = f"http://127.0.0.1:{port}/global/health"
    started = time.monotonic()

    while time.monotonic() - started < timeout:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(0.25)

    raise TimeoutError(f"Timed out waiting for debug server health check at {url}")


async def _write_debug_data(port: int, workspace_id: str, env: dict[str, str | None]) -> None:
    """Write debug server metadata to a temp file."""
    data = {"port": port, "id": workspace_id, "env": env}
    # Write to temp then atomically rename
    DEV_DATA_TEMP.write_text(json.dumps(data, indent=2))
    DEV_DATA_TEMP.rename(DEV_DATA_DIR)


class DebugWorkspacePlugin:
    """Debug workspace plugin that creates local debugging servers.

    Usage:
        plugin = DebugWorkspacePlugin()
        await plugin.create(workspace_id="dev-1", port=random_port)
    """

    def __init__(self) -> None:
        self._port: int | None = None
        self._workspace_id: str | None = None

    async def create(
        self,
        workspace_id: str,
        port: int | None = None,
        env: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Create a debug workspace.

        Args:
            workspace_id: Unique workspace identifier.
            port: Port for the debug server. Random if None.
            env: Environment variables for the server.

        Returns:
            Workspace config dict with 'type', 'url', 'id'.
        """
        if port is None:
            port = random.randint(5000, 9001)

        self._port = port
        self._workspace_id = workspace_id

        await _write_debug_data(port, workspace_id, env or dict(os.environ))
        await _wait_for_health(port)

        logger.info("Debug workspace ready on port %d (id=%s)", port, workspace_id)

        return {
            "id": workspace_id,
            "type": "remote",
            "url": f"http://localhost:{port}/",
        }

    async def remove(self) -> None:
        """Remove the debug workspace."""
        self._port = None
        self._workspace_id = None
        if DEV_DATA_DIR.exists():
            DEV_DATA_DIR.unlink()

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def workspace_id(self) -> str | None:
        return self._workspace_id


def make_debug_workspace_plugin() -> dict[str, Any]:
    """Create a debug workspace plugin config.

    Returns a config dict compatible with Craft's plugin system.
    """
    return {
        "name": "debug-workspace",
        "description": "Create a debugging server workspace",
        "version": "0.1.0",
        "workspace": {
            "type": "debug",
            "label": "Debug",
        },
    }
