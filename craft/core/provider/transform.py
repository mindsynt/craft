"""Format conversion — finish reason mapping, response metadata, message conversion"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from craft.core.provider.models import (
    AssistantMessage,
    ContentPart,
    ContentPartImage,
    ContentPartText,
    OpenAIMessage,
    ToolCallPart,
)


# ─────────────────────────────────────────────
# Finish Reason Mapping
# ─────────────────────────────────────────────


def map_openai_finish_reason(
    finish_reason: str | None,
) -> Literal["stop", "length", "content-filter", "tool-calls", "other"]:
    mapping = {
        "stop": "stop",
        "length": "length",
        "content_filter": "content-filter",
        "function_call": "tool-calls",
        "tool_calls": "tool-calls",
    }
    if finish_reason and finish_reason in mapping:
        return mapping[finish_reason]  # type: ignore
    return "other"


def map_openai_responses_finish_reason(
    finish_reason: str | None,
    has_function_call: bool = False,
) -> Literal["stop", "length", "content-filter", "tool-calls", "other"]:
    if finish_reason is None:
        return "tool-calls" if has_function_call else "stop"
    if finish_reason == "max_output_tokens":
        return "length"
    if finish_reason == "content_filter":
        return "content-filter"
    return "tool-calls" if has_function_call else "other"


# ─────────────────────────────────────────────
# Response Metadata
# ─────────────────────────────────────────────


@dataclass
class ResponseMetadata:
    id: str | None = None
    model_id: str | None = None
    timestamp: datetime | None = None


def get_response_metadata(response: dict[str, Any]) -> ResponseMetadata:
    return ResponseMetadata(
        id=response.get("id"),
        model_id=response.get("model"),
        timestamp=datetime.fromtimestamp(response["created"])
        if response.get("created")
        else None,
    )


# ─────────────────────────────────────────────
# Message Conversion
# ─────────────────────────────────────────────


def get_openai_metadata(
    part_or_message: dict[str, Any],
) -> dict[str, Any]:
    provider_options = part_or_message.get("providerOptions", {}) or {}
    copilot = provider_options.get("copilot", {})
    if isinstance(copilot, dict):
        return copilot
    return {}


def convert_to_openai_compatible_chat_messages(
    prompt: list[dict[str, Any]],
) -> list[OpenAIMessage]:
    """Port of convertToOpenAICompatibleChatMessages"""
    messages: list[OpenAIMessage] = []

    for item in prompt:
        role = item.get("role", "")
        content = item.get("content", "")
        # Extract extra metadata from the message level
        metadata = get_openai_metadata(item)

        if role == "system":
            messages.append({
                "role": "system",
                "content": content if isinstance(content, str) else content,
                **metadata,
            })

        elif role == "user":
            # If content is a list of parts
            if isinstance(content, list):
                # Single text part case
                if len(content) == 1 and content[0].get("type") == "text":
                    part_metadata = get_openai_metadata(content[0])
                    messages.append({
                        "role": "user",
                        "content": content[0]["text"],
                        **part_metadata,
                    })
                else:
                    converted_parts: list[ContentPart] = []
                    for part in content:
                        part_metadata = get_openai_metadata(part)
                        ptype = part.get("type")
                        if ptype == "text":
                            t: ContentPartText = {
                                "type": "text",
                                "text": part["text"],
                                **part_metadata,  # type: ignore
                            }
                            converted_parts.append(t)
                        elif ptype == "file":
                            media_type = part.get("mediaType", "")
                            if media_type.startswith("image/"):
                                mtype = (
                                    "image/jpeg"
                                    if media_type == "image/*"
                                    else media_type
                                )
                                data = part.get("data")
                                if isinstance(data, str):
                                    url = data
                                else:
                                    # bytes data
                                    encoded = base64.b64encode(
                                        bytes(data)
                                    ).decode("ascii")
                                    url = f"data:{mtype};base64,{encoded}"
                                img: ContentPartImage = {
                                    "type": "image_url",
                                    "image_url": {"url": url},
                                    **part_metadata,  # type: ignore
                                }
                                converted_parts.append(img)
                            else:
                                raise ValueError(
                                    f"Unsupported file media type: {media_type}"
                                )
                    messages.append({
                        "role": "user",
                        "content": converted_parts,
                        **metadata,
                    })
            else:
                messages.append({
                    "role": "user",
                    "content": content,
                    **metadata,
                })

        elif role == "assistant":
            text_parts: list[str] = []
            reasoning_text: str | None = None
            reasoning_opaque: str | None = None
            tool_calls_list: list[ToolCallPart] = []

            if isinstance(content, list):
                for part in content:
                    part_meta = get_openai_metadata(part)
                    copilot_data = (part.get("providerOptions") or {}).get(
                        "copilot", {}
                    )
                    if isinstance(copilot_data, dict):
                        part_opaque = copilot_data.get("reasoningOpaque")
                        if part_opaque and reasoning_opaque is None:
                            reasoning_opaque = part_opaque

                    ptype = part.get("type")
                    if ptype == "text":
                        text_parts.append(part.get("text", ""))
                    elif ptype == "reasoning":
                        if part.get("text"):
                            reasoning_text = part["text"]
                    elif ptype == "tool-call":
                        tc: ToolCallPart = {
                            "id": part["toolCallId"],
                            "type": "function",
                            "function": {
                                "name": part["toolName"],
                                "arguments": json.dumps(part["input"])
                                if not isinstance(part["input"], str)
                                else part["input"],
                            },
                            **part_meta,  # type: ignore
                        }
                        tool_calls_list.append(tc)
            elif isinstance(content, str):
                text_parts.append(content)

            assistant_msg: AssistantMessage = {
                "role": "assistant",
                "content": "".join(text_parts) or None,
                **metadata,
            }
            if tool_calls_list:
                assistant_msg["tool_calls"] = tool_calls_list
            if reasoning_text:
                assistant_msg["reasoning_text"] = reasoning_text
            if reasoning_opaque:
                assistant_msg["reasoning_opaque"] = reasoning_opaque

            messages.append(assistant_msg)

        elif role == "tool":
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "tool-approval-response":
                        continue
                    output = part.get("output", {})
                    content_value = _format_tool_output(output)
                    tool_response_metadata = get_openai_metadata(part)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": part.get("toolCallId", ""),
                        "content": content_value,
                        **tool_response_metadata,
                    })
            else:
                # Simple tool message
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("tool_call_id", ""),
                    "content": content if isinstance(content, str) else str(content),
                })

    return messages


def _format_tool_output(output: dict[str, Any]) -> str:
    otype = output.get("type")
    if otype in ("text", "error-text"):
        return output.get("value", "")
    if otype == "execution-denied":
        return output.get("reason", "Tool execution denied.")
    if otype in ("content", "json", "error-json"):
        return json.dumps(output.get("value"))
    return str(output)
