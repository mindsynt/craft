"""
ID 生成器 — 移植自 packages/opencode/src/id/id.ts
生成单调递增/递减的带前缀唯一 ID（类似 KSUID/ULID）
"""

from __future__ import annotations

import os
import time
from typing import Literal


# 前缀映射 (prefix -> short_prefix)
PREFIXES: dict[str, str] = {
    "event": "evt",
    "session": "ses",
    "message": "msg",
    "permission": "per",
    "question": "que",
    "user": "usr",
    "part": "prt",
    "pty": "pty",
    "tool": "tool",
    "workspace": "wrk",
    "entry": "ent",
    "workflow": "wf",
}

ID_LENGTH = 26  # 总长度: prefix + '_' + 6字节时间戳hex + 随机字符

BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# 单调 ID 生成状态
_last_timestamp: int = 0
_counter: int = 0


def _random_base62(length: int) -> str:
    """生成指定长度的 base62 随机字符串"""
    bytes_data = os.urandom(length)
    result = "".join(BASE62_CHARS[b % 62] for b in bytes_data)
    return result


def _generate(prefix: str, direction: Literal["ascending", "descending"], timestamp: int | None = None) -> str:
    """生成带前缀和方向的时间戳 ID

    Args:
        prefix: ID 前缀（如 "ses", "msg"）
        direction: "ascending" — 时间正序；"descending" — 时间倒序
        timestamp: 可选时间戳 (ms)
    """
    global _last_timestamp, _counter

    current_ts = timestamp if timestamp is not None else int(time.time() * 1000)

    if current_ts != _last_timestamp:
        _last_timestamp = current_ts
        _counter = 0
    _counter += 1

    now = (current_ts * 0x1000) + _counter
    if direction == "descending":
        now = ~now & ((1 << 48) - 1)  # 取反保持48位

    # 编码为6字节hex
    time_hex = format(now, "012x")[:12]
    random_part = _random_base62(ID_LENGTH - 12)
    return f"{prefix}_{time_hex}{random_part}"


def schema(name: str) -> str:
    """返回某类型的 ID 前缀常量（用于 schema 验证）"""
    return PREFIXES.get(name, name[:3])


def ascending(prefix_key: str, given: str | None = None) -> str:
    """生成单调递增 ID

    Args:
        prefix_key: 类型名（如 "session", "message"）
        given: 如果提供且格式正确，直接返回（用于测试/重放）
    """
    if given is not None:
        _validate_given(given, prefix_key)
        return given
    return _generate(PREFIXES[prefix_key], "ascending")


def descending(prefix_key: str, given: str | None = None) -> str:
    """生成单调递减 ID（用于倒序排序）"""
    if given is not None:
        _validate_given(given, prefix_key)
        return given
    return _generate(PREFIXES[prefix_key], "descending")


def create(prefix: str, direction: Literal["ascending", "descending"], timestamp: int | None = None) -> str:
    """底层创建函数 — 直接使用原始前缀字符串"""
    return _generate(prefix, direction, timestamp)


def timestamp_from_id(id_str: str) -> int:
    """从递增 ID 中提取时间戳（不支持递减 ID）"""
    parts = id_str.split("_")
    if len(parts) < 2:
        raise ValueError(f"Invalid ID format: {id_str}")
    prefix = parts[0]
    hex_str = id_str[len(prefix) + 1: len(prefix) + 13]
    encoded = int(hex_str, 16)
    return encoded // 0x1000


def _validate_given(given: str, prefix_key: str):
    """验证给定的 ID 是否以正确的前缀开头"""
    expected_prefix = PREFIXES.get(prefix_key, prefix_key[:3])
    if not given.startswith(expected_prefix):
        raise ValueError(f"ID {given} does not start with {expected_prefix}")
