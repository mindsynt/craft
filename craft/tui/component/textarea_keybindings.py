"""
TextArea 键盘绑定 — 移植自 component/textarea-keybindings.ts

将文本区域操作映射到键盘快捷键配置。
"""

from __future__ import annotations

from typing import Any

TEXTAREA_ACTIONS = [
    "submit", "newline",
    "move-left", "move-right", "move-up", "move-down",
    "select-left", "select-right", "select-up", "select-down",
    "line-home", "line-end",
    "select-line-home", "select-line-end",
    "visual-line-home", "visual-line-end",
    "select-visual-line-home", "select-visual-line-end",
    "buffer-home", "buffer-end",
    "select-buffer-home", "select-buffer-end",
    "delete-line", "delete-to-line-end", "delete-to-line-start",
    "backspace", "delete",
    "undo", "redo",
    "word-forward", "word-backward",
    "select-word-forward", "select-word-backward",
    "delete-word-forward", "delete-word-backward",
]

ACTION_KEY_MAP: dict[str, str] = {
    action: f"input_{action.replace('-', '_')}"
    for action in TEXTAREA_ACTIONS
}


def map_textarea_keybindings(
    keybinds: dict[str, Any],
    action: str,
) -> list[dict]:
    """将快捷键配置映射为内部键绑定格式"""
    config_key = ACTION_KEY_MAP.get(action, f"input_{action.replace('-', '_')}")
    bindings = keybinds.get(config_key, [])
    if not isinstance(bindings, list):
        return []
    result = []
    for binding in bindings:
        if isinstance(binding, dict):
            entry = {
                "name": binding.get("name", ""),
                "action": action,
            }
            if binding.get("ctrl"):
                entry["ctrl"] = True
            if binding.get("meta"):
                entry["meta"] = True
            if binding.get("shift"):
                entry["shift"] = True
            if binding.get("super"):
                entry["super"] = True
            result.append(entry)
    return result


def get_textarea_keybindings(keybinds: dict[str, Any]) -> list[dict]:
    """获取完整 TextArea 键盘绑定列表"""
    result: list[dict] = [
        {"name": "return", "action": "submit"},
        {"name": "return", "meta": True, "action": "newline"},
    ]
    for action in TEXTAREA_ACTIONS:
        result.extend(map_textarea_keybindings(keybinds, action))
    return result
