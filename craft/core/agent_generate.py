"""
Agent 自动生成 — 移植自 agent->generate.txt
通过描述自动生成新的 Agent 配置
"""

from __future__ import annotations

from craft.core.agent import agents, AgentInfo
from craft.core.permission import Ruleset


def generate_agent_from_description(description: str) -> AgentInfo | None:
    """从自然语言描述生成 Agent 配置"""
    desc = description.lower()
    
    # 规则引擎匹配
    agent_config = {
        "name": "",
        "description": description,
        "mode": "primary",
        "allowed_tools": ["read_file", "search_files"],
        "temperature": 0.5,
    }
    
    if any(w in desc for w in ["开发", "编码", "写代码", "implement", "build", "code"]):
        agent_config.update({
            "name": description.split()[0].title() if description.split() else "Custom",
            "mode": "primary",
            "allowed_tools": ["read_file", "write_file", "search_files", "terminal", "git"],
            "temperature": 0.3,
        })
    elif any(w in desc for w in ["分析", "设计", "审查", "review", "plan", "analyze"]):
        agent_config.update({
            "name": description.split()[0].title() if description.split() else "Analyst",
            "mode": "primary",
            "allowed_tools": ["read_file", "search_files"],
            "temperature": 0.5,
        })
    elif any(w in desc for w in ["搜索", "研究", "探索", "search", "explore"]):
        agent_config.update({
            "name": description.split()[0].title() if description.split() else "Explorer",
            "mode": "subagent",
            "allowed_tools": ["read_file", "search_files", "web_search"],
            "temperature": 0.7,
        })
    else:
        agent_config["name"] = description.split()[0].title() if description.split() else "Custom"
    
    agent_id = description.split()[0].lower()[:16] if description.split() else "custom"
    agent_id = agent_id.replace("-", "_")
    
    info = AgentInfo(
        name=agent_config["name"],
        description=description,
        mode=agent_config["mode"],
        temperature=agent_config["temperature"],
        allowed_tools=agent_config["allowed_tools"],
        permission=Ruleset(allow=agent_config["allowed_tools"]),
    )
    
    agents.register(agent_id, info)
    return info


def list_custom_agents() -> list[tuple[str, AgentInfo]]:
    """列出用户自定义的 Agent（非预设）"""
    from craft.core.agent import PRESET_AGENTS
    return [(aid, info) for aid, info in agents.list() if aid not in PRESET_AGENTS]
