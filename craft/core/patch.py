"""
文件补丁 — 移植自 packages/opencode/src/patch/
V4A 格式补丁解析、差异计算、补丁应用

支持 *** Begin Patch / *** End Patch 格式：
- *** Add File: <path>
- *** Delete File: <path>
- *** Update File: <path>
  - @@ context @@
  - (空格保持、减号删除、加号添加)
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Any


# ── Schema ──────────────────────────────────────────────────

PATCH_SCHEMA = {
    "patchText": str,
}


# ── 类型 ────────────────────────────────────────────────────

class UpdateFileChunk:
    """更新文件块"""
    def __init__(self, old_lines: list[str], new_lines: list[str],
                 change_context: str | None = None, is_end_of_file: bool | None = None):
        self.old_lines = old_lines
        self.new_lines = new_lines
        self.change_context = change_context
        self.is_end_of_file = is_end_of_file


class Hunk:
    """补丁块"""
    def __init__(self, type: str, path: str, contents: str | None = None,
                 move_path: str | None = None, chunks: list[UpdateFileChunk] | None = None):
        self.type = type  # "add" | "delete" | "update"
        self.path = path
        self.contents = contents
        self.move_path = move_path
        self.chunks = chunks or []


class ApplyPatchArgs:
    def __init__(self, patch: str, hunks: list[Hunk], workdir: str | None = None):
        self.patch = patch
        self.hunks = hunks
        self.workdir = workdir


class ApplyPatchFileChange:
    """文件变更"""
    def __init__(self, type: str, content: str = "",
                 unified_diff: str = "", move_path: str | None = None, new_content: str = ""):
        self.type = type  # "add" | "delete" | "update"
        self.content = content
        self.unified_diff = unified_diff
        self.move_path = move_path
        self.new_content = new_content


# ── 错误类型 ────────────────────────────────────────────────

class ApplyPatchError(Exception):
    PARSE_ERROR = "ParseError"
    IO_ERROR = "IoError"
    COMPUTE_REPLACEMENTS = "ComputeReplacements"
    IMPLICIT_INVOCATION = "ImplicitInvocation"

    def __init__(self, kind: str, message: str = ""):
        self.kind = kind
        super().__init__(message or kind)


# ── 解析器 ──────────────────────────────────────────────────

def _strip_heredoc(input_str: str) -> str:
    """去除 heredoc 包装

    处理: cat <<'EOF'\n...\nEOF 或 <<EOF\n...\nEOF
    """
    m = re.match(r'^(?:cat\s+)?<<[\'"]?(\w+)[\'"]?\s*\n([\s\S]*?)\n\1\s*$', input_str)
    if m:
        return m.group(2)
    return input_str


def _parse_patch_header(lines: list[str], start_idx: int) -> dict | None:
    """解析补丁头部

    Returns: {filePath, movePath?, nextIdx} | None
    """
    if start_idx >= len(lines):
        return None

    line = lines[start_idx]

    if line.startswith("*** Add File:"):
        file_path = line[len("*** Add File:"):].strip()
        return {"filePath": file_path, "nextIdx": start_idx + 1} if file_path else None

    if line.startswith("*** Delete File:"):
        file_path = line[len("*** Delete File:"):].strip()
        return {"filePath": file_path, "nextIdx": start_idx + 1} if file_path else None

    if line.startswith("*** Update File:"):
        file_path = line[len("*** Update File:"):].strip()
        move_path = None
        next_idx = start_idx + 1

        if next_idx < len(lines) and lines[next_idx].startswith("*** Move to:"):
            move_path = lines[next_idx][len("*** Move to:"):].strip()
            next_idx += 1

        return {"filePath": file_path, "movePath": move_path, "nextIdx": next_idx} if file_path else None

    return None


def _parse_update_file_chunks(lines: list[str], start_idx: int) -> tuple[list[UpdateFileChunk], int]:
    """解析 Update File 块"""
    chunks: list[UpdateFileChunk] = []
    i = start_idx

    while i < len(lines) and not lines[i].startswith("***"):
        if lines[i].startswith("@@"):
            context_line = lines[i][2:].strip()
            i += 1

            old_lines: list[str] = []
            new_lines: list[str] = []
            is_end_of_file = False

            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("***"):
                change_line = lines[i]

                if change_line == "*** End of File":
                    is_end_of_file = True
                    i += 1
                    break

                if change_line.startswith(" "):
                    content = change_line[1:]
                    old_lines.append(content)
                    new_lines.append(content)
                elif change_line.startswith("-"):
                    old_lines.append(change_line[1:])
                elif change_line.startswith("+"):
                    new_lines.append(change_line[1:])

                i += 1

            chunks.append(UpdateFileChunk(
                old_lines=old_lines,
                new_lines=new_lines,
                change_context=context_line or None,
                is_end_of_file=is_end_of_file or None,
            ))
        else:
            i += 1

    return chunks, i


def _parse_add_file_content(lines: list[str], start_idx: int) -> tuple[str, int]:
    """解析 Add File 内容"""
    content_lines: list[str] = []
    i = start_idx

    while i < len(lines) and not lines[i].startswith("***"):
        if lines[i].startswith("+"):
            content_lines.append(lines[i][1:])
        i += 1

    content = "\n".join(content_lines)
    return content, i


def parse_patch(patch_text: str) -> dict:
    """解析 V4A 格式补丁

    Args:
        patch_text: 补丁文本

    Returns:
        {"hunks": list[Hunk]}

    格式:
        *** Begin Patch
        *** Add File: <path>
        +content...
        *** Update File: <path>
        @@ context @@
         keep
        -remove
        +add
        *** Delete File: <path>
        *** End Patch
    """
    cleaned = _strip_heredoc(patch_text.strip())
    lines = cleaned.split("\n")
    hunks: list[Hunk] = []

    # 查找 Begin/End 标记
    begin_marker = "*** Begin Patch"
    end_marker = "*** End Patch"

    begin_idx = -1
    end_idx = -1

    for idx, line in enumerate(lines):
        if line.strip() == begin_marker:
            begin_idx = idx
        elif line.strip() == end_marker:
            end_idx = idx

    if begin_idx == -1 or end_idx == -1 or begin_idx >= end_idx:
        raise ValueError("Invalid patch format: missing Begin/End markers")

    i = begin_idx + 1

    while i < end_idx:
        header = _parse_patch_header(lines, i)
        if not header:
            i += 1
            continue

        if lines[i].startswith("*** Add File:"):
            content, next_idx = _parse_add_file_content(lines, header["nextIdx"])
            hunks.append(Hunk("add", header["filePath"], contents=content))
            i = next_idx
        elif lines[i].startswith("*** Delete File:"):
            hunks.append(Hunk("delete", header["filePath"]))
            i = header["nextIdx"]
        elif lines[i].startswith("*** Update File:"):
            chunks, next_idx = _parse_update_file_chunks(lines, header["nextIdx"])
            hunks.append(Hunk("update", header["filePath"],
                              move_path=header.get("movePath"), chunks=chunks))
            i = next_idx
        else:
            i += 1

    return {"hunks": hunks}


# ── 补丁检测 ────────────────────────────────────────────────

def maybe_parse_apply_patch(argv: list[str]) -> dict:
    """检测并解析 apply_patch 调用

    支持:
    - apply_patch <patch_text>
    - bash -lc 'apply_patch <<"EOF" ... EOF'

    Returns:
        {"type": "Body"|"PatchParseError"|"NotApplyPatch", ...}
    """
    APPLY_PATCH_COMMANDS = ["apply_patch", "applypatch"]

    if len(argv) == 2 and argv[0] in APPLY_PATCH_COMMANDS:
        try:
            result = parse_patch(argv[1])
            return {
                "type": "Body",
                "args": ApplyPatchArgs(argv[1], result["hunks"]),
            }
        except Exception as e:
            return {
                "type": "PatchParseError",
                "error": str(e),
            }

    if len(argv) == 3 and argv[0] == "bash" and argv[1] == "-lc":
        script = argv[2]
        m = re.search(r'apply_patch\s*<<[\'"](\w+)[\'"]\s*\n([\s\S]*?)\n\1', script)
        if m:
            patch_content = m.group(2)
            try:
                result = parse_patch(patch_content)
                return {
                    "type": "Body",
                    "args": ApplyPatchArgs(patch_content, result["hunks"]),
                }
            except Exception as e:
                return {
                    "type": "PatchParseError",
                    "error": str(e),
                }

    return {"type": "NotApplyPatch"}


# ── 替换计算 ────────────────────────────────────────────────

def _normalize_unicode(text: str) -> str:
    """Unicode 标点符号转 ASCII"""
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201A", "'").replace("\u201B", "'")
    text = text.replace("\u201C", '"').replace("\u201D", '"').replace("\u201E", '"').replace("\u201F", '"')
    text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-").replace("\u2013", "-")
    text = text.replace("\u2014", "-").replace("\u2015", "-")
    text = text.replace("\u2026", "...")
    text = text.replace("\u00A0", " ")
    return text


class Comparator:
    """行比较器，支持多种匹配策略"""

    @staticmethod
    def exact(a: str, b: str) -> bool:
        return a == b

    @staticmethod
    def rstrip(a: str, b: str) -> bool:
        return a.rstrip() == b.rstrip()

    @staticmethod
    def trim(a: str, b: str) -> bool:
        return a.strip() == b.strip()

    @staticmethod
    def normalized(a: str, b: str) -> bool:
        return _normalize_unicode(a.strip()) == _normalize_unicode(b.strip())


def _try_match(lines: list[str], pattern: list[str], start_idx: int,
               compare_func, eof: bool) -> int:
    """尝试匹配模式

    Args:
        lines: 原文件行
        pattern: 要匹配的模式行
        start_idx: 起始索引
        compare_func: 比较函数 (a, b) -> bool
        eof: 是否匹配到文件末尾

    Returns:
        匹配的起始索引，-1 表示未找到
    """
    if not pattern or len(pattern) > len(lines):
        return -1

    # 先尝试 EOF 匹配
    if eof:
        from_end = len(lines) - len(pattern)
        if from_end >= start_idx:
            match = True
            for j in range(len(pattern)):
                if not compare_func(lines[from_end + j], pattern[j]):
                    match = False
                    break
            if match:
                return from_end

    # 正向搜索
    for i in range(start_idx, len(lines) - len(pattern) + 1):
        match = True
        for j in range(len(pattern)):
            if not compare_func(lines[i + j], pattern[j]):
                match = False
                break
        if match:
            return i

    return -1


def _seek_sequence(lines: list[str], pattern: list[str],
                   start_idx: int, eof: bool = False) -> int:
    """按多种策略查找模式

    策略依次尝试: exact -> rstrip -> trim -> normalized
    """
    if not pattern:
        return -1

    strategies = [
        ("exact", Comparator.exact),
        ("rstrip", Comparator.rstrip),
        ("trim", Comparator.trim),
        ("normalized", Comparator.normalized),
    ]

    for _, compare_func in strategies:
        found = _try_match(lines, pattern, start_idx, compare_func, eof)
        if found != -1:
            return found

    return -1


def compute_replacements(original_lines: list[str], file_path: str,
                         chunks: list[UpdateFileChunk]) -> list[tuple[int, int, list[str]]]:
    """计算原文件中的替换位置 — 对应 TS computeReplacements"""
    replacements: list[tuple[int, int, list[str]]] = []
    line_index = 0

    for chunk in chunks:
        # 上下文定位
        if chunk.change_context:
            context_idx = _seek_sequence(original_lines, [chunk.change_context], line_index)
            if context_idx == -1:
                raise ApplyPatchError(
                    ApplyPatchError.COMPUTE_REPLACEMENTS,
                    f"Failed to find context '{chunk.change_context}' in {file_path}"
                )
            line_index = context_idx + 1

        # 纯添加（无 old_lines）
        if not chunk.old_lines:
            insertion_idx = (
                len(original_lines) - 1
                if original_lines and original_lines[-1] == ""
                else len(original_lines)
            )
            replacements.append((insertion_idx, 0, chunk.new_lines))
            continue

        # 尝试匹配 old_lines
        pattern = list(chunk.old_lines)
        new_slice = list(chunk.new_lines)
        found = _seek_sequence(original_lines, pattern, line_index, bool(chunk.is_end_of_file))

        # 重试：去除尾部空行
        if found == -1 and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = _seek_sequence(original_lines, pattern, line_index, bool(chunk.is_end_of_file))

        if found != -1:
            replacements.append((found, len(pattern), new_slice))
            line_index = found + len(pattern)
        else:
            raise ApplyPatchError(
                ApplyPatchError.COMPUTE_REPLACEMENTS,
                f"Failed to find expected lines in {file_path}:\n" + "\n".join(chunk.old_lines)
            )

    replacements.sort(key=lambda x: x[0])
    return replacements


def apply_replacements(lines: list[str], replacements: list[tuple[int, int, list[str]]]) -> list[str]:
    """应用替换（逆序以避免索引偏移）"""
    result = list(lines)
    for i in range(len(replacements) - 1, -1, -1):
        start_idx, old_len, new_segment = replacements[i]
        result[start_idx:start_idx + old_len] = new_segment
    return result


def derive_new_contents_from_chunks(file_path: str, chunks: list[UpdateFileChunk]) -> dict:
    """从 chunks 推导新文件内容 — 对应 TS deriveNewContentsFromChunks"""
    try:
        original_content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        raise ApplyPatchError(ApplyPatchError.IO_ERROR, f"Failed to read file {file_path}: {e}")

    original_lines = original_content.split("\n")
    if original_lines and original_lines[-1] == "":
        original_lines.pop()

    replacements = compute_replacements(original_lines, file_path, chunks)
    new_lines = apply_replacements(original_lines, replacements)

    # 确保末尾换行
    if not new_lines or new_lines[-1] != "":
        new_lines.append("")

    new_content = "\n".join(new_lines)
    unified_diff = "".join(difflib.unified_diff(
        original_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile="a/" + file_path, tofile="b/" + file_path,
    ))

    return {
        "unified_diff": unified_diff,
        "content": new_content,
    }


# ── Patch 类 ────────────────────────────────────────────────

class Patch:
    def __init__(self, filepath: str, old_string: str, new_string: str):
        self.filepath = filepath
        self.old_string = old_string
        self.new_string = new_string

    def apply(self) -> bool:
        try:
            path = Path(self.filepath)
            content = path.read_text(encoding="utf-8")
            if self.old_string not in content:
                return False
            new_content = content.replace(self.old_string, self.new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            return True
        except Exception:
            return False

    def dry_run(self) -> bool:
        try:
            content = Path(self.filepath).read_text(encoding="utf-8")
            return self.old_string in content
        except Exception:
            return False

    def diff(self) -> str:
        try:
            content = Path(self.filepath).read_text(encoding="utf-8")
            return "".join(difflib.unified_diff(
                content.splitlines(keepends=True),
                content.replace(self.old_string, self.new_string).splitlines(keepends=True),
                fromfile="original", tofile="patched",
            ))
        except Exception:
            return ""


class PatchManager:
    def __init__(self):
        self._history: list[Patch] = []

    def apply(self, filepath: str, old_string: str, new_string: str) -> bool:
        patch = Patch(filepath, old_string, new_string)
        if patch.apply():
            self._history.append(patch)
            return True
        return False

    def apply_v4a(self, patch_text: str) -> list[dict]:
        """应用 V4A 格式补丁 — 返回操作结果列表"""
        result = parse_patch(patch_text)
        outcomes: list[dict] = []
        for hunk in result["hunks"]:
            if hunk.type == "add":
                path = Path(hunk.path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(hunk.contents or "", encoding="utf-8")
                outcomes.append({"type": "add", "path": hunk.path, "success": True})
            elif hunk.type == "delete":
                try:
                    Path(hunk.path).unlink()
                    outcomes.append({"type": "delete", "path": hunk.path, "success": True})
                except Exception:
                    outcomes.append({"type": "delete", "path": hunk.path, "success": False})
            elif hunk.type == "update":
                try:
                    update = derive_new_contents_from_chunks(hunk.path, hunk.chunks)
                    Path(hunk.path).write_text(update["content"], encoding="utf-8")
                    outcomes.append({"type": "update", "path": hunk.path, "success": True})
                except Exception as e:
                    outcomes.append({"type": "update", "path": hunk.path, "success": False, "error": str(e)})
        return outcomes

    def undo_last(self) -> bool:
        if not self._history:
            return False
        patch = self._history.pop()
        return Patch(patch.filepath, patch.new_string, patch.old_string).apply()


patcher = PatchManager()
