"""Change directory tool."""

import os

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


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
