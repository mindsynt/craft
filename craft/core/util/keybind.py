"""快捷键辅助 — 移植自 keybind.ts

快捷键信息类型、匹配、转换、解析功能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeybindInfo:
    """快捷键信息

    对应 TS Keybind.Info。包含键名和修饰键状态。
    """
    name: str = ""
    ctrl: bool = False
    meta: bool = False
    shift: bool = False
    super_: bool = False  # super 是 Python 关键字
    leader: bool = False

    @property
    def super(self) -> bool:
        return self.super_

    @super.setter
    def super(self, value: bool):
        self.super_ = value


def keybind_match(a: KeybindInfo | None, b: KeybindInfo) -> bool:
    """匹配两个快捷键是否相同

    对应 TS match()。
    """
    if a is None:
        return False
    return (
        a.name == b.name
        and a.ctrl == b.ctrl
        and a.meta == b.meta
        and a.shift == b.shift
        and a.super_ == b.super_
    )


def keybind_from_parsed(parsed: dict, leader: bool = False) -> KeybindInfo:
    """从解析字典创建快捷键信息

    对应 TS fromParsedKey()。
    """
    name = parsed.get("name", "")
    return KeybindInfo(
        name="space" if name == " " else name,
        ctrl=parsed.get("ctrl", False),
        meta=parsed.get("meta", False),
        shift=parsed.get("shift", False),
        super_=parsed.get("super", False),
        leader=leader,
    )


def keybind_to_string(info: KeybindInfo | None) -> str:
    """将快捷键信息转换为字符串

    对应 TS toString()。
    """
    if info is None:
        return ""
    parts: list[str] = []
    if info.ctrl:
        parts.append("ctrl")
    if info.meta:
        parts.append("alt")
    if info.super_:
        parts.append("super")
    if info.shift:
        parts.append("shift")
    if info.name:
        if info.name == "delete":
            parts.append("del")
        else:
            parts.append(info.name)

    result = "+".join(parts)
    if info.leader:
        result = f"<leader> {result}" if result else "<leader>"
    return result


def keybind_parse(key: str) -> list[KeybindInfo]:
    """解析快捷键字符串

    对应 TS parse()。支持逗号分隔的组合键。
    """
    if key == "none":
        return []

    results: list[KeybindInfo] = []
    for combo in key.split(","):
        normalized = combo.replace("<leader>", "leader+")
        parts = normalized.lower().split("+")
        info = KeybindInfo()

        for part in parts:
            part = part.strip()
            if part == "ctrl":
                info.ctrl = True
            elif part in ("alt", "meta", "option"):
                info.meta = True
            elif part == "super":
                info.super_ = True
            elif part == "shift":
                info.shift = True
            elif part == "leader":
                info.leader = True
            elif part == "esc":
                info.name = "escape"
            else:
                info.name = part

        results.append(info)

    return results
