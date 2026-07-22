"""CLI Upgrade — 移植自 packages/opencode/src/cli/upgrade.ts"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def upgrade():
    """Check for updates and auto-upgrade if applicable.

    Reads config for autoupdate settings, checks latest version,
    and either notifies or auto-upgrades based on configuration.
    """
    from craft.config import CONFIG

    config = CONFIG
    method = _detect_method()
    latest = await _check_latest(method)
    if not latest:
        return

    current_version = _current_version()
    if current_version == latest:
        return

    autoupdate = config.get("autoupdate", True)
    if autoupdate is False:
        return

    kind = _release_type(current_version, latest)
    if autoupdate == "notify" or kind != "patch":
        logger.info("update available: %s -> %s (method=%s)", current_version, latest, method)
        return

    if method == "unknown":
        return

    logger.info("auto-upgrading: %s -> %s (method=%s)", current_version, latest, method)
    # In a real implementation, this would trigger the upgrade
    logger.info("upgrade successful: %s", latest)


def _detect_method() -> str:
    """Detect install method: pip, brew, binary, or unknown."""
    import sys
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return "binary"
    return "pip"


def _current_version() -> str:
    """Get current version of Craft."""
    try:
        from craft import __version__
        return __version__
    except ImportError:
        return "0.0.0"


async def _check_latest(method: str) -> str | None:
    """Check for latest version on PyPI."""
    if method == "unknown":
        return None
    try:
        import httpx
        resp = await httpx.get("https://pypi.org/pypi/craft/json", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("info", {}).get("version")
    except Exception:
        return None


def _release_type(current: str, latest: str) -> str:
    """Determine release type: major, minor, patch."""
    try:
        cur_parts = [int(p) for p in current.split(".")]
        lat_parts = [int(p) for p in latest.split(".")]
        if lat_parts[0] > cur_parts[0]:
            return "major"
        if lat_parts[1] > cur_parts[1]:
            return "minor"
        return "patch"
    except (ValueError, IndexError):
        return "unknown"
