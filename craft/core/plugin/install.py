"""安装 — 移植自 install.ts"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .shared import (
    PluginKind,
    PluginPackage,
    parse_plugin_specifier,
    read_plugin_package,
    resolve_plugin_target,
    _async_read_json,
    _async_read_text,
)

logger = logging.getLogger(__name__)


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
