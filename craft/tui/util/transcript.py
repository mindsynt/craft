"""
转录 — 移植自 util/transcript.ts

将会话消息格式化为 Markdown 转录文本。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional


def format_transcript(
    session: dict,
    messages: list[dict],
    options: dict,
) -> str:
    """将会话和消息格式化为 Markdown 转录"""
    title = session.get("title", "")
    session_id = session.get("id", "")
    created = session.get("time", {}).get("created", 0)
    updated = session.get("time", {}).get("updated", 0)

    lines: list[str] = [
        f"# {title}\n",
        f"**Session ID:** {session_id}",
        f"**Created:** {datetime.fromtimestamp(created / 1000).strftime('%c') if created else 'N/A'}",
        f"**Updated:** {datetime.fromtimestamp(updated / 1000).strftime('%c') if updated else 'N/A'}",
        "",
        "---\n",
    ]

    for msg in messages:
        info = msg.get("info", {})
        parts = msg.get("parts", [])
        lines.append(format_message(info, parts, options))
        lines.append("---\n")

    return "\n".join(lines)


def format_message(
    msg: dict,
    parts: list[dict],
    options: dict,
    providers: Any = None,
) -> str:
    """格式化单条消息"""
    result = ""

    if msg.get("role") == "user":
        result += "## User\n\n"
    else:
        result += format_assistant_header(msg, options.get("assistantMetadata", False), providers or options.get("providers"))

    for part in parts:
        result += format_part(part, options)

    return result


def format_assistant_header(
    msg: dict,
    include_metadata: bool,
    providers: Any = None,
) -> str:
    """格式化 Assistant 消息头部"""
    if not include_metadata:
        return "## Assistant\n\n"

    time_info = msg.get("time", {})
    completed = time_info.get("completed")
    created = time_info.get("created")
    duration = f"{(completed - created) / 1000:.1f}s" if completed and created else ""

    agent = msg.get("agent", "assistant")
    model_name = msg.get("modelID", "unknown")
    dur_str = f" · {duration}" if duration else ""

    return f"## Assistant ({agent} · {model_name}{dur_str})\n\n"


def format_part(part: dict, options: dict) -> str:
    """格式化消息部分"""
    part_type = part.get("type", "")

    if part_type == "text" and not part.get("synthetic"):
        return f"{part.get('text', '')}\n\n"

    if part_type == "text" and part.get("synthetic"):
        metadata = part.get("metadata", {})
        origin = metadata.get("origin", {}) if isinstance(metadata, dict) else {}
        if isinstance(origin, dict) and origin.get("kind") == "cron" and origin.get("firedAt"):
            body = part.get("text", "")
            import re as _re
            body = _re.sub(r"^\[cron fire @ [^\]]+]\s*", "", body)
            return f"_🕒 cron fire @ {origin['firedAt']} — {body}_\n\n"

    if part_type == "reasoning":
        if options.get("thinking"):
            return f"_Thinking:_\n\n{part.get('text', '')}\n\n"
        return ""

    if part_type == "tool":
        result = f"**Tool: {part.get('tool', '')}**\n"
        if options.get("toolDetails"):
            state = part.get("state", {})
            if state.get("input"):
                result += f"\n**Input:**\n```json\n{json.dumps(state['input'], indent=2)}\n```\n"
            if state.get("status") == "completed" and state.get("output"):
                result += f"\n**Output:**\n```\n{state['output']}\n```\n"
            if state.get("status") == "error" and state.get("error"):
                result += f"\n**Error:**\n```\n{state['error']}\n```\n"
        result += "\n"
        return result

    return ""
