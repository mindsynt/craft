"""
工具函数库 — 移植自 packages/opencode/src/util/ (54文件综合)
日志、错误、文件系统、锁、超时、网络、格式化、键绑定、进程、队列、颜色等
"""

from __future__ import annotations

from .abort import AbortController, abort_after, abort_after_any
from .archive import extract_zip
from .bytes import format_bytes
from .color import hex_to_ansi_bold, hex_to_rgb, is_valid_hex
from .data_url import decode_data_url
from .duration import format_duration, format_duration_precise, format_ms
from .effect_http_client import with_transient_retry
from .env_info import get_env_info
from .error import (
    ErrorCode,
    NamedError,
    create_named_error,
    error_data,
    error_format,
    error_message,
)
from .filesystem import FileSystem
from .fn import debounce, defer, memoize, throttle, Defer
from .format import (
    format_number,
    format_number_short,
    parse_keybind,
    pluralize,
    titlecase,
    truncate,
    truncate_middle,
)
from .id_gen import generate_id
from .iife import iife
from .keybind import (
    KeybindInfo,
    keybind_match,
    keybind_from_parsed,
    keybind_to_string,
    keybind_parse,
)
from .lazy import lazy
from .locale import get_system_locale
from .local_context import LocalContext, LocalContextNotFoundError, create_context
from .lock import Lock, RWLock
from .log import Log
from .media import (
    MEDIA_SIGNATURES,
    is_image_attachment,
    is_media,
    is_pdf_attachment,
    sniff_mime,
)
from .merge import merge_deep
from .network import fetch_json, is_online, is_proxied
from .pipe import pipe
from .process import (
    RunFailedError,
    run_lines,
    run_process,
    run_text,
    spawn_process,
    stop_process,
)
from .provider_priority import PROVIDER_PRIORITY, is_popular_provider
from .queue import AsyncQueue, work_parallel
from .record import is_record
from .signal import make_signal
from .ssrf import assert_safe_url, safe_fetch
from .timeout import Timeout, abort_after as timeout_abort, timeout_promise, with_timeout
from .token import estimate_tokens, md5, sha256
from .tool_compat import (
    canonical,
    resolve_name,
    schema_property_keys,
    normalize_input,
    parse_tool_input,
    stringify_tool_input,
    repair_tool_call,
    ToolRepairInput,
    RepairedToolCall,
)
from .update_schema import make_update_schema
from .which import which

__all__ = [
    "AbortController",
    "abort_after",
    "abort_after_any",
    "assert_safe_url",
    "AsyncQueue",
    "canonical",
    "create_context",
    "create_named_error",
    "debounce",
    "decode_data_url",
    "Defer",
    "defer",
    "error_data",
    "error_format",
    "error_message",
    "ErrorCode",
    "estimate_tokens",
    "extract_zip",
    "fetch_json",
    "FileSystem",
    "format_bytes",
    "format_duration",
    "format_duration_precise",
    "format_ms",
    "format_number",
    "format_number_short",
    "generate_id",
    "get_env_info",
    "get_system_locale",
    "hex_to_ansi_bold",
    "hex_to_rgb",
    "iife",
    "is_image_attachment",
    "is_media",
    "is_online",
    "is_pdf_attachment",
    "is_popular_provider",
    "is_proxied",
    "is_record",
    "is_valid_hex",
    "KeybindInfo",
    "keybind_match",
    "keybind_from_parsed",
    "keybind_to_string",
    "keybind_parse",
    "lazy",
    "LocalContext",
    "LocalContextNotFoundError",
    "Lock",
    "Log",
    "make_signal",
    "make_update_schema",
    "md5",
    "MEDIA_SIGNATURES",
    "memoize",
    "merge_deep",
    "NamedError",
    "normalize_input",
    "parse_keybind",
    "parse_tool_input",
    "pipe",
    "pluralize",
    "PROVIDER_PRIORITY",
    "RepairedToolCall",
    "repair_tool_call",
    "resolve_name",
    "RunFailedError",
    "run_lines",
    "run_process",
    "run_text",
    "RWLock",
    "safe_fetch",
    "sha256",
    "schema_property_keys",
    "sniff_mime",
    "spawn_process",
    "stop_process",
    "stringify_tool_input",
    "throttle",
    "timeout_abort",
    "timeout_promise",
    "Timeout",
    "titlecase",
    "ToolRepairInput",
    "truncate",
    "truncate_middle",
    "which",
    "with_timeout",
    "with_transient_retry",
    "work_parallel",
]

# init logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
