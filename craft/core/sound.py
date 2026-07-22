"""
声音效果 — 移植自 util/sound.ts
终端提示音、操作反馈
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess


class SoundEffects:
    def __init__(self):
        self._enabled = True
        self._system = platform.system()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True

    async def play(self, sound: str = "bell"):
        if not self._enabled:
            return
        try:
            if self._system == "darwin":
                sounds = {
                    "bell": "Tink",
                    "success": "Hero",
                    "error": "Basso",
                    "message": "Pop",
                }
                name = sounds.get(sound, "Tink")
                subprocess.run(["afplay", f"/System/Library/Sounds/{name}.aiff"],
                             capture_output=True, timeout=2)
            elif self._system == "linux":
                print("\a", end="", flush=True)
        except Exception:
            pass

    async def bell(self):
        await self.play("bell")

    async def success(self):
        await self.play("success")

    async def error(self):
        await self.play("error")


sound = SoundEffects()
