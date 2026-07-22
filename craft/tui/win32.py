"""
Win32 工具 — 移植自 win32.ts

Windows 终端模式控制：禁用 ENABLE_PROCESSED_INPUT 和 Ctrl+C 守卫。
"""

from __future__ import annotations

import os
import platform
from typing import Optional

_IS_WINDOWS = platform.system().lower() == "windows"
_STD_INPUT_HANDLE = -10
_ENABLE_PROCESSED_INPUT = 0x0001


def disable_processed_input():
    """清除控制台 stdin 的 ENABLE_PROCESSED_INPUT 标志"""
    if not _IS_WINDOWS:
        return
    if not os.isatty(0):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return
        if mode.value & _ENABLE_PROCESSED_INPUT == 0:
            return
        kernel32.SetConsoleMode(handle, mode.value & ~_ENABLE_PROCESSED_INPUT)
    except Exception:
        pass


def flush_input_buffer():
    """清空控制台输入缓冲区"""
    if not _IS_WINDOWS:
        return
    if not os.isatty(0):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
        kernel32.FlushConsoleInputBuffer(handle)
    except Exception:
        pass


_unhook: Optional[callable] = None


def install_ctrlc_guard() -> Optional[callable]:
    """安装 Ctrl+C 守卫，持续清除 ENABLE_PROCESSED_INPUT"""
    global _unhook
    if not _IS_WINDOWS:
        return None
    if not os.isatty(0):
        return None
    if _unhook:
        return _unhook

    import ctypes
    import threading

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
        return None
    initial = mode.value

    def _enforce():
        try:
            m = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(m)) == 0:
                return
            if m.value & _ENABLE_PROCESSED_INPUT:
                kernel32.SetConsoleMode(handle, m.value & ~_ENABLE_PROCESSED_INPUT)
        except Exception:
            pass

    def _loop():
        import time
        while True:
            _enforce()
            time.sleep(0.1)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()

    def _restore():
        global _unhook
        try:
            kernel32.SetConsoleMode(handle, initial)
        except Exception:
            pass
        _unhook = None

    _unhook = _restore
    return _restore
