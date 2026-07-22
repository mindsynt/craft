"""Core types and registry for the tool/function system."""

from __future__ import annotations

import logging
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Core Types
# ═══════════════════════════════════════════════════════════════

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
    metadata: dict[str, Any] = Field(default_factory=dict)
    title: str = ""


class RecoverableError(Exception):
    """Marks a tool failure as agent-recoverable: the model can fix it on
    the next turn (bad arguments, non-existent resource)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.recoverable = True


class ToolResultError(Exception):
    """A tool execution error that carries metadata."""
    def __init__(self, message: str, metadata: dict[str, Any] | None = None,
                 attachments: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.tool_result_metadata = metadata or {}
        self.tool_result_attachments = attachments or []


# ═══════════════════════════════════════════════════════════════
# Base Tool + Registry
# ═══════════════════════════════════════════════════════════════

class Tool:
    def __init__(self, name: str = "", description: str = "",
                 parameters: dict | None = None,
                 handler: Callable | None = None):
        self.spec = ToolSpec(name=name, description=description,
                             parameters=parameters or {})
        self.handler = handler

    async def execute(self, **kwargs) -> ToolResult:
        if not self.handler:
            return ToolResult(success=False, error=f"工具 {self.spec.name} 未实现")
        try:
            r = self.handler(**kwargs)
            if hasattr(r, "__await__"):
                r = await r
            return ToolResult(content=str(r))
        except RecoverableError:
            raise
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def to_openai(self) -> dict:
        return {"type": "function", "function": {
            "name": self.spec.name, "description": self.spec.description,
            "parameters": self.spec.parameters,
        }}

    def to_anthropic(self) -> dict:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "input_schema": self.spec.parameters,
        }


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

    def to_anthropic_tools(self) -> list[dict]:
        return [t.to_anthropic() for t in self._tools.values()]

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {tool_name}")
        return await tool.execute(**kwargs)

    def __len__(self):
        return len(self._tools)


registry = ToolRegistry()


def tool(name: str, description: str = "", parameters: dict | None = None):
    def decorator(fn):
        registry.register(Tool(name=name, description=description,
                               parameters=parameters, handler=fn))
        return fn
    return decorator
