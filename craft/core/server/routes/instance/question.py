"""问题路由 — 移植自 routes/instance/question.ts

问题请求列表、回复、拒绝、never-ask 状态。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.core.inbox import Inbox

logger = logging.getLogger(__name__)

inbox = Inbox()
_never_ask_enabled = False


class QuestionRoutes:
    """问题路由处理器

    对应 TS QuestionRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /question/

        列出待处理问题。
        """
        items = inbox.list(unread_only=True)
        questions = []
        for item in items:
            if item.get("actionable", False):
                questions.append({
                    "id": item.get("id", ""),
                    "type": item.get("type", "question"),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "source": item.get("source", "system"),
                    "createdAt": item.get("created_at", 0),
                })
        return questions

    @staticmethod
    async def never_ask(request: Any) -> Any:
        """GET /question/never-ask

        获取 never-ask 状态。
        """
        return _never_ask_enabled

    @staticmethod
    async def set_never_ask(request: Any) -> Any:
        """POST /question/never-ask

        设置 never-ask 状态。
        """
        global _never_ask_enabled
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass
        _never_ask_enabled = body.get("enabled", False)
        return _never_ask_enabled

    @staticmethod
    async def reply(request: Any, request_id: str) -> Any:
        """POST /question/:requestID/reply

        回答问题。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        answers = body.get("answers", [])
        inbox.mark_read(request_id)
        logger.info("Question replied", extra={"request_id": request_id, "answers": answers})
        return True

    @staticmethod
    async def reject(request: Any, request_id: str) -> Any:
        """POST /question/:requestID/reject

        拒绝问题。
        """
        inbox.mark_read(request_id)
        logger.info("Question rejected", extra={"request_id": request_id})
        return True
