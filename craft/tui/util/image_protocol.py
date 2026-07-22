"""
图片协议 — 移植自 util/image-protocol.ts

Kitty 终端图片协议检测和渲染。
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

ImageProtocol = str  # "kitty"

_next_id = 1
CHUNK = 4096


def detect_image_protocol() -> str | None:
    """检测终端支持的图片协议"""
    e = os.environ
    if e.get("KITTY_WINDOW_ID"):
        return "kitty"
    if e.get("TERM") == "xterm-kitty":
        return "kitty"
    if e.get("TERM") == "xterm-ghostty" or e.get("GHOSTTY_RESOURCES_DIR"):
        return "kitty"
    if e.get("TERM_PROGRAM") == "WezTerm":
        return "kitty"
    return None


def alloc_image_id() -> int:
    global _next_id
    val = _next_id
    _next_id += 1
    return val


def kitty_display(image_id: int, file_path: str, cols: int, rows: int):
    """通过 Kitty 协议在终端显示图片"""
    b64 = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
    out: list[str] = ["\x1b7\x1b[1;1H"]
    for i in range(0, len(b64), CHUNK):
        chunk = b64[i : i + CHUNK]
        more = 1 if i + CHUNK < len(b64) else 0
        if i == 0:
            out.append(
                f"\x1b_Gf=100,a=T,q=2,c={cols},r={rows},z=-1,i={image_id},C=1,m={more};{chunk}\x1b\\"
            )
        else:
            out.append(f"\x1b_Gm={more};{chunk}\x1b\\")
    out.append("\x1b8")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def kitty_clear(image_id: int):
    """清除 Kitty 协议显示的图片"""
    sys.stdout.write(f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\")
    sys.stdout.flush()
