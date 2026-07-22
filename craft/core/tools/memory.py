"""Memory search tool."""

from typing import Any

from .registry import tool


@tool(name="memory", description="记忆搜索(BM25 搜索标记文本)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {"type": "string", "enum": ["search"], "default": "search"},
              "query": {"type": "string", "description": "搜索查询"},
              "scope": {"type": "string", "enum": ["global", "projects", "sessions"]},
              "scope_id": {"type": "string"},
              "type": {"type": "string"},
              "limit": {"type": "integer"},
          },
          "required": ["query"],
      })
async def memory(query: str, operation: str = "search",
                 scope: str = "", scope_id: str = "",
                 type: str = "", limit: int = 10) -> str:
    try:
        from craft.core.memory import memory as memory_svc
        results = memory_svc.search(query)
        if not results:
            return (
                f"未找到 \"{query}\" 的匹配.\n\n"
                "0 个结果并不意味着从未记录过。在放弃前:\n"
                "1. 使用更少/更独特的关键词重试\n"
                "2. 对于文字字符串(URL、端口、路径) — 直接在记忆目录中搜索\n"
                "3. 对于精确回忆 — 使用历史工具\n"
            )
        lines = [f"找到 {len(results)} 个匹配 (BM25排序, 最佳优先):", ""]
        for r in results:
            content = getattr(r, "content", str(r))[:200]
            lines.append(f"### {getattr(r, 'id', '?')}")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"[错误] {e}"
