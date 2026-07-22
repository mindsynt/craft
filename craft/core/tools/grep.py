"""Grep file content search tool."""

import asyncio
import os

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


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
