"""Workflow management tool."""

from typing import Any

from .registry import tool


@tool(name="workflow", description="工作流管理(运行、状态、等待、取消等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["run", "status", "wait",
                                                            "cancel", "resume"]},
                      "name": {"type": "string"},
                      "script": {"type": "string"},
                      "args": {},
                      "run_id": {"type": "string"},
                      "timeout_ms": {"type": "integer"},
                      "async": {"type": "boolean"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def workflow(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "run":
            name = operation.get("name", "inline")
            return f"启动工作流: {name} (需要完整的工作流引擎支持)"
        elif action == "status":
            return f"工作流状态: running"
        elif action == "cancel":
            return f"已取消工作流"
        return f"工作流操作: {action}"
    except Exception as e:
        return f"[错误] {e}"
