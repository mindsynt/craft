"""
音效 — 移植自 util/sound.ts

播放音效和提示音 (脉冲/持续音)。
使用 pygame 或命令行程式 (afplay/ffplay/mpv 等)。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

SOUND_PLAYERS = [
    "ffplay",
    "mpv",
    "mpg123",
    "mpg321",
    "mplayer",
    "afplay",
    "play",
    "omxplayer",
    "aplay",
    "cmdmp3",
    "cvlc",
    "powershell.exe",
]

DIR = Path(tempfile.gettempdir()) / "craft-sfx"
DIR.mkdir(parents=True, exist_ok=True)

_kind: str | None = None
_seq = 0
_proc: subprocess.Popen | None = None
_tail: asyncio.TimerHandle | None = None


def _pick_player() -> str | None:
    global _kind
    if _kind is not None:
        return _kind
    for cmd in SOUND_PLAYERS:
        if shutil.which(cmd):
            _kind = cmd
            return cmd
    return None


def _player_args(player: str, file: str, volume: float) -> list[str]:
    if player == "ffplay":
        return [player, "-autoexit", "-nodisp", "-af", f"volume={volume}", file]
    if player == "mpv":
        return [player, "--no-video", "--audio-display=no", "--volume", str(round(volume * 100)), file]
    if player == "mpg123" or player == "mpg321":
        return [player, "-g", str(round(volume * 100)), file]
    if player == "mplayer":
        return [player, "-vo", "null", "-volume", str(round(volume * 100)), file]
    if player in ("afplay", "omxplayer", "aplay", "cmdmp3"):
        return [player, file]
    if player == "play":
        return [player, "-v", str(volume), file]
    if player == "cvlc":
        return [player, f"--gain={volume}", "--play-and-exit", file]
    # powershell
    escaped = file.replace("'", "''")
    return [player, "-c", f"(New-Object Media.SoundPlayer '{escaped}').PlaySync()"]


async def play_file(file: str, volume: float = 0.35) -> Optional[int]:
    """播放 WAV 文件"""
    player = _pick_player()
    if not player:
        return None
    args = _player_args(player, file, volume)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait()


def start():
    """开始持续音 (hum)"""
    stop()
    # Placeholder - real WAV files would be bundled
    # For now, this is a no-op without asset files


def stop(delay: float = 0):
    """停止持续音"""
    global _seq, _proc, _tail
    _seq += 1
    if _tail:
        _tail.cancel()
        _tail = None
    if _proc:
        _proc.terminate()
        _proc = None


_pulse_index = 0


async def pulse(scale: float = 1.0):
    """播放脉冲音"""
    global _pulse_index
    stop(0.14)
    _pulse_index += 1
    # Placeholder - real WAV files would be needed
    # For now, this is a no-op without asset files


def dispose():
    stop()
