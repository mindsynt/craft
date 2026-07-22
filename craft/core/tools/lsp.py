"""LSP (Language Server Protocol) tool."""

import os

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


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
