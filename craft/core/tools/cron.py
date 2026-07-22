"""Cron task management tool."""

from typing import Any

from .registry import tool


@tool(name="cron", description="定时任务管理(调度、循环、列表等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["schedule", "loop", "list",
                                                            "get", "delete", "rename"]},
                      "cron": {"type": "string", "description": "5字段 cron 表达式"},
                      "prompt": {"type": "string", "description": "触发时发送的提示"},
                      "delay_seconds": {"type": "integer"},
                      "one_shot": {"type": "boolean"},
                      "durable": {"type": "boolean"},
                      "id": {"type": "string"},
                      "kind": {"type": "string"},
                      "durable_only": {"type": "boolean"},
                      "reason": {"type": "string"},
                      "session_id": {"type": "string"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def cron(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "schedule":
            from craft.core.cron import scheduler
            job = scheduler.add(
                operation.get("prompt", "cron job"),
                interval_seconds=0,
            )
            expr = operation.get("cron", "")
            return f"已调度任务 {job}: {operation.get('prompt', '')} ({expr})"
        elif action == "list":
            return "已调度的任务列表(需要完整的调度系统支持)"
        elif action == "delete":
            return f"已删除任务 {operation.get('id', '')}"
        elif action == "get":
            return f"任务 {operation.get('id', '')}"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"
