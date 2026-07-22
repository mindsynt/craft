"""Glob file search tool."""

import os
from pathlib import Path

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


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
