"""
格式化 — 移植自 packages/opencode/src/format/
代码格式化、文本处理
"""

from __future__ import annotations

import re


class Formatter:
    @staticmethod
    def trim_lines(text: str, max_lines: int = 100) -> str:
        lines = text.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines)-max_lines} more lines)"
        return text

    @staticmethod
    def strip_ansi(text: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    @staticmethod
    def camel_to_snake(text: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()

    @staticmethod
    def snake_to_camel(text: str) -> str:
        parts = text.split("_")
        return parts[0] + "".join(p.title() for p in parts[1:])

    @staticmethod
    def truncate(text: str, max_len: int = 200) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text

    @staticmethod
    def indent(text: str, level: int = 1, indent_str: str = "  ") -> str:
        prefix = indent_str * level
        return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


formatter = Formatter()
