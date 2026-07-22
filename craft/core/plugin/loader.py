"""加载器 — 移植自 loader.ts"""

from __future__ import annotations

import importlib
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

from .shared import (
    PluginKind,
    PluginSource,
    PluginPackage,
    is_deprecated_plugin,
    plugin_source,
    resolve_plugin_target,
    create_plugin_entry,
    check_plugin_compatibility,
)

logger = logging.getLogger(__name__)


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
