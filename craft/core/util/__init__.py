"""
工具函数库 — 移植自 packages/opencode/src/util/ (54文件综合)
日志、错误、文件系统、锁、超时、网络、格式化、键绑定、进程、队列、颜色等
"""

from __future__ import annotations

from .archive import extract_zip
from .bytes import format_bytes
from .color import hex_to_ansi_bold, hex_to_rgb, is_valid_hex
from .data_url import decode_data_url
from .duration import format_duration, format_duration_precise, format_ms
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
from .lazy import lazy
from .locale import get_system_locale
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
from .queue import AsyncQueue, work_parallel
from .record import is_record
from .signal import make_signal
from .timeout import Timeout, abort_after, timeout_promise, with_timeout
from .token import estimate_tokens, md5, sha256
from .which import which

__all__ = [
    "abort_after",
    "AsyncQueue",
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
    "get_system_locale",
    "hex_to_ansi_bold",
    "hex_to_rgb",
    "is_image_attachment",
    "is_media",
    "is_online",
    "is_pdf_attachment",
    "is_proxied",
    "is_record",
    "is_valid_hex",
    "lazy",
    "Lock",
    "Log",
    "make_signal",
    "md5",
    "MEDIA_SIGNATURES",
    "memoize",
    "merge_deep",
    "NamedError",
    "parse_keybind",
    "pipe",
    "pluralize",
    "RunFailedError",
    "run_lines",
    "run_process",
    "run_text",
    "RWLock",
    "sha256",
    "sniff_mime",
    "spawn_process",
    "stop_process",
    "throttle",
    "timeout_promise",
    "Timeout",
    "titlecase",
    "truncate",
    "truncate_middle",
    "which",
    "with_timeout",
    "work_parallel",
]

# init logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
