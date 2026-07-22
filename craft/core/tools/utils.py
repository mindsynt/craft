"""Helper utilities for tools."""

import os
import re

from .session_cwd import SessionCwd


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
