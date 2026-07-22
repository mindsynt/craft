"""
Spinner — 移植自 ui/spinner.ts

Knight Rider 风格扫描动画加载指示器。
"""

from __future__ import annotations

import math
from typing import Any, Optional


def create_frames(width: int = 8, style: str = "diamonds",
                  hold_start: int = 30, hold_end: int = 9) -> list[str]:
    """创建 Knight Rider 风格扫描动画帧"""
    # Simplified implementation
    frames: list[str] = []
    chars = ["■", "◼", "◻", "□", "▪", "▫", "▮", "▯"]
    if style == "diamonds":
        chars = ["⬥", "◆", "⬩", "⬪"]
    elif style == "plane":
        chars = ["🛸", "·", "∙", "˙"]

    total = width + hold_end + (width - 1) + hold_start

    for frame_idx in range(total):
        line = ""
        for pos in range(width):
            # Simplified scanning: one active position
            active = frame_idx % (width * 2)
            if active >= width:
                active = 2 * width - active - 1
            if pos == active:
                line += chars[0] if style != "plane" else "🛸"
            elif abs(pos - active) < 3 and style != "plane":
                line += "·"
            else:
                line += " " if style == "plane" else "·"
        frames.append(line)

    return frames


class Spinner:
    """Spinner 加载指示器"""

    def __init__(self, text: str = "..."):
        self.text = text
        self._frames = create_frames()
        self._running = False
        self._frame_idx = 0

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def next_frame(self) -> str:
        frame = self._frames[self._frame_idx % len(self._frames)]
        self._frame_idx += 1
        return f"{frame} {self.text}"

    @property
    def is_running(self) -> bool:
        return self._running
