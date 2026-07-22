"""Trajectory serialization — ported from trajectory.ts.

Serializes session messages into a wire format suitable for plugins and
external consumers.
"""

from __future__ import annotations

from typing import Any


def file_url_summary(url: str, mime: str, filename: str | None = None) -> str:
    """Replace data: URLs with a compact summary tag."""
    if not url.startswith("data:"):
        return url
    parts = [f"[data-url:{mime}"]
    if filename:
        parts.append(f":{filename}")
    parts.append("]")
    return "".join(parts)


def serialize_file_part(part: dict[str, Any]) -> dict[str, Any]:
    """Serialize a file part for the wire format."""
    return {
        **part,
        "url": file_url_summary(
            part.get("url", ""),
            part.get("mime", part.get("mediaType", "")),
            part.get("filename"),
        ),
    }


def sanitize_tool_state(state: dict[str, Any]) -> dict[str, Any]:
    """Strip data: URLs from tool result attachments."""
    if state.get("attachments") and len(state["attachments"]) > 0:
        return {
            **state,
            "attachments": [serialize_file_part(a) for a in state["attachments"]],
        }
    return state


def serialize_part(part: dict[str, Any]) -> dict[str, Any]:
    """Serialize a part for the trajectory wire format."""
    if part.get("type") == "file":
        return serialize_file_part(part)
    if part.get("type") == "tool":
        return {**part, "state": sanitize_tool_state(part.get("state", {}))}
    return part


def user_query_text(parts: list[dict[str, Any]]) -> str:
    """Concatenate non-synthetic, non-ignored user text parts."""
    texts: list[str] = []
    for p in parts:
        if p.get("type") == "text" and not p.get("synthetic") and not p.get("ignored"):
            texts.append(p.get("text", ""))
    return "\n".join(texts)


def assistant_final_text(message: dict[str, Any], parts: list[dict[str, Any]]) -> str | None:
    """Last non-synthetic assistant text, or stringified structured output."""
    if message.get("structured") is not None:
        import json
        return json.dumps(message["structured"])
    for p in reversed(parts):
        if p.get("type") == "text" and not p.get("synthetic"):
            return p.get("text")
    return None


def serialize_trajectory_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize a slice of session messages into the wire trajectory format."""
    result: list[dict[str, Any]] = []
    for msg in msgs:
        info = msg.get("info", msg)
        parts = msg.get("parts", [])
        result.append({
            **info,
            "created": info.get("time", {}).get("created", 0),
            "parts": [serialize_part(p) for p in parts],
        })
    return result


def with_assistant_parts(
    msgs: list[dict[str, Any]],
    assistant: dict[str, Any],
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace the assistant entry in a message slice with freshly loaded parts."""
    idx = None
    for i, m in enumerate(msgs):
        info = m.get("info", m)
        if info.get("id") == assistant.get("id"):
            idx = i
            break
    if idx is None:
        return [*msgs, {"info": assistant, "parts": parts}]
    result = list(msgs)
    result[idx] = {"info": assistant, "parts": parts}
    return result


def session_error_text(error: Any) -> str | None:
    """Stringify an assistant error blob."""
    if error is None:
        return None
    if isinstance(error, dict):
        if "message" in error:
            return str(error["message"])
        return None
    if isinstance(error, str):
        return error
    return str(error)
