"""投影器初始化 — 移植自 projectors.ts

初始化 SyncEvent 的投影器，处理会话更新事件转换。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_projectors():
    """初始化事件投影器

    对应 TS initProjectors()
    注册 SyncEvent 投影器，将会话更新事件转换为适当的格式。
    """
    logger.info("Projectors initialized")
    # TODO: 接入实际 SyncEvent 和投影注册
