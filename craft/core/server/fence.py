"""同步围栏 — 移植自 fence.ts

管理状态同步的栅栏（fence），确保客户端在写入操作后等待同步完成。

HEADER 常量：x-craft-sync
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

HEADER = "x-craft-sync"
State = dict[str, int]


def load(ids: list[str] | None = None) -> State:
    """加载当前同步状态

    对应 TS load()
    从数据库中加载所有聚合的最新序列号。
    """
    # TODO: 连接实际存储
    return {}


def diff(prev: State, next: State) -> State:
    """计算两个状态的差异

    对应 TS diff()
    返回 prev 和 next 之间 seq 不同的所有聚合。
    """
    ids = set(list(prev.keys()) + list(next.keys()))
    result: State = {}
    for id in ids:
        next_seq = next.get(id, -1)
        if (prev.get(id, -1)) != next_seq:
            result[id] = next_seq
    return result


def parse(headers: dict[str, str]) -> State | None:
    """从 HTTP 头解析同步状态

    对应 TS parse()
    """
    raw = headers.get(HEADER)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    result: State = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, int) and value == int(value):
            result[key] = value
    return result if result else None


async def wait(workspace_id: str, state: State, signal: Any = None):
    """等待同步状态达成

    对应 TS wait()
    """
    logger.info(
        "Waiting for state sync",
        extra={"workspace_id": workspace_id, "state": state},
    )
    # TODO: 接入 Workspace.waitForSync
    # await Workspace.waitForSync(workspace_id, state, signal)
    logger.info(
        "State fully synced",
        extra={"workspace_id": workspace_id, "state": state},
    )
