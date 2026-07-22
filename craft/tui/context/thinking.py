"""
Thinking 上下文 — 移植自 context/thinking.ts

推理显示模式管理（show/hide）、推理摘要提取。
"""

from __future__ import annotations

import re
from typing import Callable, Optional

ThinkingMode = str  # "show" | "hide"

MODES: list[ThinkingMode] = ["show", "hide"]


def reasoning_summary(text: str) -> dict:
    """从推理文本中提取标题和正文"""
    content = text.strip()
    match = re.match(r"^\*\*([^*\n]+)\*\*(?:\r?\n\r?\n|$)", content)
    if not match:
        return {"title": None, "body": content}
    return {
        "title": match.group(1).strip(),
        "body": content[match.end():].strip(),
    }


def is_thinking_mode(value) -> bool:
    """检查值是否为有效的 ThinkingMode"""
    return isinstance(value, str) and value in MODES


def next_thinking_mode(current: ThinkingMode) -> ThinkingMode:
    """切换到下一个思考模式"""
    try:
        idx = MODES.index(current)
        return MODES[(idx + 1) % len(MODES)]
    except ValueError:
        return "show"


class ThinkingModeManager:
    """思考模式管理器"""

    def __init__(self, kv_store: Optional[dict] = None):
        self._kv = kv_store or {}
        had_stored = "thinking_mode" in self._kv
        legacy = self._kv.get("thinking_visibility")

        if not had_stored:
            if legacy is True:
                self._set("show")
            elif legacy is False:
                self._set("hide")

        if self._get() == "minimal":
            self._set("hide")

    def _get(self) -> str:
        return self._kv.get("thinking_mode", "hide")

    def _set(self, value: str):
        self._kv["thinking_mode"] = value

    @property
    def mode(self) -> str:
        val = self._get()
        return val if is_thinking_mode(val) else "hide"

    def set_mode(self, next_mode: ThinkingMode):
        """设置思考显示模式"""
        self._set(next_mode if is_thinking_mode(next_mode) else "hide")
