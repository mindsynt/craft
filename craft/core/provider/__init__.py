"""
LLM 提供商系统 — 移植自 MiMo-Code packages/opencode/src/provider/
支持 OpenAI / Anthropic / Ollama / 自定义，流式 + 非流式

向后兼容的 re-exports — 所有公共 API 保持 from craft.core.provider import X 可用。
"""

from __future__ import annotations

import logging

from craft.core.provider.base import BaseProvider, ProviderError
from craft.core.provider.models import (
    AssistantMessage,
    Choice,
    ContentPart,
    ContentPartImage,
    ContentPartText,
    OpenAIMessage,
    OpenAIResponse,
    ResponsesAssistantMessage,
    ResponsesFunctionCall,
    ResponsesFunctionCallOutput,
    ResponsesIncludeValue,
    ResponsesInputItem,
    ResponsesItemReference,
    ResponsesSystemMessage,
    ResponsesUserMessage,
    SystemContentPart,
    SystemMessage,
    TokenUsage,
    ToolCallPart,
    ToolMessage,
    UserMessage,
)
from craft.core.provider.openai_error import (
    OVERFLOW_PATTERNS,
    ParsedAPICallError,
    ParsedStreamError,
    is_overflow,
    parse_api_call_error,
    parse_stream_error,
)
from craft.core.provider.openai_config import (
    OpenAICompatibleProviderOptions,
    ProviderSettings,
)
from craft.core.provider.openai_compatible import OpenAIProvider
from craft.core.provider.openai_responses import OpenAIResponsesProvider
from craft.core.provider.schema import *  # noqa: F401, F403
from craft.core.provider.transform import (
    ResponseMetadata,
    convert_to_openai_compatible_chat_messages,
    get_openai_metadata,
    get_response_metadata,
    map_openai_finish_reason,
    map_openai_responses_finish_reason,
)
from craft.core.provider.tools import prepare_tools, prepare_responses_tools
from craft.core.provider.image import compress_image, DEFAULT_MAX_IMAGE_BYTES
from craft.core.provider.web_search import *  # noqa: F401, F403
from craft.core.provider.copilot import get_copilot_metadata
from craft.core.provider.anthropic import AnthropicProvider
from craft.core.provider.registry import PROVIDER_MAP, get_provider, register_provider

logger = logging.getLogger(__name__)

__all__ = [
    # Base
    "BaseProvider",
    "ProviderError",
    # Models
    "SystemContentPart",
    "ContentPartText",
    "ContentPartImage",
    "ContentPart",
    "SystemMessage",
    "UserMessage",
    "ToolCallPart",
    "AssistantMessage",
    "ToolMessage",
    "OpenAIMessage",
    "TokenUsage",
    "Choice",
    "OpenAIResponse",
    "ResponsesIncludeValue",
    "ResponsesSystemMessage",
    "ResponsesUserMessage",
    "ResponsesAssistantMessage",
    "ResponsesFunctionCall",
    "ResponsesFunctionCallOutput",
    "ResponsesItemReference",
    "ResponsesInputItem",
    # Error
    "OVERFLOW_PATTERNS",
    "is_overflow",
    "ParsedStreamError",
    "parse_stream_error",
    "ParsedAPICallError",
    "parse_api_call_error",
    # Config
    "OpenAICompatibleProviderOptions",
    "ProviderSettings",
    # OpenAI
    "OpenAIProvider",
    # OpenAI Responses
    "OpenAIResponsesProvider",
    # Anthropic
    "AnthropicProvider",
    # Transform
    "ResponseMetadata",
    "get_response_metadata",
    "get_openai_metadata",
    "convert_to_openai_compatible_chat_messages",
    "map_openai_finish_reason",
    "map_openai_responses_finish_reason",
    # Tools
    "prepare_tools",
    "prepare_responses_tools",
    # Image
    "DEFAULT_MAX_IMAGE_BYTES",
    "compress_image",
    # Copilot
    "get_copilot_metadata",
    # Registry
    "PROVIDER_MAP",
    "register_provider",
    "get_provider",
]
