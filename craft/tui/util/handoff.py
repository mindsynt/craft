"""
任务交接 — 移植自 util/handoff.ts

检测 "try-best" 循环触发交接，确定交接目标 (codex/claude)。
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

HandoffTarget = Literal["codex", "claude"]


def detection_from_part(part: dict) -> Optional[dict]:
    """从消息 part 中提取交接检测信息"""
    if part.get("type") != "text":
        return None
    origin = (part.get("metadata") or {}).get("origin")
    if not isinstance(origin, dict):
        return None
    if origin.get("kind") != "try_best":
        return None
    provider_id = origin.get("providerID")
    model_id = origin.get("modelID")
    if not isinstance(provider_id, str) or not isinstance(model_id, str):
        return None

    incident = origin.get("incident")
    if not isinstance(incident, dict):
        return None
    evidence = incident.get("evidence")
    if not isinstance(evidence, dict):
        return None

    reason = incident.get("reason")
    if reason not in ("edit_repeat", "bash_retry", "action_streak"):
        return None
    tool = evidence.get("tool")
    count = evidence.get("count")
    if not isinstance(tool, str) or not isinstance(count, (int, float)):
        return None

    result = {
        "sessionID": part.get("sessionID", ""),
        "providerID": provider_id,
        "modelID": model_id,
        "reason": reason,
        "evidence": {
            "tool": tool,
            "count": int(count),
        },
    }
    if isinstance(evidence.get("path"), str):
        result["evidence"]["path"] = evidence["path"]
    if isinstance(evidence.get("command"), str):
        result["evidence"]["command"] = evidence["command"]
    if isinstance(evidence.get("similarity"), (int, float)):
        result["evidence"]["similarity"] = evidence["similarity"]
    action = evidence.get("action")
    if action in ("edit", "verify"):
        result["evidence"]["action"] = action
    return result


def handoff_targets(provider_id: str, model_id: str) -> list[HandoffTarget]:
    """根据当前 provider/model 决定交接目标"""
    current = f"{provider_id}/{model_id}".lower()
    codex = provider_id.lower() == "openai" or bool(re.search(r"(?:gpt|codex)", current))
    claude = bool(re.search(r"(?:anthropic|claude)", current))
    if codex:
        return ["claude"]
    if claude:
        return ["codex"]
    return ["codex", "claude"]


def format_harness_reminder(target: HandoffTarget, detail: str) -> str:
    """生成系统提示，指导 LLM 转到指定 harness"""
    skill = "codex" if target == "codex" else "claude-code"
    harness = "Codex CLI" if target == "codex" else "Claude Code CLI"
    return "\n".join([
        "<system-reminder>",
        f"Try-best loop detection paused the previous turn: {detail}",
        f"The user explicitly selected and authorized the {harness} harness to take over the unfinished work.",
        f"You MUST load and follow the `{skill}` skill now and invoke {harness} as the primary executor.",
        f"The selected {harness} must perform the investigation and implementation. Do not substitute.",
        "Give the selected harness the complete user goal, relevant workspace state, the failed approach.",
        f"Stay in this CLI and supervise {harness} until it completes or reaches a concrete blocker.",
        "Inspect the harness result and workspace changes, ensure its validation is complete.",
        "</system-reminder>",
    ])
