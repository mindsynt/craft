"""Invalid tool call handler."""

from .registry import tool


@tool(name="invalid", description="不要使用 - 报告无效工具调用",
      parameters={
          "type": "object",
          "properties": {
              "tool": {"type": "string", "description": "工具名称"},
              "error": {"type": "string", "description": "错误信息"},
          },
          "required": ["tool", "error"],
      })
async def invalid(tool: str, error: str) -> str:
    return f"提供给工具 {tool} 的参数无效: {error}"
