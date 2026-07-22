"""共享工具 — 移植自 shared.ts"""

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
# 共享工具
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
