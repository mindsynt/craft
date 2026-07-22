"""工具/Function 系统"""

from __future__ import annotations

import logging
from typing import Any, Callable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object", "properties": {}, "required": [],
    })


class ToolResult(BaseModel):
    success: bool = True
    content: str = ""
    error: str | None = None


class Tool:
    def __init__(self, name: str = "", description: str = "", parameters: dict | None = None,
                 handler: Callable | None = None):
        self.spec = ToolSpec(name=name, description=description, parameters=parameters or {})
        self.handler = handler

    async def execute(self, **kwargs) -> ToolResult:
        if not self.handler:
            return ToolResult(success=False, error=f"工具 {self.spec.name} 未实现")
        try:
            r = self.handler(**kwargs)
            if hasattr(r, "__await__"):
                r = await r
            return ToolResult(content=str(r))
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def to_openai(self) -> dict:
        return {"type": "function", "function": {
            "name": self.spec.name, "description": self.spec.description,
            "parameters": self.spec.parameters,
        }}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.spec.name] = tool
        logger.info(f"工具注册: {tool.spec.name}")

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def to_openai_tools(self) -> list[dict]:
        return [t.to_openai() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {name}")
        return await tool.execute(**kwargs)

    def __len__(self):
        return len(self._tools)


registry = ToolRegistry()


def tool(name: str, description: str = "", parameters: dict | None = None):
    def decorator(fn):
        registry.register(Tool(name=name, description=description, parameters=parameters, handler=fn))
        return fn
    return decorator


@tool(name="read_file", description="读取文件内容",
      parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})
async def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[错误] {e}"


@tool(name="write_file", description="写入文件内容",
      parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]})
async def write_file(path: str, content: str) -> str:
    try:
        import os; os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f: f.write(content)
        return f"已写入 {len(content)} 字符"
    except Exception as e:
        return f"[错误] {e}"
