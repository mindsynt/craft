"""
脚本解析 — 移植自 packages/opencode/src/workflow/resolve.ts
"""

from __future__ import annotations

import re
from pathlib import Path


META_RE = re.compile(r"export\s+const\s+meta\s*=")


def is_inline_script(name_or_script: str) -> bool:
    """检查是否为内联脚本 — 移植自 resolve.ts isInlineScript"""
    return bool(META_RE.search(name_or_script))


SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


async def resolve_workflow_script(name: str, start: str, stop: str) -> str | None:
    """解析工作流脚本 — 移植自 resolve.ts resolveWorkflowScript"""
    if not SAFE_NAME_RE.match(name):
        raise ValueError(f"invalid workflow name: {name}")

    # 从 start 向上查找到 stop
    subdirs = [".mimocode/workflows", ".claude/workflows"]
    candidates = []
    current = start
    while True:
        for sub in subdirs:
            candidate = Path(current) / sub / f"{name}.js"
            if candidate.exists():
                candidates.append(str(candidate))
        if current == stop:
            break
        parent = str(Path(current).parent)
        if parent == current:
            break
        current = parent

    for found in candidates:
        return Path(found).read_text(encoding="utf-8")
    return None
