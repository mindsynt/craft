"""
星空背景 — 移植自 starry-background.tsx (10KB)
终端星空动画效果
"""

from __future__ import annotations

import asyncio
import math
import random


class Star:
    def __init__(self, width: int, height: int):
        self.x = random.randint(0, width)
        self.y = random.randint(0, height)
        self.size = random.uniform(0.5, 2.0)
        self.brightness = random.uniform(0.3, 1.0)
        self.speed = random.uniform(0.01, 0.05)
        self.twinkle_phase = random.uniform(0, math.pi * 2)

    def update(self, time: float):
        self.brightness = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(time * self.speed + self.twinkle_phase))


class StarryBackground:
    """星空背景"""

    def __init__(self, width: int = 80, height: int = 24, star_count: int = 50):
        self.width = width
        self.height = height
        self.stars = [Star(width, height) for _ in range(star_count)]
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def render_frame(self, time: float) -> str:
        """生成一帧星空"""
        lines = []
        for y in range(self.height):
            line = ""
            for x in range(self.width):
                nearby_stars = [s for s in self.stars
                               if abs(s.x - x) < 1 and abs(s.y - y) < 1]
                if nearby_stars:
                    s = nearby_stars[0]
                    s.update(time)
                    if s.brightness > 0.7:
                        line += "✦"
                    elif s.brightness > 0.5:
                        line += "·"
                    else:
                        line += " "
                else:
                    line += " "
            lines.append(line)
        return "\n".join(lines)

    async def animate(self, duration: float = 2.0):
        """短时动画"""
        self.start()
        start = 0
        while self._running and start < duration:
            frame = self.render_frame(start)
            print("\033[H\033[J" + frame, end="", flush=True)
            await asyncio.sleep(0.05)
            start += 0.05
        self.stop()


starry = StarryBackground()
