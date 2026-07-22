"""
提问系统 — 移植自 packages/opencode/src/question/
用户交互、选择、确认、输入
"""

from __future__ import annotations

from typing import Any


class Question:
    def __init__(self, text: str, type: str = "text", default: Any = None,
                 choices: list[str] | None = None):
        self.text = text
        self.type = type
        self.default = default
        self.choices = choices or []

    async def ask(self) -> Any:
        if self.choices:
            print(f"{self.text} ({', '.join(self.choices)})")
            val = input(f"[{self.default or ''}]: ").strip()
        else:
            val = input(f"{self.text}: ").strip()
        if not val and self.default is not None:
            return self.default
        if self.type == "int":
            try:
                return int(val)
            except ValueError:
                return self.default
        if self.type == "bool":
            return val.lower() in ("y", "yes", "true", "1")
        return val

    async def confirm(self) -> bool:
        val = input(f"{self.text} [Y/n]: ").strip().lower()
        return not val or val in ("y", "yes")


def ask(text: str, default: Any = None) -> Question:
    return Question(text, default=default)


def confirm(text: str) -> Question:
    return Question(text, type="bool")


def select(text: str, choices: list[str]) -> Question:
    return Question(text, type="select", choices=choices)
