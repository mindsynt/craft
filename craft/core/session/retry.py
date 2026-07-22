"""Retry logic — ported from retry.ts.

Rate limit detection, exponential backoff, retry scheduling.
"""

from __future__ import annotations

import re
import time
import math
from typing import Any

GO_UPSELL_MESSAGE = "Free usage exceeded, subscribe to Go https://opencode.ai/go"
RETRY_INITIAL_DELAY = 2000  # ms
RETRY_BACKOFF_FACTOR = 2
RETRY_MAX_DELAY_NO_HEADERS = 30_000
RETRY_MAX_DELAY = 2_147_483_647

NETWORK_ERROR_CODES = {"ECONNRESET", "EPIPE", "ETIMEDOUT"}
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504, 529}
SSE_TIMEOUT_MESSAGE = "SSE read timed out"


def is_rate_limit_message(message: str) -> bool:
    lower = message.lower()
    return any(
        phrase in lower
        for phrase in [
            "too many requests",
            "too_many_requests",
            "rate limit",
            "rate_limit",
            "rate increased too quickly",
        ]
    )


def is_retryable_transient_error(error: Any) -> bool:
    """Single source of truth for 'is this transient and retryable?'"""
    status: Any = None
    if isinstance(error, dict):
        status = error.get("status") or error.get("statusCode")
    elif isinstance(error, Exception):
        status = getattr(error, "status", None) or getattr(error, "statusCode", None) or getattr(error, "status_code", None)
        if status is None:
            resp = getattr(error, "response", None)
            if resp is not None:
                status = getattr(resp, "status", None)

    if status is not None:
        status_int = int(status) if isinstance(status, str) else status
        if status_int in RETRYABLE_HTTP_STATUS:
            return True

    if isinstance(error, Exception):
        code = getattr(error, "code", None)
        if code and code in NETWORK_ERROR_CODES:
            return True
        if str(error) == SSE_TIMEOUT_MESSAGE:
            return True

    if isinstance(error, dict):
        code = error.get("code", "")
        if code in NETWORK_ERROR_CODES:
            return True

    return False


def retry_delay(attempt: int, error: Any = None) -> int:
    """Calculate retry delay with exponential backoff."""
    if error:
        headers = None
        if isinstance(error, dict):
            headers = error.get("data", {}).get("responseHeaders", error.get("responseHeaders"))
        elif hasattr(error, "data") and hasattr(error.data, "get"):
            headers = error.data.get("responseHeaders")

        if headers:
            retry_after_ms = headers.get("retry-after-ms")
            if retry_after_ms:
                parsed = float(retry_after_ms)
                if math.isfinite(parsed):
                    return min(int(parsed), RETRY_MAX_DELAY)

            retry_after = headers.get("retry-after")
            if retry_after:
                parsed = float(retry_after)
                if math.isfinite(parsed):
                    return min(math.ceil(parsed * 1000), RETRY_MAX_DELAY)

                parsed_date = _parse_http_date(retry_after)
                if parsed_date and parsed_date > 0:
                    return min(math.ceil(parsed_date), RETRY_MAX_DELAY)

    return min(
        RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1)),
        RETRY_MAX_DELAY_NO_HEADERS,
    )


def _parse_http_date(s: str) -> float | None:
    """Try to parse an HTTP date string into milliseconds from now."""
    try:
        # Common HTTP date formats
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%A, %d-%b-%y %H:%M:%S %Z",
            "%a %b %d %H:%M:%S %Y",
        ]:
            try:
                from datetime import datetime
                dt = datetime.strptime(s, fmt)
                return (dt.timestamp() * 1000) - (time.time() * 1000)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def retryable(error: Any) -> str | None:
    """Determine if an error is retryable and return a user-facing message."""
    # Context overflow should not be retried
    if isinstance(error, dict):
        name = error.get("name", error.get("_tag", ""))
    else:
        name = getattr(error, "name", None) or type(error).__name__

    # Catch raw errors / network / SSE-timeout
    if is_retryable_transient_error(error):
        msg = str(error) if isinstance(error, Exception) else error.get("message", str(error))
        return msg or "Transient network error"

    # APIError handling
    if isinstance(error, dict) and name == "APIError":
        data = error.get("data", error)
        status = data.get("statusCode")
        message = data.get("message", "")
        response_body = data.get("responseBody", "")

        if status == 400 and "upstream_error" in response_body:
            return message

        if "FreeUsageLimitError" in response_body:
            return GO_UPSELL_MESSAGE

        if "SubscriptionUsageLimitError" in response_body:
            return None

        is_429 = (
            status == 429
            or is_rate_limit_message(message)
            or (isinstance(response_body, str) and is_rate_limit_message(response_body))
        )
        if is_429:
            return "Too Many Requests"

        is_retryable = data.get("isRetryable", False)
        if not is_retryable and not (status is not None and status >= 500):
            return None

        if "Overloaded" in message:
            return "Provider is overloaded"
        return message

    # Plain text / JSON error handling
    if isinstance(error, dict):
        data = error.get("data", error)
        msg = data.get("message", "")

        if isinstance(msg, str):
            import json
            try:
                json_obj = json.loads(msg)
                if isinstance(json_obj, dict):
                    # Check JSON error shapes
                    code = str(json_obj.get("code", ""))
                    error_code = str(json_obj.get("error", {}).get("code", ""))
                    error_type = str(json_obj.get("error", {}).get("type", ""))
                    error_message = str(json_obj.get("error", {}).get("message", ""))

                    is_429 = code == "429" or error_code == "429" or str(json_obj.get("status", "")) == "429"
                    if error_type == "too_many_requests" or is_429 or is_rate_limit_message(error_message) or is_rate_limit_message(str(json_obj.get("message", ""))):
                        return "Too Many Requests"
                    if "exhausted" in code or "unavailable" in code:
                        return "Provider is overloaded"
                    if json_obj.get("type") == "error" and "rate_limit" in error_code:
                        return "Rate Limited"
                    return None
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

            # Plain text rate limit check
            if is_rate_limit_message(msg):
                return msg

    return None


def retry_policy(
    parse_fn,  # callable to parse error from unknown
    set_fn,    # callable to set retry state
):
    """Build a retry schedule policy (simplified)."""
    # Returns a retry function that takes (attempt, error) -> (wait_ms, message) or None to stop
    def schedule(attempt: int, error: Any) -> tuple[int, str] | None:
        parsed = parse_fn(error) if callable(parse_fn) else error
        msg = retryable(parsed)
        if msg is None:
            return None
        wait = retry_delay(attempt, parsed)
        now_ms = time.time() * 1000
        set_fn({"attempt": attempt, "message": msg, "next": now_ms + wait})
        return (wait, msg)

    return schedule
