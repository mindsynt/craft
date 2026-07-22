"""问题路由 — 移植自 routes/instance/question.ts

问题请求列表、回复、拒绝、never-ask 状态。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class QuestionRoutes:
    """问题路由处理器

    对应 TS QuestionRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /question/
        
        列出待处理问题。
        """
        # TODO: 接入 Question.Service
        return []

    @staticmethod
    async def never_ask(request: Any) -> Any:
        """GET /question/never-ask
        
        获取 never-ask 状态。
        """
        # TODO: 接入 Question.Service
        return False

    @staticmethod
    async def set_never_ask(request: Any) -> Any:
        """POST /question/never-ask
        
        设置 never-ask 状态。
        """
        # TODO: 接入 Question.Service
        return False

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /question/:requestID/reply
        
        回答问题。
        """
        # TODO: 接入 Question.Service
        return True

    @staticmethod
    async def reject(request: Any, request_id: str) -> Any:
        """POST /question/:requestID/reject
        
        拒绝问题。
        """
        # TODO: 接入 Question.Service
        return True
