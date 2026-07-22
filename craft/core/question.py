"""
提问系统 — 移植自 packages/opencode/src/question/
用户交互、多选问答、异步回复、事件驱动
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from craft.core.bus import define_event, bus
from craft.core.id import ascending as id_ascending


# ── Schema ──────────────────────────────────────────────────

@dataclass
class Option:
    """选项 — 对应 TS Question.Option"""
    label: str
    description: str = ""


@dataclass
class QuestionInfo:
    """问题信息 — 对应 TS Question.Info"""
    question: str
    header: str
    options: list[Option]
    multiple: bool = False
    custom: bool = True
    key: str | None = None
    params: dict[str, str] | None = None


@dataclass
class QuestionPrompt:
    """问题提示 — 对应 TS Question.Prompt"""
    question: str
    header: str
    options: list[Option]
    multiple: bool = False


@dataclass
class QuestionTool:
    """问题工具引用 — 对应 TS Question.Tool"""
    messageID: str
    callID: str


@dataclass
class QuestionRequest:
    """问题请求 — 对应 TS Question.Request"""
    id: str
    sessionID: str
    questions: list[QuestionInfo]
    tool: QuestionTool | None = None


# ── 事件 ────────────────────────────────────────────────────

QuestionAsked = define_event("question.asked", {
    "id": str,
    "sessionID": str,
    "questions": list,
    "tool": dict,
})

QuestionReplied = define_event("question.replied", {
    "sessionID": str,
    "requestID": str,
    "answers": list,
})

QuestionRejected = define_event("question.rejected", {
    "sessionID": str,
    "requestID": str,
})


# ── 错误 ────────────────────────────────────────────────────

class QuestionError(Exception):
    pass


class RejectedError(QuestionError):
    """用户拒绝了问题"""
    def __init__(self):
        super().__init__("The user dismissed this question")


# ── 问答系统 ────────────────────────────────────────────────

Answer = list[str]  # 每个问题的答案是一个标签数组


class QuestionService:
    """问答服务 — 对应 TS Question.Service

    支持:
    - ask: 异步提问，等待回复
    - reply: 回复问题
    - reject: 拒绝问题
    - list: 列出待回复的问题
    """

    def __init__(self):
        self._pending: dict[str, dict] = {}  # question_id -> {request, future}
        self._never_ask = False

    def ask(self, sessionID: str, questions: list[QuestionInfo],
            tool: QuestionTool | None = None) -> asyncio.Future:
        """异步提问

        Returns: Future 会在回复时 resolve，拒绝时 raise RejectedError
        """
        qid = id_ascending("question")
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        request = QuestionRequest(
            id=qid,
            sessionID=sessionID,
            questions=questions,
            tool=tool,
        )

        self._pending[qid] = {"request": request, "future": future}

        # 通过总线发布问题事件
        bus.publish(QuestionAsked["type"], {
            "id": qid,
            "sessionID": sessionID,
            "questions": [q.__dict__ for q in questions],
            "tool": tool.__dict__ if tool else {},
        })

        return future

    def reply(self, requestID: str, answers: list[Answer]):
        """回复问题 — 对应 TS Question.reply"""
        entry = self._pending.get(requestID)
        if not entry:
            return

        del self._pending[requestID]
        request = entry["request"]
        future = entry["future"]

        bus.publish(QuestionReplied["type"], {
            "sessionID": request.sessionID,
            "requestID": requestID,
            "answers": [list(a) for a in answers],
        })

        if not future.done():
            future.set_result(answers)

    def reject(self, requestID: str):
        """拒绝问题 — 对应 TS Question.reject"""
        entry = self._pending.get(requestID)
        if not entry:
            return

        del self._pending[requestID]
        request = entry["request"]
        future = entry["future"]

        bus.publish(QuestionRejected["type"], {
            "sessionID": request.sessionID,
            "requestID": requestID,
        })

        if not future.done():
            future.set_exception(RejectedError())

    def list_pending(self) -> list[QuestionRequest]:
        """列出待回复的问题"""
        return [entry["request"] for entry in self._pending.values()]

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def never_ask(self) -> bool:
        return self._never_ask

    @never_ask.setter
    def never_ask(self, enabled: bool):
        self._never_ask = enabled


question_service = QuestionService()


# ── 便捷函数 ────────────────────────────────────────────────

class Question:
    """同步 Question 封装（用于 CLI 场景）"""

    def __init__(self, text: str, type: str = "text", default: Any = None,
                 choices: list[str] | None = None):
        self.text = text
        self.type = type
        self.default = default
        self.choices = choices or []

    async def ask(self) -> Any:
        if self.choices:
            print(f"{self.text} ({', '.join(self.choices)})")
            val = input(f"[{self.default or ''}]: ").strip()
        else:
            val = input(f"{self.text}: ").strip()
        if not val and self.default is not None:
            return self.default
        if self.type == "int":
            try:
                return int(val)
            except ValueError:
                return self.default
        if self.type == "bool":
            return val.lower() in ("y", "yes", "true", "1")
        return val

    async def confirm(self) -> bool:
        val = input(f"{self.text} [Y/n]: ").strip().lower()
        return not val or val in ("y", "yes")


def ask(text: str, default: Any = None) -> Question:
    return Question(text, default=default)


def confirm(text: str) -> Question:
    return Question(text, type="bool")


def select(text: str, choices: list[str]) -> Question:
    return Question(text, type="select", choices=choices)
