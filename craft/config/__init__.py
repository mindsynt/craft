"""配置系统包 — 移植自 MiMo-Code packages/opencode/src/config/
支持多层级配置：全局 ~/.craft/config.jsonc → 项目 .craft/config.jsonc → 环境变量
"""

from __future__ import annotations

from typing import Any

# ── 错误类型 ──
from .error import (
    ConfigJsonError,
    ConfigInvalidError,
    ConfigFrontmatterError,
)

# ── 路径与常量 ──
from .paths import (
    CONFIG_DIR,
    PROJECT_CONFIG_FILES,
    MIMOCODE_GITIGNORE_ENTRIES,
    ensure_gitignore,
    find_config_files,
    find_config_directories,
    read_config_file,
)

# ── JSON / JSONC 解析 ──
from .parse import (
    find_project_config,
    load_jsonc_file,
    parse_jsonc,
    validate_schema,
    substitute_variables,
    config_entry_name_from_path,
    merge_config,
    load_config_file,
)

# ── 终端状态 ──
from .console_state import (
    ConsoleState,
    empty_console_state,
)

# ── 快捷键 ──
from .keybinds import (
    KeybindsConfig,
)

# ── 格式化 / LSP ──
from .formatter import (
    FormatterEntry,
    FormatterInfo,
    LSPEntry,
    LSPInfo,
)

# ── MCP ──
from .mcp import (
    MCPLocalConfig,
    MCPRemoteConfig,
    MCPConfig,
    MCP_SENSITIVE_KEYS,
    mcp_redact_string,
    mcp_redact_command,
    mcp_from_claude,
)

# ── 托管配置 ──
from .managed import (
    MANAGED_PLIST_DOMAIN,
    PLIST_META_KEYS,
    system_managed_config_dir,
    managed_config_dir,
    parse_managed_plist,
    read_managed_preferences,
)

# ── 配置模型 ──
from .settings import (
    # 基本类型
    ModelID,
    LayoutType,
    LAYOUT_VALUES,
    PermissionAction,
    PERMISSION_ACTIONS,
    PermissionInfo,
    parse_permission,
    # Provider 配置
    ModelCostConfig,
    ModelLimitConfig,
    ModelModalityConfig,
    ModelConfig,
    ProviderConfig,
    # Server 配置
    ServerConfig,
    # Plugin 配置
    PluginSpec,
    PluginOrigin,
    plugin_specifier,
    plugin_options,
    deduplicate_plugin_origins,
    # 子配置
    SkillsConfig,
    HistoryConfig,
    CommandConfig,
    ComposeConfig,
    COMPOSE_DEFAULT_DOCS_DIR,
    resolve_compose_docs_dir,
    AgentConfig,
    CompactionConfig,
    CheckpointPushCapsConfig,
    CheckpointConfig,
    MemoryConfig,
    DreamConfig,
    DistillConfig,
    VoiceConfig,
    WorkflowConfig,
    ToolConfig,
    WatcherConfig,
    ExperimentalConfig,
    # Markdown
    MARKDOWN_FILE_REGEX,
    MARKDOWN_SHELL_REGEX,
    parse_markdown_frontmatter,
    # 主配置模型
    CraftConfig,
    parse_thresholds,
)

# ── 配置加载 ──
from .load import (
    load_config,
    load_config_full,
    get_config,
    reload_config,
    get_provider_config,
    get_agent_config,
    get_mcp_configs,
    is_provider_enabled,
)
