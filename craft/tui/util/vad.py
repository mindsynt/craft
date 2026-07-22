"""
语音检测 (VAD) — 移植自 util/vad.ts

基于 WebrtcVAD 的实时语音活动检测器。
需要 numpy。
"""

from __future__ import annotations

import math
from typing import Callable, Optional

VAD_SAMPLE_RATE = 16000
HOP_SIZE = 256


class RealtimeVAD:
    """实时语音活动检测器"""

    def __init__(
        self,
        on_segment: Callable,
        on_active_change: Optional[Callable] = None,
        start_threshold: float = 0.8,
        end_threshold: float = 0.7,
        pad_start_s: float = 0.6,
        min_silence_s: float = 0.8,
        max_segment_s: float = 60.0,
    ):
        self.on_segment = on_segment
        self.on_active_change = on_active_change
        self.start_threshold = start_threshold
        self.end_threshold = end_threshold
        self.pad_start_s = pad_start_s
        self.min_silence_s = min_silence_s
        self.max_segment_s = max_segment_s

        # Internal state
        self.buffer: list[int] = []
        self.buffer_offset = 0
        self.src_buffer: list[int] = []
        self.src_buffer_offset = 0
        self.active = False
        self.active_start_s = 0.0
        self.sum_positive_s = 0.0
        self.silence_start_s: Optional[float] = None
        self.initialized = False

    def init(self):
        """初始化 VAD（使用同步调用）"""
        self.initialized = True
        # In a real implementation, this would load a WASM module
        # For now, use a simple energy-based VAD as fallback

    def _energy_vad(self, frame: list[int]) -> float:
        """简单的能量检测 VAD（替代品）"""
        if not frame:
            return 0.0
        energy = sum(abs(s) for s in frame) / len(frame)
        # Normalize to 0-1 range (assuming 16-bit PCM)
        return min(1.0, energy / 8000.0)

    def push(self, audio: list[int]):
        """输入音频数据"""
        if not self.initialized:
            return

        self.src_buffer.extend(audio)
        self.buffer.extend(audio)

        processed = 0
        for pos in range(0, len(self.buffer) - HOP_SIZE + 1, HOP_SIZE):
            processed = pos + HOP_SIZE
            frame = self.buffer[pos:pos + HOP_SIZE]
            chunk_offset_s = (self.buffer_offset + pos) / VAD_SAMPLE_RATE
            self._process_chunk(chunk_offset_s, frame)

        if processed > 0:
            self.buffer = self.buffer[processed:]
            self.buffer_offset += processed

    def flush(self):
        """处理剩余数据"""
        if not self.active:
            return
        audio = self.src_buffer[:]
        if len(audio) > VAD_SAMPLE_RATE * 0.2:
            start_s = self.src_buffer_offset / VAD_SAMPLE_RATE
            end_s = start_s + len(audio) / VAD_SAMPLE_RATE
            self.on_segment({"audio": audio, "startS": start_s, "endS": end_s})
        if self.on_active_change:
            self.on_active_change(False)
        self._reset()

    def destroy(self):
        """释放资源"""
        self.initialized = False
        self.buffer = []
        self.src_buffer = []

    def _reset(self):
        self.active = False
        self.sum_positive_s = 0.0
        self.silence_start_s = None
        self.src_buffer = []
        self.src_buffer_offset = self.buffer_offset

    def _process_frame(self, frame: list[int]) -> float:
        """处理一帧返回概率"""
        return self._energy_vad(frame)

    def _process_chunk(self, chunk_offset_s: float, frame: list[int]):
        """处理一块音频数据"""
        prob = self._process_frame(frame)
        hop_s = HOP_SIZE / VAD_SAMPLE_RATE

        if not self.active:
            if prob >= self.start_threshold:
                self.active = True
                self.active_start_s = chunk_offset_s
                self.sum_positive_s = hop_s
                if self.on_active_change:
                    self.on_active_change(True)
            else:
                new_src_offset = max(0, int((chunk_offset_s - self.pad_start_s) * VAD_SAMPLE_RATE))
                cut_pos = new_src_offset - self.src_buffer_offset
                if cut_pos > 0:
                    self.src_buffer = self.src_buffer[cut_pos:]
                    self.src_buffer_offset = new_src_offset
            return

        if prob >= self.end_threshold:
            self.silence_start_s = None
            self.sum_positive_s += hop_s
        elif self.silence_start_s is None:
            self.silence_start_s = chunk_offset_s

        should_cut = (
            (self.silence_start_s is not None and chunk_offset_s - self.silence_start_s >= self.min_silence_s)
            or (chunk_offset_s - self.active_start_s >= self.max_segment_s)
        )

        if should_cut:
            cut_src_pos = int(chunk_offset_s * VAD_SAMPLE_RATE) - self.src_buffer_offset
            audio = self.src_buffer[:cut_src_pos]
            if len(audio) > VAD_SAMPLE_RATE * 0.2:
                start_s = self.src_buffer_offset / VAD_SAMPLE_RATE
                end_s = start_s + len(audio) / VAD_SAMPLE_RATE
                self.on_segment({"audio": audio, "startS": start_s, "endS": end_s})
            self.src_buffer = self.src_buffer[cut_src_pos:]
            self.src_buffer_offset += cut_src_pos
            self.active = False
            self.sum_positive_s = 0.0
            self.silence_start_s = None
            if self.on_active_change:
                self.on_active_change(False)
