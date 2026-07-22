"""
工作区 — 移植自 packages/opencode/src/workflow/workspace.ts
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_in_workspace(root: str, rel: str) -> str:
    """解析工作空间内的路径 — 移植自 workspace.ts resolveInWorkspace"""
    abs_path = str(Path(root).resolve() / rel)
    root_resolved = str(Path(root).resolve())
    if abs_path != root_resolved and not abs_path.startswith(root_resolved + "/"):
        raise ValueError(f"workspace path escapes the workspace root: {rel}")
    return abs_path


def make_file_hooks(root: str) -> dict:
    """创建工作空间文件钩子 — 移植自 workspace.ts makeFileHooks"""

    async def _read_file(rel: str) -> str | None:
        abs_path = resolve_in_workspace(root, rel)
        p = Path(abs_path)
        return p.read_text(encoding="utf-8") if p.exists() else None

    async def _write_file(rel: str, content: str) -> None:
        abs_path = resolve_in_workspace(root, rel)
        Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_path).write_text(content, encoding="utf-8")

    async def _exists(rel: str) -> bool:
        abs_path = resolve_in_workspace(root, rel)
        return Path(abs_path).exists()

    async def _glob(pattern: str) -> list[str]:
        import glob as glob_mod
        results = []
        for p in glob_mod.glob(pattern, root_dir=root, recursive=True):
            if not p.startswith("..") and not Path(p).is_absolute():
                results.append(p)
        return sorted(results)

    return {
        "readFile": _read_file,
        "writeFile": _write_file,
        "exists": _exists,
        "glob": _glob,
    }
