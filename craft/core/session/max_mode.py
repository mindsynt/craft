"""Max mode — ported from max-mode.ts.

Runs N parallel propose-only candidates, judges the best one, and replays
it through the processor. Simplified for Craft.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from craft.core.session.processor import (
    ProcessorResult,
    ProposedToolCall,
    ReplayInput,
    TextNgramMonitor,
)

DEFAULT_CANDIDATES = 5
MAX_MODE_AGENT = "max"


@dataclass
class Candidate:
    index: int = 0
    reasoning: str = ""
    reasoning_metadata: dict | None = None
    text: str = ""
    text_metadata: dict | None = None
    tool_calls: list[ProposedToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Any = None
    provider_metadata: dict | None = None


@dataclass
class MaxStepInput:
    handle: Any = None  # Processor handle
    user: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    system: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    tools: dict[str, Any] = field(default_factory=dict)
    candidates: int = DEFAULT_CANDIDATES


JUDGE_SYSTEM = (
    "You are a judge selecting the single best next step for a coding agent. "
    "You will see several independent candidate drafts for the SAME step. Each candidate contains "
    "its reasoning, its message text, and the tool calls it proposes to make next. "
    "Pick the ONE candidate that has the most correct, grounded, and useful next step. "
    "Prefer candidates whose reasoning is sound and whose proposed tool calls are appropriate and safe. "
    "Respond with ONLY the integer index of the winning candidate (e.g. `2`). No other text."
)


def render_candidate(c: Candidate, label: int) -> str:
    """Render a candidate compactly for the judge."""
    tools_str = (
        "(no tool calls — final answer / text only)"
        if not c.tool_calls
        else "\n".join(
            f"  - {t.tool_name}({t.input})" for t in c.tool_calls
        )
    )
    reasoning = c.reasoning.strip() or "(no reasoning emitted)"
    text = c.text.strip() or "(no text emitted)"
    return (
        f"### Candidate {label}\n"
        f"Reasoning:\n{reasoning}\n"
        f"Message:\n{text}\n"
        f"Proposed tool calls:\n{tools_str}"
    )


def parse_judge_index(out: str, count: int) -> int:
    """Parse the judge's reply into a valid candidate index."""
    import re
    m = re.search(r"\d+", out)
    if not m:
        return 0
    try:
        picked = int(m.group(0))
    except ValueError:
        return 0
    if picked < 0 or picked >= count:
        return 0
    return picked
