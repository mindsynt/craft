"""插件系统包 — 移植自 packages/opencode/src/plugin/
支持：动态加载、生命周期钩子、依赖注入、规范解析、元数据跟踪
"""

from __future__ import annotations

from typing import Any

# ── 共享工具 ──
from .shared import (
    PluginSource,
    PluginKind,
    PluginPackage,
    PluginEntry,
    is_deprecated_plugin,
    parse_plugin_specifier,
    is_path_plugin_spec,
    plugin_source,
    read_plugin_package,
    resolve_path_plugin_target,
    resolve_plugin_target,
    create_plugin_entry,
    check_plugin_compatibility,
    read_v1_plugin,
    read_plugin_id,
    resolve_plugin_id,
    read_package_themes,
)

# ── 安装 ──
from .install import (
    Target,
    PatchInput,
    PatchItem,
    install_plugin,
    read_plugin_manifest,
    patch_plugin_config,
)

# ── 匹配器 ──
from .matcher import (
    ActorMatcher,
    matches_actor,
)

# ── 元数据 ──
from .meta import (
    MetaEntry,
    Theme,
    TouchItem,
    MetaState,
    touch,
    touch_many,
    set_theme,
    list_meta,
)

# ── 加载器 ──
from .loader import (
    LoaderPlan,
    LoaderResolved,
    LoaderMissing,
    LoaderLoaded,
    LoaderReport,
    loader_resolve,
    loader_load,
    loader_load_external,
)

# ── 管理器 ──
from .manager import (
    PluginHook,
    PluginManifest,
    Plugin,
    PluginManager,
    plugin_manager,
    get_internal_plugins,
)

# ── Provider 插件 ──
from .xai import (
    make_xai_auth_plugin,
)
from .mimo import (
    make_mimo_auth_plugin,
    make_anthropic_proxy_plugin,
)
from .codex import (
    make_codex_auth_plugin,
)
from .copilot import (
    copilot_models_fetch,
    make_copilot_auth_plugin,
)
from .cloudflare import (
    make_cloudflare_workers_auth_plugin,
    make_cloudflare_ai_gateway_auth_plugin,
)
from .hook_plugins import (
    make_subagent_progress_checker_plugin,
    make_checkpoint_splitover_plugin,
)

__all__ = [
    "PluginManager",
    "Plugin",
    "PluginManifest",
    "PluginHook",
    "plugin_manager",
    "PluginSource",
    "PluginKind",
    "PluginPackage",
    "PluginEntry",
    "Target",
    "PatchInput",
    "PatchItem",
    "LoaderPlan",
    "LoaderResolved",
    "LoaderMissing",
    "LoaderLoaded",
    "LoaderReport",
    "MetaEntry",
    "Theme",
    "TouchItem",
    "MetaState",
    "ActorMatcher",
    # Functions
    "is_deprecated_plugin",
    "parse_plugin_specifier",
    "is_path_plugin_spec",
    "plugin_source",
    "read_plugin_package",
    "resolve_path_plugin_target",
    "resolve_plugin_target",
    "create_plugin_entry",
    "check_plugin_compatibility",
    "read_v1_plugin",
    "read_plugin_id",
    "resolve_plugin_id",
    "read_package_themes",
    "install_plugin",
    "read_plugin_manifest",
    "patch_plugin_config",
    "matches_actor",
    "touch",
    "touch_many",
    "set_theme",
    "list_meta",
    "loader_resolve",
    "loader_load",
    "loader_load_external",
    "copilot_models_fetch",
    "get_internal_plugins",
    # Provider plugins
    "make_xai_auth_plugin",
    "make_mimo_auth_plugin",
    "make_anthropic_proxy_plugin",
    "make_codex_auth_plugin",
    "make_cloudflare_workers_auth_plugin",
    "make_cloudflare_ai_gateway_auth_plugin",
    "make_copilot_auth_plugin",
    "make_subagent_progress_checker_plugin",
    "make_checkpoint_splitover_plugin",
]
