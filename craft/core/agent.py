"""
Agent 系统 — 移植自 MiMo-Code packages/opencode/src/agent/
多 Agent 架构、身份管理、运行时权限、子代理生成

包含：预设 Agent（build, plan, explore, title, summary, dream, distill,
checkpoint-writer, compaction）+ 运行时权限 + LLM 驱动的 Agent 生成
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from craft.core.permission import Ruleset, merge_rulesets

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# AgentInfo — 单个 Agent 定义（移植自 agent.ts Info zod schema）
# ═══════════════════════════════════════════════════════════

class AgentInfo(BaseModel):
    name: str
    description: str = ""
    mode: str = "primary"  # "primary" | "subagent" | "all"
    native: bool = False
    hidden: bool = False
    color: str = ""
    prompt: str = ""
    temperature: float | None = None
    top_p: float | None = None
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    permission: Ruleset = Field(default_factory=Ruleset)
    hard_permission: Ruleset | None = None
    model: str | None = None  # "provider/model" optional
    steps: int | None = None
    tool_allowlist: list[str] | None = None  # None = all allowed at schema level
    options: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# SYSTEM_SPAWNED_AGENT_TYPES（移植自 agent/config.ts）
# ═══════════════════════════════════════════════════════════

SYSTEM_SPAWNED_AGENT_TYPES: set[str] = {
    "checkpoint-writer", "dream", "distill",
}


def decide_ask_routing(
    agent_name: str,
    ask_actor: dict | None = None,
    session_parent_id: str | None = None,
    orchestrator_enabled: bool = False,
) -> dict:
    """决定权限 ask 的路由方式 — 移植自 config.ts decideAskRouting

    返回:
      {"interactive": True/False}
      or {"interactive": True, "forward": {"parentSessionID": "..."}}
      or {"interactive": False, "inherit": {"parentSessionID": "..."}}
    """
    is_system = (
        SYSTEM_SPAWNED_AGENT_TYPES.intersection(
            {ask_actor.get("agent")} if ask_actor else {agent_name}
        )
    )
    if is_system:
        return {"interactive": False}

    is_orch_peer = (
        orchestrator_enabled
        and (ask_actor or {}).get("background")
        and (ask_actor or {}).get("mode") == "peer"
        and ((ask_actor or {}).get("parentActorID") or session_parent_id)
    )
    if is_orch_peer and session_parent_id:
        return {"interactive": True, "forward": {"parentSessionID": session_parent_id}}

    # Background subagent with a parent session: inherit parent's grants
    if (ask_actor or {}).get("background") and session_parent_id:
        return {"interactive": False, "inherit": {"parentSessionID": session_parent_id}}

    return {"interactive": not (ask_actor or {}).get("background")}


# ═══════════════════════════════════════════════════════════
# 预设 Agent 定义
# ═══════════════════════════════════════════════════════════

# 生成用 prompt 常量（占位符，完整 prompt 可从文件加载）
PROMPT_EXPLORE = """You are a fast agent specialized for exploring codebases.
Use this when you need to quickly find files by patterns, search code for keywords,
or answer questions about the codebase. Be thorough and efficient."""

PROMPT_TITLE = """Generate a concise, descriptive title for this conversation."""

PROMPT_SUMMARY = """Summarize the key points and decisions made in this conversation."""

PROMPT_DREAM = """You are a creative agent. Explore ideas, generate possibilities, and think freely.
You have access to memory for storing discoveries."""

PROMPT_DISTILL = """You are a distillation agent. Extract and condense key information from
the conversation history into concise, structured memory entries."""

PROMPT_GENERATE = """You are an agent configuration generator. Given a user's request,
generate an agent configuration with identifier, whenToUse description, and systemPrompt."""

PROMPT_COMPACTION = """You are a context compaction agent. Compress the conversation
history while preserving all semantically important information."""


PRESET_AGENTS: dict[str, AgentInfo] = {
    # ── Primary Agents ──
    "build": AgentInfo(
        name="build",
        description="Executes tools based on configured permissions.",
        mode="primary",
        native=True,
        color="#fb8147",
        allowed_tools=["*"],
        permission=Ruleset(allow=["*"]),
    ),
    "plan": AgentInfo(
        name="plan",
        description="Plan mode. Disallows all edit tools.",
        mode="primary",
        native=True,
        color="#c7e2a8",
        allowed_tools=["read_file", "search_files"],
        permission=Ruleset(allow=["read_file", "search_files"]),
        hard_permission=Ruleset(deny=["write_file", "terminal", "git", "edit"]),
    ),
    "compose": AgentInfo(
        name="compose",
        description="Compose mode. Orchestrates workflows with built-in compose skills.",
        mode="primary",
        native=True,
        color="#a7a3d8",
        permission=Ruleset(allow=["*"]),
    ),
    # ── Sub-agents ──
    "general": AgentInfo(
        name="general",
        description="General-purpose agent for researching complex questions and executing multi-step tasks.",
        mode="subagent",
        native=True,
        color="#aac4e1",
        permission=Ruleset(allow=["*"]),
    ),
    "explore": AgentInfo(
        name="explore",
        description="Fast agent specialized for exploring codebases. Use to quickly find files, search code, or answer questions.",
        mode="subagent",
        native=True,
        color="#f5c9b0",
        prompt=PROMPT_EXPLORE,
        allowed_tools=["read_file", "search_files", "web_search", "grep"],
        permission=Ruleset(allow=["read_file", "search_files", "grep"]),
    ),
    # ── Hidden Utility Sub-agents ──
    "title": AgentInfo(
        name="title",
        description="Generate conversation titles.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        prompt=PROMPT_TITLE,
        temperature=0.5,
        tool_allowlist=[],
    ),
    "summary": AgentInfo(
        name="summary",
        description="Summarize conversations.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        prompt=PROMPT_SUMMARY,
        tool_allowlist=[],
    ),
    "compaction": AgentInfo(
        name="compaction",
        description="Compress conversation context.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        prompt=PROMPT_COMPACTION,
        tool_allowlist=[],
    ),
    "checkpoint-writer": AgentInfo(
        name="checkpoint-writer",
        description="Writes checkpoints. Internal system agent.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        tool_allowlist=["read", "write", "edit", "glob", "grep"],
    ),
    "dream": AgentInfo(
        name="dream",
        description="Creative exploration agent with memory access.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        prompt=PROMPT_DREAM,
        allowed_tools=["read", "write", "edit", "glob", "grep", "memory", "bash"],
        tool_allowlist=["read", "write", "edit", "glob", "grep", "memory", "bash"],
        permission=Ruleset(allow=["read", "write", "edit", "glob", "grep", "memory", "bash"]),
    ),
    "distill": AgentInfo(
        name="distill",
        description="Distillation agent for extracting key information into memory.",
        mode="subagent",
        native=True,
        hidden=True,
        color="",
        prompt=PROMPT_DISTILL,
        allowed_tools=["read", "write", "edit", "glob", "grep", "memory", "bash"],
        tool_allowlist=["read", "write", "edit", "glob", "grep", "memory", "bash"],
        permission=Ruleset(allow=["read", "write", "edit", "glob", "grep", "memory", "bash"]),
    ),
}


# ═══════════════════════════════════════════════════════════
# runtimePermission — 合并 agent + user + hardPermission
# ═══════════════════════════════════════════════════════════

def runtime_permission(agent: AgentInfo, user_rules: Ruleset | None = None) -> Ruleset:
    """合并 Agent 权限与用户/会话权限，然后追加 hard_permission。
    移植自 agent.ts runtimePermission()"""
    return merge_rulesets(agent.permission, user_rules, agent.hard_permission)


# ═══════════════════════════════════════════════════════════
# AgentRegistry
# ═══════════════════════════════════════════════════════════

class AgentRegistry:
    """Agent 注册表 — 移植自 agent.ts Service"""

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

    def list_visible(self) -> list[tuple[str, AgentInfo]]:
        """列出可见且非 subagent 的 Agent"""
        return [
            (a, i) for a, i in self._agents.items()
            if not i.hidden and i.mode != "subagent"
        ]

    def list_subagents(self) -> list[tuple[str, AgentInfo]]:
        """列出 subagent 类型的 Agent"""
        return [
            (a, i) for a, i in self._agents.items()
            if i.mode == "subagent"
        ]

    def default(self) -> str:
        """返回默认 Agent ID（首个可见 primary agent）"""
        for aid, info in self._agents.items():
            if info.mode == "primary" and not info.hidden:
                return aid
        return "build"

    def runtime_permission(self, agent_id: str, user_rules: Ruleset | None = None) -> Ruleset:
        agent = self.get(agent_id)
        if not agent:
            return Ruleset()
        return merge_rulesets(agent.permission, user_rules, agent.hard_permission)

    def check_tool(self, agent_id: str, tool_name: str, user_rules: Ruleset | None = None) -> bool:
        return self.runtime_permission(agent_id, user_rules).evaluate(tool_name)

    def is_system_spawned(self, agent_id: str) -> bool:
        return agent_id in SYSTEM_SPAWNED_AGENT_TYPES


agents = AgentRegistry()


# ═══════════════════════════════════════════════════════════
# generate — LLM 驱动的 Agent 生成
# ═══════════════════════════════════════════════════════════

async def generate(
    description: str,
    existing_names: list[str] | None = None,
) -> dict | None:
    """用 LLM 从自然语言描述生成 Agent 配置 — 移植自 agent.ts Agent.generate()

    实际生产环境会调用 LLM API；当前为基于规则的快速生成。
    返回: {"identifier": str, "whenToUse": str, "systemPrompt": str}
    """
    existing = existing_names or [n for n, _ in agents.list()]
    desc = description.lower()

    identifier = description.split()[0].lower().replace("-", "_")[:24] if description.split() else "custom"

    # Deduplicate against existing
    if identifier in existing:
        idx = 2
        while f"{identifier}_{idx}" in existing:
            idx += 1
        identifier = f"{identifier}_{idx}"

    # Classify task type
    if any(w in desc for w in ["开发", "编码", "写代码", "implement", "build", "code", "feature"]):
        when_to_use = f"Use when you need to implement or build: {description}"
        system_prompt = (
            f"You are an agent specialized in: {description}. "
            "Implement directly — write working code, don't just provide plans."
        )
    elif any(w in desc for w in ["分析", "设计", "审查", "review", "plan", "analyze", "architect"]):
        when_to_use = f"Use when you need to analyze, review, or design: {description}"
        system_prompt = (
            f"You are an agent specialized in: {description}. "
            "Analyze thoroughly but do not modify code."
        )
    elif any(w in desc for w in ["搜索", "研究", "探索", "search", "research", "explore", "find"]):
        when_to_use = f"Use when you need to research or explore: {description}"
        system_prompt = (
            f"You are an agent specialized in: {description}. "
            "Search thoroughly and report findings."
        )
    elif any(w in desc for w in ["调试", "debug", "fix", "修复", "bug"]):
        when_to_use = f"Use when you need to debug or fix: {description}"
        system_prompt = (
            f"You are an agent specialized in debugging: {description}. "
            "Find root causes and fix issues systematically."
        )
    elif any(w in desc for w in ["测试", "test", "unit"]):
        when_to_use = f"Use when you need to write tests for: {description}"
        system_prompt = (
            f"You are an agent specialized in testing: {description}. "
            "Write comprehensive tests following TDD principles."
        )
    else:
        when_to_use = f"Use when you need to handle: {description}"
        system_prompt = (
            f"You are an agent specialized in: {description}. "
            "Handle the task efficiently and thoroughly."
        )

    result = {
        "identifier": identifier,
        "whenToUse": when_to_use,
        "systemPrompt": system_prompt,
    }

    # Auto-register
    info = AgentInfo(
        name=identifier,
        description=description,
        mode="subagent",
        prompt=system_prompt,
        allowed_tools=["read_file", "search_files"],
        permission=Ruleset(allow=["read_file", "search_files"]),
    )
    agents.register(identifier, info)

    return result
