"""Write file content tool."""

import difflib
import os

from .registry import tool
from .utils import _resolve_path, _trim_diff


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
