"""Provider configuration dataclasses"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass
class OpenAICompatibleProviderOptions:
    user: str | None = None
    reasoning_effort: str | None = None
    text_verbosity: str | None = None
    thinking_budget: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> OpenAICompatibleProviderOptions:
        if not d:
            return cls()
        return cls(
            user=d.get("user"),
            reasoning_effort=d.get("reasoningEffort") or d.get("reasoning_effort"),
            text_verbosity=d.get("textVerbosity") or d.get("text_verbosity"),
            thinking_budget=d.get("thinking_budget") or d.get("thinkingBudget"),
        )


class ProviderSettings(TypedDict, total=False):
    api_key: str
    base_url: str
    organization: str
    project: str
    supports_structured_outputs: bool
    max_tokens: int
    temperature: float
    top_p: float
    reasoning_effort: str
    thinking_budget: int
