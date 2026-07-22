"""
Part 工具 — 移植自 component/prompt/part.ts

消息部分的剥离/分配/展开占位符。
"""

from __future__ import annotations

from typing import Any


def strip_part(part: dict) -> dict:
    """剥离消息部分的 id/messageID/sessionID 元数据"""
    return {k: v for k, v in part.items() if k not in ("id", "messageID", "sessionID")}


def assign_part(part: dict, id_generator: Any = None) -> dict:
    """为消息部分分配 ID"""
    result = dict(part)
    if id_generator:
        result["id"] = id_generator
    else:
        import time
        result["id"] = f"p{int(time.time() * 1000)}"
    return result


def expand_placeholders(plain_text: str, marks: list[dict]) -> str:
    """用真实粘贴内容替换编辑器中的占位符 span

    Marks 是 [(start_width, end_width, text)] 列表，按从右到左顺序替换。
    """
    sorted_marks = sorted(marks, key=lambda m: m.get("start", 0), reverse=True)
    result = plain_text
    for mark in sorted_marks:
        start = mark.get("start", 0)
        end = mark.get("end", 0)
        text = mark.get("text", "")
        # Convert width offsets to string indices
        str_start = _width_to_string_index_raw(result, start)
        str_end = _width_to_string_index_raw(result, end)
        result = result[:str_start] + text + result[str_end:]
    return result


def _width_to_string_index_raw(text: str, width_offset: int) -> int:
    """简易宽度转索引"""
    w = 0
    for i, ch in enumerate(text):
        if w >= width_offset:
            return i
        w += 2 if ord(ch) > 0x2E80 else 1
        if ch in "\n":
            w -= w - 1 if w > 1 else 0
        if ch == "\t":
            w += 1
    return len(text)
