"""
语音输入 — 移植自 util/voice.ts
基础语音输入支持（需要系统麦克风权限）
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


class VoiceInput:
    def __init__(self):
        self._recording = False
        self._audio_data: bytes | None = None

    @property
    def is_available(self) -> bool:
        """检查系统是否支持语音输入"""
        import sys
        if sys.platform == "darwin":
            return os.path.exists("/usr/bin/sox") or os.path.exists("/opt/homebrew/bin/sox")
        return False

    async def record(self, duration: float = 5.0) -> bytes | None:
        """录制音频"""
        if not self.is_available:
            return None
        self._recording = True
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            
            proc = await asyncio.create_subprocess_exec(
                "sox", "-d", tmp_path, "rate", "16k",
                timeout=duration,
            )
            await asyncio.sleep(duration)
            proc.terminate()
            
            self._audio_data = Path(tmp_path).read_bytes()
            os.unlink(tmp_path)
            return self._audio_data
        except Exception:
            return None
        finally:
            self._recording = False

    def transcribe(self, audio: bytes | None = None) -> str:
        """模拟转写（实际需要 Whisper 等 ASR 服务）"""
        return "[语音输入需要 ASR 服务支持]"


voice = VoiceInput()
