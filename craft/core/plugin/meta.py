"""元数据 — 移植自 meta.ts"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from craft.config import CONFIG_DIR

from .shared import (
    PluginSource,
    PluginPackage,
    _async_read_json,
    _async_write_json,
    plugin_source,
    parse_plugin_specifier,
)

logger = logging.getLogger(__name__)


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
