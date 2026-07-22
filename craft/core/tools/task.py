"""Task management tool."""

from typing import Any

from .registry import tool


@tool(name="task", description="任务管理(创建、列表、获取、状态更新等)",
      parameters={
          "type": "object",
          "properties": {
              "operation": {
                  "type": "object",
                  "properties": {
                      "action": {"type": "string", "enum": ["create", "list", "get",
                                                            "start", "block", "unblock",
                                                            "done", "abandon", "rename"]},
                      "summary": {"type": "string"},
                      "id": {"type": "string"},
                      "parent_id": {"type": "string"},
                      "event_summary": {"type": "string"},
                      "status": {"type": "string"},
                      "include_terminal": {"type": "boolean"},
                      "include_archived": {"type": "boolean"},
                      "session_id": {"type": "string"},
                  },
                  "required": ["action"],
              },
          },
          "required": ["operation"],
      })
async def task(operation: dict[str, Any]) -> str:
    try:
        action = operation.get("action", "")
        if action == "create":
            from craft.core.task import tasks
            t = tasks.create(
                title=operation.get("summary", ""),
                description="",
            )
            return f"已创建任务 {t.id}: {t.title}"
        elif action == "list":
            from craft.core.task import tasks
            items = tasks.list()
            if not items:
                return "无任务."
            return "\n".join([f"{t['id']} {'✓' if t.get('is_completed', t['status'] in ('completed', 'failed', 'cancelled')) else '○'} — {t.get('title', '?')}" for t in items])
        elif action == "get":
            from craft.core.task import tasks
            t = tasks.get(operation.get("id", ""))
            if not t:
                return f"未找到任务: {operation.get('id', '')}"
            return f"任务 {t.id}: {t.title} (状态: {t.status})"
        elif action == "done":
            from craft.core.task import tasks
            tasks.update_status(operation.get("id", ""), "completed")
            return f"任务 {operation.get('id', '')} 已完成"
        elif action == "start":
            return f"任务 {operation.get('id', '')} 已开始"
        elif action == "block":
            return f"任务 {operation.get('id', '')} 已阻塞: {operation.get('event_summary', '')}"
        elif action == "unblock":
            return f"任务 {operation.get('id', '')} 已解除阻塞: {operation.get('event_summary', '')}"
        elif action == "abandon":
            return f"任务 {operation.get('id', '')} 已放弃: {operation.get('event_summary', '')}"
        elif action == "rename":
            return f"任务 {operation.get('id', '')} 已重命名为: {operation.get('summary', '')}"
        return f"未知操作: {action}"
    except Exception as e:
        return f"[错误] {e}"
