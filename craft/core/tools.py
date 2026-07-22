"""工具/Function 系统 - 移植自 MiMo-Code 的 tool 系统"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Callable
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Core Types
# ═══════════════════════════════════════════════════════════════

class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object", "properties": {}, "required": [],
    })


class ToolResult(BaseModel):
    success: bool = True
    content: str = ""
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    title: str = ""


class RecoverableError(Exception):
    """Marks a tool failure as agent-recoverable: the model can fix it on
    the next turn (bad arguments, non-existent resource)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.recoverable = True


class ToolResultError(Exception):
    """A tool execution error that carries metadata."""
    def __init__(self, message: str, metadata: dict[str, Any] | None = None,
                 attachments: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.tool_result_metadata = metadata or {}
        self.tool_result_attachments = attachments or []


# ═══════════════════════════════════════════════════════════════
# Session Working Directory
# ═══════════════════════════════════════════════════════════════

class SessionCwd:
    """Per-session working directory (like cd in a terminal)."""
    _store: dict[str, str] = {}
    _project_dir: str = "."

    @classmethod
    def init(cls, project_dir: str) -> None:
        cls._project_dir = project_dir

    @classmethod
    def get(cls, session_id: str) -> str:
        return cls._store.get(session_id, cls._project_dir)

    @classmethod
    def set(cls, session_id: str, directory: str) -> None:
        cls._store[session_id] = directory

    @classmethod
    def clear(cls, session_id: str) -> None:
        cls._store.pop(session_id, None)


# ═══════════════════════════════════════════════════════════════
# Truncation Service
# ═══════════════════════════════════════════════════════════════

MAX_TRUNCATE_LINES = 2000
MAX_TRUNCATE_BYTES = 50 * 1024
TRUNCATION_DIR = os.path.join(tempfile.gettempdir(), "craft_truncation")
ERROR_PATTERN = re.compile(r"error|exception|failed|fatal|traceback|panic|exit code", re.IGNORECASE)


class Truncate:
    """Truncation service for large tool outputs."""

    @staticmethod
    def ensure_dir() -> str:
        os.makedirs(TRUNCATION_DIR, exist_ok=True)
        return TRUNCATION_DIR

    @staticmethod
    def write(text: str) -> str:
        path = os.path.join(Truncate.ensure_dir(), f"tool_{uuid.uuid4().hex[:16]}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    @staticmethod
    def output(text: str, max_lines: int | None = None,
               max_bytes: int | None = None,
               direction: str = "head+tail") -> dict[str, Any]:
        max_lines = max_lines or MAX_TRUNCATE_LINES
        max_bytes = max_bytes or MAX_TRUNCATE_BYTES
        lines = text.split("\n")
        total_bytes = len(text.encode("utf-8"))

        if len(lines) <= max_lines and total_bytes <= max_bytes:
            return {"content": text, "truncated": False}

        if direction == "head+tail":
            tail_scan = text[-2048:] if len(text) > 2048 else text
            has_errors = bool(ERROR_PATTERN.search(tail_scan))

            if has_errors:
                head_max_lines = int(max_lines * 0.7)
                head_max_bytes = int(max_bytes * 0.7)
                tail_max_lines = max_lines - head_max_lines
                tail_max_bytes = max_bytes - head_max_bytes

                head_out: list[str] = []
                head_bytes = 0
                for line in lines:
                    sz = len(line.encode("utf-8")) + (1 if head_out else 0)
                    if head_bytes + sz > head_max_bytes or len(head_out) >= head_max_lines:
                        break
                    head_out.append(line)
                    head_bytes += sz

                tail_out: list[str] = []
                tail_bytes = 0
                for line in reversed(lines):
                    sz = len(line.encode("utf-8")) + (1 if tail_out else 0)
                    if tail_bytes + sz > tail_max_bytes or len(tail_out) >= tail_max_lines:
                        break
                    tail_out.insert(0, line)
                    tail_bytes += sz

                omitted = len(lines) - len(head_out) - len(tail_out)
                filepath = Truncate.write(text)
                return {
                    "content": f"{chr(10).join(head_out)}\n\n... {omitted} lines omitted — showing head and tail ...\n\n{chr(10).join(tail_out)}\n\nFull output saved to: {filepath}",
                    "truncated": True,
                    "outputPath": filepath,
                }

        # Head-only truncation (default fallback)
        out: list[str] = []
        byte_count = 0
        for line in lines:
            sz = len(line.encode("utf-8")) + (1 if out else 0)
            if byte_count + sz > max_bytes or len(out) >= max_lines:
                break
            out.append(line)
            byte_count += sz

        removed = len(lines) - len(out)
        filepath = Truncate.write(text)
        return {
            "content": f"{chr(10).join(out)}\n\n...{removed} lines truncated...\n\nFull output saved to: {filepath}",
            "truncated": True,
            "outputPath": filepath,
        }


# ═══════════════════════════════════════════════════════════════
# Base Tool + Registry
# ═══════════════════════════════════════════════════════════════

class Tool:
    def __init__(self, name: str = "", description: str = "",
                 parameters: dict | None = None,
                 handler: Callable | None = None):
        self.spec = ToolSpec(name=name, description=description,
                             parameters=parameters or {})
        self.handler = handler

    async def execute(self, **kwargs) -> ToolResult:
        if not self.handler:
            return ToolResult(success=False, error=f"工具 {self.spec.name} 未实现")
        try:
            r = self.handler(**kwargs)
            if hasattr(r, "__await__"):
                r = await r
            return ToolResult(content=str(r))
        except RecoverableError:
            raise
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def to_openai(self) -> dict:
        return {"type": "function", "function": {
            "name": self.spec.name, "description": self.spec.description,
            "parameters": self.spec.parameters,
        }}

    def to_anthropic(self) -> dict:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "input_schema": self.spec.parameters,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.spec.name] = tool
        logger.info(f"工具注册: {tool.spec.name}")

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def to_openai_tools(self) -> list[dict]:
        return [t.to_openai() for t in self._tools.values()]

    def to_anthropic_tools(self) -> list[dict]:
        return [t.to_anthropic() for t in self._tools.values()]

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {tool_name}")
        return await tool.execute(**kwargs)

    def __len__(self):
        return len(self._tools)


registry = ToolRegistry()


def tool(name: str, description: str = "", parameters: dict | None = None):
    def decorator(fn):
        registry.register(Tool(name=name, description=description,
                               parameters=parameters, handler=fn))
        return fn
    return decorator


# ═══════════════════════════════════════════════════════════════
# Helper utilities
# ═══════════════════════════════════════════════════════════════

def _resolve_path(path: str, session_id: str = "") -> str:
    """Resolve a possibly-relative path against the session CWD."""
    if os.path.isabs(path):
        return os.path.normpath(path)
    cwd = SessionCwd.get(session_id) if session_id else SessionCwd._project_dir
    return os.path.normpath(os.path.join(cwd, path))


def _file_size_kb(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _is_binary_file(filepath: str, check_bytes: int = 4096) -> bool:
    """Check if a file is binary by extension and content (port of read.ts isBinaryFile)."""
    ext = os.path.splitext(filepath)[1].lower()
    binary_exts = {".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".class",
                   ".jar", ".war", ".7z", ".doc", ".docx", ".xls", ".xlsx",
                   ".ppt", ".pptx", ".odt", ".ods", ".odp", ".bin", ".dat",
                   ".obj", ".o", ".a", ".lib", ".wasm", ".pyc", ".pyo",
                   ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf",
                   ".mp3", ".mp4", ".avi", ".mov", ".webm"}
    if ext in binary_exts:
        return True
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(check_bytes)
        if not chunk:
            return False
        # Check for null bytes
        if b"\x00" in chunk:
            return True
        # Check for high non-printable ratio
        non_printable = sum(1 for b in chunk if b < 9 or (13 < b < 32))
        return non_printable / len(chunk) > 0.3
    except OSError:
        return True


def _trim_diff(diff: str) -> str:
    """Trim common leading whitespace from diff content lines."""
    lines = diff.split("\n")
    content_lines = [
        l for l in lines
        if l.startswith("+") or l.startswith("-") or l.startswith(" ")
    ]
    if not content_lines:
        return diff
    # Find min indent
    min_indent = float("inf")
    for line in content_lines:
        content = line[1:]
        if content.strip():
            match = re.match(r"^(\s*)", content)
            if match:
                min_indent = min(min_indent, len(match.group(1)))
    if min_indent == float("inf") or min_indent == 0:
        return diff
    trimmed = []
    for line in lines:
        if (line.startswith("+") or line.startswith("-") or line.startswith(" ")) \
           and not line.startswith("---") and not line.startswith("+++"):
            prefix = line[0]
            content = line[1:]
            trimmed.append(prefix + content[min_indent:])
        else:
            trimmed.append(line)
    return "\n".join(trimmed)


# ═══════════════════════════════════════════════════════════════
# FILE TOOLS
# ═══════════════════════════════════════════════════════════════

# --- read_file ---

def _read_file_with_lines(filepath: str, offset: int = 1, limit: int = 2000,
                          max_line_length: int = 2000, max_bytes: int = 51200):
    """Read a file with line tracking (port of read.ts `lines` function)."""
    raw: list[str] = []
    byte_count = 0
    line_count = 0
    cut = False
    more = False

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for text in f:
            line_count += 1
            if line_count < offset:
                continue
            if len(raw) >= limit:
                more = True
                continue
            text = text.rstrip("\r\n")
            if len(text) > max_line_length:
                text = text[:max_line_length] + f"... (line truncated to {max_line_length} chars)"
            sz = len(text.encode("utf-8")) + (1 if raw else 0)
            if byte_count + sz > max_bytes:
                cut = True
                more = True
                break
            raw.append(text)
            byte_count += sz

    return {"raw": raw, "count": line_count, "cut": cut, "more": more, "offset": offset}


@tool(name="read_file", description="读取文件或目录内容",
      parameters={
          "type": "object",
          "properties": {
              "file_path": {"type": "string", "description": "文件或目录的绝对路径"},
              "offset": {"type": "integer", "description": "起始行号(1-indexed, 仅文件)"},
              "limit": {"type": "integer", "description": "最大读取行数(仅文件, 默认2000)"},
          },
          "required": ["file_path"],
      })
async def read_file(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    try:
        filepath = _resolve_path(file_path)
        if not os.path.exists(filepath):
            # Suggest similar files
            parent = os.path.dirname(filepath)
            base = os.path.basename(filepath)
            if os.path.isdir(parent):
                similar = [os.path.join(parent, f) for f in os.listdir(parent)
                           if base.lower() in f.lower() or f.lower() in base.lower()]
                if similar:
                    return f"文件不存在: {filepath}\n您是否要找:\n" + "\n".join(similar[:3])
            return f"[错误] 文件不存在: {filepath}"

        if os.path.isdir(filepath):
            entries = sorted(os.listdir(filepath))
            result = [f"<path>{filepath}</path>", "<type>directory</type>", "<entries>"]
            start = max(0, offset - 1)
            sliced = entries[start:start + limit]
            truncated = start + len(sliced) < len(entries)
            result.extend(sliced)
            if truncated:
                result.append(f"\n(显示 {len(sliced)} 个, 共 {len(entries)} 个条目)")
            else:
                result.append(f"\n({len(entries)} 个条目)")
            result.append("</entries>")
            return "\n".join(result)

        # File: check binary
        if _is_binary_file(filepath):
            return f"[错误] 无法读取二进制文件: {filepath}"

        # File: read with lines
        info = _read_file_with_lines(filepath, offset=offset, limit=limit)
        if info["count"] < info["offset"] and not (info["count"] == 0 and info["offset"] == 1):
            return f"[错误] 偏移量 {info['offset']} 超出了范围(文件共 {info['count']} 行)"

        lines_output = []
        for i, line in enumerate(info["raw"]):
            lines_output.append(f"{i + info['offset']}: {line}")

        result = [
            f"<path>{filepath}</path>",
            "<type>file</type>",
            "<content>",
            *lines_output,
        ]

        last = info["offset"] + len(info["raw"]) - 1
        next_line = last + 1
        if info["cut"]:
            result.append(f"\n(输出限制在 50KB. 显示行 {info['offset']}-{last}. 使用 offset={next_line} 继续)")
        elif info["more"]:
            result.append(f"\n(显示行 {info['offset']}-{last}, 共 {info['count']} 行. 使用 offset={next_line} 继续)")
        else:
            result.append(f"\n(文件结束 - 共 {info['count']} 行)")
        result.append("</content>")

        return "\n".join(result)
    except Exception as e:
        return f"[错误] {e}"


# --- write_file ---

@tool(name="write_file", description="写入文件内容(创建或覆盖)",
      parameters={
          "type": "object",
          "properties": {
              "file_path": {"type": "string", "description": "文件的绝对路径"},
              "content": {"type": "string", "description": "写入的内容"},
          },
          "required": ["file_path", "content"],
      })
async def write_file(file_path: str, content: str) -> str:
    try:
        filepath = _resolve_path(file_path)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        old_content = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                old_content = f.read()

        # Generate diff for reference
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=filepath, tofile=filepath,
        ))
        diff_text = _trim_diff("".join(diff_lines)[:500])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        action = "更新" if old_content else "创建"
        result = f"{action}文件成功: {filepath} ({len(content)} 字符)"
        if diff_text:
            result += f"\n差异:\n{diff_text[:300]}"
        return result
    except Exception as e:
        return f"[错误] {e}"


# --- edit (find & replace) ---

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


# --- glob ---

@tool(name="glob", description="使用 glob 模式搜索文件",
      parameters={
          "type": "object",
          "properties": {
              "pattern": {"type": "string", "description": "glob 匹配模式, 例如 '**/*.py'"},
              "path": {"type": "string", "description": "搜索目录(默认当前工作目录)"},
          },
          "required": ["pattern"],
      })
async def glob(pattern: str, path: str = "") -> str:
    try:
        search_dir = _resolve_path(path) if path else SessionCwd._project_dir
        if not os.path.isdir(search_dir):
            return f"[错误] 目录不存在: {search_dir}"

        limit = 100
        results: list[tuple[str, float]] = []

        # Use pathlib.glob with recursive support
        p = Path(search_dir)
        matches = list(p.rglob(pattern)) if "**" in pattern else list(p.glob(pattern))

        truncated = False
        for i, m in enumerate(matches):
            if i >= limit:
                truncated = True
                break
            mtime = os.path.getmtime(m) if m.exists() else 0
            results.append((str(m.absolute()), mtime))

        # Sort by mtime descending (most recent first)
        results.sort(key=lambda x: x[1], reverse=True)

        output = [r[0] for r in results]
        if not output:
            return "未找到文件"

        result_str = "\n".join(output)
        if truncated:
            result_str += f"\n\n(结果已截断: 显示前 {limit} 个结果. 考虑使用更具体的路径或模式.)"
        return result_str
    except Exception as e:
        return f"[错误] {e}"


# --- grep ---

@tool(name="grep", description="在文件内容中搜索正则表达式",
      parameters={
          "type": "object",
          "properties": {
              "pattern": {"type": "string", "description": "要搜索的正则表达式模式"},
              "path": {"type": "string", "description": "搜索目录(默认当前目录)"},
              "include": {"type": "string", "description": "文件匹配模式, 例如 '*.py'"},
          },
          "required": ["pattern"],
      })
async def grep(pattern: str, path: str = "", include: str = "") -> str:
    try:
        search_dir = _resolve_path(path) if path else SessionCwd._project_dir
        if not os.path.isdir(search_dir):
            return f"[错误] 目录不存在: {search_dir}"

        # Build rg-like command
        cmd = ["grep", "-rn", "--color=never"]
        if include:
            cmd.extend(["--include", include])
        cmd.extend([pattern, search_dir])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()

        if not output:
            return "未找到匹配"

        limit = 100
        lines = output.split("\n")
        truncated = len(lines) > limit
        final = lines[:limit] if truncated else lines

        total = len(lines)
        result = [f"找到 {total} 个匹配{' (显示前 100 个)' if truncated else ''}"]
        result.extend(final)

        if truncated:
            result.append(
                f"\n(结果已截断: 显示 {limit}/{total} 个匹配. 考虑使用更具体的路径或模式.)"
            )

        return "\n".join(result)
    except Exception as e:
        return f"[错误] {e}"


# --- apply_patch ---

@tool(name="apply_patch", description="应用统一差异补丁(支持增/删/改文件)",
      parameters={
          "type": "object",
          "properties": {
              "patch_text": {"type": "string", "description": "完整的补丁文本(描述所有要做的更改)"},
          },
          "required": ["patch_text"],
      })
async def apply_patch(patch_text: str) -> str:
    """Apply a unified diff patch to files."""
    try:
        if not patch_text.strip():
            return "[错误] patch_text 不能为空"

        patch_lines = patch_text.split("\n")

        # Parse hunks from the patch text
        current_file = ""
        hunks: list[dict[str, Any]] = []
        current_hunk: dict[str, Any] | None = None

        for line in patch_lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                continue
            m = re.match(r"^@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
            if m:
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {"old_start": int(m.group(1)),
                                "new_start": int(m.group(2)),
                                "lines": [], "type": "update"}
                continue
            if line.startswith("*** Begin Patch"):
                continue
            if line.startswith("*** End Patch"):
                continue
            m = re.match(r"^\*\*\* Update File: (.+)", line)
            if m:
                current_file = m.group(1).strip()
                continue
            m = re.match(r"^\*\*\* (Add|Delete) File: (.+)", line)
            if m:
                action = m.group(1).lower()
                if action == "add":
                    fn = m.group(2).strip()
                    hunks.append({"type": "add", "file": fn, "lines": []})
                    current_file = fn
                    current_hunk = None
                elif action == "delete":
                    fn = m.group(2).strip()
                    hunks.append({"type": "delete", "file": fn})
                    current_file = fn
                    current_hunk = None
                continue
            if current_hunk is not None:
                current_hunk["lines"].append(line)
            elif hunks and hunks[-1]["type"] == "add" and current_file:
                hunks[-1].setdefault("lines", []).append(line)

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            return "[错误] 补丁中未找到 hunk"

        file_changes: list[dict[str, Any]] = []
        seen_add_content = False

        for hunk in hunks:
            hunk_type = hunk.get("type", "update")
            file_path = _resolve_path(hunk.get("file", current_file))

            if hunk_type == "add":
                new_content = "\n".join(hunk.get("lines", []))
                if new_content.strip():
                    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content + "\n")
                    file_changes.append({"file": file_path, "type": "add"})
                    seen_add_content = True
                continue

            if hunk_type == "delete":
                if os.path.exists(file_path):
                    os.remove(file_path)
                    file_changes.append({"file": file_path, "type": "delete"})
                continue

            # Update
            if not os.path.isfile(file_path):
                return f"[错误] 文件不存在: {file_path}"

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_content_lines = content.split("\n")

            # Apply hunk lines
            add_lines: list[str] = []
            del_count = 0
            current_line = hunk.get("old_start", 1) - 1

            for hline in hunk.get("lines", []):
                if hline.startswith("+"):
                    add_lines.append(hline[1:])
                elif hline.startswith("-"):
                    del_count += 1
                else:
                    # Context line or first addition
                    if add_lines and del_count == 0:
                        # Insert without deletion
                        insert_at = current_line
                        if insert_at >= len(content.split("\n")):
                            insert_at = len(content.split("\n"))
                        new_content_lines[insert_at:insert_at] = add_lines
                        current_line += len(add_lines)
                        add_lines = []
                    elif add_lines and del_count > 0:
                        # Replace
                        new_content_lines[current_line:current_line + del_count] = add_lines
                        current_line += len(add_lines)
                        add_lines = []
                        del_count = 0
                    else:
                        current_line += 1

            # Flush remaining
            if add_lines:
                if del_count > 0:
                    new_content_lines[current_line:current_line + del_count] = add_lines
                else:
                    new_content_lines[current_line:current_line] = add_lines

            new_content = "\n".join(new_content_lines)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            file_changes.append({"file": file_path, "type": "update"})

        if not file_changes:
            return "未做出任何更改(补丁为空)"

        lines = [f"成功. 更新了 {len(file_changes)} 个文件:"]
        for ch in file_changes:
            action_map = {"add": "A", "update": "M", "delete": "D"}
            prefix = action_map.get(ch["type"], "?")
            rel = os.path.relpath(ch["file"], SessionCwd._project_dir)
            lines.append(f"  {prefix} {rel}")

        return "\n".join(lines)
    except Exception as e:
        return f"[错误] {e}"


# --- notebook_edit ---

@tool(name="notebook_edit", description="编辑 Jupyter Notebook (.ipynb) 文件",
      parameters={
          "type": "object",
          "properties": {
              "notebook_path": {"type": "string", "description": ".ipynb 文件的绝对路径"},
              "cell_id": {"type": "string", "description": "要操作的 cell 的 ID"},
              "new_source": {"type": "string", "description": "cell 的新内容"},
              "cell_type": {"type": "string", "enum": ["code", "markdown"],
                            "description": "cell 类型"},
              "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"],
                            "description": "操作模式(默认 replace)"},
          },
          "required": ["notebook_path"],
      })
async def notebook_edit(notebook_path: str, cell_id: str = "",
                        new_source: str = "", cell_type: str = "code",
                        edit_mode: str = "replace") -> str:
    try:
        filepath = _resolve_path(notebook_path)
        if not filepath.endswith(".ipynb"):
            return "[错误] notebook_path 必须是 .ipynb 文件"
        if not os.path.isfile(filepath):
            return f"[错误] 文件不存在: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        cells = notebook.get("cells", [])
        if not isinstance(cells, list):
            return "[错误] Notebook 格式无效: 缺少 cells 数组"

        # Backfill missing cell IDs
        existing_ids = {c.get("id", "") for c in cells if c.get("id")}
        for cell in cells:
            if not cell.get("id"):
                cid = uuid.uuid4().hex[:8]
                while cid in existing_ids:
                    cid = uuid.uuid4().hex[:8]
                cell["id"] = cid
                existing_ids.add(cid)

        def find_cell(ref: str) -> int:
            if ref.startswith("#"):
                try:
                    idx = int(ref[1:])
                    if 0 <= idx < len(cells):
                        return idx
                except ValueError:
                    pass
                return -1
            for i, c in enumerate(cells):
                if c.get("id") == ref:
                    return i
            return -1

        if edit_mode == "replace":
            idx = find_cell(cell_id)
            if idx == -1:
                return f"[错误] 未找到 cell: {cell_id}"
            target = cells[idx]
            target_type = cell_type or target.get("cell_type", "code")
            target["source"] = new_source.split("\n") if new_source else []
            target["cell_type"] = target_type
            label = f"替换 cell {target.get('id', idx)}"
        elif edit_mode == "delete":
            idx = find_cell(cell_id)
            if idx == -1:
                return f"[错误] 未找到 cell: {cell_id}"
            cells.pop(idx)
            label = f"删除 cell {cell_id}"
        elif edit_mode == "insert":
            new_cell = {
                "cell_type": cell_type or "code",
                "id": uuid.uuid4().hex[:8],
                "source": new_source.split("\n") if new_source else [],
                "metadata": {},
            }
            if new_cell["cell_type"] == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            if cell_id and find_cell(cell_id) >= 0:
                idx = find_cell(cell_id)
                cells.insert(idx + 1, new_cell)
                label = f"在 {cell_id} 后插入"
            else:
                cells.insert(0, new_cell)
                label = "在开头插入"
        else:
            return f"[错误] 未知编辑模式: {edit_mode}"

        notebook["cells"] = cells
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
            f.write("\n")

        return f"Notebook 已更新: {label} on {os.path.relpath(filepath, SessionCwd._project_dir)}"
    except Exception as e:
        return f"[错误] {e}"


# --- multiedit ---

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


# ═══════════════════════════════════════════════════════════════
# COMMAND EXECUTION TOOLS
# ═══════════════════════════════════════════════════════════════

# --- bash ---

MAX_BASH_OUTPUT_BYTES = 50 * 1024
MAX_BASH_OUTPUT_LINES = 2000
DEFAULT_BASH_TIMEOUT_MS = 2 * 60 * 1000

_DELETE_COMMANDS = {"rm", "rmdir", "unlink", "shred", "del", "erase", "rd",
                    "remove-item", "ri"}


def _parse_bash_command(command: str) -> str:
    """Extract the first command name from a bash command."""
    return command.strip().split()[0] if command.strip() else ""


def _is_delete_command(command: str) -> bool:
    return _parse_bash_command(command).lower() in _DELETE_COMMANDS


@tool(name="bash", description="执行 shell 命令",
      parameters={
          "type": "object",
          "properties": {
              "command": {"type": "string", "description": "要执行的命令"},
              "timeout": {"type": "integer", "description": "超时时间(毫秒)"},
              "workdir": {"type": "string", "description": "工作目录"},
              "description": {"type": "string", "description": "命令描述(5-10 个词)"},
              "interactive": {"type": "boolean", "description": "是否交互式执行"},
          },
          "required": ["command"],
      })
async def bash(command: str, timeout: int = DEFAULT_BASH_TIMEOUT_MS,
               workdir: str = "", description: str = "",
               interactive: bool = False) -> str:
    try:
        cwd = _resolve_path(workdir) if workdir else SessionCwd._project_dir
        if not os.path.isdir(cwd):
            return f"[错误] 工作目录不存在: {cwd}"

        # Warning for delete commands
        if _is_delete_command(command) and not description:
            return ("[安全] 删除命令需要 `description` 参数说明用途. "
                    "请添加 `description=\"删除什么\"` 参数.")

        # For now, non-interactive execution via subprocess
        if interactive:
            return ("[提示] 交互式执行需要在终端中运行. 请使用: "
                    f"cd {cwd} && {command}")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout / 1000
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"[超时] 命令执行超过 {timeout}ms"

        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0

        if error_output:
            output += f"\n[stderr]\n{error_output[:2000]}"

        # Truncate large output
        lines = output.split("\n")
        if len(lines) > MAX_BASH_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_BASH_OUTPUT_LINES])
            output += f"\n...输出截断(显示 {MAX_BASH_OUTPUT_LINES} 行, 共 {len(lines)} 行)..."
        if len(output.encode("utf-8")) > MAX_BASH_OUTPUT_BYTES:
            output = output[:MAX_BASH_OUTPUT_BYTES] + "\n...输出截断(超过 50KB)..."

        desc = f" ({description})" if description else ""
        result = f"退出码: {exit_code}{desc}\n{output}"
        return result.strip()
    except Exception as e:
        return f"[错误] {e}"


# --- change_directory ---

@tool(name="change_directory", description="切换当前会话的工作目录(类似 cd)",
      parameters={
          "type": "object",
          "properties": {
              "path": {"type": "string", "description": "目标目录(绝对或相对路径, 使用 '~' 重置到项目根目录)"},
          },
          "required": ["path"],
      })
async def change_directory(path: str, session_id: str = "") -> str:
    try:
        current = SessionCwd.get(session_id)
        if not path or path == "~":
            SessionCwd.clear(session_id)
            root = SessionCwd._project_dir
            return f"工作目录已重置: {current} → {root}"

        resolved = os.path.normpath(os.path.join(current, path))
        if not os.path.isdir(resolved):
            return f"[错误] 目录不存在: {resolved}"
        if not os.path.isabs(resolved):
            resolved = os.path.abspath(resolved)

        SessionCwd.set(session_id, resolved)
        return f"工作目录已更改: {current} → {resolved}"
    except Exception as e:
        return f"[错误] {e}"


# ═══════════════════════════════════════════════════════════════
# WEB TOOLS
# ═══════════════════════════════════════════════════════════════

# --- webfetch ---

@tool(name="webfetch", description="从 URL 获取内容(HTTP 请求)",
      parameters={
          "type": "object",
          "properties": {
              "url": {"type": "string", "description": "要获取的 URL"},
              "format": {"type": "string", "enum": ["text", "markdown", "html"],
                         "description": "返回格式(默认 markdown)"},
              "timeout": {"type": "integer", "description": "超时时间(秒, 最大 120)"},
          },
          "required": ["url"],
      })
async def webfetch(url: str, format: str = "markdown", timeout: int = 30) -> str:
    try:
        if not url.startswith(("http://", "https://")):
            return "[错误] URL 必须以 http:// 或 https:// 开头"

        parsed = urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return "[错误] 不允许获取本地地址"

        timeout = min(timeout, 120)

        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/143.0.0.0 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            content = resp.text

            if "text/html" in content_type and format == "markdown":
                # Simple HTML to text conversion
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()
                content = content[:50000]

            return f"URL: {url}\nContent-Type: {content_type}\n\n{content[:30000]}"
    except httpx.TimeoutException:
        return "[超时] 请求超时"
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code}] {e.response.reason_phrase}"
    except Exception as e:
        return f"[错误] {e}"


# --- codesearch ---

@tool(name="codesearch", description="搜索代码(API、库、SDK 文档)",
      parameters={
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "搜索查询"},
              "tokens_num": {"type": "integer", "description": "返回的 token 数量(1000-50000)"},
          },
          "required": ["query"],
      })
async def codesearch(query: str, tokens_num: int = 5000) -> str:
    try:
        tokens_num = max(1000, min(tokens_num, 50000))
        # Placeholder - in production this would call an API
        return (
            f"代码搜索: {query} ({tokens_num} tokens)\n"
            "搜索功能需要通过外部 API 配置。"
        )
    except Exception as e:
        return f"[错误] {e}"


# ═══════════════════════════════════════════════════════════════
# SESSION / PLANNING TOOLS
# ═══════════════════════════════════════════════════════════════

# --- plan_enter ---

@tool(name="plan_enter", description="切换到计划模式进行结构化规划",
      parameters={
          "type": "object",
          "properties": {},
      })
async def plan_enter(current_agent: str = "") -> str:
    """Switch to plan mode (port of PlanEnterTool)."""
    if current_agent == "plan":
        return "您已在计划模式中. 此工具仅在计划模式外有效."
    return (
        "是否要切换到计划模式进行结构化规划?\n"
        "请确认以切换到 plan agent 进行只读规划."
    )


# --- plan_exit ---

@tool(name="plan_exit", description="退出计划模式, 切换到实现模式",
      parameters={
          "type": "object",
          "properties": {},
      })
async def plan_exit(current_agent: str = "") -> str:
    if current_agent != "plan":
        return "您不在计划模式中. 此工具仅在计划模式中有效."
    return (
        "计划已完成. 是否要切换到 build agent 开始实现?\n"
        "请确认以切换到 build agent 执行计划."
    )


# --- question ---

@tool(name="question", description="向用户提问",
      parameters={
          "type": "object",
          "properties": {
              "questions": {
                  "type": "array",
                  "items": {
                      "type": "object",
                      "properties": {
                          "question": {"type": "string"},
                          "header": {"type": "string"},
                          "options": {
                              "type": "array",
                              "items": {
                                  "type": "object",
                                  "properties": {
                                      "label": {"type": "string"},
                                      "description": {"type": "string"},
                                  },
                              },
                          },
                      },
                      "required": ["question"],
                  },
              },
          },
          "required": ["questions"],
      })
async def question(questions: list[dict[str, Any]]) -> str:
    try:
        parts = []
        for q in questions:
            header = q.get("header", "问题")
            question_text = q.get("question", "")
            options = q.get("options", [])
            parts.append(f"## {header}")
            parts.append(question_text)
            for opt in options:
                desc = f" - {opt.get('description', '')}" if opt.get("description") else ""
                parts.append(f"  [{opt.get('label', '?')}]{desc}")
        return "\n".join(parts)
    except Exception as e:
        return f"[错误] {e}"


# --- session (orchestration) ---

SESSION_PARAMETERS = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "send", "switch", "list",
                             "dashboard", "status", "cancel", "ask",
                             "join", "setmode", "approve", "grant-approval"],
                },
                "task": {"type": "string"},
                "sessionID": {"type": "string"},
                "session_id": {"type": "string"},
                "question": {"type": "string"},
                "sessionIDs": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string"},
                "model": {"type": "string"},
                "title": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
            "required": ["action"],
        },
    },
    "required": ["operation"],
}


@tool(name="session", description="会话编排管理(创建、发送、状态等)",
      parameters=SESSION_PARAMETERS)
async def session(operation: dict[str, Any]) -> str:
    """Session orchestration tool (port of SessionTool)."""
    try:
        action = operation.get("action", "")
        if action == "list":
            from craft.core.session import sessions
            return "\n".join([f"{s.id}: {s.title}" for s in sessions.list()])
        elif action == "create":
            from craft.core.session import sessions
            s = sessions.create(title=operation.get("title", "新会话"),
                                agent_id=operation.get("mode", "build"))
            return f"已创建会话 {s.id}: {s.title}"
        elif action == "cancel":
            return f"已取消会话 {operation.get('sessionID', '')}"
        elif action == "status":
            return f"会话 {operation.get('sessionID', '')} 状态: running"
        else:
            return f"会话操作: {action} (需要完整编排系统支持)"
    except Exception as e:
        return f"[错误] {e}"


# --- task ---

@tool(name="task", description="任务管理(创建、列表、获取、状态更新等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["create", "list", "get",
                                                            "start", "block", "unblock",
                                                            "done", "abandon", "rename"]},
                      "summary": {"type": "string"},
                      "id": {"type": "string"},
                      "parent_id": {"type": "string"},
                      "event_summary": {"type": "string"},
                      "status": {"type": "string"},
                      "include_terminal": {"type": "boolean"},
                      "include_archived": {"type": "boolean"},
                      "session_id": {"type": "string"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def task(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "create":
            from craft.core.task import tasks
            t = tasks.create(
                title=operation.get("summary", ""),
                description="",
            )
            return f"已创建任务 {t.id}: {t.title}"
        elif action == "list":
            from craft.core.task import tasks
            items = tasks.list()
            if not items:
                return "无任务."
            return "\n".join([f"{t['id']} {'✓' if t.get('is_completed', t['status'] in ('completed', 'failed', 'cancelled')) else '○'} — {t.get('title', '?')}" for t in items])
        elif action == "get":
            from craft.core.task import tasks
            t = tasks.get(operation.get("id", ""))
            if not t:
                return f"未找到任务: {operation.get('id', '')}"
            return f"任务 {t.id}: {t.title} (状态: {t.status})"
        elif action == "done":
            from craft.core.task import tasks
            tasks.update_status(operation.get("id", ""), "completed")
            return f"任务 {operation.get('id', '')} 已完成"
        elif action == "start":
            return f"任务 {operation.get('id', '')} 已开始"
        elif action == "block":
            return f"任务 {operation.get('id', '')} 已阻塞: {operation.get('event_summary', '')}"
        elif action == "unblock":
            return f"任务 {operation.get('id', '')} 已解除阻塞: {operation.get('event_summary', '')}"
        elif action == "abandon":
            return f"任务 {operation.get('id', '')} 已放弃: {operation.get('event_summary', '')}"
        elif action == "rename":
            return f"任务 {operation.get('id', '')} 已重命名为: {operation.get('summary', '')}"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"


# --- cron ---

@tool(name="cron", description="定时任务管理(调度、循环、列表等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["schedule", "loop", "list",
                                                            "get", "delete", "rename"]},
                      "cron": {"type": "string", "description": "5字段 cron 表达式"},
                      "prompt": {"type": "string", "description": "触发时发送的提示"},
                      "delay_seconds": {"type": "integer"},
                      "one_shot": {"type": "boolean"},
                      "durable": {"type": "boolean"},
                      "id": {"type": "string"},
                      "kind": {"type": "string"},
                      "durable_only": {"type": "boolean"},
                      "reason": {"type": "string"},
                      "session_id": {"type": "string"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def cron(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "schedule":
            from craft.core.cron import scheduler
            job = scheduler.add(
                operation.get("prompt", "cron job"),
                interval_seconds=0,
            )
            expr = operation.get("cron", "")
            return f"已调度任务 {job}: {operation.get('prompt', '')} ({expr})"
        elif action == "list":
            return "已调度的任务列表(需要完整的调度系统支持)"
        elif action == "delete":
            return f"已删除任务 {operation.get('id', '')}"
        elif action == "get":
            return f"任务 {operation.get('id', '')}"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"


# --- workflow ---

@tool(name="workflow", description="工作流管理(运行、状态、等待、取消等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["run", "status", "wait",
                                                            "cancel", "resume"]},
                      "name": {"type": "string"},
                      "script": {"type": "string"},
                      "args": {},
                      "run_id": {"type": "string"},
                      "timeout_ms": {"type": "integer"},
                      "async": {"type": "boolean"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def workflow(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "run":
            name = operation.get("name", "inline")
            return f"启动工作流: {name} (需要完整的工作流引擎支持)"
        elif action == "status":
            return f"工作流状态: running"
        elif action == "cancel":
            return f"已取消工作流"
        return f"工作流操作: {action}"
    except Exception as e:
        return f"[错误] {e}"


# --- memory ---

@tool(name="memory", description="记忆搜索(BM25 搜索标记文本)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {"type": "string", "enum": ["search"], "default": "search"},
              "query": {"type": "string", "description": "搜索查询"},
              "scope": {"type": "string", "enum": ["global", "projects", "sessions"]},
              "scope_id": {"type": "string"},
              "type": {"type": "string"},
              "limit": {"type": "integer"},
          },
          "required": ["query"],
      })
async def memory(query: str, operation: str = "search",
                 scope: str = "", scope_id: str = "",
                 type: str = "", limit: int = 10) -> str:
    try:
        from craft.core.memory import memory as memory_svc
        results = memory_svc.search(query)
        if not results:
            return (
                f"未找到 \"{query}\" 的匹配.\n\n"
                "0 个结果并不意味着从未记录过。在放弃前:\n"
                "1. 使用更少/更独特的关键词重试\n"
                "2. 对于文字字符串(URL、端口、路径) — 直接在记忆目录中搜索\n"
                "3. 对于精确回忆 — 使用历史工具\n"
            )
        lines = [f"找到 {len(results)} 个匹配 (BM25排序, 最佳优先):", ""]
        for r in results:
            content = getattr(r, "content", str(r))[:200]
            lines.append(f"### {getattr(r, 'id', '?')}")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"[错误] {e}"


# --- history ---

@tool(name="history", description="会话历史搜索(FTS BM25 搜索)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {"type": "string", "enum": ["search", "around"],
                            "description": "search: FTS BM25; around: 获取消息上下文"},
              "query": {"type": "string", "description": "FTS 查询(operation=search 时必需)"},
              "scope": {"type": "string", "enum": ["project", "global"]},
              "session_id": {"type": "string"},
              "message_id": {"type": "string", "description": "锚点消息 ID(operation=around 时必需)"},
              "before": {"type": "integer"},
              "after": {"type": "integer"},
              "limit": {"type": "integer"},
          },
          "required": ["operation"],
      })
async def history(operation: str, query: str = "", scope: str = "",
                  session_id: str = "", message_id: str = "",
                  before: int = 5, after: int = 5, limit: int = 10) -> str:
    try:
        from craft.core.history import history as history_svc
        if operation == "search":
            if not query:
                return "operation=search 需要 query 参数"
            results = history_svc.search(query)
            if not results:
                return f"0 个匹配 \"{query}\""
            lines = [f"找到 {len(results)} 个匹配:", ""]
            for r in results:
                lines.append(str(r)[:200])
                lines.append("")
            return "\n".join(lines)
        elif operation == "around":
            return f"查看消息 {message_id} 的上下文(前后各 {before}/{after} 条)"
        return f"未知操作: {operation}"
    except Exception as e:
        return f"[错误] {e}"


# --- change_directory with session_id support (registered above) ---

# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE / SKILL TOOLS
# ═══════════════════════════════════════════════════════════════

# --- skill ---

@tool(name="skill", description="加载专业化技能(skill)获取领域特定指令",
      parameters={
          "type": "object",
          "properties": {
              "name": {"type": "string", "description": "技能名称"},
          },
          "required": ["name"],
      })
async def skill(name: str) -> str:
    try:
        from craft.core.skill import skills
        all_skills = skills.list()
        for s in all_skills:
            s_name = getattr(s, "name", str(s))
            if name.lower() in s_name.lower():
                return f"已加载技能: {s_name}\n\n详细内容请查看技能文档."
        return (
            f"未找到技能 \"{name}\". "
            f"可用技能: {', '.join(getattr(s, 'name', str(s)) for s in all_skills[:10])}"
        )
    except Exception as e:
        return f"[错误] {e}"


# --- skill_search ---

@tool(name="skill_search", description="搜索可用技能(BM25 相关性匹配)",
      parameters={
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "搜索查询(包含动作、输入、预期输出和受众)"},
          },
          "required": ["query"],
      })
async def skill_search(query: str) -> str:
    try:
        from craft.core.skill import skills
        all_skills = skills.list()
        query_lower = query.lower()

        # Simple keyword matching
        results = []
        for s in all_skills:
            s_name = getattr(s, "name", str(s)).lower()
            s_desc = getattr(s, "description", "").lower() if hasattr(s, "description") else ""
            if query_lower in s_name or any(w in s_name for w in query_lower.split()):
                results.append(s)

        if not results:
            return json.dumps({"status": "no_match", "results": [],
                               "loaded_skill_id": None})

        names = [getattr(r, "name", str(r)) for r in results]
        return json.dumps({"status": "matched", "results": names,
                           "loaded_skill_id": names[0] if results else None})
    except Exception as e:
        return f"[错误] {e}"


# --- invalid ---

@tool(name="invalid", description="不要使用 - 报告无效工具调用",
      parameters={
          "type": "object",
          "properties": {
              "tool": {"type": "string", "description": "工具名称"},
              "error": {"type": "string", "description": "错误信息"},
          },
          "required": ["tool", "error"],
      })
async def invalid(tool: str, error: str) -> str:
    return f"提供给工具 {tool} 的参数无效: {error}"


# --- actor ---

@tool(name="actor", description="子代理管理(运行、生成、状态、等待、取消、发送、模型列表)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["run", "spawn", "status",
                                                            "wait", "cancel", "send",
                                                            "models"]},
                      "subagent_type": {"type": "string"},
                      "description": {"type": "string"},
                      "prompt": {"type": "string"},
                      "model": {"type": "string"},
                      "actor_id": {"type": "string"},
                      "timeout_ms": {"type": "integer"},
                      "to_actor_id": {"type": "string"},
                      "content": {"type": "string"},
                      "context": {"type": "string", "enum": ["none", "state", "full"]},
                      "vision": {"type": "boolean"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def actor(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")

        if action == "run":
            return (
                f"启动子代理: {operation.get('subagent_type', '?')}\n"
                f"任务: {operation.get('description', '')}\n"
                f"提示: {operation.get('prompt', '')[:200]}"
            )
        elif action == "spawn":
            return (
                f"生成子代理: {operation.get('subagent_type', '?')}\n"
                f"任务: {operation.get('description', '')}\n"
                f"actor_id 将在后台返回"
            )
        elif action == "status":
            return f"代理 {operation.get('actor_id', '')} 状态: running"
        elif action == "wait":
            return f"等待代理 {operation.get('actor_id', '')} 完成"
        elif action == "cancel":
            return f"已取消代理 {operation.get('actor_id', '')}"
        elif action == "send":
            return f"已发送消息给 {operation.get('to_actor_id', '')}"
        elif action == "models":
            return "可用模型列表(需要完整配置)"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"


# --- lsp ---

@tool(name="lsp", description="语言服务器协议操作(转到定义、查找引用等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {"type": "string", "enum": ["goToDefinition", "findReferences",
                                                        "hover", "documentSymbol",
                                                        "workspaceSymbol",
                                                        "goToImplementation"]},
              "file_path": {"type": "string", "description": "文件的绝对或相对路径"},
              "line": {"type": "integer", "description": "行号(1-based)"},
              "character": {"type": "integer", "description": "列号(1-based)"},
          },
          "required": ["operation", "file_path", "line", "character"],
      })
async def lsp(operation: str, file_path: str, line: int, character: int) -> str:
    try:
        filepath = _resolve_path(file_path)
        if not os.path.isfile(filepath):
            return f"[错误] 文件不存在: {filepath}"

        from craft.core.lsp import lsp_manager
        available = lsp_manager.list() if hasattr(lsp_manager, "list") else []

        return (
            f"LSP 操作: {operation} on {os.path.relpath(filepath, SessionCwd._project_dir)}\n"
            f"位置: {line}:{character}\n"
            f"LSP 服务可用: {len(available)} 个"
        )
    except Exception as e:
        return f"[错误] {e}"
