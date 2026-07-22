"""
配置系统 — 移植自 MiMo-Code packages/opencode/src/config/
支持多层级配置：全局 ~/.craft/config.jsonc → 项目 .craft/config.jsonc → 环境变量
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / ".craft"
PROJECT_CONFIG_FILES = ["craft.jsonc", "craft.json", ".craft/config.jsonc", ".craft/config.json"]

# ═══════════════════════════════════════════════════════════
# 错误类型 (对应 error.ts)
# ═══════════════════════════════════════════════════════════


class ConfigJsonError(Exception):
    """JSON 解析错误"""

    def __init__(self, path: str, message: str | None = None):
        self.path = path
        self.message = message or f"Failed to parse config: {path}"
        super().__init__(self.message)


class ConfigInvalidError(Exception):
    """Schema 验证错误"""

    def __init__(self, path: str, issues: list[dict] | None = None, message: str | None = None):
        self.path = path
        self.issues = issues or []
        self.message = message or f"Invalid config: {path}"
        super().__init__(self.message)


class ConfigFrontmatterError(Exception):
    """Markdown frontmatter 解析错误"""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(message)


# ═══════════════════════════════════════════════════════════
# 解析工具 (对应 parse.ts)
# ═══════════════════════════════════════════════════════════


def find_project_config(start: str | None = None) -> str | None:
    """从当前目录向上查找项目配置"""
    cwd = Path(start or os.getcwd())
    for parent in [cwd] + list(cwd.parents):
        for name in PROJECT_CONFIG_FILES:
            p = parent / name
            if p.exists():
                return str(p)
    return None


def load_jsonc_file(path: str) -> dict:
    """加载 JSON/JSONC 配置文件，去除注释"""
    try:
        text = Path(path).read_text(encoding="utf-8")
        return parse_jsonc(text, path)
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise ConfigJsonError(path, str(e)) from e


def parse_jsonc(text: str, filepath: str) -> dict:
    """解析 JSONC 文本，支持 // 和 # 注释，支持尾逗号"""
    result, errors = _parse_jsonc_inner(text)
    if errors:
        lines = text.split("\n")
        issues = []
        for err in errors:
            line_no = text[: err["offset"]].count("\n") + 1
            problem_line = lines[line_no - 1] if line_no <= len(lines) else ""
            msg = f"{err['msg']} at line {line_no}"
            if problem_line:
                msg += f"\n   Line {line_no}: {problem_line}"
            issues.append(msg)
        raise ConfigJsonError(filepath, "\n".join(issues))
    return result


def _strip_jsonc_comments(text: str) -> str:
    """去除 JSONC 中的注释（单行 //, # 和多行 /* */），正确处理字符串"""
    result = []
    i = 0
    in_string = False
    string_char = None
    escape = False

    while i < len(text):
        ch = text[i]

        # 字符串状态
        if in_string:
            if escape:
                escape = False
                result.append(ch)
                i += 1
                continue
            if ch == "\\":
                escape = True
                result.append(ch)
                i += 1
                continue
            if ch == string_char:
                in_string = False
            result.append(ch)
            i += 1
            continue

        # 行注释 //
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            end = text.find("\n", i)
            if end == -1:
                break
            result.append("\n")
            i = end + 1
            continue

        # 行注释 #
        if ch == "#":
            end = text.find("\n", i)
            if end == -1:
                break
            result.append("\n")
            i = end + 1
            continue

        # 多行注释 /* */
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                break
            # 保留注释内的换行
            for c in text[i:end + 2]:
                if c == "\n":
                    result.append("\n")
            i = end + 2
            continue

        # 字符串开始
        if ch in ('"', "'"):
            in_string = True
            string_char = ch

        result.append(ch)
        i += 1

    return "".join(result)


def _parse_jsonc_inner(text: str) -> tuple[dict, list[dict]]:
    """JSONC 解析器"""
    errors = []

    # 去除注释
    cleaned_text = _strip_jsonc_comments(text)

    # 去除尾逗号
    cleaned_text = re.sub(r",\s*([}\]])", r"\1", cleaned_text)

    try:
        data = json.loads(cleaned_text)
        if not isinstance(data, dict):
            errors.append({"msg": "Expected a JSON object", "offset": 0})
            return {}, errors
        return data, []
    except json.JSONDecodeError as e:
        errors.append({"msg": str(e), "offset": e.pos})
        return {}, errors


def validate_schema(data: dict, source: str) -> dict:
    """基础 schema 验证 — 确保顶层是 dict"""
    if not isinstance(data, dict):
        raise ConfigInvalidError(source, [{"msg": "Config must be a JSON object"}])
    return data


# ═══════════════════════════════════════════════════════════
# 变量替换 (对应 variable.ts)
# ═══════════════════════════════════════════════════════════


def substitute_variables(text: str, config_dir: str | None = None, config_source: str | None = None, missing: str = "error") -> str:
    """
    应用 {env:VAR} 和 {file:path} 替换到配置文本中。
    missing: "error" — 文件不存在则抛错；"empty" — 返回空字符串
    """
    # 环境变量替换
    result = re.sub(r"\{env:([^}]+)\}", lambda m: os.environ.get(m.group(1), ""), text)

    # 文件引用替换
    file_refs = list(re.finditer(r"\{file:[^}]+\}", result))
    if not file_refs:
        return result

    config_dir_p = Path(config_dir) if config_dir else Path.cwd()
    out = ""
    cursor = 0

    for match in file_refs:
        token = match.group(0)
        idx = match.start()
        out += result[cursor:idx]

        # 检查是否在注释行中
        line_start = result.rfind("\n", 0, idx) + 1
        prefix = result[line_start:idx].strip()
        if prefix.startswith("//") or prefix.startswith("#"):
            out += token
            cursor = idx + len(token)
            continue

        file_path_raw = token.replace("{file:", "").rstrip("}")
        path_obj = Path(file_path_raw)

        # 处理 ~/
        if file_path_raw.startswith("~/"):
            path_obj = Path.home() / file_path_raw[2:]
        elif not path_obj.is_absolute():
            path_obj = config_dir_p / file_path_raw

        try:
            content = path_obj.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            if missing == "empty":
                content = ""
            else:
                err_msg = f'bad file reference: "{token}" {path_obj} does not exist'
                raise ConfigInvalidError(
                    path=config_source or "unknown",
                    message=err_msg,
                ) from None
        except Exception as e:
            raise ConfigInvalidError(
                path=config_source or "unknown",
                message=f'bad file reference: "{token}": {e}',
            ) from e

        out += json.dumps(content)[1:-1]
        cursor = idx + len(token)

    out += result[cursor:]
    return out


# ═══════════════════════════════════════════════════════════
# Entry Name (对应 entry-name.ts)
# ═══════════════════════════════════════════════════════════


def config_entry_name_from_path(file_path: str, search_roots: list[str]) -> str:
    """从文件路径提取配置项名称"""
    normalized = file_path.replace("\\", "/")
    for root in search_roots:
        idx = normalized.find(root)
        if idx >= 0:
            candidate = normalized[idx + len(root):]
            ext_idx = candidate.rfind(".")
            return candidate[:ext_idx] if ext_idx > 0 else candidate
    # fallback to basename
    name = Path(file_path).stem
    return name


# ═══════════════════════════════════════════════════════════
# Gitignore (对应 gitignore.ts)
# ═══════════════════════════════════════════════════════════

MIMOCODE_GITIGNORE_ENTRIES = [
    "node_modules",
    "package.json",
    "package-lock.json",
    "bun.lock",
    ".gitignore",
    ".cron-lock",
    "scheduled_tasks.json",
]


def ensure_gitignore(dir_path: str) -> None:
    """确保 .craft 目录有 .gitignore"""
    gitignore_path = Path(dir_path) / ".gitignore"
    if gitignore_path.exists():
        return
    try:
        gitignore_path.write_text("\n".join(MIMOCODE_GITIGNORE_ENTRIES))
    except PermissionError:
        pass


# ═══════════════════════════════════════════════════════════
# Console State (对应 console-state.ts)
# ═══════════════════════════════════════════════════════════


@dataclass
class ConsoleState:
    """控制台状态"""
    console_managed_providers: list[str] = field(default_factory=list)
    active_org_name: str | None = None
    switchable_org_count: int = 0


def empty_console_state() -> ConsoleState:
    return ConsoleState(
        console_managed_providers=[],
        active_org_name=None,
        switchable_org_count=0,
    )


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
# Keybinds (对应 keybinds.ts)
# ═══════════════════════════════════════════════════════════


@dataclass
class KeybindsConfig:
    """快捷键配置"""
    leader: str = "ctrl+x"
    app_exit: str = "ctrl+c,ctrl+d,<leader>q"
    editor_open: str = "<leader>e"
    theme_list: str = "<leader>t"
    sidebar_toggle: str = "<leader>b"
    scrollbar_toggle: str = "none"
    username_toggle: str = "none"
    status_view: str = "<leader>s"
    session_export: str = "<leader>x"
    session_new: str = "<leader>n"
    session_list: str = "<leader>l"
    session_timeline: str = "<leader>g"
    session_fork: str = "none"
    session_rename: str = "ctrl+r"
    session_delete: str = "ctrl+d"
    stash_delete: str = "ctrl+d"
    model_provider_list: str = "ctrl+a"
    model_favorite_toggle: str = "ctrl+f"
    session_share: str = "none"
    session_unshare: str = "none"
    session_interrupt: str = "escape"
    session_compact: str = "<leader>c"
    messages_page_up: str = "pageup,ctrl+alt+b"
    messages_page_down: str = "pagedown,ctrl+alt+f"
    messages_line_up: str = "ctrl+alt+y"
    messages_line_down: str = "ctrl+alt+e"
    messages_half_page_up: str = "ctrl+alt+u"
    messages_half_page_down: str = "ctrl+alt+d"
    messages_first: str = "ctrl+g,home"
    messages_last: str = "ctrl+alt+g,end"
    messages_next: str = "none"
    messages_previous: str = "none"
    messages_last_user: str = "none"
    messages_copy: str = "<leader>y"
    messages_undo: str = "<leader>u"
    messages_redo: str = "<leader>r"
    messages_toggle_conceal: str = "<leader>h"
    tool_details: str = "none"
    model_list: str = "<leader>m"
    model_cycle_recent: str = "f2"
    model_cycle_recent_reverse: str = "shift+f2"
    model_cycle_favorite: str = "none"
    model_cycle_favorite_reverse: str = "none"
    command_list: str = "ctrl+p"
    agent_list: str = "<leader>a"
    agent_cycle: str = "tab"
    agent_cycle_reverse: str = "shift+tab"
    variant_cycle: str = "ctrl+t"
    variant_list: str = "none"
    input_clear: str = "ctrl+c"
    input_paste: str = "super+v,ctrl+v"
    input_submit: str = "return"
    input_newline: str = "shift+return,ctrl+return,alt+return,ctrl+j"
    input_move_left: str = "left,ctrl+b"
    input_move_right: str = "right,ctrl+f"
    input_move_up: str = "up"
    input_move_down: str = "down"
    input_select_left: str = "shift+left"
    input_select_right: str = "shift+right"
    input_select_up: str = "shift+up"
    input_select_down: str = "shift+down"
    input_line_home: str = "ctrl+a"
    input_line_end: str = "ctrl+e"
    input_select_line_home: str = "ctrl+shift+a"
    input_select_line_end: str = "ctrl+shift+e"
    input_visual_line_home: str = "alt+a"
    input_visual_line_end: str = "alt+e"
    input_select_visual_line_home: str = "alt+shift+a"
    input_select_visual_line_end: str = "alt+shift+e"
    input_buffer_home: str = "home"
    input_buffer_end: str = "end"
    input_select_buffer_home: str = "shift+home"
    input_select_buffer_end: str = "shift+end"
    input_delete_line: str = "ctrl+shift+d"
    input_delete_to_line_end: str = "ctrl+k"
    input_delete_to_line_start: str = "ctrl+u"
    input_backspace: str = "backspace,shift+backspace"
    input_delete: str = "ctrl+d,delete,shift+delete"
    input_undo: str = "ctrl+-,super+z"
    input_redo: str = "ctrl+.,super+shift+z"
    input_word_forward: str = "alt+f,alt+right,ctrl+right"
    input_word_backward: str = "alt+b,alt+left,ctrl+left"
    input_select_word_forward: str = "alt+shift+f,alt+shift+right"
    input_select_word_backward: str = "alt+shift+b,alt+shift+left"
    input_delete_word_forward: str = "alt+d,alt+delete,ctrl+delete"
    input_delete_word_backward: str = "ctrl+w,ctrl+backspace,alt+backspace"
    history_previous: str = "up"
    history_next: str = "down"
    session_child_first: str = "<leader>down"
    session_child_cycle: str = "right"
    session_child_cycle_reverse: str = "left"
    session_parent: str = "up"
    terminal_suspend: str = "ctrl+z"
    terminal_title_toggle: str = "none"
    tips_toggle: str = "<leader>h"
    plugin_manager: str = "none"
    display_thinking: str = "none"


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
# MCP 配置 (对应 mcp.ts)
# ═══════════════════════════════════════════════════════════


class MCPLocalConfig(BaseModel):
    """本地 MCP 服务器配置"""
    type: str = "local"
    command: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout: int | None = None


class MCPRemoteConfig(BaseModel):
    """远程 MCP 服务器配置"""
    type: str = "remote"
    url: str = ""
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: dict[str, str] | bool | None = None
    timeout: int | None = None


class MCPConfig(BaseModel):
    """MCP 服务器配置"""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    # 扩充
    type: str = "local"
    url: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    command_list: list[str] = Field(default_factory=list)
    timeout: int | None = None


MCP_SENSITIVE_KEYS = [
    "authorization", "token", "api_key", "apikey", "key", "secret", "password", "credential",
]


def mcp_redact_string(text: str) -> str:
    """脱敏 MCP 配置中的敏感信息"""
    text = re.sub(r'(Bearer\s+)[^\s]+', r'\1****', text, flags=re.IGNORECASE)
    return text


def mcp_redact_command(command: list[str]) -> list[str]:
    """脱敏命令中的敏感参数"""
    result = []
    for i, item in enumerate(command):
        if i > 0 and any(k in command[i - 1].lower() for k in MCP_SENSITIVE_KEYS):
            result.append("****")
        else:
            result.append(mcp_redact_string(item))
    return result


def mcp_from_claude(name: str, data: Any) -> dict:
    """从 Claude Code 格式转换 MCP 配置"""
    if not isinstance(data, dict):
        return {"warning": f'skipped Claude Code MCP server "{name}"; server config is not an object.'}

    if data.get("type") == "sse":
        return {"warning": f'skipped Claude Code MCP server "{name}"; unsupported transport "sse".'}

    args = data.get("args")
    if args is not None and not isinstance(args, list):
        return {"warning": f'skipped Claude Code MCP server "{name}"; args is not an array.'}

    args_list = args if isinstance(args, list) else []
    if not all(isinstance(a, str) for a in args_list):
        return {"warning": f'skipped Claude Code MCP server "{name}"; args must contain only strings.'}

    enabled = not data.get("disabled", False)
    environment = data.get("environment") or data.get("env")
    if isinstance(environment, dict):
        environment = {k: str(v) for k, v in environment.items() if isinstance(v, str)}
    else:
        environment = None

    timeout = data.get("timeout") if isinstance(data.get("timeout"), (int, float)) else None
    transport_type = data.get("type")

    local_types = {"stdio", "local"}
    remote_types = {"http", "streamable-http", "remote"}

    if isinstance(data.get("command"), str) and (not transport_type or transport_type in local_types):
        command = [data["command"]] + args_list
        config = {
            "type": "local",
            "command": command,
            "enabled": enabled,
        }
        if environment:
            config["environment"] = environment
        if timeout is not None:
            config["timeout"] = timeout
        return {"config": config}

    if data.get("command") is not None:
        return {"warning": f'skipped Claude Code MCP server "{name}"; command is not a string.'}

    if isinstance(data.get("url"), str) and (not transport_type or transport_type in remote_types):
        config = {
            "type": "remote",
            "url": data["url"],
            "enabled": enabled,
        }
        headers = data.get("headers")
        if isinstance(headers, dict):
            config["headers"] = {k: str(v) for k, v in headers.items() if isinstance(v, str)}
        oauth_data = data.get("oauth")
        if oauth_data is not None and oauth_data is not False:
            if isinstance(oauth_data, dict):
                oauth_result = {}
                for ok in ("clientId", "clientSecret", "scope", "redirectUri"):
                    if ok in oauth_data and isinstance(oauth_data[ok], str):
                        oauth_result[ok] = oauth_data[ok]
                if oauth_result:
                    config["oauth"] = oauth_result
        elif oauth_data is False:
            config["oauth"] = False
        if environment:
            config["environment"] = environment
        if timeout is not None:
            config["timeout"] = timeout
        return {"config": config}

    if data.get("url") is not None:
        return {"warning": f'skipped Claude Code MCP server "{name}"; url is not a string.'}

    if transport_type and transport_type not in local_types and transport_type not in remote_types:
        return {"warning": f'skipped Claude Code MCP server "{name}"; unsupported transport "{transport_type}".'}

    return {"warning": f'skipped Claude Code MCP server "{name}"; missing command or url.'}


# ═══════════════════════════════════════════════════════════
# Formatter 配置 (对应 formatter.ts)
# ═══════════════════════════════════════════════════════════


class FormatterEntry(BaseModel):
    """格式化条目"""
    disabled: bool | None = None
    command: list[str] | None = None
    environment: dict[str, str] | None = None
    extensions: list[str] | None = None


# FormatterInfo 可以是 True/False (启用/禁用全部) 或 dict[name, Entry]
FormatterInfo = bool | dict[str, FormatterEntry]


# ═══════════════════════════════════════════════════════════
# LSP 配置 (对应 lsp.ts)
# ═══════════════════════════════════════════════════════════


class LSPEntry(BaseModel):
    """LSP 条目"""
    command: list[str] = Field(default_factory=list)
    extensions: list[str] | None = None
    disabled: bool | None = None
    env: dict[str, str] = Field(default_factory=dict)
    initialization: dict[str, Any] = Field(default_factory=dict)


# LSPInfo 可以是 True(启用默认) 或 dict[name, Entry] 或 dict[name, Disabled]
LSPInfo = bool | dict[str, LSPEntry | dict]


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

MARKDOWN_FILE_REGEX = re.compile(r"(?<![\w`])@(\.?[^\s`,.]*(?:\.[^\s`,.]+)*)")
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
# Managed Config (对应 managed.ts)
# ═══════════════════════════════════════════════════════════

MANAGED_PLIST_DOMAIN = "ai.craft.managed"
PLIST_META_KEYS = {
    "PayloadDisplayName", "PayloadIdentifier", "PayloadType",
    "PayloadUUID", "PayloadVersion", "_manualProfile",
}


def system_managed_config_dir() -> str:
    """获取系统托管配置目录"""
    import platform
    system = platform.system()
    if system == "Darwin":
        return "/Library/Application Support/craft"
    elif system == "Windows":
        return os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "craft")
    else:
        return "/etc/craft"


def managed_config_dir() -> str:
    """获取托管配置目录（可被测试覆盖）"""
    return os.environ.get("CRAFT_TEST_MANAGED_CONFIG_DIR") or system_managed_config_dir()


def parse_managed_plist(json_text: str) -> str:
    """解析托管 plist JSON，去除元数据键"""
    raw = json.loads(json_text)
    for key in list(raw.keys()):
        if key in PLIST_META_KEYS:
            del raw[key]
    return json.dumps(raw)


def read_managed_preferences() -> dict | None:
    """读取 macOS MDM 托管的 plist 配置"""
    import platform
    if platform.system() != "Darwin":
        return None

    import subprocess
    import plistlib

    username = os.environ.get("USER") or os.environ.get("USERNAME", "")
    paths = [
        f"/Library/Managed Preferences/{username}/{MANAGED_PLIST_DOMAIN}.plist",
        f"/Library/Managed Preferences/{MANAGED_PLIST_DOMAIN}.plist",
    ]

    for plist_path in paths:
        if not Path(plist_path).exists():
            continue
        try:
            result = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", plist_path],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                continue
            return {
                "source": f"mobileconfig:{plist_path}",
                "text": parse_managed_plist(result.stdout),
            }
        except Exception:
            continue
    return None


# ═══════════════════════════════════════════════════════════
# Paths (对应 paths.ts)
# ═══════════════════════════════════════════════════════════


def find_config_files(name: str, start_dir: str, stop_dir: str | None = None) -> list[str]:
    """从 start_dir 向上查找所有匹配的配置文件"""
    results: list[str] = []
    current = Path(start_dir).resolve()
    stop = Path(stop_dir).resolve() if stop_dir else None

    while True:
        for ext in [".jsonc", ".json"]:
            p = current / f"{name}{ext}"
            if p.exists():
                results.append(str(p))
        if stop and current == stop:
            break
        if current.parent == current:
            break
        current = current.parent

    results.reverse()
    return results


def find_config_directories(start_dir: str, stop_dir: str | None = None) -> list[str]:
    """从 start_dir 向上查找所有 .craft 目录"""
    dirs: list[str] = []
    cfg_dir_path = str(CONFIG_DIR)  # global dir always first

    current = Path(start_dir).resolve()
    stop = Path(stop_dir).resolve() if stop_dir else None

    while True:
        craft_dir = current / ".craft"
        if craft_dir.is_dir():
            dirs.append(str(craft_dir))
        if stop and current == stop:
            break
        if current.parent == current:
            break
        current = current.parent

    dirs = [cfg_dir_path] + dirs

    # deduplicate
    seen: set[str] = set()
    unique = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def read_config_file(filepath: str) -> str | None:
    """读取配置文件，不存在返回 None"""
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception as e:
        raise ConfigJsonError(filepath, str(e)) from e


# ═══════════════════════════════════════════════════════════
# 深度合并工具
# ═══════════════════════════════════════════════════════════


def merge_config(base: dict, overlay: dict, concat_arrays: bool = False) -> dict:
    """深度合并配置

    Args:
        base: 基础配置
        overlay: 覆盖配置
        concat_arrays: 如果 True，数组合并而非替换
    """
    result = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = merge_config(result[k], v, concat_arrays)
        elif isinstance(v, list) and concat_arrays and k in result and isinstance(result[k], list):
            combined = result[k] + v
            if k == "instructions":
                # dedup instructions
                result[k] = list(dict.fromkeys(combined))
            else:
                result[k] = combined
        else:
            result[k] = v
    return result


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


# ═══════════════════════════════════════════════════════════
# 配置加载链
# ═══════════════════════════════════════════════════════════


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
        cleaned = "\n".join(lines)
        # 去除尾逗号
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(cleaned)
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise ConfigJsonError(path, str(e)) from e


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


def get_agent_config(agent_id: str | None = None) -> AgentConfig:
    """获取 Agent 配置"""
    cfg = get_config()
    aid = agent_id or cfg.default_agent
    return cfg.agent.get(aid, AgentConfig(name=aid))


def get_mcp_configs() -> dict[str, MCPConfig]:
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
