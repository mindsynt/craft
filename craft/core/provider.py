"""
LLM 提供商系统 — 移植自 MiMo-Code packages/opencode/src/provider/
支持 OpenAI / Anthropic / Ollama / 自定义，流式 + 非流式
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Literal,
    NotRequired,
    Protocol,
    TypedDict,
    runtime_checkable,
)

from craft.config import get_config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# OpenAI-Compatible API Types (from openai-compatible-api-types.ts)
# ─────────────────────────────────────────────


class SystemContentPart(TypedDict):
    type: Literal["text"]
    text: str


ContentPartText = TypedDict("ContentPartText", {"type": Literal["text"], "text": str})
ContentPartImage = TypedDict(
    "ContentPartImage",
    {"type": Literal["image_url"], "image_url": dict[str, str]},
)
ContentPart = ContentPartText | ContentPartImage


class SystemMessage(TypedDict):
    role: Literal["system"]
    content: str | list[SystemContentPart]


class UserMessage(TypedDict):
    role: Literal["user"]
    content: str | list[ContentPart]


class ToolCallPart(TypedDict):
    id: str
    type: Literal["function"]
    function: dict[str, str]


class AssistantMessage(TypedDict):
    role: Literal["assistant"]
    content: str | None
    tool_calls: NotRequired[list[ToolCallPart] | None]
    reasoning_text: NotRequired[str | None]
    reasoning_opaque: NotRequired[str | None]


class ToolMessage(TypedDict):
    role: Literal["tool"]
    content: str
    tool_call_id: str


OpenAIMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage


class TokenUsage(TypedDict, total=False):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: dict | None
    completion_tokens_details: dict | None


class Choice(TypedDict, total=False):
    index: int
    message: dict
    finish_reason: str | None
    delta: dict | None


class OpenAIResponse(TypedDict, total=False):
    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: TokenUsage | None


# ─────────────────────────────────────────────
# OpenAI Responses API Types (from openai-responses-api-types.ts)
# ─────────────────────────────────────────────

ResponsesIncludeValue = Literal[
    "web_search_call.action.sources",
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
    "reasoning.encrypted_content",
]


class ResponsesSystemMessage(TypedDict):
    role: Literal["system", "developer"]
    content: str


class ResponsesUserMessage(TypedDict):
    role: Literal["user"]
    content: list[dict]


class ResponsesAssistantMessage(TypedDict):
    role: Literal["assistant"]
    content: list[dict]
    id: NotRequired[str | None]


class ResponsesFunctionCall(TypedDict):
    type: Literal["function_call"]
    call_id: str
    name: str
    arguments: str
    id: NotRequired[str | None]


class ResponsesFunctionCallOutput(TypedDict):
    type: Literal["function_call_output"]
    call_id: str
    output: str


class ResponsesItemReference(TypedDict):
    type: Literal["item_reference"]
    id: str


ResponsesInputItem = (
    ResponsesSystemMessage
    | ResponsesUserMessage
    | ResponsesAssistantMessage
    | ResponsesFunctionCall
    | ResponsesFunctionCallOutput
    | ResponsesItemReference
)


# ─────────────────────────────────────────────
# Provider Options (from openai-compatible-chat-options.ts)
# ─────────────────────────────────────────────


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


# ─────────────────────────────────────────────
# Error Handling (from error.ts)
# ─────────────────────────────────────────────

OVERFLOW_PATTERNS = [
    re.compile(r"prompt is too long", re.I),
    re.compile(r"input is too long for requested model", re.I),
    re.compile(r"exceeds the context window", re.I),
    re.compile(r"input token count.*exceeds the maximum", re.I),
    re.compile(r"maximum prompt length is \d+", re.I),
    re.compile(r"reduce the length of the messages", re.I),
    re.compile(r"maximum context length is \d+ tokens", re.I),
    re.compile(r"exceeds the limit of \d+", re.I),
    re.compile(r"exceeds the available context size", re.I),
    re.compile(r"greater than the context length", re.I),
    re.compile(r"context window exceeds limit", re.I),
    re.compile(r"exceeded model token limit", re.I),
    re.compile(r"context[_ ]length[_ ]exceeded", re.I),
    re.compile(r"request entity too large", re.I),
    re.compile(r"context length is only \d+ tokens", re.I),
    re.compile(r"input length.*exceeds.*context length", re.I),
    re.compile(r"prompt too long; exceeded (?:max )?context length", re.I),
    re.compile(r"too large for model with \d+ maximum context length", re.I),
    re.compile(r"model_context_window_exceeded", re.I),
]


def is_overflow(message: str) -> bool:
    if any(p.search(message) for p in OVERFLOW_PATTERNS):
        return True
    if re.match(r"^4(00|13)\s*(status code)?\s*\(no body\)", message, re.I):
        return True
    return False


@dataclass
class ParsedStreamError:
    type: str  # "context_overflow" | "api_error"
    message: str
    response_body: str
    is_retryable: bool = False


def parse_stream_error(input_data: Any) -> ParsedStreamError | None:
    """Port of parseStreamError from error.ts"""
    if not isinstance(input_data, dict):
        return None
    if input_data.get("type") != "error":
        return None
    err = input_data.get("error", {})
    if not isinstance(err, dict):
        return None

    code = err.get("code")
    if code == "context_length_exceeded":
        return ParsedStreamError(
            type="context_overflow",
            message="Input exceeds context window of this model",
            response_body=json.dumps(input_data),
        )
    if code == "insufficient_quota":
        return ParsedStreamError(
            type="api_error",
            message="Quota exceeded. Check your plan and billing details.",
            response_body=json.dumps(input_data),
            is_retryable=False,
        )
    if code == "usage_not_included":
        return ParsedStreamError(
            type="api_error",
            message="To use Codex with your ChatGPT plan, upgrade to Plus: https://chatgpt.com/explore/plus.",
            response_body=json.dumps(input_data),
            is_retryable=False,
        )
    if code == "invalid_prompt":
        return ParsedStreamError(
            type="api_error",
            message=err.get("message", "Invalid prompt."),
            response_body=json.dumps(input_data),
            is_retryable=False,
        )
    return None


def _try_json(value: Any) -> dict | None:
    if isinstance(value, str):
        try:
            result = json.loads(value)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass
    if isinstance(value, dict):
        return value
    return None


@dataclass
class ParsedAPICallError:
    type: str  # "context_overflow" | "api_error"
    message: str
    status_code: int | None = None
    is_retryable: bool = False
    response_body: str | None = None
    response_headers: dict[str, str] | None = None


def parse_api_call_error(
    error: Exception,
    provider_id: str = "",
    status_code: int | None = None,
    response_body: str | None = None,
) -> ParsedAPICallError:
    """Port of parseAPICallError from error.ts"""
    message = str(error)
    body = _try_json(response_body)

    # Check overflow
    if is_overflow(message) or status_code == 413:
        return ParsedAPICallError(
            type="context_overflow",
            message=message,
            status_code=status_code,
            response_body=response_body,
        )

    if body and isinstance(body.get("error"), dict):
        err_code = body["error"].get("code")
        if err_code == "context_length_exceeded":
            return ParsedAPICallError(
                type="context_overflow",
                message=message,
                status_code=status_code,
                response_body=response_body,
            )

    # Default: api_error
    is_retryable = status_code == 404 if provider_id.startswith("openai") else False
    return ParsedAPICallError(
        type="api_error",
        message=message,
        status_code=status_code,
        is_retryable=is_retryable,
        response_body=response_body,
    )


# ─────────────────────────────────────────────
# Finish Reason Mapping (from map-openai-compatible-finish-reason.ts)
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
# Response Metadata (from get-response-metadata.ts)
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
# Message Conversion (from convert-to-openai-compatible-chat-messages.ts)
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


# ─────────────────────────────────────────────
# Tool Preparation (from openai-compatible-prepare-tools.ts)
# ─────────────────────────────────────────────


def prepare_tools(
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
) -> tuple[
    list[dict[str, Any]] | None,
    dict[str, Any] | str | None,
    list[dict[str, str]],
]:
    """Port of prepareTools"""
    warnings: list[dict[str, str]] = []

    if not tools:
        return None, None, warnings

    openai_tools: list[dict[str, Any]] = []
    for tool in tools:
        ttype = tool.get("type")
        if ttype == "provider":
            warnings.append({
                "type": "unsupported",
                "feature": f"tool type: {ttype}",
            })
        else:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description"),
                    "parameters": tool.get("inputSchema", tool.get("parameters", {})),
                },
            })

    if tool_choice is None:
        return openai_tools if openai_tools else None, None, warnings

    if isinstance(tool_choice, str):
        if tool_choice in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tool_choice, warnings

    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type")
        if tc_type in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tc_type, warnings
        if tc_type == "tool":
            return (
                openai_tools if openai_tools else None,
                {
                    "type": "function",
                    "function": {"name": tool_choice.get("toolName", "")},
                },
                warnings,
            )

    return openai_tools if openai_tools else None, tool_choice, warnings


# ─────────────────────────────────────────────
# Base Provider Classes
# ─────────────────────────────────────────────


class ProviderError(Exception):
    def __init__(self, message: str, code: int = 500, provider: str = ""):
        self.code = code
        self.provider = provider
        super().__init__(message)


class BaseProvider(ABC):
    def __init__(self, name: str, model: str = ""):
        self.name = name
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        ...


# ─────────────────────────────────────────────
# OpenAI Provider (enhanced with MiMo-Code features)
# ─────────────────────────────────────────────


class OpenAIProvider(BaseProvider):
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        supports_structured_outputs: bool = False,
    ):
        super().__init__("openai", model)
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._organization = organization
        self._project = project
        self._supports_structured_outputs = supports_structured_outputs
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
            kwargs: dict[str, Any] = {
                "api_key": key,
                "base_url": self._base_url,
            }
            if self._organization:
                kwargs["organization"] = self._organization
            if self._project:
                kwargs["project"] = self._project
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        try:
            # Parse provider options
            opts = OpenAICompatibleProviderOptions.from_dict(
                kwargs.pop("providerOptions", None)
            )

            # Prepare tools
            openai_tools, tool_choice, _ = prepare_tools(
                tools, kwargs.pop("tool_choice", None)
            )

            # Build request args
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": messages,
            }
            if openai_tools:
                api_kwargs["tools"] = openai_tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice

            # Standard params
            for param in (
                "max_tokens",
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "seed",
                "user",
            ):
                value = kwargs.pop(param, None) or getattr(opts, param, None)
                if value is not None:
                    api_kwargs[param] = value

            # Response format: support structured outputs
            response_format = kwargs.pop("response_format", None)
            if response_format and isinstance(response_format, dict):
                if self._supports_structured_outputs and response_format.get("schema"):
                    api_kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "schema": response_format["schema"],
                            "name": response_format.get("name", "response"),
                            "description": response_format.get("description"),
                        },
                    }
                elif response_format.get("type") == "json":
                    api_kwargs["response_format"] = {"type": "json_object"}

            # Reasoning effort
            if opts.reasoning_effort:
                api_kwargs["reasoning_effort"] = opts.reasoning_effort

            # Any extra kwargs
            api_kwargs.update(kwargs)

            resp = await self.client.chat.completions.create(**api_kwargs)

            choice = resp.choices[0]
            msg = choice.message

            # Build content with reasoning support (Copilot-style)
            content_parts: list[dict] = []
            if msg.content:
                content_parts.append({"type": "text", "text": msg.content})
            if getattr(msg, "reasoning_text", None):
                content_parts.append({
                    "type": "reasoning",
                    "text": msg.reasoning_text,
                })
            if getattr(msg, "reasoning_content", None):
                content_parts.append({
                    "type": "reasoning",
                    "text": msg.reasoning_content,
                })

            result: dict[str, Any] = {
                "content": msg.content or "",
                "content_parts": content_parts,
                "finish_reason": map_openai_finish_reason(
                    getattr(choice, "finish_reason", None)
                ),
                "tool_calls": self._extract_tools(msg),
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens
                    if resp.usage
                    else 0,
                },
                "metadata": {
                    "id": resp.id,
                    "model": resp.model,
                    "created": resp.created,
                },
            }

            # Detailed token info
            if resp.usage:
                if resp.usage.prompt_tokens_details:
                    result["usage"]["cached_tokens"] = (
                        resp.usage.prompt_tokens_details.cached_tokens
                    )
                if resp.usage.completion_tokens_details:
                    result["usage"]["reasoning_tokens"] = (
                        resp.usage.completion_tokens_details.reasoning_tokens
                    )

            return result

        except Exception as e:
            err_str = str(e).lower()
            if "api_key" in err_str or "missing credentials" in err_str:
                raise ProviderError(
                    "请设置 OPENAI_API_KEY 环境变量", 401, "openai"
                ) from e
            raise ProviderError(str(e), 500, "openai") from e

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        try:
            # Parse provider options
            opts = OpenAICompatibleProviderOptions.from_dict(
                kwargs.pop("providerOptions", None)
            )

            openai_tools, tool_choice, _ = prepare_tools(
                tools, kwargs.pop("tool_choice", None)
            )

            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if openai_tools:
                api_kwargs["tools"] = openai_tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice

            for param in (
                "max_tokens",
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "seed",
                "user",
            ):
                value = kwargs.pop(param, None) or getattr(opts, param, None)
                if value is not None:
                    api_kwargs[param] = value

            if opts.reasoning_effort:
                api_kwargs["reasoning_effort"] = opts.reasoning_effort

            api_kwargs.update(kwargs)

            stream = await self.client.chat.completions.create(**api_kwargs)

            is_first = True
            active_reasoning = False
            reasoning_opaque: str | None = None

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None and not getattr(chunk, "usage", None):
                    continue

                # response-metadata on first chunk
                if is_first:
                    is_first = False
                    yield {
                        "type": "response-metadata",
                        "id": chunk.id,
                        "model": chunk.model,
                        "created": chunk.created,
                    }

                # Emit reasoning via reasoning_text (Copilot-style)
                if delta:
                    rtext = getattr(delta, "reasoning_text", None) or getattr(
                        delta, "reasoning_content", None
                    )
                    if rtext:
                        if not active_reasoning:
                            yield {"type": "reasoning-start", "id": "reasoning-0"}
                            active_reasoning = True
                        yield {
                            "type": "reasoning-delta",
                            "id": "reasoning-0",
                            "delta": rtext,
                        }

                    # Capture reasoning_opaque for multi-turn
                    r_opaque = getattr(delta, "reasoning_opaque", None)
                    if r_opaque:
                        reasoning_opaque = r_opaque

                    # Content
                    if delta.content:
                        if active_reasoning:
                            yield {
                                "type": "reasoning-end",
                                "id": "reasoning-0",
                                "providerMetadata": (
                                    {"copilot": {"reasoningOpaque": reasoning_opaque}}
                                    if reasoning_opaque
                                    else None
                                ),
                            }
                            active_reasoning = False
                        yield {"type": "content", "content": delta.content}

                    # Tool calls
                    if getattr(delta, "tool_calls", None):
                        if active_reasoning:
                            yield {
                                "type": "reasoning-end",
                                "id": "reasoning-0",
                                "providerMetadata": (
                                    {"copilot": {"reasoningOpaque": reasoning_opaque}}
                                    if reasoning_opaque
                                    else None
                                ),
                            }
                            active_reasoning = False
                        for tc in delta.tool_calls:
                            yield {
                                "type": "tool-call-delta",
                                "index": tc.index,
                                "id": tc.id,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "",
                                },
                            }

                # Usage
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                    usage_data: dict[str, Any] = {
                        "type": "usage",
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                    }
                    if usage.prompt_tokens_details:
                        usage_data["cached_tokens"] = (
                            usage.prompt_tokens_details.cached_tokens
                        )
                    if usage.completion_tokens_details:
                        usage_data["reasoning_tokens"] = (
                            usage.completion_tokens_details.reasoning_tokens
                        )
                    yield usage_data

            # Flush active reasoning
            if active_reasoning:
                yield {
                    "type": "reasoning-end",
                    "id": "reasoning-0",
                    "providerMetadata": (
                        {"copilot": {"reasoningOpaque": reasoning_opaque}}
                        if reasoning_opaque
                        else None
                    ),
                }

        except Exception as e:
            err_str = str(e).lower()
            yield {
                "type": "error",
                "message": "请设置 OPENAI_API_KEY"
                if "api_key" in err_str or "missing credentials" in err_str
                else str(e),
            }

    def _extract_tools(self, msg) -> list[dict] | None:
        if not getattr(msg, "tool_calls", None):
            return None
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]


# ─────────────────────────────────────────────
# OpenAI Responses API Provider
# ─────────────────────────────────────────────


class OpenAIResponsesProvider(BaseProvider):
    """
    OpenAI Responses API provider.
    Uses the newer /v1/responses endpoint with built-in tools
    (web_search, code_interpreter, file_search, etc.)
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__("openai-responses", model)
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._http_client = None

    @property
    def _session(self):
        if self._http_client is None:
            import httpx

            key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=300,
            )
        return self._http_client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """Use Responses API for non-streaming requests"""
        return await self._responses_create(messages, tools, stream=False, **kwargs)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        """Use Responses API for streaming requests"""
        async for chunk in self._responses_stream(messages, tools, **kwargs):
            yield chunk

    async def _responses_create(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Call the OpenAI Responses API"""
        from openai import AsyncOpenAI

        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        key = self._api_key or os.environ.get("OPENAI_API_KEY", "")

        # Convert messages to Responses API input format
        input_items = self._convert_to_responses_input(messages)

        # Prepare tools
        responses_tools, tool_choice, _ = prepare_responses_tools(
            tools, kwargs.pop("tool_choice", None)
        )

        body: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "input": input_items,
        }

        if responses_tools:
            body["tools"] = responses_tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        for param in (
            "temperature",
            "top_p",
            "max_output_tokens",
            "instructions",
            "store",
            "metadata",
            "user",
            "parallel_tool_calls",
        ):
            value = kwargs.pop(param, None)
            if value is not None:
                body[param] = value

        if opts.reasoning_effort:
            body["reasoning"] = {"effort": opts.reasoning_effort}

        # Use the standard OpenAI client's responses API if available
        try:
            client = AsyncOpenAI(api_key=key, base_url=self._base_url)
            if hasattr(client, "responses") and hasattr(
                client.responses, "create"
            ):
                resp = await client.responses.create(**body)
            else:
                # Fallback to raw HTTP
                resp = await self._raw_responses_create(body)

            return self._parse_responses_response(resp)
        except Exception as e:
            raise ProviderError(str(e), 500, self.name) from e

    async def _raw_responses_create(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Raw HTTP call to Responses API"""
        response = await self._session.post("/responses", json=body)
        response.raise_for_status()
        return response.json()

    async def _responses_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        """Stream from Responses API"""
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        input_items = self._convert_to_responses_input(messages)
        responses_tools, tool_choice, _ = prepare_responses_tools(
            tools, kwargs.pop("tool_choice", None)
        )

        body: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "input": input_items,
            "stream": True,
        }

        if responses_tools:
            body["tools"] = responses_tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        for param in (
            "temperature",
            "top_p",
            "max_output_tokens",
            "instructions",
            "store",
            "user",
        ):
            value = kwargs.pop(param, None)
            if value is not None:
                body[param] = value

        if opts.reasoning_effort:
            body["reasoning"] = {"effort": opts.reasoning_effort}

        try:
            async with self._session.stream(
                "POST", "/responses", json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    yield self._process_responses_chunk(chunk)
        except Exception as e:
            yield {"type": "error", "message": str(e)}

    def _convert_to_responses_input(
        self, messages: list[dict]
    ) -> list[ResponsesInputItem]:
        """Convert standard messages to Responses API input format"""
        input_items: list[ResponsesInputItem] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                input_items.append({"role": "system", "content": content})

            elif role == "user":
                parts: list[dict] = []
                if isinstance(content, str):
                    parts.append({"type": "input_text", "text": content})
                elif isinstance(content, list):
                    for part in content:
                        ptype = part.get("type")
                        if ptype == "text":
                            parts.append({"type": "input_text", "text": part["text"]})
                        elif ptype == "image_url":
                            parts.append({
                                "type": "input_image",
                                "image_url": part["image_url"]["url"],
                            })
                        elif ptype == "file":
                            media_type = part.get("mediaType", "")
                            if media_type.startswith("image/"):
                                parts.append({
                                    "type": "input_image",
                                    "image_url": f"data:{media_type};base64,{base64.b64encode(bytes(part['data'])).decode()}",
                                })
                input_items.append({"role": "user", "content": parts})

            elif role == "assistant":
                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    texts = [
                        p["text"]
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    text_content = "".join(texts)
                input_items.append({
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text_content}],
                })

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                output = content if isinstance(content, str) else json.dumps(content)
                input_items.append({
                    "type": "function_call_output",
                    "call_id": tool_call_id,
                    "output": output,
                })

        return input_items

    def _parse_responses_response(
        self, resp: Any
    ) -> dict[str, Any]:
        """Parse a Responses API response into standard format"""
        # Handle both SDK response objects and raw dicts
        if isinstance(resp, dict):
            data = resp
        else:
            # OpenAI SDK response object
            data = resp.to_dict() if hasattr(resp, "to_dict") else resp.model_dump()

        output_text = ""
        tool_calls_list: list[dict] = []
        has_function_call = False

        for item in data.get("output", []):
            if item.get("type") == "message":
                for cp in item.get("content", []):
                    if cp.get("type") == "output_text":
                        output_text += cp.get("text", "")
            elif item.get("type") == "function_call":
                has_function_call = True
                tool_calls_list.append({
                    "id": item.get("call_id", item.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                })

        usage = data.get("usage", {}) or {}
        return {
            "content": output_text,
            "tool_calls": tool_calls_list or None,
            "finish_reason": map_openai_responses_finish_reason(
                data.get("incomplete_details", {}).get("reason"),
                has_function_call=has_function_call,
            ),
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            "metadata": {
                "id": data.get("id"),
                "model": data.get("model"),
                "created": data.get("created_at"),
            },
        }

    def _process_responses_chunk(
        self, chunk: dict[str, Any]
    ) -> dict[str, Any]:
        """Process a streaming Responses API chunk"""
        chunk_type = chunk.get("type", "")

        if chunk_type == "response.output_text.delta":
            return {"type": "content", "content": chunk.get("delta", "")}
        elif chunk_type == "response.output_item.added":
            item = chunk.get("item", {})
            if item.get("type") == "function_call":
                return {
                    "type": "tool-call-start",
                    "id": item.get("call_id", item.get("id")),
                    "name": item.get("name"),
                }
        elif chunk_type == "response.function_call_arguments.delta":
            return {
                "type": "tool-call-delta",
                "id": chunk.get("item_id"),
                "delta": chunk.get("delta", ""),
            }
        elif chunk_type == "response.completed":
            return {"type": "done"}
        elif chunk_type == "response.error":
            return {"type": "error", "message": str(chunk.get("error", ""))}

        return {"type": "other", "data": chunk}


def prepare_responses_tools(
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
    strict_json_schema: bool = False,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | str | None, list[dict]]:
    """Port of prepareResponsesTools"""
    warnings: list[dict] = []

    if not tools:
        return None, None, warnings

    openai_tools: list[dict[str, Any]] = []
    for tool in tools:
        ttype = tool.get("type")
        if ttype == "function":
            openai_tools.append({
                "type": "function",
                "name": tool.get("name", ""),
                "description": tool.get("description"),
                "parameters": tool.get(
                    "inputSchema", tool.get("parameters", {})
                ),
                "strict": strict_json_schema,
            })

        elif ttype == "provider":
            tool_id = tool.get("id", "")
            args = tool.get("args", {}) or {}

            if tool_id == "openai.web_search":
                openai_tools.append({
                    "type": "web_search",
                    "filters": (
                        {"allowed_domains": args.get("filters", {}).get("allowedDomains")}
                        if args.get("filters")
                        else None
                    ),
                    "search_context_size": args.get("searchContextSize"),
                    "user_location": args.get("userLocation"),
                })

            elif tool_id == "openai.web_search_preview":
                openai_tools.append({
                    "type": "web_search_preview",
                    "search_context_size": args.get("searchContextSize"),
                    "user_location": args.get("userLocation"),
                })

            elif tool_id == "openai.code_interpreter":
                container = args.get("container")
                if container is None:
                    container_val: Any = {"type": "auto", "file_ids": None}
                elif isinstance(container, str):
                    container_val = container
                else:
                    container_val = {
                        "type": "auto",
                        "file_ids": container.get("fileIds") if isinstance(container, dict) else None,
                    }
                openai_tools.append({
                    "type": "code_interpreter",
                    "container": container_val,
                })

            elif tool_id == "openai.file_search":
                openai_tools.append({
                    "type": "file_search",
                    "vector_store_ids": args.get("vectorStoreIds", []),
                    "max_num_results": args.get("maxNumResults"),
                    "ranking_options": (
                        {
                            "ranker": args["ranking"]["ranker"],
                            "score_threshold": args["ranking"]["scoreThreshold"],
                        }
                        if args.get("ranking")
                        else None
                    ),
                })

            elif tool_id == "openai.image_generation":
                openai_tools.append({
                    "type": "image_generation",
                    "background": args.get("background"),
                    "input_fidelity": args.get("inputFidelity"),
                    "model": args.get("model"),
                    "quality": args.get("quality"),
                    "size": args.get("size"),
                    "output_format": args.get("outputFormat"),
                })

            elif tool_id == "openai.local_shell":
                openai_tools.append({"type": "local_shell"})

            else:
                warnings.append({
                    "type": "unsupported",
                    "feature": f"tool id: {tool_id}",
                })

        else:
            warnings.append({"type": "unsupported", "feature": "tool type"})

    # Handle tool_choice
    if tool_choice is None:
        return openai_tools if openai_tools else None, None, warnings

    if isinstance(tool_choice, str):
        if tool_choice in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tool_choice, warnings

    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type")
        if tc_type in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tc_type, warnings

        if tc_type == "tool":
            tool_name = tool_choice.get("toolName", "")
            if tool_name in (
                "code_interpreter",
                "file_search",
                "image_generation",
                "web_search_preview",
                "web_search",
            ):
                tc_result: dict[str, Any] = {"type": tool_name}
            else:
                tc_result = {"type": "function", "name": tool_name}
            return openai_tools if openai_tools else None, tc_result, warnings

    return openai_tools if openai_tools else None, tool_choice, warnings


# ─────────────────────────────────────────────
# Anthropic Provider
# ─────────────────────────────────────────────


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        model: str = "claude-sonnet-4",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__("anthropic", model)
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key
                or os.environ.get("ANTHROPIC_API_KEY", ""),
                base_url=self._base_url,
            )
        return self._client

    def _split(self, messages: list[dict]):
        system, msgs = None, []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)
        return system, msgs

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        system, msgs = self._split(messages)
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        try:
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": msgs,
                "max_tokens": kwargs.pop("max_tokens", 4096),
            }
            if system:
                api_kwargs["system"] = system
            if tools:
                api_kwargs["tools"] = tools
            if opts.thinking_budget:
                api_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": opts.thinking_budget,
                }

            resp = await self.client.messages.create(**api_kwargs)
            content_parts = []
            text = ""
            for block in resp.content:
                if block.type == "text":
                    text += block.text
                    content_parts.append({"type": "text", "text": block.text})
                elif block.type == "thinking":
                    content_parts.append({
                        "type": "reasoning",
                        "text": block.thinking,
                    })

            return {
                "content": text,
                "content_parts": content_parts,
                "usage": {
                    "input_tokens": resp.usage.input_tokens if resp.usage else 0,
                    "output_tokens": resp.usage.output_tokens if resp.usage else 0,
                },
            }
        except Exception as e:
            raise ProviderError(str(e), 500, "anthropic") from e

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        system, msgs = self._split(messages)
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        try:
            api_kwargs: dict[str, Any] = {
                "model": kwargs.pop("model", self.model),
                "messages": msgs,
                "max_tokens": kwargs.pop("max_tokens", 4096),
            }
            if system:
                api_kwargs["system"] = system
            if tools:
                api_kwargs["tools"] = tools
            if opts.thinking_budget:
                api_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": opts.thinking_budget,
                }

            async with self.client.messages.stream(**api_kwargs) as stream:
                async for text_delta in stream.text_stream:
                    yield {"type": "content", "content": text_delta}
        except Exception as e:
            yield {"type": "error", "message": str(e)}


# ─────────────────────────────────────────────
# Provider Options Schema & Settings
# ─────────────────────────────────────────────


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


# ─────────────────────────────────────────────
# Image Compression (from image.ts)
# ─────────────────────────────────────────────

DEFAULT_MAX_IMAGE_BYTES = 4_500_000


def compress_image(
    data: bytes,
    media_type: str = "image/jpeg",
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    format: str = "JPEG",
) -> tuple[str, str] | None:
    """
    Compress an image to fit within max_bytes.
    Returns (base64_data, media_type) or None if compression fails.
    Port of compressImage from image.ts
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        return None

    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        return None

    # Try progressively lower quality, then smaller dimensions
    scales = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1]
    qualities = [85, 65, 45, 30]

    for scale in scales:
        if scale < 1.0:
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            scaled = img.resize((w, h), Image.LANCZOS)
        else:
            scaled = img

        for quality in qualities:
            buf = io.BytesIO()
            try:
                scaled.save(buf, format=format, quality=quality)
                if buf.tell() <= max_bytes:
                    return (
                        base64.b64encode(buf.getvalue()).decode("ascii"),
                        f"image/{format.lower()}",
                    )
            except Exception:
                continue

    return None


# ─────────────────────────────────────────────
# Provider Registry & Factory
# ─────────────────────────────────────────────


PROVIDER_MAP: dict[str, Any] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "openai-responses": OpenAIResponsesProvider,
    "ollama": lambda **kw: OpenAIProvider(base_url="http://localhost:11434/v1", **kw),
}


def register_provider(name: str, factory: Any) -> None:
    """Register a custom provider factory."""
    PROVIDER_MAP[name] = factory


def get_provider(
    provider_name: str | None = None,
    model: str | None = None,
    settings: ProviderSettings | None = None,
) -> BaseProvider:
    cfg = get_config()
    if model and "/" in model:
        provider_name, model = model.split("/", 1)
    provider_name = provider_name or "openai"
    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4",
        "ollama": "llama3",
        "openai-responses": "gpt-4o",
    }
    model = model or defaults.get(provider_name, "")
    factory = PROVIDER_MAP.get(provider_name)
    if not factory:
        raise ProviderError(
            f"未知提供商: {provider_name}，可用: {', '.join(PROVIDER_MAP.keys())}",
            400,
        )

    # Apply settings from config
    settings_dict: dict[str, Any] = {"model": model}
    if settings:
        settings_dict.update(settings)

    return factory(**settings_dict)
