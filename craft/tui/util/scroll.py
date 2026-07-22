"""
滚动 — 移植自 util/scroll.ts

自定义滚动加速度策略，替代默认的 macOS 滚动加速。
"""

from __future__ import annotations

from typing import Optional


class CustomSpeedScroll:
    """固定速度的滚动加速器"""

    def __init__(self, speed: int = 3):
        self._speed = speed

    def tick(self, _now: Optional[float] = None) -> int:
        return self._speed

    def reset(self):
        pass


def get_scroll_acceleration(tui_config: Optional[dict] = None):
    """根据 TUI 配置选择合适的滚动加速器"""
    if not tui_config:
        return CustomSpeedScroll(3)

    scroll_accel = tui_config.get("scroll_acceleration")
    if isinstance(scroll_accel, dict) and scroll_accel.get("enabled"):
        # MacOSScrollAccel - would need native implementation
        return CustomSpeedScroll(3)

    scroll_speed = tui_config.get("scroll_speed")
    if scroll_speed is not None and isinstance(scroll_speed, (int, float)):
        return CustomSpeedScroll(int(scroll_speed))

    return CustomSpeedScroll(3)
