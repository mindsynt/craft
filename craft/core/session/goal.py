"""Session goal system — ported from goal.ts.

Per-session stop-condition goal: once a goal is set, the main loop
refuses to stop until an independent judge decides the condition is satisfied.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Goal:
    condition: str
    react: int = 0  # Number of judge-driven re-entries


@dataclass
class Verdict:
    ok: bool = False
    impossible: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        d: dict = {"ok": self.ok, "reason": self.reason}
        if self.impossible:
            d["impossible"] = True
        return d


class GoalManager:
    """In-memory session goal manager."""

    def __init__(self):
        self._goals: dict[str, Goal] = {}
        self._last_verdicts: dict[str, dict] = {}

    def set(self, session_id: str, condition: str) -> None:
        self._goals[session_id] = Goal(condition=condition, react=0)

    def get(self, session_id: str) -> Goal | None:
        return self._goals.get(session_id)

    def clear(self, session_id: str) -> None:
        self._goals.pop(session_id, None)
        self._last_verdicts.pop(session_id, None)

    def bump_react(self, session_id: str) -> int:
        goal = self._goals.get(session_id)
        if not goal:
            return 0
        goal.react += 1
        return goal.react

    def record_verdict(self, session_id: str, verdict: Verdict, attempt: int = 0,
                       message_id: str | None = None, error: bool = False) -> None:
        self._last_verdicts[session_id] = {
            "verdict": verdict.to_dict(),
            "attempt": attempt,
            "message_id": message_id,
            "error": error,
        }

    def get_last_verdict(self, session_id: str) -> dict | None:
        return self._last_verdicts.get(session_id)

    @property
    def goals(self) -> dict[str, Goal]:
        return dict(self._goals)


goal_manager = GoalManager()

# Judge system prompt
JUDGE_SYSTEM = """You are evaluating a stop-condition hook in Craft. Read the conversation transcript carefully, then judge whether the user-provided condition is satisfied.

Your response must be a JSON object with one of these shapes:
- {"ok": true, "reason": "<quote evidence from the transcript that satisfies the condition>"}
- {"ok": false, "reason": "<quote what is missing or what blocks the condition>"}
- {"ok": false, "impossible": true, "reason": "<explain why the condition can never be satisfied>"}

Always include a "reason" field, quoting specific text from the transcript whenever possible. If the transcript does not contain clear evidence that the condition is satisfied, return {"ok": false, "reason": "insufficient evidence in transcript"}.
"""


def judge_user_prompt(condition: str) -> str:
    return (
        f"Based on the conversation transcript above, has the following stopping condition been satisfied? "
        f"Answer based on transcript evidence only.\n\nCondition: {condition}"
    )
