"""Plan mode tools."""

from .registry import tool


@tool(name="plan_enter", description="切换到计划模式进行结构化规划",
      parameters={
          "type": "object",
          "properties": {},
      })
async def plan_enter(current_agent: str = "") -> str:
    """Switch to plan mode (port of PlanEnterTool)."""
    if current_agent == "plan":
        return "您已在计划模式中. 此工具仅在计划模式外有效."
    return (
        "是否要切换到计划模式进行结构化规划?\n"
        "请确认以切换到 plan agent 进行只读规划."
    )


@tool(name="plan_exit", description="退出计划模式, 切换到实现模式",
      parameters={
          "type": "object",
          "properties": {},
      })
async def plan_exit(current_agent: str = "") -> str:
    if current_agent != "plan":
        return "您不在计划模式中. 此工具仅在计划模式中有效."
    return (
        "计划已完成. 是否要切换到 build agent 开始实现?\n"
        "请确认以切换到 build agent 执行计划."
    )
