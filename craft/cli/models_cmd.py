"""
CLI Models 命令 — 移植自 packages/opencode/src/cli/cmd/models.ts
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def handle_models_list(args: dict) -> None:
    """列出所有可用模型"""
    try:
        from craft.core.provider import get_models
        models = get_models()
    except ImportError:
        models = []

    if not models:
        print("No models available.")
        return

    provider_filter = args.get("provider", "")

    print(f"{'ID':<32} {'Provider':<16} {'Name'}")
    print("-" * 80)
    for m in models:
        pid = m.get("provider_id", m.get("provider", ""))
        if provider_filter and pid != provider_filter:
            continue
        mid = m.get("model_id", m.get("id", "?"))
        name = m.get("name", mid)
        print(f"{mid:<32} {pid:<16} {name}")
