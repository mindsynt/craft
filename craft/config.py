"""
配置系统 — 移植自 MiMo-Code packages/opencode/src/config/
支持多层级配置：全局 ~/.craft/config.jsonc → 项目 .craft/config.jsonc → 环境变量
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".craft"
PROJECT_CONFIG_FILES = ["craft.jsonc", "craft.json", ".craft/config.jsonc", ".craft/config.json"]


def find_project_config(start: str | None = None) -> str | None:
    """从当前目录向上查找项目配置"""
    cwd = Path(start or os.getcwd())
    for parent in [cwd] + list(cwd.parents):
        for name in PROJECT_CONFIG_FILES:
            p = parent / name
            if p.exists():
                return str(p)
    return None


class ProviderConfig(BaseModel):
    """模型提供商配置"""
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    temperature: float | None = None
    model: str | None = None
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])


class MCPConfig(BaseModel):
    """MCP 服务器配置"""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class CheckpointConfig(BaseModel):
    """检查点配置"""
    memory_reconcile_on_search: bool = True
    memory_search_score_floor: float = 0.15


class CraftConfig(BaseModel):
    """完整配置"""
    schema_ref: str = "https://mimo.xiaomi.com/mimocode/config.json"
    log_level: str = "INFO"
    model: str = ""
    default_agent: str = "build"
    agent: dict[str, AgentConfig] = Field(default_factory=dict)
    provider: dict[str, ProviderConfig] = Field(default_factory=dict)
    mcp: dict[str, MCPConfig] = Field(default_factory=dict)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)


def load_config_file(path: str) -> dict:
    """加载 JSON/JSONC 配置文件"""
    try:
        text = Path(path).read_text(encoding="utf-8")
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            lines.append(line)
        return json.loads("\n".join(lines))
    except Exception:
        return {}


def merge_config(base: dict, overlay: dict) -> dict:
    """深度合并配置"""
    result = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = merge_config(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> CraftConfig:
    """加载完整配置链"""
    config = CraftConfig()

    # 全局配置
    global_files = [CONFIG_DIR / "mimocode.jsonc", CONFIG_DIR / "config.jsonc", CONFIG_DIR / "config.json"]
    for f in global_files:
        if f.exists():
            data = load_config_file(str(f))
            config = CraftConfig(**merge_config(config.model_dump(), data))

    # 项目配置
    project_file = find_project_config()
    if project_file:
        data = load_config_file(project_file)
        config = CraftConfig(**merge_config(config.model_dump(), data))

    # 环境变量覆盖
    if os.environ.get("OPENAI_API_KEY"):
        if "openai" not in config.provider:
            config.provider["openai"] = ProviderConfig()
        config.provider["openai"].api_key = os.environ["OPENAI_API_KEY"]

    return config


_config: CraftConfig | None = None


def get_config() -> CraftConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config():
    global _config
    _config = load_config()
