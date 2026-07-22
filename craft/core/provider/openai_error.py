"""Error handling for providers — ported from error.ts"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


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
