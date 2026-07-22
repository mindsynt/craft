"""Code search tool."""

from .registry import tool


@tool(name="codesearch", description="搜索代码(API、库、SDK 文档)",
      parameters={
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "搜索查询"},
              "tokens_num": {"type": "integer", "description": "返回的 token 数量(1000-50000)"},
          },
          "required": ["query"],
      })
async def codesearch(query: str, tokens_num: int = 5000) -> str:
    try:
        tokens_num = max(1000, min(tokens_num, 50000))
        # Placeholder - in production this would call an API
        return (
            f"代码搜索: {query} ({tokens_num} tokens)\n"
            "搜索功能需要通过外部 API 配置。"
        )
    except Exception as e:
        return f"[错误] {e}"
