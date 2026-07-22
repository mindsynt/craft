"""Session processor — ported from processor.ts.

Handles LLM streaming events, tool call lifecycle, and text n-gram detection.
Simplified for the Craft Python environment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ProcessorResult(str, Enum):
    OVERFLOW = "overflow"
    STOP = "stop"
    CONTINUE = "continue"
    TEXT_REPEAT = "text-repeat"


@dataclass
class ProposedToolCall:
    tool_call_id: str = ""
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayInput:
    reasoning: str = ""
    reasoning_metadata: dict[str, Any] | None = None
    text: str = ""
    text_metadata: dict[str, Any] | None = None
    tool_calls: list[ProposedToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Any = None
    provider_metadata: dict[str, Any] | None = None
    tools: dict[str, Any] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    selection: dict | None = None  # {'winner': int, 'total': int}
    thinking_ms: int | None = None
    overhead: dict | None = None  # {'cost': float, 'tokensIn': int, 'tokensOut': int}


@dataclass
class AgentMetrics:
    tokens_in: int = 0
    tokens_out: int = 0
    files_changed: int = 0


class TextNgramMonitor:
    """Monitor for repeated text n-grams to detect text loops."""

    def __init__(self, min_ngram: int = 50, max_ngram: int = 100, threshold: int = 5):
        self.min_ngram = min_ngram
        self.max_ngram = max_ngram
        self.threshold = threshold
        self._ngrams: dict[str, int] = {}
        self._buffer: list[str] = []
        self._repeated = False

    def append(self, text: str) -> bool:
        """Append text and check for n-gram repeats."""
        if self._repeated:
            return True
        self._buffer.append(text)
        combined = "".join(self._buffer[-20:])
        for n in range(self.min_ngram, min(self.max_ngram, len(combined)) + 1):
            for i in range(len(combined) - n + 1):
                ngram = combined[i : i + n]
                if len(ngram.strip()) < n * 0.5:
                    continue
                count = self._ngrams.get(ngram, 0) + 1
                self._ngrams[ngram] = count
                if count >= self.threshold:
                    self._repeated = True
                    return True
        return False

    @property
    def repeated(self) -> bool:
        return self._repeated

    def reset(self) -> None:
        self._ngrams.clear()
        self._buffer.clear()
        self._repeated = False


class ProcessorContext:
    """Context object for processor execution."""

    def __init__(
        self,
        session_id: str = "",
        message_id: str = "",
        model: dict[str, Any] | None = None,
    ):
        self.session_id = session_id
        self.message_id = message_id
        self.model = model or {}
        self.should_break = False
        self.blocked = False
        self.needs_overflow = False
        self.current_text: dict | None = None
        self.reasoning_map: dict[str, dict] = {}
        self.step_started_at: float | None = None
        self.first_token_at: float | None = None
        self.text_ngram_monitor: TextNgramMonitor | None = None
        self.text_ngram_repeat = False
        self.tool_calls: dict[str, dict] = {}
        self.agent_metrics: AgentMetrics = field(default_factory=AgentMetrics)


def compute_diff(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute file diffs from step-start/step-finish snapshots."""
    from_snapshot: str | None = None
    to_snapshot: str | None = None
    for item in messages:
        info = item.get("info", item)
        parts = item.get("parts", [])
        if from_snapshot is None:
            for part in parts:
                if part.get("type") == "step-start" and part.get("snapshot"):
                    from_snapshot = part["snapshot"]
                    break
        for part in parts:
            if part.get("type") == "step-finish" and part.get("snapshot"):
                to_snapshot = part["snapshot"]
    if from_snapshot and to_snapshot:
        # Simplified diff computation
        return [{"file": "snapshot", "additions": 0, "deletions": 0}]
    return []
