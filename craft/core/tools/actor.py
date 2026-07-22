"""Sub-agent (actor) management tool."""

from typing import Any

from .registry import tool


@tool(name="actor", description="子代理管理(运行、生成、状态、等待、取消、发送、模型列表)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["run", "spawn", "status",
                                                            "wait", "cancel", "send",
                                                            "models"]},
                      "subagent_type": {"type": "string"},
                      "description": {"type": "string"},
                      "prompt": {"type": "string"},
                      "model": {"type": "string"},
                      "actor_id": {"type": "string"},
                      "timeout_ms": {"type": "integer"},
                      "to_actor_id": {"type": "string"},
                      "content": {"type": "string"},
                      "context": {"type": "string", "enum": ["none", "state", "full"]},
                      "vision": {"type": "boolean"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def actor(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")

        if action == "run":
            return (
                f"启动子代理: {operation.get('subagent_type', '?')}\n"
                f"任务: {operation.get('description', '')}\n"
                f"提示: {operation.get('prompt', '')[:200]}"
            )
        elif action == "spawn":
            return (
                f"生成子代理: {operation.get('subagent_type', '?')}\n"
                f"任务: {operation.get('description', '')}\n"
                f"actor_id 将在后台返回"
            )
        elif action == "status":
            return f"代理 {operation.get('actor_id', '')} 状态: running"
        elif action == "wait":
            return f"等待代理 {operation.get('actor_id', '')} 完成"
        elif action == "cancel":
            return f"已取消代理 {operation.get('actor_id', '')}"
        elif action == "send":
            return f"已发送消息给 {operation.get('to_actor_id', '')}"
        elif action == "models":
            return "可用模型列表(需要完整配置)"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"
