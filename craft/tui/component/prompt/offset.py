"""
Offset 工具 — 移植自 component/prompt/offset.ts

编辑器光标/标记位置在显示宽度 (CJK=2) 和 UTF-16 字符串索引之间转换。
"""

from __future__ import annotations

import re


def _char_width(ch: str) -> int:
    """计算字符显示宽度"""
    if ch == "\n":
        return 1
    if ch == "\t":
        return 2
    # CJK range check
    code = ord(ch)
    if code >= 0x2E80 and code <= 0x9FFF:
        return 2
    if code >= 0xF900 and code <= 0xFAFF:
        return 2
    if code >= 0xFF01 and code <= 0xFF60:
        return 2
    if code >= 0xFE30 and code <= 0xFE4F:
        return 2
    return 1


def width_to_string_index(text: str, width_offset: int) -> int:
    """显示宽度偏移 → UTF-16 字符串索引"""
    width = 0
    idx = 0
    for ch in text:
        if width >= width_offset:
            break
        width += _char_width(ch)
        idx += 1
    return idx


def string_index_to_width(text: str, string_index: int) -> int:
    """UTF-16 字符串索引 → 显示宽度偏移"""
    width = 0
    for i, ch in enumerate(text):
        if i >= string_index:
            break
        width += _char_width(ch)
    return width


def char_after_cursor(text: str, cursor_width: int) -> str | None:
    """获取宽度光标后的字符"""
    idx = width_to_string_index(text, cursor_width)
    if idx < len(text):
        return text[idx]
    return None


def token_end_width(text: str, start_width: int) -> int:
    """查找从 start_width 开始的 token 结束宽度位置"""
    start_idx = width_to_string_index(text, start_width)
    end_idx = start_idx
    while end_idx < len(text) and not re.match(r"\s", text[end_idx]):
        end_idx += 1
    return string_index_to_width(text, end_idx)
