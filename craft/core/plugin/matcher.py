"""匹配器 — 移植自 matcher.ts"""

from __future__ import annotations

import re
from typing import Any

BUILT_IN_AGENTS = [
    "build",
    "plan",
    "explore",
    "general",
    "title",
    "summary",
    "dream",
    "distill",
    "compaction",
    "main",
    "checkpoint-writer",
]


class ActorMatcher(dict):
    """Actor 匹配器，类似于 TS 的 ActorMatcher 类型"""
    mode: str | None = None
    agent_type: str | list[str] | dict[str, list[str]] | None = None


def matches_actor(
    matcher: dict[str, Any] | None,
    input_data: dict[str, str],
) -> bool:
    """检查输入是否匹配 Actor 匹配器"""
    agent_type = input_data.get("agentType", "")
    is_built_in = agent_type in BUILT_IN_AGENTS

    if matcher is None:
        return not is_built_in

    matcher_mode = matcher.get("mode")
    if matcher_mode and matcher_mode != input_data.get("mode"):
        return False

    at = matcher.get("agentType")
    if at is None:
        return not is_built_in

    if isinstance(at, str):
        if is_built_in:
            return False
        try:
            return bool(re.match(at, agent_type))
        except re.error:
            return False

    if isinstance(at, list):
        return agent_type in at

    if isinstance(at, dict):
        if "excludeOnly" in at:
            return agent_type not in at["excludeOnly"]
        exclude = at.get("exclude", [])
        if agent_type in exclude:
            return False
        include = at.get("include", [])
        return agent_type in include

    return False
