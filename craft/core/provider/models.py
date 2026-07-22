"""OpenAI-Compatible API Types + Responses API Types — TypedDict definitions"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


# ─────────────────────────────────────────────
# OpenAI-Compatible API Types
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
# OpenAI Responses API Types
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
