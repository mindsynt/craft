"""Edit tool — find and replace text in files."""

import difflib
import os
import re

from typing import Any

from .registry import RecoverableError, tool
from .utils import _resolve_path, _trim_diff


EDIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "文件的绝对路径"},
        "old_string": {"type": "string", "description": "要替换的文本"},
        "new_string": {"type": "string", "description": "替换后的文本"},
        "replace_all": {"type": "boolean", "description": "替换所有匹配项(默认 false)"},
    },
    "required": ["file_path", "old_string", "new_string"],
}


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n")


def _detect_line_ending(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _levenshtein(a: str, b: str) -> int:
    """Levenshtein distance."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[m][n]


def _find_string_fuzzy(content: str, old_string: str) -> str | None:
    """Try multiple strategies to find old_string in content (port of edit.ts Replacers)."""
    # 1. Exact match first
    if old_string in content:
        return old_string

    content_lines = content.split("\n")
    search_lines = old_string.split("\n")

    # 2. Line-trimmed match
    if search_lines[-1] == "":
        search_lines = search_lines[:-1]

    for i in range(len(content_lines) - len(search_lines) + 1):
        match = True
        for j in range(len(search_lines)):
            if content_lines[i + j].strip() != search_lines[j].strip():
                match = False
                break
        if match:
            # Reconstruct exact match
            return "\n".join(content_lines[i:i + len(search_lines)])

    # 3. Block anchor matching (first/last lines)
    if len(search_lines) >= 3:
        first_search = search_lines[0].strip()
        last_search = search_lines[-1].strip()

        candidates = []
        for i in range(len(content_lines)):
            if content_lines[i].strip() != first_search:
                continue
            for j in range(i + 2, len(content_lines)):
                if content_lines[j].strip() == last_search:
                    candidates.append((i, j))
                    break

        for start, end in candidates:
            actual_block = content_lines[start:end + 1]
            if len(actual_block) >= len(search_lines):
                # Similarity check
                total_sim = 0.0
                count = 0
                for k in range(1, min(len(search_lines), len(actual_block)) - 1):
                    orig = actual_block[k].strip()
                    srch = search_lines[k].strip()
                    max_len = max(len(orig), len(srch))
                    if max_len == 0:
                        continue
                    dist = _levenshtein(orig, srch)
                    total_sim += 1 - dist / max_len
                    count += 1
                avg_sim = total_sim / count if count > 0 else 0
                if avg_sim >= 0.3:
                    return "\n".join(actual_block)

    return None


@tool(name="edit", description="对文件执行文本替换编辑",
      parameters=EDIT_PARAMETERS)
async def edit(file_path: str, old_string: str, new_string: str,
               replace_all: bool = False) -> str:
    try:
        if old_string == new_string:
            return "无需修改: old_string 和 new_string 相同"

        filepath = _resolve_path(file_path)
        if not os.path.isfile(filepath):
            return f"[错误] 文件不存在: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        ending = _detect_line_ending(content)
        old_normalized = _normalize_line_endings(old_string)
        new_normalized = _normalize_line_endings(new_string)

        # Try exact match first, then fuzzy
        old_exact = _find_string_fuzzy(content, old_string)
        if old_exact is None:
            return f"[错误] 在文件中未找到匹配的文本.\n建议: 检查缩进和前后文是否与目标文件一致."

        matched = old_exact

        # Generate diff
        new_content = content.replace(matched, new_normalized, -1 if replace_all else 1)
        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(old_lines, new_lines,
                                                fromfile=filepath, tofile=filepath))
        diff_text = _trim_diff("".join(diff_lines)[:500])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        result = "编辑应用成功."
        if diff_text:
            result += f"\n差异:\n{diff_text[:400]}"
        return result
    except RecoverableError:
        raise
    except Exception as e:
        return f"[错误] {e}"


@tool(name="multiedit", description="对文件执行多次编辑操作",
      parameters={
          "type": "object",
          "properties": {
              "file_path": {"type": "string", "description": "文件的绝对路径"},
              "edits": {
                  "type": "array",
                  "items": {
                      "type": "object",
                      "properties": {
                          "old_string": {"type": "string"},
                          "new_string": {"type": "string"},
                          "replace_all": {"type": "boolean"},
                      },
                      "required": ["old_string", "new_string"],
                  },
              },
          },
          "required": ["file_path", "edits"],
      })
async def multiedit(file_path: str, edits: list[dict[str, Any]]) -> str:
    try:
        filepath = _resolve_path(file_path)
        results = []
        for entry in edits:
            r = await edit(
                file_path=filepath,
                old_string=entry.get("old_string", ""),
                new_string=entry.get("new_string", ""),
                replace_all=entry.get("replace_all", False),
            )
            if r.startswith("[错误]"):
                return f"编辑 #{len(results) + 1} 失败: {r}"
            results.append(r)
        return f"完成 {len(results)} 次编辑. 最后一次: {results[-1] if results else '无'}"
    except Exception as e:
        return f"[错误] {e}"
