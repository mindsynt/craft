"""History search tool."""

from typing import Any

from .registry import tool


@tool(name="history", description="会话历史搜索(FTS BM25 搜索)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {"type": "string", "enum": ["search", "around"],
                            "description": "search: FTS BM25; around: 获取消息上下文"},
              "query": {"type": "string", "description": "FTS 查询(operation=search 时必需)"},
              "scope": {"type": "string", "enum": ["project", "global"]},
              "session_id": {"type": "string"},
              "message_id": {"type": "string", "description": "锚点消息 ID(operation=around 时必需)"},
              "before": {"type": "integer"},
              "after": {"type": "integer"},
              "limit": {"type": "integer"},
          },
          "required": ["operation"],
      })
async def history(operation: str, query: str = "", scope: str = "",
                  session_id: str = "", message_id: str = "",
                  before: int = 5, after: int = 5, limit: int = 10) -> str:
    try:
        from craft.core.history import history as history_svc
        if operation == "search":
            if not query:
                return "operation=search 需要 query 参数"
            results = history_svc.search(query)
            if not results:
                return f"0 个匹配 \"{query}\""
            lines = [f"找到 {len(results)} 个匹配:", ""]
            for r in results:
                lines.append(str(r)[:200])
                lines.append("")
            return "\n".join(lines)
        elif operation == "around":
            return f"查看消息 {message_id} 的上下文(前后各 {before}/{after} 条)"
        return f"未知操作: {operation}"
    except Exception as e:
        return f"[错误] {e}"
