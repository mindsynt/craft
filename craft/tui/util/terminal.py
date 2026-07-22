"""
终端工具 — 移植自 util/terminal.ts

终端检测辅助函数、终端颜色查询 (OSC 10/11/4)。
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import sys
from typing import Optional


def is_mac_native_terminal(
    input_platform: Optional[str] = None,
    term_program: Optional[str] = None,
) -> bool:
    """检测是否为 macOS 原生终端 (Apple_Terminal)"""
    return (
        (input_platform or platform.system().lower()) == "darwin"
        and (term_program or os.environ.get("TERM_PROGRAM")) == "Apple_Terminal"
    )


def is_windows_terminal(wt_session: Optional[str] = None) -> bool:
    """检测是否为 Windows Terminal"""
    return bool(wt_session or os.environ.get("WT_SESSION"))


def is_plain_terminal(
    input_platform: Optional[str] = None,
    term_program: Optional[str] = None,
    plain: Optional[str] = None,
) -> bool:
    """检测是否为纯文本终端（无高级 TUI 支持）"""
    plain_val = plain or os.environ.get("CRAFT_TUI_PLAIN") or os.environ.get("MIMOCODE_TUI_PLAIN")
    if plain_val in ("false", "0"):
        return False
    if plain_val in ("true", "1"):
        return True
    return is_mac_native_terminal(input_platform, term_program)


async def query_terminal_colors() -> dict:
    """通过 OSC 转义序列查询终端颜色

    Returns:
        {"background": RGBA | None, "foreground": RGBA | None, "colors": [RGBA]}
    """
    result = {"background": None, "foreground": None, "colors": []}

    if not sys.stdin.isatty():
        return result

    # Since Python can't easily do raw terminal I/O like Node.js,
    # this is a simplified version. A real implementation would use
    # termios/select to read escape responses.
    return result
