"""配置加载链 — 多层级配置加载：全局 → 项目 → 环境变量"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .error import ConfigJsonError
from .paths import CONFIG_DIR, find_config_directories, read_config_file
from .parse import substitute_variables, parse_jsonc, merge_config
from .settings import CraftConfig, ProviderConfig


def _normalize_loaded_config(data: dict, source: str) -> dict:
    """规范化加载的配置，处理废弃字段"""
    data = dict(data)
    # 移除已废弃的 tui 相关字段
    had_legacy = any(k in data for k in ["theme", "keybinds", "tui"])
    if had_legacy:
        data.pop("theme", None)
        data.pop("keybinds", None)
        data.pop("tui", None)
    return data


def _load_and_substitute(filepath: str) -> dict:
    """加载文件并进行变量替换"""
    text = read_config_file(filepath)
    if text is None:
        return {}
    expanded = substitute_variables(text, config_dir=str(Path(filepath).parent), config_source=filepath)
    data = parse_jsonc(expanded, filepath)
    return _normalize_loaded_config(data, filepath)


def load_config() -> CraftConfig:
    """加载完整配置链：全局 → 项目 → 环境变量"""
    config = CraftConfig()

    # 全局配置
    global_files = [
        CONFIG_DIR / "craft.jsonc",
        CONFIG_DIR / "craft.json",
        CONFIG_DIR / "config.jsonc",
        CONFIG_DIR / "config.json",
    ]
    for f in global_files:
        if f.exists():
            data = _load_and_substitute(str(f))
            config = CraftConfig(**merge_config(config.model_dump(), data))

    # 项目配置
    from .parse import find_project_config
    project_file = find_project_config()
    if project_file:
        data = _load_and_substitute(project_file)
        config = CraftConfig(**merge_config(config.model_dump(), data))

    # 环境变量覆盖
    if os.environ.get("OPENAI_API_KEY"):
        if "openai" not in config.provider:
            config.provider["openai"] = ProviderConfig()
        config.provider["openai"].api_key = os.environ["OPENAI_API_KEY"]

    return config


def load_config_full(directory: str | None = None, worktree: str | None = None) -> CraftConfig:
    """完整配置加载链（支持多层级 discovery）"""
    config = CraftConfig()

    # 1. 全局配置
    global_dir = str(CONFIG_DIR)
    for filename in ["craft.jsonc", "craft.json", "config.jsonc", "config.json"]:
        fp = Path(global_dir) / filename
        if fp.exists():
            data = _load_and_substitute(str(fp))
            config = CraftConfig(**merge_config(config.model_dump(), data))

    # 2. 项目配置 — 目录向上搜索
    start = directory or os.getcwd()
    for cfg_dir in find_config_directories(start, worktree):
        for filename in ["craft.jsonc", "craft.json", "config.jsonc", "config.json"]:
            fp = Path(cfg_dir) / filename
            if fp.exists():
                data = _load_and_substitute(str(fp))
                config = CraftConfig(**merge_config(config.model_dump(), data))

    # 3. 环境变量
    if os.environ.get("OPENAI_API_KEY"):
        if "openai" not in config.provider:
            config.provider["openai"] = ProviderConfig()
        config.provider["openai"].api_key = os.environ["OPENAI_API_KEY"]

    if os.environ.get("CRAFT_CONFIG_CONTENT"):
        import json as _json
        try:
            extra = _json.loads(os.environ["CRAFT_CONFIG_CONTENT"])
            if isinstance(extra, dict):
                config = CraftConfig(**merge_config(config.model_dump(), extra))
        except json.JSONDecodeError:
            pass

    return config


# ═══════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════

_config: CraftConfig | None = None


def get_config() -> CraftConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config():
    global _config
    _config = load_config()


# ═══════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════


def get_provider_config(provider_id: str, model: str | None = None) -> ProviderConfig:
    """获取提供商配置"""
    cfg = get_config()
    pc = cfg.provider.get(provider_id, ProviderConfig())
    if model and not pc.model:
        pc.model = f"{provider_id}/{model}" if "/" not in model else model
    return pc


def get_agent_config(agent_id: str | None = None) -> Any:
    """获取 Agent 配置"""
    from .settings import AgentConfig
    cfg = get_config()
    aid = agent_id or cfg.default_agent
    return cfg.agent.get(aid, AgentConfig(name=aid))


def get_mcp_configs() -> dict[str, Any]:
    """获取所有 MCP 配置"""
    return get_config().mcp


def is_provider_enabled(provider_id: str) -> bool:
    """检查提供商是否启用"""
    cfg = get_config()
    if cfg.enabled_providers is not None:
        return provider_id in cfg.enabled_providers
    if cfg.disabled_providers is not None:
        return provider_id not in cfg.disabled_providers
    return True
