"""
TUI Schema — 移植自 config/tui-schema.ts

TUI 配置的 Zod 验证模式（Python 版使用 dataclass/attrs/dict 验证）。
"""

from __future__ import annotations

from typing import Any, Optional

TUI_OPTIONS_SCHEMA = {
    "scroll_speed": {"type": "number", "min": 0.001, "description": "TUI scroll speed"},
    "scroll_acceleration": {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "description": "Scroll acceleration settings",
    },
    "diff_style": {
        "type": "string",
        "enum": ["auto", "stacked"],
        "description": "Diff rendering style",
    },
    "mouse": {
        "type": "boolean",
        "description": "Enable or disable mouse capture",
    },
}

TUI_SCHEMA = {
    "type": "object",
    "properties": {
        "$schema": {"type": "string"},
        "theme": {"type": "string"},
        "keybinds": {"type": "object", "additionalProperties": {"type": "string"}},
        "plugin": {"type": "array", "items": {"type": "string"}},
        "plugin_enabled": {
            "type": "object",
            "additionalProperties": {"type": "boolean"},
        },
        "scroll_speed": {"type": "number"},
        "scroll_acceleration": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
        },
        "diff_style": {"type": "string", "enum": ["auto", "stacked"]},
        "mouse": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def validate_tui_config(data: dict) -> tuple[bool, Optional[str]]:
    """验证 TUI 配置（简化的 schema 验证）"""
    if not isinstance(data, dict):
        return False, "Config must be a dictionary"

    allowed_keys = set(TUI_SCHEMA["properties"].keys())
    for key in data:
        if key not in allowed_keys:
            return False, f"Unknown key: {key}"

    if "diff_style" in data and data["diff_style"] not in ("auto", "stacked"):
        return False, "diff_style must be 'auto' or 'stacked'"

    if "scroll_speed" in data:
        val = data["scroll_speed"]
        if not isinstance(val, (int, float)) or val < 0.001:
            return False, "scroll_speed must be >= 0.001"

    return True, None


def make_keybind_override() -> dict:
    """创建键绑定覆盖类型"""
    return object  # dict[str, str | None]
