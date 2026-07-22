"""
Diff 回滚 — 移植自 util/revert-diff.ts

解析 diff 文本，提取文件名和修改统计。
"""

from __future__ import annotations

import re


def get_revert_diff_files(diff_text: str) -> list[dict]:
    """解析 diff 文本，返回文件名和修改统计列表"""
    if not diff_text:
        return []

    files: list[dict] = []
    current_file: dict | None = None

    # Simple parser for unified diff format
    for line in diff_text.splitlines():
        # Match diff header: --- a/file or +++ b/file
        m = re.match(r'^[-+]{3}\s+[ab]/(.+)$', line)
        if m and line.startswith('---'):
            fname = m.group(1)
            if current_file:
                files.append(current_file)
            current_file = {"filename": fname, "additions": 0, "deletions": 0}
        # Count additions/deletions
        if current_file:
            if line.startswith('+') and not line.startswith('+++'):
                current_file["additions"] += 1
            elif line.startswith('-') and not line.startswith('---'):
                current_file["deletions"] += 1

    if current_file:
        files.append(current_file)

    return files
