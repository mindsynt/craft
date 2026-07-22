"""
CLI Providers 命令 — 移植自 packages/opencode/src/cli/cmd/providers.ts
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def handle_providers_list(args: dict) -> None:
    """列出所有配置的 Provider"""
    try:
        from craft.core.provider import get_providers
        providers = get_providers()
    except ImportError:
        providers = []

    if not providers:
        print("No providers configured.")
        return

    print(f"{'Name':<20} {'Type':<16} {'Model':<24} {'Enabled'}")
    print("-" * 80)
    for p in providers:
        name = p.get("name", "?")
        ptype = p.get("type", "?")
        model = p.get("model", "")
        enabled = "✓" if p.get("enabled", True) else "✗"
        print(f"{name:<20} {ptype:<16} {model:<24} {enabled}")


async def handle_providers_add(args: dict) -> None:
    """添加新的 Provider"""
    name = args.get("name", "")
    if not name:
        print("Error: --name is required")
        return
    print(f"Adding provider: {name} (not yet implemented)")


async def handle_providers_remove(args: dict) -> None:
    """移除 Provider"""
    name = args.get("name", "")
    if not name:
        print("Error: --name is required")
        return
    print(f"Removing provider: {name} (not yet implemented)")
