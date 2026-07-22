"""
插件系统 — 移植自 packages/opencode/src/plugin/
支持：动态加载、生命周期钩子、依赖注入、规范解析、元数据跟踪
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

PLUGIN_DIR = CONFIG_DIR / "plugins"

# ──────────────────────────────────────────────
# 共享工具 — 移植自 shared.ts
# ──────────────────────────────────────────────

PluginSource = Literal["file", "npm"]
PluginKind = Literal["server", "tui"]

DEPRECATED_PLUGIN_PACKAGES = ["opencode-openai-codex-auth", "opencode-copilot-auth"]


def is_deprecated_plugin(spec: str) -> bool:
    """检查插件是否已被弃用（现已内置）"""
    return any(pkg in spec for pkg in DEPRECATED_PLUGIN_PACKAGES)


def parse_plugin_specifier(spec: str) -> dict[str, str]:
    """解析插件规范字符串为 {pkg, version}"""
    # Handle npm package@version format
    at_idx = spec.rfind("@")
    if at_idx > 0 and "/" not in spec[at_idx + 1 :]:
        pkg = spec[:at_idx]
        version = spec[at_idx + 1:] or "latest"
        return {"pkg": pkg, "version": version}
    if "://" in spec:
        return {"pkg": spec, "version": ""}
    return {"pkg": spec, "version": "latest" if spec else ""}


def is_path_plugin_spec(spec: str) -> bool:
    """检查是否为文件路径插件规范"""
    if spec.startswith("file://") or spec.startswith("."):
        return True
    if os.path.isabs(spec):
        return True
    # Windows absolute path check
    if len(spec) > 1 and spec[1] == ":" and spec[0].isalpha():
        return True
    return False


def plugin_source(spec: str) -> PluginSource:
    """判断插件来源：file 或 npm"""
    return "file" if is_path_plugin_spec(spec) else "npm"


@dataclass
class PluginPackage:
    """插件包信息"""
    dir: str
    pkg: str  # path to package.json
    json: dict[str, Any]


@dataclass
class PluginEntry:
    """插件入口信息"""
    spec: str
    source: PluginSource
    target: str
    pkg: PluginPackage | None = None
    entry: str | None = None


INDEX_FILES = ["index.ts", "index.js", "index.mjs", "index.py"]


async def read_plugin_package(target: str) -> PluginPackage | None:
    """读取插件包的 package.json"""
    try:
        if target.startswith("file://"):
            file = target[7:]
        else:
            file = target
        stat = await _async_stat(file)
        if stat and stat.get("is_dir"):
            dir_path = file
        else:
            dir_path = os.path.dirname(file)
        pkg_path = os.path.join(dir_path, "package.json")
        data = await _async_read_json(pkg_path)
        if data is None:
            return None
        return PluginPackage(dir=dir_path, pkg=pkg_path, json=data)
    except Exception as e:
        logger.debug(f"read_plugin_package failed: {e}")
        return None


async def resolve_path_plugin_target(spec: str) -> str:
    """解析文件路径插件目标"""
    if spec.startswith("file://"):
        raw = spec[7:]
    else:
        raw = spec
    if os.path.isabs(raw):
        file = raw
    else:
        file = os.path.abspath(raw)

    stat = await _async_stat(file)
    if stat and stat.get("is_dir"):
        pkg_json = os.path.join(file, "package.json")
        if os.path.exists(pkg_json):
            return f"file://{file}"
        index = await _resolve_directory_index(file)
        if index:
            return f"file://{index}"
        raise FileNotFoundError(f"Plugin directory {file} is missing package.json or index file")

    if spec.startswith("file://"):
        return spec
    return f"file://{file}"


async def resolve_plugin_target(spec: str) -> str:
    """解析插件规范为目标路径"""
    if is_path_plugin_spec(spec):
        return await resolve_path_plugin_target(spec)
    # For npm specs, return the spec itself (Craft doesn't have npm integration yet)
    parsed = parse_plugin_specifier(spec)
    return parsed["pkg"]


def _extract_export_value(value: Any) -> str | None:
    """从 exports 对象中提取导出值"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("import", "default"):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
    return None


def _package_main(pkg: PluginPackage) -> str | None:
    """获取包的 main 字段"""
    value = pkg.json.get("main")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_export_path(raw: str, pkg_dir: str) -> str:
    """解析导出路径为绝对路径"""
    if raw.startswith("file://"):
        return raw[7:]
    if os.path.isabs(raw):
        return raw
    return os.path.abspath(os.path.join(pkg_dir, raw))


def _resolve_package_entrypoint(spec: str, kind: PluginKind, pkg: PluginPackage) -> str | None:
    """从 package.json 中解析入口点"""
    exports = pkg.json.get("exports")
    if isinstance(exports, dict):
        raw = _extract_export_value(exports.get(f"./{kind}"))
        if raw:
            resolved = _resolve_export_path(raw, pkg.dir)
            if os.path.isfile(resolved):
                return f"file://{resolved}"
            return resolved

    if kind != "server":
        return None
    main = _package_main(pkg)
    if main:
        resolved = _resolve_export_path(main, pkg.dir)
        if os.path.isfile(resolved):
            return f"file://{resolved}"
        return resolved
    return None


async def _resolve_directory_index(dir_path: str) -> str | None:
    """查找目录中的索引文件"""
    for name in INDEX_FILES:
        file = os.path.join(dir_path, name)
        if os.path.isfile(file):
            return file
    return None


async def _resolve_target_directory(target: str) -> str | None:
    """检查目标是否为目录"""
    target_path = target[7:] if target.startswith("file://") else target
    stat = await _async_stat(target_path)
    if stat and stat.get("is_dir"):
        return target_path
    return None


async def resolve_plugin_entrypoint(spec: str, target: str, kind: PluginKind, pkg: PluginPackage | None = None) -> str | None:
    """解析插件入口点"""
    source = plugin_source(spec)
    if pkg is None and source == "npm":
        pkg = await read_plugin_package(target)
    elif pkg is None:
        pkg = await read_plugin_package(target)

    if pkg:
        entry = _resolve_package_entrypoint(spec, kind, pkg)
        if entry:
            return entry

    dir_path = await _resolve_target_directory(target)
    if kind == "tui":
        if source == "file" and dir_path:
            index = await _resolve_directory_index(dir_path)
            if index:
                return f"file://{index}"
        if source == "npm":
            return None
        if dir_path:
            return None
        return target

    if dir_path and pkg and isinstance(pkg.json.get("exports"), dict):
        if source == "file":
            index = await _resolve_directory_index(dir_path)
            if index:
                return f"file://{index}"
        return None

    return target


async def create_plugin_entry(spec: str, target: str, kind: PluginKind) -> PluginEntry:
    """创建插件入口信息"""
    source = plugin_source(spec)
    pkg = None
    if source == "npm":
        pkg = await read_plugin_package(target)
    else:
        try:
            pkg = await read_plugin_package(target)
        except Exception:
            pkg = None
    entry = await resolve_plugin_entrypoint(spec, target, kind, pkg)
    return PluginEntry(spec=spec, source=source, target=target, pkg=pkg, entry=entry)


async def check_plugin_compatibility(target: str, opencode_version: str, pkg: PluginPackage | None = None) -> None:
    """检查插件版本兼容性"""
    if not opencode_version:
        return
    # Simple semver check - port of the TS version
    hit = pkg or await read_plugin_package(target)
    if not hit:
        return
    engines = hit.json.get("engines")
    if not isinstance(engines, dict):
        return
    range_spec = engines.get("opencode")
    if not isinstance(range_spec, str):
        return
    # Simple version range check - Python semver equivalent
    if not _semver_satisfies(opencode_version, range_spec):
        raise RuntimeError(
            f"Plugin requires opencode {range_spec} but running {opencode_version}"
        )


def _semver_satisfies(version: str, range_spec: str) -> bool:
    """简单的 semver 范围检查"""
    # For now, just check if it's a valid version string
    # A proper implementation would use packaging or semver library
    try:
        parts = version.split(".")
        int(parts[0])  # validate it's numeric
        # If range is ">=x.y.z", check major version
        if range_spec.startswith(">="):
            required = range_spec[2:].strip()
            req_parts = required.split(".")
            return tuple(int(p) for p in parts) >= tuple(int(p) for p in req_parts)
        if range_spec.startswith("^"):
            required = range_spec[1:].strip()
            req_parts = required.split(".")
            return parts[0] == req_parts[0]
        if range_spec.startswith("~"):
            required = range_spec[1:].strip()
            req_parts = required.split(".")
            return parts[:2] == req_parts[:2]
        return version == range_spec
    except (ValueError, IndexError):
        return True


def read_v1_plugin(
    mod: dict[str, Any],
    spec: str,
    kind: PluginKind,
    mode: Literal["strict", "detect"] = "strict",
) -> dict[str, Any] | None:
    """读取 V1 插件格式"""
    default = mod.get("default")
    if not isinstance(default, dict):
        if mode == "detect":
            return None
        raise TypeError(f"Plugin {spec} must default export an object with {kind}()")

    if mode == "detect" and "id" not in default and "server" not in default and "tui" not in default:
        return None

    server = default.get("server")
    tui = default.get("tui")
    if server is not None and not callable(server):
        raise TypeError(f"Plugin {spec} has invalid server export")
    if tui is not None and not callable(tui):
        raise TypeError(f"Plugin {spec} has invalid tui export")
    if server is not None and tui is not None:
        raise TypeError(f"Plugin {spec} must default export either server() or tui(), not both")
    if kind == "server" and server is None:
        raise TypeError(f"Plugin {spec} must default export an object with server()")
    if kind == "tui" and tui is None:
        raise TypeError(f"Plugin {spec} must default export an object with tui()")

    return default


def read_plugin_id(id_value: Any, spec: str) -> str | None:
    """读取插件 ID"""
    if id_value is None:
        return None
    if not isinstance(id_value, str):
        raise TypeError(f"Plugin {spec} has invalid id type {type(id_value).__name__}")
    value = id_value.strip()
    if not value:
        raise TypeError(f"Plugin {spec} has an empty id")
    return value


async def resolve_plugin_id(
    source: PluginSource,
    spec: str,
    target: str,
    id_value: str | None = None,
    pkg: PluginPackage | None = None,
) -> str:
    """解析插件 ID"""
    if source == "file":
        if id_value:
            return id_value
        raise TypeError(f"Path plugin {spec} must export id")
    if id_value:
        return id_value
    hit = pkg or await read_plugin_package(target)
    if hit and isinstance(hit.json.get("name"), str) and hit.json["name"].strip():
        return hit.json["name"].strip()
    raise TypeError(f"Plugin package is missing name")


def read_package_themes(spec: str, pkg: PluginPackage) -> list[str]:
    """读取包主题文件列表"""
    field = pkg.json.get("oc-themes")
    if field is None:
        return []
    if not isinstance(field, list):
        raise TypeError(f"Plugin {spec} has invalid oc-themes field")
    result: list[str] = []
    for item in field:
        if not isinstance(item, str):
            raise TypeError(f"Plugin {spec} has invalid oc-themes entry")
        raw = item.strip()
        if not raw:
            raise TypeError(f"Plugin {spec} has empty oc-themes entry")
        if raw.startswith("file://") or (len(raw) > 1 and raw[1] == ":" and raw[0].isalpha()):
            raise TypeError(f"Plugin {spec} oc-themes entry must be relative: {item}")
        resolved = _resolve_export_path(raw, pkg.dir)
        result.append(resolved)
    return list(dict.fromkeys(result))  # deduplicate preserving order


# ──────────────────────────────────────────────
# 安装 — 移植自 install.ts
# ──────────────────────────────────────────────

@dataclass
class Target:
    """安装目标"""
    kind: PluginKind
    opts: dict[str, Any] | None = None


@dataclass
class PatchInput:
    """补丁输入"""
    spec: str
    targets: list[Target]
    force: bool = False
    global_: bool = False
    vcs: str | None = None
    worktree: str = ""
    directory: str = ""
    config: str | None = None


@dataclass
class PatchItem:
    """补丁项"""
    kind: PluginKind
    mode: Literal["noop", "add", "replace"]
    file: str


async def install_plugin(spec: str) -> dict[str, Any]:
    """安装插件"""
    try:
        target = await resolve_plugin_target(spec)
        return {"ok": True, "target": target}
    except Exception as e:
        return {"ok": False, "code": "install_failed", "error": str(e)}


def _plugin_list(data: Any) -> list[Any] | None:
    """从配置数据中提取插件列表"""
    if not isinstance(data, dict):
        return None
    plugin = data.get("plugin")
    if not isinstance(plugin, list):
        return None
    return plugin


def _plugin_spec(item: Any) -> str | None:
    """从插件项中提取规范字符串"""
    if isinstance(item, str):
        return item
    if isinstance(item, (list, tuple)) and len(item) > 0 and isinstance(item[0], str):
        return item[0]
    return None


def _patch_plugin_list(
    config_text: str,
    plugin_list: list[Any] | None,
    spec: str,
    next_item: Any,
    force: bool = False,
) -> tuple[Literal["noop", "add", "replace"], str]:
    """修补插件配置列表"""
    parsed_pkg = parse_plugin_specifier(spec)["pkg"]
    rows = []
    if plugin_list:
        for i, item in enumerate(plugin_list):
            item_spec = _plugin_spec(item)
            rows.append({"item": item, "i": i, "spec": item_spec})

    dups = [r for r in rows if r["spec"] and (r["spec"] == spec or parse_plugin_specifier(r["spec"])["pkg"] == parsed_pkg)]

    if not dups:
        mode: Literal["add", "replace"] = "add"
        # Simple JSON patching by reconstructing
        import json as _json
        if plugin_list is None:
            data = _json.loads(config_text) if config_text.strip() else {}
            data["plugin"] = [next_item]
            return "add", _json.dumps(data, indent=2)
        else:
            data = _json.loads(config_text) if config_text.strip() else {}
            data["plugin"] = list(plugin_list) + [next_item]
            return "add", _json.dumps(data, indent=2)

    if not force:
        return "noop", config_text

    keep = dups[0]
    if len(dups) == 1 and keep["spec"] == spec:
        return "noop", config_text

    import json as _json
    data = _json.loads(config_text) if config_text.strip() else {}
    plugin_copy = list(data.get("plugin", []))
    if isinstance(keep["item"], str):
        plugin_copy[keep["i"]] = next_item
    elif isinstance(keep["item"], (list, tuple)) and isinstance(keep["item"][0], str):
        if isinstance(plugin_copy[keep["i"]], list):
            plugin_copy[keep["i"]][0] = spec

    to_delete = sorted(
        [r["i"] for r in dups if r["i"] != keep["i"]],
        reverse=True,
    )
    for idx in to_delete:
        plugin_copy.pop(idx)

    data["plugin"] = plugin_copy
    return "replace", _json.dumps(data, indent=2)


async def read_plugin_manifest(target: str) -> dict[str, Any]:
    """读取插件清单"""
    try:
        pkg = await read_plugin_package(target)
    except Exception as e:
        return {"ok": False, "code": "manifest_read_failed", "file": target, "error": str(e)}

    if not pkg:
        return {"ok": False, "code": "manifest_read_failed", "file": target, "error": "package.json not found"}

    try:
        spec = pkg.json.get("name", os.path.basename(pkg.dir))
        targets: list[dict[str, Any]] = []
        exports = pkg.json.get("exports")
        if isinstance(exports, dict):
            server_val = exports.get("./server")
            if server_val:
                targets.append({"kind": "server"})
            tui_val = exports.get("./tui")
            if tui_val:
                targets.append({"kind": "tui"})
        if not any(t["kind"] == "server" for t in targets) and pkg.json.get("main"):
            targets.insert(0, {"kind": "server"})
        if not targets:
            return {"ok": False, "code": "manifest_no_targets", "file": pkg.pkg}
        return {"ok": True, "targets": targets}
    except Exception as e:
        return {"ok": False, "code": "manifest_read_failed", "file": pkg.pkg, "error": str(e)}


def _patch_dir(input: PatchInput) -> str:
    """确定补丁目录"""
    if input.global_:
        return input.config or str(Path.home() / ".craft")
    return os.path.join(input.directory, ".craft")


def _patch_name(kind: PluginKind) -> str:
    return "mimocode" if kind == "server" else "tui"


async def patch_plugin_config(input: PatchInput) -> dict[str, Any]:
    """修补插件配置"""
    patch_dir = _patch_dir(input)
    items: list[dict[str, Any]] = []
    for target in input.targets:
        result = await _patch_one(patch_dir, target, input.spec, input.force)
        if not result.get("ok"):
            result["dir"] = patch_dir
            return result
        items.append(result["item"])
    return {"ok": True, "dir": patch_dir, "items": items}


async def _patch_one(dir_path: str, target: Target, spec: str, force: bool) -> dict[str, Any]:
    """修补单个目标"""
    name = _patch_name(target.kind)
    files = _config_files(dir_path, name)
    cfg = files[0]
    for file in files:
        if os.path.exists(file):
            cfg = file
            break

    try:
        src = await _async_read_text(cfg)
    except FileNotFoundError:
        src = "{}"
    except Exception as e:
        return {"ok": False, "code": "patch_failed", "kind": target.kind, "error": str(e)}

    text = src.strip() or "{}"

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        lines = text[: e.pos].split("\n")
        return {
            "ok": False,
            "code": "invalid_json",
            "kind": target.kind,
            "file": cfg,
            "line": len(lines),
            "col": len(lines[-1]) + 1,
            "parse": str(e),
        }

    plugin_list = _plugin_list(data)
    item: Any = [spec, target.opts] if target.opts else spec
    mode, out_text = _patch_plugin_list(text, plugin_list, spec, item, force)

    if mode == "noop":
        return {"ok": True, "item": {"kind": target.kind, "mode": mode, "file": cfg}}

    try:
        with open(cfg, "w") as f:
            f.write(out_text)
    except Exception as e:
        return {"ok": False, "code": "patch_failed", "kind": target.kind, "error": str(e)}

    return {"ok": True, "item": {"kind": target.kind, "mode": mode, "file": cfg}}


def _config_files(dir_path: str, name: str) -> list[str]:
    """获取配置文件路径列表"""
    jsonc = os.path.join(dir_path, f"{name}.jsonc")
    json_f = os.path.join(dir_path, f"{name}.json")
    return [jsonc, json_f]


# ──────────────────────────────────────────────
# Matcher — 移植自 matcher.ts
# ──────────────────────────────────────────────

BUILT_IN_AGENTS = [
    "build",
    "plan",
    "explore",
    "general",
    "title",
    "summary",
    "dream",
    "distill",
    "compaction",
    "main",
    "checkpoint-writer",
]


class ActorMatcher(dict):
    """Actor 匹配器，类似于 TS 的 ActorMatcher 类型"""
    mode: str | None = None
    agent_type: str | list[str] | dict[str, list[str]] | None = None


def matches_actor(
    matcher: dict[str, Any] | None,
    input_data: dict[str, str],
) -> bool:
    """检查输入是否匹配 Actor 匹配器"""
    agent_type = input_data.get("agentType", "")
    is_built_in = agent_type in BUILT_IN_AGENTS

    if matcher is None:
        return not is_built_in

    matcher_mode = matcher.get("mode")
    if matcher_mode and matcher_mode != input_data.get("mode"):
        return False

    at = matcher.get("agentType")
    if at is None:
        return not is_built_in

    if isinstance(at, str):
        if is_built_in:
            return False
        try:
            return bool(re.match(at, agent_type))
        except re.error:
            return False

    if isinstance(at, list):
        return agent_type in at

    if isinstance(at, dict):
        if "excludeOnly" in at:
            return agent_type not in at["excludeOnly"]
        exclude = at.get("exclude", [])
        if agent_type in exclude:
            return False
        include = at.get("include", [])
        return agent_type in include

    return False


# ──────────────────────────────────────────────
# Meta — 移植自 meta.ts
# ──────────────────────────────────────────────

@dataclass
class Theme:
    """主题文件信息"""
    src: str
    dest: str
    mtime: int | None = None
    size: int | None = None


@dataclass
class MetaEntry:
    """元数据条目"""
    id: str
    source: PluginSource
    spec: str
    target: str
    requested: str | None = None
    version: str | None = None
    modified: int | None = None
    first_time: int = 0
    last_time: int = 0
    time_changed: int = 0
    load_count: int = 0
    fingerprint: str = ""
    themes: dict[str, Theme] | None = None


MetaState = Literal["first", "updated", "same"]


@dataclass
class TouchItem:
    """触摸项"""
    spec: str
    target: str
    id: str


def _meta_file_path() -> str:
    """元数据文件路径"""
    # Try environment variable, fall back to state directory
    env_path = os.environ.get("CRAFT_PLUGIN_META_FILE")
    if env_path:
        return env_path
    state_dir = CONFIG_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / "plugin-meta.json")


def _file_target(spec: str, target: str) -> str | None:
    """获取文件插件目标路径"""
    if spec.startswith("file://"):
        return spec[7:]
    if target.startswith("file://"):
        return target[7:]
    return None


async def _modified_at(file: str) -> int | None:
    """获取文件修改时间"""
    try:
        stat = os.stat(file)
        return int(stat.st_mtime * 1000)
    except OSError:
        return None


def _resolved_target(target: str) -> str:
    """解析目标路径"""
    if target.startswith("file://"):
        return target[7:]
    return target


async def _npm_version(target: str) -> str | None:
    """获取 npm 包版本"""
    resolved = _resolved_target(target)
    try:
        stat = os.stat(resolved)
        dir_path = resolved if stat.st_mode & 0o40000 else os.path.dirname(resolved)
        pkg_data = await _async_read_json(os.path.join(dir_path, "package.json"))
        if pkg_data and isinstance(pkg_data, dict):
            return pkg_data.get("version")
    except Exception:
        pass
    return None


async def _entry_core(item: TouchItem) -> dict[str, Any]:
    """构建条目核心信息"""
    source = plugin_source(item.spec)
    core: dict[str, Any] = {"id": item.id, "source": source, "spec": item.spec, "target": item.target}
    if source == "file":
        file_path = _file_target(item.spec, item.target)
        if file_path:
            core["modified"] = await _modified_at(file_path)
    else:
        core["requested"] = parse_plugin_specifier(item.spec).get("version")
        core["version"] = await _npm_version(item.target)
    return core


def _fingerprint(core: dict[str, Any]) -> str:
    """计算指纹"""
    if core.get("source") == "file":
        return f"{core['target']}|{core.get('modified', '')}"
    return f"{core['target']}|{core.get('requested', '')}|{core.get('version', '')}"


async def _read_meta_store(file_path: str) -> dict[str, dict[str, Any]]:
    """读取元数据存储"""
    try:
        data = await _async_read_json(file_path)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _next_meta_entry(
    prev: dict[str, Any] | None,
    core: dict[str, Any],
    now: int,
) -> tuple[MetaState, dict[str, Any]]:
    """计算下一个元数据条目"""
    entry: dict[str, Any] = {
        **core,
        "first_time": prev.get("first_time", now) if prev else now,
        "last_time": now,
        "time_changed": prev.get("time_changed", now) if prev else now,
        "load_count": (prev.get("load_count", 0) if prev else 0) + 1,
        "fingerprint": _fingerprint(core),
        "themes": prev.get("themes") if prev else None,
    }
    if prev:
        state: MetaState = "same" if prev.get("fingerprint") == entry["fingerprint"] else "updated"
    else:
        state = "first"
    if state == "updated":
        entry["time_changed"] = now
    return state, entry


async def touch_many(items: list[TouchItem]) -> list[dict[str, Any]]:
    """批量触摸插件元数据"""
    if not items:
        return []
    file_path = _meta_file_path()
    results: list[dict[str, Any]] = []
    store = await _read_meta_store(file_path)
    now = int(time.time() * 1000)
    for item in items:
        core = await _entry_core(item)
        prev = store.get(item.id)
        state, entry = _next_meta_entry(prev, core, now)
        store[item.id] = entry
        results.append({"state": state, "entry": entry})
    await _async_write_json(file_path, store)
    return results


async def touch(spec: str, target: str, id_value: str) -> dict[str, Any]:
    """触摸单个插件元数据"""
    results = await touch_many([TouchItem(spec=spec, target=target, id=id_value)])
    if results:
        return results[0]
    raise RuntimeError("Failed to touch plugin metadata.")


async def set_theme(id_value: str, name: str, theme: Theme) -> None:
    """设置主题元数据"""
    file_path = _meta_file_path()
    store = await _read_meta_store(file_path)
    entry = store.get(id_value)
    if not entry:
        return
    themes = entry.get("themes") or {}
    themes[name] = {"src": theme.src, "dest": theme.dest, "mtime": theme.mtime, "size": theme.size}
    entry["themes"] = themes
    await _async_write_json(file_path, store)


async def list_meta() -> dict[str, dict[str, Any]]:
    """列出所有插件元数据"""
    return await _read_meta_store(_meta_file_path())


# ──────────────────────────────────────────────
# Loader — 移植自 loader.ts
# ──────────────────────────────────────────────

@dataclass
class LoaderPlan:
    """加载器计划"""
    spec: str
    options: dict[str, Any] | None = None
    deprecated: bool = False


@dataclass
class LoaderResolved:
    """已解析的插件"""
    plan: LoaderPlan
    source: PluginSource
    target: str
    entry: str
    pkg: PluginPackage | None = None


@dataclass
class LoaderMissing:
    """缺失的插件"""
    plan: LoaderPlan
    source: PluginSource
    target: str
    pkg: PluginPackage | None = None
    message: str = ""


@dataclass
class LoaderLoaded:
    """已加载的插件"""
    resolved: LoaderResolved
    mod: dict[str, Any]


@dataclass
class LoaderReport:
    """加载报告回调"""
    start: Callable | None = None
    missing: Callable | None = None
    error: Callable | None = None


async def loader_resolve(plan: LoaderPlan, kind: PluginKind) -> dict[str, Any]:
    """解析插件到具体入口点"""
    target = ""
    try:
        target = await resolve_plugin_target(plan.spec)
    except Exception as e:
        return {"ok": False, "stage": "install", "error": str(e)}
    if not target:
        return {"ok": False, "stage": "install", "error": f"Plugin {plan.spec} target is empty"}

    try:
        base = await create_plugin_entry(plan.spec, target, kind)
    except Exception as e:
        return {"ok": False, "stage": "entry", "error": str(e)}

    if not base.entry:
        return {
            "ok": False,
            "stage": "missing",
            "value": {
                "plan": plan,
                "source": base.source,
                "target": base.target,
                "pkg": base.pkg,
                "message": f"Plugin {plan.spec} does not expose a {kind} entrypoint",
            },
        }

    if base.source == "npm":
        try:
            await check_plugin_compatibility(base.target, "", base.pkg)
        except Exception as e:
            return {"ok": False, "stage": "compatibility", "error": str(e)}

    resolved = LoaderResolved(
        plan=plan,
        source=base.source,
        target=base.target,
        entry=base.entry,
        pkg=base.pkg,
    )
    return {"ok": True, "value": resolved}


async def loader_load(row: LoaderResolved) -> dict[str, Any]:
    """导入已解析的插件模块"""
    try:
        entry_path = row.entry
        if entry_path.startswith("file://"):
            entry_path = entry_path[7:]

        if entry_path.endswith(".py"):
            # Python module loading
            spec = importlib.util.spec_from_file_location(
                f"craft_plugin_{hash(entry_path)}",
                entry_path,
            )
            if spec is None or spec.loader is None:
                return {"ok": False, "error": f"Failed to load spec from {entry_path}"}
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod_dict = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
        else:
            # For non-Python files, try importlib
            mod_dict = {}
            spec2 = importlib.util.spec_from_file_location(
                f"craft_plugin_{hash(entry_path)}",
                entry_path,
            )
            if spec2 and spec2.loader:
                mod = importlib.util.module_from_spec(spec2)
                spec2.loader.exec_module(mod)
                mod_dict = {k: v for k, v in vars(mod).items() if not k.startswith("_")}

        return {"ok": True, "value": LoaderLoaded(resolved=row, mod=mod_dict)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def loader_load_external(
    items: list[tuple[dict[str, Any], str]],  # list of (spec dict, origin)
    kind: PluginKind,
    report: LoaderReport | None = None,
    finish: Callable | None = None,
    missing: Callable | None = None,
    wait: Callable | None = None,
) -> list[Any]:
    """加载所有外部插件"""
    candidates: list[tuple[dict[str, Any], LoaderPlan]] = []
    for origin_spec, origin in items:
        spec_str = origin_spec.get("spec", origin_spec.get("name", ""))
        plan = LoaderPlan(
            spec=spec_str,
            options=origin_spec.get("options"),
            deprecated=is_deprecated_plugin(spec_str),
        )
        candidates.append(({"origin": origin, "spec": origin_spec}, plan))

    results: list[Any] = []
    for candidate_info, plan in candidates:
        if plan.deprecated:
            continue

        if report and report.start:
            try:
                await report.start(candidate_info, False)
            except Exception:
                pass

        resolved_result = await loader_resolve(plan, kind)
        if not resolved_result.get("ok"):
            stage = resolved_result.get("stage")
            if stage == "missing":
                missing_value = resolved_result.get("value", {})
                if missing:
                    try:
                        val = await missing(missing_value, candidate_info["origin"], False)
                        if val is not None:
                            results.append(val)
                    except Exception:
                        pass
                if report and report.missing:
                    try:
                        await report.missing(
                            candidate_info,
                            False,
                            missing_value.get("message", ""),
                            missing_value,
                        )
                    except Exception:
                        pass
            else:
                if report and report.error:
                    try:
                        await report.error(candidate_info, False, stage, resolved_result.get("error"))
                    except Exception:
                        pass
            continue

        resolved = resolved_result["value"]
        loaded_result = await loader_load(resolved)
        if not loaded_result.get("ok"):
            if report and report.error:
                try:
                    await report.error(candidate_info, False, "load", loaded_result.get("error"), resolved)
                except Exception:
                    pass
            continue

        loaded = loaded_result["value"]

        if finish:
            try:
                result = await finish(loaded, candidate_info["origin"], False)
                if result is not None:
                    results.append(result)
            except Exception:
                pass
        else:
            results.append(loaded)

    # Retry file plugins if wait is provided
    if wait:
        for i, (candidate_info, plan) in enumerate(candidates):
            if i < len(results) and results[i] is not None:
                continue
            if plugin_source(plan.spec) != "file":
                continue
            try:
                await wait()
            except Exception:
                pass
            # Retry
            if report and report.start:
                try:
                    await report.start(candidate_info, True)
                except Exception:
                    pass

            resolved_result = await loader_resolve(plan, kind)
            if not resolved_result.get("ok"):
                continue

            resolved = resolved_result["value"]
            loaded_result = await loader_load(resolved)
            if not loaded_result.get("ok"):
                continue

            loaded = loaded_result["value"]
            if finish:
                try:
                    result = await finish(loaded, candidate_info["origin"], True)
                    if result is not None:
                        results.append(result)
                except Exception:
                    pass
            else:
                results.append(loaded)

    return results


# ──────────────────────────────────────────────
# Copilot Models — 移植自 github-copilot/models.ts
# ──────────────────────────────────────────────

import json as _json


async def copilot_models_fetch(
    base_url: str,
    headers: dict[str, str] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """获取 GitHub Copilot 模型列表"""
    import urllib.request

    req = urllib.request.Request(f"{base_url}/models")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch models: {e}") from e

    result = dict(existing or {})
    raw_items = data.get("data", [])
    remote_map: dict[str, Any] = {}
    for m in raw_items:
        if m.get("model_picker_enabled") and m.get("policy", {}).get("state") != "disabled":
            remote_map[m["id"]] = m

    # Prune existing models not in the response
    for key in list(result.keys()):
        mid = result[key].get("api", {}).get("id")
        if mid and mid not in remote_map:
            del result[key]

    # Add / update from remote
    for mid, m in remote_map.items():
        caps = m.get("capabilities", {})
        limits = caps.get("limits", {})
        supports = caps.get("supports", {})
        vision = limits.get("vision", {})
        reasoning = (
            supports.get("adaptive_thinking", False)
            or bool(supports.get("reasoning_effort", []))
            or supports.get("max_thinking_budget") is not None
            or supports.get("min_thinking_budget") is not None
        )
        has_image = supports.get("vision", False) or any(
            t.startswith("image/") for t in vision.get("supported_media_types", [])
        )
        supported_endpoints = m.get("supported_endpoints", [])
        is_msg_api = "/v1/messages" in supported_endpoints

        prev = result.get(mid)
        result[mid] = {
            "id": mid,
            "providerID": "github-copilot",
            "api": {
                "id": m["id"],
                "url": f"{base_url}/v1" if is_msg_api else base_url,
                "npm": "@ai-sdk/anthropic" if is_msg_api else "@ai-sdk/github-copilot",
            },
            "status": "active",
            "limit": {
                "context": limits.get("max_context_window_tokens", 0),
                "input": limits.get("max_prompt_tokens", 0),
                "output": limits.get("max_output_tokens", 0),
            },
            "capabilities": {
                "temperature": prev.get("capabilities", {}).get("temperature", True) if prev else True,
                "reasoning": prev.get("capabilities", {}).get("reasoning", reasoning) if prev else reasoning,
                "attachment": prev.get("capabilities", {}).get("attachment", True) if prev else True,
                "toolcall": supports.get("tool_calls", False),
                "input": {"text": True, "audio": False, "image": has_image, "video": False, "pdf": False},
                "output": {"text": True, "audio": False, "image": False, "video": False, "pdf": False},
                "interleaved": False,
            },
            "family": prev.get("family", caps.get("family", "")) if prev else caps.get("family", ""),
            "name": prev.get("name", m.get("name", "")) if prev else m.get("name", ""),
            "cost": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
            "options": prev.get("options", {}) if prev else {},
            "headers": prev.get("headers", {}) if prev else {},
            "release_date": prev.get("release_date", "") if prev else "",
        }

    return result


# ──────────────────────────────────────────────
# 插件钩子系统
# ──────────────────────────────────────────────

class PluginHook:
    """插件钩子"""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str):
        def decorator(fn: Callable):
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    def emit(self, event: str, *args, **kwargs):
        for handler in self._handlers.get(event, []):
            try:
                r = handler(*args, **kwargs)
                if hasattr(r, "__await__"):
                    import asyncio
                    asyncio.create_task(r)
            except Exception as e:
                logger.error(f"[Plugin Hook] {event}: {e}")


class PluginManifest:
    def __init__(self, name: str, version: str = "0.1.0", description: str = ""):
        self.name = name
        self.version = version
        self.description = description
        self.entry_point: str = ""
        self.dependencies: list[str] = []


class Plugin:
    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.module = None
        self.enabled = True
        self.hooks = PluginHook()

    def load(self):
        try:
            spec = importlib.util.spec_from_file_location(
                self.manifest.name, self.manifest.entry_point
            )
            if spec and spec.loader:
                self.module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.module)
                if hasattr(self.module, "setup"):
                    self.module.setup(self.hooks)
                logger.info(f"[Plugin] 加载: {self.manifest.name} v{self.manifest.version}")
                return True
        except Exception as e:
            logger.error(f"[Plugin] 加载失败 {self.manifest.name}: {e}")
        return False

    def unload(self):
        if hasattr(self.module, "teardown"):
            try:
                self.module.teardown()
            except Exception as e:
                logger.error(f"[Plugin] 卸载失败 {self.manifest.name}: {e}")
        self.module = None
        self.enabled = False


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._global_hooks = PluginHook()

    def discover(self, directory: str | None = None):
        dir_path = directory or str(PLUGIN_DIR)
        if not os.path.isdir(dir_path):
            return
        for entry in os.listdir(dir_path):
            plugin_dir = os.path.join(dir_path, entry)
            if not os.path.isdir(plugin_dir):
                continue
            manifest_file = os.path.join(plugin_dir, "plugin.json")
            if os.path.exists(manifest_file):
                import json
                try:
                    data = json.loads(open(manifest_file).read())
                    manifest = PluginManifest(
                        name=data.get("name", entry),
                        version=data.get("version", "0.1.0"),
                        description=data.get("description", ""),
                    )
                    manifest.entry_point = os.path.join(plugin_dir, data.get("main", "main.py"))
                    if os.path.exists(manifest.entry_point):
                        plugin = Plugin(manifest)
                        self._plugins[manifest.name] = plugin
                        logger.info(f"[Plugin] 发现: {manifest.name}")
                except Exception as e:
                    logger.error(f"[Plugin] 读取失败 {entry}: {e}")

    def install(self, manifest: PluginManifest) -> Plugin:
        plugin = Plugin(manifest)
        self._plugins[manifest.name] = plugin
        return plugin

    def load_all(self):
        for name, plugin in self._plugins.items():
            if plugin.enabled:
                plugin.load()

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def list(self) -> list[dict]:
        return [{"name": p.manifest.name, "version": p.manifest.version,
                 "description": p.manifest.description, "enabled": p.enabled}
                for p in self._plugins.values()]

    def unload_all(self):
        for plugin in self._plugins.values():
            plugin.unload()

    @property
    def hooks(self) -> PluginHook:
        return self._global_hooks


plugin_manager = PluginManager()


# ──────────────────────────────────────────────
# Provider 插件工厂 — 移植自 xai.ts, mimo.ts, codex.ts, cloudflare.ts, copilot.ts
# ──────────────────────────────────────────────

# 这些提供者插件在原始 TS 中返回 Hooks 对象（{auth, "chat.headers", "chat.params", ...}）
# 在 Python 中，它们被适配为返回 dict，由加载器框架使用


def make_xai_auth_plugin() -> dict[str, Any]:
    """xAI (Grok) OAuth + Device Code 认证插件"""
    return {
        "name": "xai-auth",
        "provider": "xai",
        "auth": {
            "provider": "xai",
            "methods": [
                {
                    "label": "xAI Grok OAuth (SuperGrok Subscription)",
                    "type": "oauth",
                    "authorize_url": "https://auth.x.ai/oauth2/authorize",
                    "token_url": "https://auth.x.ai/oauth2/token",
                    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
                    "scope": "openid profile email offline_access grok-cli:access api:access",
                    "redirect_uri": "http://127.0.0.1:56121/callback",
                },
                {
                    "label": "xAI Grok OAuth (Headless / Remote / VPS)",
                    "type": "device_code",
                    "device_auth_url": "https://auth.x.ai/oauth2/device/code",
                    "token_url": "https://auth.x.ai/oauth2/token",
                    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
                    "scope": "openid profile email offline_access grok-cli:access api:access",
                },
                {
                    "label": "Manually enter API Key",
                    "type": "api",
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "User-Agent": "craft/0.1.0"}}
            if output.get("model", {}).get("providerID") == "xai"
            else output
        ),
    }


def make_mimo_auth_plugin() -> dict[str, Any]:
    """小米 MiMo 认证 + Anthropic 代理插件"""
    return {
        "name": "mimo-auth",
        "provider": "xiaomi",
        "auth": {
            "provider": "xiaomi",
            "methods": [
                {
                    "label": "Browser Login (小米登录)",
                    "type": "oauth",
                    "platform_url": os.environ.get("MIMO_PLATFORM_URL", "https://platform.xiaomimimo.com"),
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "X-Mimo-Source": "craft-cli"}}
            if output.get("model", {}).get("providerID") == "xiaomi"
            else output
        ),
    }


def make_anthropic_proxy_plugin() -> dict[str, Any]:
    """Anthropic 代理插件（移除 anthropic-beta 头）"""
    return {
        "name": "anthropic-proxy",
        "provider": "anthropic",
        "auth": {
            "provider": "anthropic",
            "methods": [],
        },
    }


def make_codex_auth_plugin() -> dict[str, Any]:
    """OpenAI Codex 认证插件"""
    return {
        "name": "codex-auth",
        "provider": "openai",
        "auth": {
            "provider": "openai",
            "methods": [
                {
                    "label": "ChatGPT Pro/Plus (browser)",
                    "type": "oauth",
                    "issuer": "https://auth.openai.com",
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                    "scope": "openid profile email offline_access",
                    "redirect_path": "/auth/callback",
                    "port": 1455,
                },
                {
                    "label": "ChatGPT Pro/Plus (headless)",
                    "type": "device_code",
                    "issuer": "https://auth.openai.com",
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                },
                {
                    "label": "Manually enter API Key",
                    "type": "api",
                },
            ],
        },
        "chat.headers": lambda input_data, output: (
            {
                **output,
                "headers": {
                    **output.get("headers", {}),
                    "originator": "craft",
                    "User-Agent": "craft/0.1.0",
                },
            }
            if output.get("model", {}).get("providerID") == "openai"
            else output
        ),
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if output.get("model", {}).get("providerID") == "openai"
            else output
        ),
    }


def make_cloudflare_workers_auth_plugin() -> dict[str, Any]:
    """Cloudflare Workers AI 认证插件"""
    prompts = []
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        prompts.append({
            "type": "text",
            "key": "accountId",
            "message": "Enter your Cloudflare Account ID",
            "placeholder": "e.g. 1234567890abcdef1234567890abcdef",
        })
    return {
        "name": "cloudflare-workers-auth",
        "provider": "cloudflare-workers-ai",
        "auth": {
            "provider": "cloudflare-workers-ai",
            "methods": [{"type": "api", "label": "API key", "prompts": prompts}],
        },
    }


def make_cloudflare_ai_gateway_auth_plugin() -> dict[str, Any]:
    """Cloudflare AI Gateway 认证插件"""
    prompts = []
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        prompts.append({
            "type": "text",
            "key": "accountId",
            "message": "Enter your Cloudflare Account ID",
            "placeholder": "e.g. 1234567890abcdef1234567890abcdef",
        })
    if not os.environ.get("CLOUDFLARE_GATEWAY_ID"):
        prompts.append({
            "type": "text",
            "key": "gatewayId",
            "message": "Enter your Cloudflare AI Gateway ID",
            "placeholder": "e.g. my-gateway",
        })
    return {
        "name": "cloudflare-ai-gateway-auth",
        "provider": "cloudflare-ai-gateway",
        "auth": {
            "provider": "cloudflare-ai-gateway",
            "methods": [{"type": "api", "label": "Gateway API token", "prompts": prompts}],
        },
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if output.get("model", {}).get("providerID") == "cloudflare-ai-gateway"
            and str(output.get("model", {}).get("api", {}).get("id", "")).lower().startswith("openai/")
            and output.get("model", {}).get("capabilities", {}).get("reasoning")
            else output
        ),
    }


def make_copilot_auth_plugin() -> dict[str, Any]:
    """GitHub Copilot 认证插件"""
    return {
        "name": "copilot-auth",
        "provider": "github-copilot",
        "auth": {
            "provider": "github-copilot",
            "methods": [
                {
                    "type": "oauth",
                    "label": "Login with GitHub Copilot",
                    "client_id": "Ov23li8tweQw6odWQebz",
                    "device_code_url": "https://github.com/login/device/code",
                    "access_token_url": "https://github.com/login/oauth/access_token",
                    "scope": "read:user",
                },
            ],
        },
        "provider.models": lambda provider, ctx: (
            copilot_models_fetch(
                "https://api.githubcopilot.com",
                {"Authorization": f"Bearer {ctx.get('auth', {}).get('refresh', '')}"},
                provider.get("models", {}),
            )
        ),
        "chat.params": lambda input_data, output: (
            {**output, "maxOutputTokens": None}
            if "github-copilot" in str(output.get("model", {}).get("providerID", ""))
            and "gpt" in str(output.get("model", {}).get("api", {}).get("id", ""))
            else output
        ),
        "chat.headers": lambda input_data, output: (
            {**output, "headers": {**output.get("headers", {}), "anthropic-beta": "interleaved-thinking-2025-05-14"}}
            if "github-copilot" in str(output.get("model", {}).get("providerID", ""))
            and output.get("model", {}).get("api", {}).get("npm") == "@ai-sdk/anthropic"
            else output
        ),
    }


# ──────────────────────────────────────────────
# Hook 插件 — 移植自 subagent-progress-checker.ts, checkpoint-splitover.ts
# ──────────────────────────────────────────────

def make_subagent_progress_checker_plugin() -> dict[str, Any]:
    """子代理进度检查插件"""
    required_sections = [
        "## §1 Task identity",
        "## §2 Subagent intent",
        "## §3 Files and code sections",
        "## §4 Verbatim commands",
        "## §5 Outcome and discoveries",
    ]

    return {
        "name": "subagent-progress-checker",
        "actor.postStop": {
            "matcher": {
                "agentType": {
                    "excludeOnly": [
                        "checkpoint-writer",
                        "title",
                        "summary",
                        "dream",
                        "distill",
                        "compaction",
                        "main",
                    ],
                },
            },
            "run": async_plugin_hook(lambda input_data, output: _check_progress(input_data, output, required_sections)),
        },
    }


async def _check_progress(input_data: dict, output: dict, required_sections: list[str]) -> dict:
    """检查子代理进度"""
    task_id = input_data.get("task_id")
    if not task_id:
        return output  # no-op

    if input_data.get("canWrite") is False:
        return output

    file_path = _progress_path(input_data.get("sessionID", ""), task_id)

    body = None
    try:
        body = await _async_read_text(file_path)
    except Exception:
        body = None

    if body is None:
        output["continue"] = True
        output["reason"] = _build_progress_feedback("missing", task_id, file_path, required_sections=required_sections)
        return output

    missing = [s for s in required_sections if s not in body]
    if missing:
        output["continue"] = True
        output["reason"] = _build_progress_feedback("incomplete", task_id, file_path, missing=missing, required_sections=required_sections)
        return output

    # Inject frontmatter
    try:
        now = int(time.time() * 1000)
        frontmatter = f"---\nwritten-at: {now}\n---\n"
        # Replace existing frontmatter if present
        import re as _re
        if _re.match(r"^---\n", body):
            body = _re.sub(r"^---\n.*?\n---\n", frontmatter, body, count=1, flags=_re.DOTALL)
        else:
            body = frontmatter + body
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(body)
    except Exception as e:
        logger.error(f"frontmatter injection failed: {e}")

    return output


def _progress_path(session_id: str, task_id: str) -> str:
    """获取进度文件路径"""
    state_dir = CONFIG_DIR / "state"
    return str(state_dir / "sessions" / session_id / "progress" / f"{task_id}.md")


PROGRESS_TEMPLATE = """## §1 Task identity
- task_id: {task_id}
- short summary: <one line>

## §2 Subagent intent
What this subagent was asked to do (one paragraph).

## §3 Files and code sections
- path/to/file.ext: <what you did with it>

## §4 Verbatim commands
Exact commands you ran or commands the user/task asked to be runnable later. Keep BACKTICK-FENCED for grep-ability.
```
<command>
```

## §5 Outcome and discoveries
- Outcome (success/partial/failed): <reason>
- Discoveries that may matter for other tasks: <bullets>
"""


def _build_progress_feedback(
    kind: str,
    task_id: str,
    file_path: str,
    missing: list[str] | None = None,
    required_sections: list[str] | None = None,
) -> str:
    """构建进度反馈消息"""
    if kind == "missing":
        return (
            f"Before terminating, write the task progress journal to:\n"
            f"  {file_path}\n\n"
            f"Required structure (5 sections, headings exact):\n\n"
            f"{PROGRESS_TEMPLATE.replace('{task_id}', task_id)}\n\n"
            f"Write the file now using the Write tool, then terminate normally."
        )

    lines = [
        f"tasks/{task_id}/progress.md exists but is missing required sections:",
    ]
    if missing:
        lines.extend(f"  - {s}" for s in missing)
    lines.extend([
        "",
        "Add the missing sections. For reference, the full required template is:",
        "",
        PROGRESS_TEMPLATE.replace("{task_id}", task_id),
        "",
        "Re-write the file using Write tool, then terminate normally.",
    ])
    return "\n".join(lines)


def make_checkpoint_splitover_plugin() -> dict[str, Any]:
    """检查点拆分插件"""
    return {
        "name": "checkpoint-splitover",
        "actor.preStop": {
            "matcher": {"agentType": {"include": ["checkpoint-writer"]}},
            "run": async_plugin_hook(_run_checkpoint_splitover),
        },
    }


async def _run_checkpoint_splitover(input_data: dict, output: dict) -> dict:
    """运行检查点拆分"""
    session_id = input_data.get("parentSessionID", input_data.get("sessionID", ""))
    actor_id = input_data.get("actorID", "")

    try:
        project_id = input_data.get("project", {}).get("id", "")
        violations = await _run_validators_for_checkpoint(
            session_id,
            project_id=project_id,
        )
        if not violations:
            return output

        extract_required = [v for v in violations if v.get("severity") == "extract-required"]
        if extract_required:
            output["continue"] = True
            output["reason"] = _build_extraction_reflection(extract_required)
            return output

        errors = [v for v in violations if v.get("severity") == "error"]
        if errors:
            output["continue"] = True
            output["reason"] = _build_reflection_message(errors, session_id, project_id)
            return output

    except Exception as e:
        logger.error(f"checkpoint-splitover hook failed: {e}")

    return output


async def _run_validators_for_checkpoint(
    session_id: str,
    prior_titles: set[str] | None = None,
    expected_revisions: list[str] | None = None,
    project_id: str = "",
) -> list[dict]:
    """运行检查点验证器"""
    violations: list[dict] = []
    # Simplified validation logic
    if not session_id:
        violations.append({
            "type": "missing_session",
            "severity": "error",
            "message": "Session ID is required for checkpoint",
        })
    return violations


def _build_extraction_reflection(violations: list[dict]) -> str:
    """构建提取反射消息"""
    parts = ["The following checkpoint validations require extraction:"]
    for v in violations:
        parts.append(f"- {v.get('message', 'Unknown validation')}")
    return "\n".join(parts)


def _build_reflection_message(errors: list[dict], session_id: str, project_id: str) -> str:
    """构建反射消息"""
    parts = ["Checkpoint validation errors:"]
    for e in errors:
        parts.append(f"- {e.get('message', 'Unknown error')}")
    return "\n".join(parts)


# ──────────────────────────────────────────────
# 异步文件操作辅助
# ──────────────────────────────────────────────

async def _async_stat(path: str) -> dict | None:
    """异步 stat 操作"""
    try:
        stat = os.stat(path)
        return {
            "is_dir": bool(stat.st_mode & 0o40000),
            "mtime_ms": int(stat.st_mtime * 1000),
            "size": stat.st_size,
        }
    except OSError:
        return None


async def _async_read_text(path: str) -> str:
    """异步读取文本文件"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def _async_read_json(path: str) -> Any:
    """异步读取 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


async def _async_write_json(path: str, data: Any) -> None:
    """异步写入 JSON 文件"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────
# Async plugin hook wrapper
# ──────────────────────────────────────────────

def async_plugin_hook(fn):
    """包装异步插件钩子函数"""
    def wrapper(input_data, output):
        return asyncio.ensure_future(fn(input_data, output))
    return wrapper


# ──────────────────────────────────────────────
# 内部插件注册表
# ──────────────────────────────────────────────

INTERNAL_PLUGINS: list[dict[str, Any]] = [
    make_mimo_auth_plugin(),
    make_anthropic_proxy_plugin(),
    make_codex_auth_plugin(),
    make_xai_auth_plugin(),
    make_copilot_auth_plugin(),
    make_cloudflare_workers_auth_plugin(),
    make_cloudflare_ai_gateway_auth_plugin(),
    make_checkpoint_splitover_plugin(),
    make_subagent_progress_checker_plugin(),
]


def get_internal_plugins() -> list[dict[str, Any]]:
    """获取内置插件列表"""
    return INTERNAL_PLUGINS


# ──────────────────────────────────────────────
# 兼容性重导出 — 保持 PluginManager 对外 API 不变
# ──────────────────────────────────────────────

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
