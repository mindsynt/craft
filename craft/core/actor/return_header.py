"""
返回头 — 移植自 packages/opencode/src/actor/return-header.ts

解析子代理输出的 **Status**/**Summary** 头，用于跟踪任务结果。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 返回状态常量 — 移植自 RETURN_STATUSES
RETURN_STATUSES = ["success", "partial", "failed", "blocked"]

ReturnStatus = str  # "success" | "partial" | "failed" | "blocked"


@dataclass
class ParsedReturnHeader:
    """解析后的返回头 — 移植自 return-header.ts ParsedReturnHeader"""
    status: ReturnStatus | None = None
    summary: str | None = None


# regex 模式 — 移植自 STATUS_RE / SUMMARY_RE
STATUS_RE = re.compile(r"^\s*\*\*Status\*\*:\s*(success|partial|failed|blocked)\b", re.IGNORECASE | re.MULTILINE)
SUMMARY_RE = re.compile(r"\*\*Summary\*\*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def parse_return_header(final_text: str | None) -> ParsedReturnHeader:
    """解析 **Status**/**Summary** 头 — 移植自 return-header.ts parseReturnHeader()

    子代理被要求在其最终输出中包含这些头（参见 spawn.ts 中的 RETURN_FORMAT_INSTRUCTION）。
    缺失/格式错误 → 返回空 ParsedReturnHeader。
    """
    if not final_text:
        return ParsedReturnHeader()

    status_match = STATUS_RE.search(final_text)
    summary_match = SUMMARY_RE.search(final_text)

    result = ParsedReturnHeader()
    if status_match:
        result.status = status_match.group(1).lower()
    if summary_match:
        result.summary = summary_match.group(1).strip()
    return result
