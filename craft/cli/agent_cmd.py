"""
CLI Agent 命令 — 移植自 packages/opencode/src/cli/cmd/agent.ts
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def handle_agent_create(args: dict) -> None:
    """创建新 Agent — 移植自 agent.ts AgentCreateCommand"""
    from craft.core.agent import agents, AgentInfo
    from craft.core.permission import Ruleset

    description = args.get("description", "")
    if not description:
        print("Error: --description is required")
        return

    name = args.get("name", description.split()[0].lower() if description.split() else "custom")
    mode = args.get("mode", "subagent")
    tools_str = args.get("tools", "read_file,search_files")
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]

    info = AgentInfo(
        name=name,
        description=description,
        mode=mode,
        allowed_tools=tools,
        permission=Ruleset(allow=tools),
    )
    agents.register(name, info)
    print(f"Agent '{name}' created (mode={mode})")


async def handle_agent_list(args: dict) -> None:
    """列出所有 Agent — 移植自 agent.ts 部分"""
    from craft.core.agent import agents

    mode = args.get("mode")
    items = agents.list(mode=mode)

    print(f"{'ID':<24} {'Name':<16} {'Mode':<12} {'Description'}")
    print("-" * 80)
    for aid, info in items:
        hidden_mark = " (hidden)" if info.hidden else ""
        print(f"{aid:<24} {info.name:<16} {info.mode:<12}{hidden_mark} {info.description}")


async def handle_agent_show(args: dict) -> None:
    """显示特定 Agent 详情"""
    from craft.core.agent import agents

    agent_id = args.get("agent_id", "")
    if not agent_id:
        print("Error: agent_id is required")
        return

    info = agents.get(agent_id)
    if not info:
        print(f"Error: agent '{agent_id}' not found")
        return

    print(f"Name:          {info.name}")
    print(f"ID:            {agent_id}")
    print(f"Mode:          {info.mode}")
    print(f"Native:        {info.native}")
    print(f"Hidden:        {info.hidden}")
    print(f"Color:         {info.color or '(none)'}")
    print(f"Description:   {info.description}")
    print(f"Tools:         {', '.join(info.allowed_tools)}")
    if info.tool_allowlist is not None:
        print(f"Tool Allowlist: {', '.join(info.tool_allowlist)}")
    if info.temperature is not None:
        print(f"Temperature:   {info.temperature}")
    if info.steps is not None:
        print(f"Steps:         {info.steps}")
    if info.model:
        print(f"Model:         {info.model}")
    if info.prompt:
        print(f"Prompt:        {info.prompt[:80]}...")


async def handle_agent_generate(args: dict) -> None:
    """用 LLM 生成 Agent — 移植自 agent.ts generate"""
    from craft.core.agent import generate

    description = args.get("description", "")
    if not description:
        print("Error: --description is required")
        return

    result = await generate(description)
    if result:
        print(f"Generated agent '{result['identifier']}'")
        print(f"  When to use: {result['whenToUse']}")
        print(f"  System prompt: {result['systemPrompt'][:80]}...")
