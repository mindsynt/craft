"""
Agent 系统 — 移植自 MiMo-Code packages/opencode/src/agent/
多 Agent 架构、身份管理、运行时权限
"""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field
from craft.core.permission import Ruleset, merge_rulesets

logger = logging.getLogger(__name__)


class AgentInfo(BaseModel):
    name: str
    description: str = ""
    mode: str = "primary"
    color: str = ""
    prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    permission: Ruleset = Field(default_factory=Ruleset)
    hard_permission: Ruleset | None = None


PRESET_AGENTS: dict[str, AgentInfo] = {
    "build": AgentInfo(
        name="Build", description="全栈开发、编码、测试", mode="primary", color="blue",
        prompt="你是一个全栈工程师。直接实现代码，不要只给方案。",
        allowed_tools=["read_file", "write_file", "search_files", "terminal", "git"],
        permission=Ruleset(allow=["read_file", "write_file", "search_files", "terminal", "git"]),
    ),
    "plan": AgentInfo(
        name="Plan", description="架构分析、方案输出（只读）", mode="primary", color="amber",
        prompt="你是一个软件架构师。只读分析，不修改代码。",
        allowed_tools=["read_file", "search_files"],
        permission=Ruleset(allow=["read_file", "search_files"]),
        hard_permission=Ruleset(deny=["write_file", "terminal", "git"]),
    ),
}


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        for aid, info in PRESET_AGENTS.items():
            self.register(aid, info)

    def register(self, agent_id: str, info: AgentInfo):
        self._agents[agent_id] = info

    def get(self, agent_id: str) -> AgentInfo | None:
        return self._agents.get(agent_id)

    def list(self, mode: str | None = None) -> list[tuple[str, AgentInfo]]:
        items = [(a, i) for a, i in self._agents.items()]
        if mode:
            items = [(a, i) for a, i in items if i.mode == mode or i.mode == "all"]
        return items

    def default(self) -> str:
        return "build"

    def runtime_permission(self, agent_id: str, user_rules: Ruleset | None = None) -> Ruleset:
        agent = self.get(agent_id)
        if not agent:
            return Ruleset()
        return merge_rulesets(agent.permission, user_rules, agent.hard_permission)

    def check_tool(self, agent_id: str, tool_name: str, user_rules: Ruleset | None = None) -> bool:
        return self.runtime_permission(agent_id, user_rules).evaluate(tool_name)


agents = AgentRegistry()
