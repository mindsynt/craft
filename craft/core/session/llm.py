"""LLM integration — ported from llm.ts.

Simplified LLM streaming and system array building for Craft.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from craft.core.session.retry import is_retryable_transient_error

OUTPUT_TOKEN_MAX = 8192


def is_transient_capacity_error(error: Any) -> bool:
    """Legacy wrapper — use is_retryable_transient_error from retry."""
    return is_retryable_transient_error(error)


def persistent_retry_schedule(attempt: int) -> float:
    """Exponential backoff schedule for persistent retries."""
    import math
    delay = 500 * (2 ** (attempt - 1))  # 500ms base
    return min(delay, 5 * 60 * 1000)  # cap at 5 minutes


class LLMService:
    """Simplified LLM service for Craft."""

    def __init__(self):
        pass

    def build_system_array(
        self,
        agent: dict[str, Any],
        model: dict[str, Any],
        system: list[str],
        user: dict[str, Any],
    ) -> list[str]:
        """Build the system prompt array for an LLM request."""
        from craft.core.session.system import provider as get_provider_prompt

        parts: list[str] = []

        # Agent prompt or provider prompt
        agent_prompt = agent.get("prompt")
        if agent_prompt:
            parts.append(agent_prompt)
        else:
            provider_prompts = get_provider_prompt(model)
            parts.extend(provider_prompts)

        # Custom system prompts
        parts.extend(s for s in system if s)

        # User system
        user_system = user.get("system", "")
        if user_system:
            parts.append(user_system)

        # Collapse to single message if multiple
        combined = "\n\n".join(p for p in parts if p)
        return [combined] if combined else []


llm_service = LLMService()
