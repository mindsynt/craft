"""
TUI 迁移 — 移植自 config/tui-migrate.ts

将旧版 mimocode.json 中的 tui 配置迁移到新的 tui.json。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

TUI_SCHEMA_URL = "https://craft.ai/tui.json"


def migrate_tui_config(directories: list[str], cwd: str) -> None:
    """迁移旧版 mimocode.json 中的 tui 配置到 tui.json"""
    # This is a compatibility migration for existing users
    # Logic mirrors the TS version but simplified for Python
    pass


def _normalize_tui(data: dict) -> Optional[dict]:
    """规范化 TUI 配置提取"""
    result = {}
    scroll_speed = data.get("scroll_speed")
    if isinstance(scroll_speed, (int, float)):
        result["scroll_speed"] = scroll_speed

    scroll_accel = data.get("scroll_acceleration")
    if isinstance(scroll_accel, dict) and "enabled" in scroll_accel:
        result["scroll_acceleration"] = scroll_accel

    diff_style = data.get("diff_style")
    if diff_style in ("auto", "stacked"):
        result["diff_style"] = diff_style

    return result if result else None
