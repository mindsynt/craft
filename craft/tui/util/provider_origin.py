"""
提供商来源 — 移植自 util/provider-origin.ts

检查 provider 是否属于控制台托管提供商。
"""

from __future__ import annotations

from typing import Sequence


def is_console_managed_provider(
    console_managed_providers: Sequence[str],
    provider_id: str,
) -> bool:
    """判断 provider 是否由控制台托管"""
    return provider_id in console_managed_providers
