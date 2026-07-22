"""
上下文压缩 — 移植自 MiMo-Code compaction 系统
长对话自动压缩、历史缩减、Token 预算管理
"""

from __future__ import annotations

import json
import time
from typing import Any

COMPACTION_THRESHOLD = 8000  # token
RESERVED_TOKENS = 2000
TAIL_TURNS = 2


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def should_compact(messages: list[dict]) -> bool:
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return total > COMPACTION_THRESHOLD


def compact_messages(messages: list[dict], max_tokens: int = 6000) -> list[dict]:
    """压缩消息列表：保留系统提示 + 最近 N 轮 + 摘要中间内容"""
    if not should_compact(messages):
        return messages
    
    result = []
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    
    # 保留系统提示
    result.extend(system_msgs)
    
    # 保留最近 TAIL_TURNS 轮
    tail = non_system[-TAIL_TURNS * 2:] if len(non_system) > TAIL_TURNS * 2 else []
    middle = non_system[:len(non_system) - len(tail)] if tail else []
    
    if middle:
        summary = "".join(
            f"{'用户' if m.get('role')=='user' else '助手'}: {m.get('content','')[:100]}\n"
            for m in middle
        )
        result.append({
            "role": "system",
            "content": f"[上下文压缩] 以下为压缩的早期对话摘要:\n{summary[:2000]}",
        })
    
    result.extend(tail)
    return result


def get_token_budget(messages: list[dict]) -> dict:
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return {
        "total": total,
        "available": max(COMPACTION_THRESHOLD - total - RESERVED_TOKENS, 0),
        "needs_compact": total > COMPACTION_THRESHOLD,
    }
