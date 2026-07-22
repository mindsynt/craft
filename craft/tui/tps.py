"""
TPS — 移植自 feature-plugins/sidebar/tps.ts

Token 每秒计算：流式 TPS 和已完成 TPS。
"""

from __future__ import annotations

import math

MIN_STREAMING_ELAPSED_SEC = 0.5
MIN_COMPLETED_ELAPSED_SEC = 0.001


def estimate_tokens(text: str) -> int:
    """简易 token 估算（约 4 字符/token）"""
    return max(1, len(text) // 4)


def streaming_tps(combined_text: str, started_at: float, now: float) -> float | None:
    """计算流式 TPS"""
    tokens = estimate_tokens(combined_text)
    if tokens == 0:
        return None
    elapsed_sec = (now - started_at)
    if elapsed_sec < MIN_STREAMING_ELAPSED_SEC:
        return None
    return tokens / elapsed_sec


def completed_tps(
    output_tokens: int,
    reasoning_tokens: int,
    started_at: float,
    completed_at: float,
) -> float | None:
    """计算已完成 TPS"""
    tokens = output_tokens + reasoning_tokens
    if tokens == 0:
        return None
    elapsed_sec = (completed_at - started_at)
    if elapsed_sec < MIN_COMPLETED_ELAPSED_SEC:
        return None
    return tokens / elapsed_sec


def format_tps(tps: float | None) -> str | None:
    """格式化 TPS 显示"""
    if tps is None:
        return None
    if tps < 1:
        return "<1 t/s"
    return f"{round(tps)} t/s"
