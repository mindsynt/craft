"""
自动补全触发检测 — 移植自 component/prompt/autocomplete-detect.ts

检测何时应该显示自动补全弹窗：基于当前位置前的触发符 (@/ $/ /)
"""

from __future__ import annotations

import re
from typing import Literal, Optional

TriggerKind = Literal["@", "$", "/"]


def exact_submit_option(
    trigger: TriggerKind | None,
    query: str,
    options: list[dict],
) -> Optional[dict]:
    """检查是否能精确匹配提交选项（仅 / 命令）"""
    if trigger != "/":
        return None
    for option in options:
        if option.get("submitOnSelect") and option.get("display", "").rstrip() == "/" + query:
            return option
    return None


def detect_trigger(value: str, cursor_width: int) -> Optional[dict]:
    """检测当前输入位置是否需要显示自动补全

    Args:
        value: 编辑器纯文本 (UTF-16)
        cursor_width: 显示宽度光标偏移 (CJK=2)

    Returns:
        {"kind": "@"|"$"|"/", "index": width_position} 或 None
    """
    if cursor_width == 0:
        return None

    cursor_index = _width_to_string_index(value, cursor_width)

    # "/" 在开头且光标前无空格 → 保留传统单命令行为
    if value.startswith("/") and not re.search(r"\s", value[:cursor_index]):
        return {"kind": "/", "index": 0}

    # 光标前最近的 @ $ /，token 前必须是空格或字符串开头
    text = value[:cursor_index]
    idx = max(text.rfind("@"), text.rfind("$"), text.rfind("/"))
    if idx == -1:
        return None

    dollar = text.rfind("$")
    slash = text.rfind("/")

    if idx == slash:
        kind = "/"
    elif idx == dollar:
        kind = "$"
    else:
        kind = "@"

    before = value[idx - 1] if idx > 0 else None
    between = text[idx:]

    if (before is None or re.match(r"\s", before)) and not re.search(r"\s", between):
        # "/" 需要至少一个非斜杠字符
        if kind == "/" and len(between) <= 1:
            return None
        return {"kind": kind, "index": _string_index_to_width(value, idx)}

    return None


def _char_width(ch: str) -> int:
    """计算字符显示宽度（CJK=2，制表符=2，换行=1）"""
    if ch == "\n":
        return 1
    if ch == "\t":
        return 2
    # Simple CJK width check
    if ord(ch) >= 0x4E00 and ord(ch) <= 0x9FFF:
        return 2
    if ord(ch) >= 0x3000 and ord(ch) <= 0x303F:
        return 2
    if ord(ch) >= 0xFF00 and ord(ch) <= 0xFFEF:
        return 2
    return 1


def _width_to_string_index(text: str, width_offset: int) -> int:
    """将显示宽度偏移转为 UTF-16 索引"""
    width = 0
    idx = 0
    for ch in text:
        if width >= width_offset:
            break
        width += _char_width(ch)
        idx += len(ch)
    return idx


def _string_index_to_width(text: str, string_index: int) -> int:
    """将 UTF-16 索引转为显示宽度偏移"""
    width = 0
    idx = 0
    for ch in text:
        if idx >= string_index:
            break
        width += _char_width(ch)
        idx += len(ch)
    return width
