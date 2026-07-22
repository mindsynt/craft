"""格式化与 LSP 配置 — 对应 formatter.ts, lsp.ts"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FormatterEntry(BaseModel):
    """格式化条目"""
    disabled: bool | None = None
    command: list[str] | None = None
    environment: dict[str, str] | None = None
    extensions: list[str] | None = None


# FormatterInfo 可以是 True/False (启用/禁用全部) 或 dict[name, Entry]
FormatterInfo = bool | dict[str, FormatterEntry]


class LSPEntry(BaseModel):
    """LSP 条目"""
    command: list[str] = Field(default_factory=list)
    extensions: list[str] | None = None
    disabled: bool | None = None
    env: dict[str, str] = Field(default_factory=dict)
    initialization: dict[str, Any] = Field(default_factory=dict)


# LSPInfo 可以是 True(启用默认) 或 dict[name, Entry] 或 dict[name, Disabled]
LSPInfo = bool | dict[str, LSPEntry | dict]
