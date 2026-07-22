"""配置模型 — CraftConfig 及所有子配置模型"""

from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .error import ConfigFrontmatterError, ConfigInvalidError
from .mcp import MCPConfig
from .keybinds import KeybindsConfig
from .formatter import FormatterEntry, FormatterInfo, LSPEntry, LSPInfo
from .console_state import ConsoleState

# ═══════════════════════════════════════════════════════════
# Model ID (对应 model-id.ts)
# ═══════════════════════════════════════════════════════════

# ModelID 只是一个字符串约束: provider/model 或 group name
ModelID = str


# ═══════════════════════════════════════════════════════════
# Layout (对应 layout.ts)
# ═══════════════════════════════════════════════════════════

LayoutType = str  # "auto" | "stretch"
LAYOUT_VALUES = ["auto", "stretch"]


# ═══════════════════════════════════════════════════════════
# Permission (对应 permission.ts)
# ═══════════════════════════════════════════════════════════

PermissionAction = str  # "ask" | "allow" | "deny"
PERMISSION_ACTIONS = ["ask", "allow", "deny"]

# Permission: dict[str, PermissionAction] — key 是工具名或 "*"
PermissionInfo = dict[str, PermissionAction]


def parse_permission(data: Any) -> PermissionInfo:
    """解析权限配置

    支持:
    - "allow" → {"*": "allow"}
    - {"*": "allow", "write": "deny"} → 直接使用
    """
    if isinstance(data, str):
        action = data if data in PERMISSION_ACTIONS else "ask"
        return {"*": action}
    if isinstance(data, dict):
        result: PermissionInfo = {}
        for key, val in data.items():
            if key == "__originalKeys":
                continue
            if isinstance(val, str) and val in PERMISSION_ACTIONS:
                result[key] = val
            elif isinstance(val, dict):
                # 嵌套规则
                result[key] = val  # type: ignore
            else:
                result[key] = str(val) if val in PERMISSION_ACTIONS else "ask"
        return result
    return {}


# ═══════════════════════════════════════════════════════════
# Server (对应 server.ts)
# ═══════════════════════════════════════════════════════════


class ServerConfig(BaseModel):
    """服务器配置"""
    port: int | None = None
    hostname: str | None = None
    mdns: bool | None = None
    mdns_domain: str | None = None
    cors: list[str] | None = None


# ═══════════════════════════════════════════════════════════
# Provider 配置 (对应 provider.ts, 增强)
# ═══════════════════════════════════════════════════════════


class ModelCostConfig(BaseModel):
    """模型费用"""
    input: float = 0.0
    output: float = 0.0
    cache_read: float | None = None
    cache_write: float | None = None


class ModelLimitConfig(BaseModel):
    """模型限制"""
    context: int = 4096
    input: int | None = None
    output: int = 4096


class ModelModalityConfig(BaseModel):
    """模型模态"""
    input: list[str] = Field(default_factory=lambda: ["text"])
    output: list[str] = Field(default_factory=lambda: ["text"])


class ModelConfig(BaseModel):
    """模型配置"""
    id: str | None = None
    name: str | None = None
    family: str | None = None
    release_date: str | None = None
    attachment: bool | None = None
    reasoning: bool | None = None
    temperature: bool | None = None
    tool_call: bool | None = None
    cost: ModelCostConfig | None = None
    limit: ModelLimitConfig | None = None
    modalities: ModelModalityConfig | None = None
    experimental: bool | None = None
    status: str | None = None  # "alpha" | "beta" | "deprecated"
    options: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    variants: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    """模型提供商配置"""
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7

    # 增强字段
    name: str | None = None
    api: str | None = None
    env: list[str] | None = None
    id: str | None = None
    npm: str | None = None
    whitelist: list[str] | None = None
    blacklist: list[str] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    only_configured_models: bool = False


# ═══════════════════════════════════════════════════════════
# Plugin 配置 (对应 plugin.ts)
# ═══════════════════════════════════════════════════════════

# Plugin Spec: str (name) or [str, dict] (name + options)
PluginSpec = str | tuple[str, dict]


@dataclass
class PluginOrigin:
    """Plugin 来源"""
    spec: PluginSpec
    source: str
    scope: str  # "global" | "local"


def plugin_specifier(spec: PluginSpec) -> str:
    """获取插件标识符"""
    return spec[0] if isinstance(spec, (list, tuple)) else spec


def plugin_options(spec: PluginSpec) -> dict | None:
    """获取插件选项"""
    return spec[1] if isinstance(spec, (list, tuple)) and len(spec) > 1 else None


def deduplicate_plugin_origins(plugins: list[PluginOrigin]) -> list[PluginOrigin]:
    """去重插件来源，保留胜出的 spec"""
    seen: set[str] = set()
    result: list[PluginOrigin] = []
    for plugin in reversed(plugins):
        spec = plugin_specifier(plugin.spec)
        name = spec if spec.startswith("file://") else spec.split("/")[-1] if "/" in spec else spec
        if name in seen:
            continue
        seen.add(name)
        result.append(plugin)
    result.reverse()
    return result


# ═══════════════════════════════════════════════════════════
# Skills 配置 (对应 skills.ts)
# ═══════════════════════════════════════════════════════════


class SkillsConfig(BaseModel):
    """技能配置"""
    paths: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# History (对应 history.ts)
# ═══════════════════════════════════════════════════════════


class HistoryConfig(BaseModel):
    """历史记录配置"""
    kinds: list[str] | None = None


# ═══════════════════════════════════════════════════════════
# Command 配置 (对应 command.ts)
# ═══════════════════════════════════════════════════════════


class CommandConfig(BaseModel):
    """命令配置"""
    template: str = ""
    description: str | None = None
    agent: str | None = None
    model: ModelID | None = None
    subtask: bool | None = None


# ═══════════════════════════════════════════════════════════
# Compose 配置 (对应 compose.ts)
# ═══════════════════════════════════════════════════════════


class ComposeConfig(BaseModel):
    """Compose 模式配置"""
    docs: str | None = None
    docs_absolute: bool | None = None


COMPOSE_DEFAULT_DOCS_DIR = "docs/compose"


def resolve_compose_docs_dir(worktree: str, cfg: ComposeConfig | None = None) -> str:
    """解析 docs 目录路径"""
    configured = cfg.docs if cfg and cfg.docs else COMPOSE_DEFAULT_DOCS_DIR
    if os.path.isabs(configured) or (cfg and cfg.docs_absolute):
        return os.path.abspath(os.path.join(worktree, configured))
    return configured


# ═══════════════════════════════════════════════════════════
# Agent 配置 (对应 agent.ts, 增强)
# ═══════════════════════════════════════════════════════════


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    temperature: float | None = None
    model: str | None = None
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    permission: PermissionInfo = Field(default_factory=dict)
    variant: str | None = None
    top_p: float | None = None
    prompt: str | None = None
    disable: bool | None = None
    mode: str | None = None  # "subagent" | "primary" | "all"
    hidden: bool | None = None
    color: str | None = None
    steps: int | None = None
    tool_allowlist: list[str] | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    def get_permission(self, tool: str) -> str | None:
        """获取工具权限"""
        if self.permission:
            if tool in self.permission:
                p = self.permission[tool]
                return p if isinstance(p, str) else None
            if "*" in self.permission:
                p = self.permission["*"]
                return p if isinstance(p, str) else None
        return None


# ═══════════════════════════════════════════════════════════
# Markdown / Frontmatter (对应 markdown.ts)
# ═══════════════════════════════════════════════════════════

MARKDOWN_FILE_REGEX = re.compile(r"(?<![\\w`])@(\\.?[^\\s`,.]*(?:\\.[^\\s`,.]+)*)")
MARKDOWN_SHELL_REGEX = re.compile(r"!`([^`]+)`")


def parse_markdown_frontmatter(file_path: str) -> dict:
    """解析 Markdown 文件的 YAML frontmatter"""
    content = Path(file_path).read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        return {"data": {}, "content": content.strip()}

    frontmatter_text = match.group(1)
    body = content[match.end():].strip()

    try:
        import yaml
        data = yaml.safe_load(frontmatter_text) or {}
    except ImportError:
        # 简易解析
        data = _parse_simple_yaml(frontmatter_text)
    except Exception as e:
        # fallback: 宽松解析
        try:
            data = _parse_fallback_yaml(frontmatter_text)
        except Exception:
            raise ConfigFrontmatterError(
                file_path,
                f"{file_path}: Failed to parse YAML frontmatter: {e}",
            )

    if not isinstance(data, dict):
        data = {}

    return {"data": data, "content": body}


def _parse_simple_yaml(text: str) -> dict:
    """简易 YAML key: value 解析"""
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            result[key] = value
    return result


def _parse_fallback_yaml(frontmatter: str) -> dict:
    """宽松 frontmatter 解析 — 处理 Claude Code 的不标准 YAML"""
    lines = frontmatter.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            result.append(line)
            continue
        if re.match(r"^\s+", line):
            result.append(line)
            continue
        kv = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
        if not kv:
            result.append(line)
            continue
        key = kv.group(1)
        value = kv.group(2).strip()
        if value in ("", ">", "|") or value.startswith('"') or value.startswith("'"):
            result.append(line)
            continue
        if ":" in value:
            result.append(f"{key}: |-")
            result.append(f"  {value}")
            continue
        result.append(line)

    processed = "\n".join(result)
    try:
        import yaml
        return yaml.safe_load(processed) or {}
    except ImportError:
        return _parse_simple_yaml(processed)


# ═══════════════════════════════════════════════════════════
# Compaction 配置 (来自 config.ts)
# ═══════════════════════════════════════════════════════════


class CompactionConfig(BaseModel):
    """压缩配置"""
    auto: bool = True
    prune: bool = True
    tail_turns: int = 2
    preserve_recent_tokens: int | None = None
    reserved: int | None = None


class CheckpointPushCapsConfig(BaseModel):
    """检查点推送容量"""
    tasks_ledger: int = 2000
    focus_task: int = 4000
    actor_ledger: int = 500
    memory_titles: int = 500
    global_: int = 6000
    checkpoint: int = 11000
    memory: int = 10000
    notes: int = 6000
    design_decisions: int = 3000
    open_notes: int = 800
    recent_user: int = 16000
    recent_user_per_msg: int = 2000


class CheckpointConfig(BaseModel):
    """检查点配置"""
    memory_reconcile_on_search: bool = True
    memory_search_score_floor: float = 0.15
    thresholds: list[str] | None = None
    reserved: int | None = None
    max_writer_failures: int | None = None
    fork: bool | None = None
    task_archive_days: int | None = None
    push_caps: CheckpointPushCapsConfig | None = None


class MemoryConfig(BaseModel):
    """记忆配置"""
    cc_index: bool = False


class DreamConfig(BaseModel):
    """梦境（记忆整合）配置"""
    auto: bool = True
    interval_days: int = 7


class DistillConfig(BaseModel):
    """蒸馏配置"""
    auto: bool = True
    interval_days: int = 30


class VoiceConfig(BaseModel):
    """语音配置"""
    asr_model: ModelID | None = None
    control_model: ModelID | None = None


class WorkflowConfig(BaseModel):
    """工作流配置"""
    max_concurrent_agents: int | None = None
    max_depth: int = 8
    max_lifecycle_agents: int = 1000
    script_deadline_ms: int = 12 * 3600 * 1000


class ToolConfig(BaseModel):
    """工具配置"""
    invocation_style: str | None = None  # "json" | "shell"
    invocation_style_by_tool: dict[str, str] = Field(default_factory=dict)


class WatcherConfig(BaseModel):
    """文件监听配置"""
    ignore: list[str] = Field(default_factory=list)


class ExperimentalConfig(BaseModel):
    """实验性功能配置"""
    disable_paste_summary: bool | None = None
    batch_tool: bool | None = None
    open_telemetry: bool | None = None
    primary_tools: list[str] | None = None
    continue_loop_on_deny: bool | None = None
    mcp_timeout: int | None = None
    predict_next_prompt: bool | None = None


# ═══════════════════════════════════════════════════════════
# 完整 CraftConfig (主入口)
# ═══════════════════════════════════════════════════════════


def parse_thresholds(value: Any) -> list[str] | None:
    """解析阈值配置，支持百分比和绝对值"""
    if isinstance(value, list):
        return [str(v) for v in value]
    return None


# Type alias forward declarations
FormatterInfo = bool | dict[str, "FormatterEntry"]
LSPInfo = bool | dict[str, "LSPEntry | dict"]


class CraftConfig(BaseModel):
    """完整配置"""
    # Schema
    schema_ref: str = "https://mimo.xiaomi.com/mimocode/config.json"
    schema_url: str | None = Field(default=None, alias="$schema")

    # 基础
    log_level: str = "INFO"
    model: str = ""
    small_model: ModelID | None = None
    vision_model: ModelID | None = None
    model_groups: dict[str, Any] = Field(default_factory=dict)
    default_agent: str = "build"
    username: str | None = None

    # Agent & Mode
    agent: dict[str, AgentConfig] = Field(default_factory=dict)
    mode: dict[str, AgentConfig] = Field(default_factory=dict)

    # Provider
    provider: dict[str, ProviderConfig] = Field(default_factory=dict)
    enabled_providers: list[str] | None = None
    disabled_providers: list[str] | None = None

    # MCP
    mcp: dict[str, MCPConfig] = Field(default_factory=dict)
    mcp_origins: dict[str, Any] | None = None

    # 权限
    permission: PermissionInfo = Field(default_factory=dict)
    tools: dict[str, bool] | None = None
    tool: ToolConfig | None = None

    # 服务器
    server: ServerConfig | None = None

    # 命令 & 技能
    command: dict[str, CommandConfig] = Field(default_factory=dict)
    compose: ComposeConfig | None = None
    skills: SkillsConfig | None = None
    plugin: list[PluginSpec] = Field(default_factory=list)
    plugin_origins: list[PluginOrigin] | None = None

    # 格式 & LSP
    formatter: FormatterInfo | None = None
    lsp: LSPInfo | None = None

    # 检查点
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)

    # 压缩
    compaction: CompactionConfig | None = None

    # 历史
    history: HistoryConfig | None = None

    # 记忆
    memory: MemoryConfig | None = None

    # 梦境 & 蒸馏
    dream: DreamConfig | None = None
    distill: DistillConfig | None = None

    # 语音
    voice: VoiceConfig | None = None

    # 工作流
    workflow: WorkflowConfig | None = None

    # 文件监听
    watcher: WatcherConfig | None = None

    # 实验性
    experimental: ExperimentalConfig | None = None

    # 共享
    share: str | None = None  # "manual" | "auto" | "disabled"
    autoshare: bool | None = None

    # 自动更新
    autoupdate: bool | str | None = None

    # 布局
    layout: LayoutType | None = None

    # 快照
    snapshot: bool | None = None

    # 企业
    enterprise: dict[str, Any] | None = None

    # 说明
    instructions: list[str] = Field(default_factory=list)

    # 快捷键
    keybinds: KeybindsConfig | None = None

    # 控制台状态
    console_state: ConsoleState | None = None

    def model_post_init(self, __context: Any) -> None:
        """初始化后的后处理"""
        if self.autoshare is True and not self.share:
            self.share = "auto"
        if not self.username:
            import getpass
            self.username = getpass.getuser()
        # 迁移 $schema
        if self.schema_url and not self.schema_ref:
            self.schema_ref = self.schema_url
        elif not self.schema_url:
            self.schema_url = self.schema_ref
