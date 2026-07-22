"""LLM request prefix builder — ported from llm-request-prefix.ts.

Builds the LLM request prefix (system + tools + inherited messages).
"""

from __future__ import annotations

from typing import Any

from craft.core.session.llm import llm_service


def build_llm_request_prefix(
    session_id: str,
    agent: dict[str, Any],
    model: dict[str, Any],
    messages: list[dict[str, Any]],
    additions: list[str],
) -> dict[str, Any]:
    """Build the LLM request prefix.

    Given identical inputs this returns deep-equal output.
    Used by both the parent runLoop and checkpoint writer for consistent
    prefix cache sharing.
    """
    # Convert messages to model format
    inherited_messages = _to_model_messages(messages)

    # Find last user message
    last_user_msg = None
    for m in reversed(messages):
        info = m.get("info", m)
        if info.get("role") == "user":
            last_user_msg = info
            break

    if not last_user_msg:
        raise ValueError("build_llm_request_prefix: no user message in msgs")

    # Build system array
    system = llm_service.build_system_array(
        agent=agent,
        model=model,
        system=additions,
        user=last_user_msg,
    )

    # Resolve tools
    tools = _resolve_tools(model, agent)

    return {
        "system": system,
        "tools": tools,
        "inherited_messages": inherited_messages,
    }


def _to_model_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert session messages to model message format."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        info = msg.get("info", msg)
        parts = msg.get("parts", [])
        role = info.get("role", "user")
        content_parts: list[dict] = []
        for part in parts:
            ptype = part.get("type", "")
            if ptype == "text":
                content_parts.append({"type": "text", "text": part.get("text", "")})
            elif ptype == "tool":
                state = part.get("state", {})
                status = state.get("status", "pending")
                if status == "completed":
                    content_parts.append({
                        "type": "tool_result",
                        "tool_use_id": part.get("call_id", ""),
                        "content": state.get("output", ""),
                    })
                else:
                    content_parts.append({
                        "type": "tool_use",
                        "id": part.get("call_id", ""),
                        "name": part.get("tool", ""),
                        "input": state.get("input", {}),
                    })
            elif ptype == "file":
                content_parts.append({
                    "type": "file",
                    "source": {"type": "base64", "media_type": part.get("mime", ""), "data": ""},
                })
        result.append({"role": role, "content": content_parts, "id": info.get("id", "")})
    return result


def _resolve_tools(
    model: dict[str, Any],
    agent: dict[str, Any],
) -> dict[str, Any]:
    """Resolve tools available for this agent/model combination."""
    # Simplified tool resolution — returns a dict of tool name -> tool info
    tools: dict[str, Any] = {}

    # Common tools available to all agents
    common_tools = [
        "read_file", "write_file", "patch", "search_files",
        "terminal", "web_search", "web_fetch",
    ]

    for name in common_tools:
        tools[name] = {
            "description": f"Tool: {name}",
            "parameters": {"type": "object", "properties": {}},
        }

    return tools
