"""工具兼容辅助 — 移植自 tool-compat.ts

工具名称和参数的规范化、修复，用于 AI SDK 兼容。
"""

from __future__ import annotations

import json
import re
from typing import Any


def canonical(name: str) -> str:
    """规范化名称：去除分隔符并转小写

    对应 TS canonical()。将 PascalCase, camelCase, snake_case, kebab-case
    统一为可比较的 token。
    """
    return re.sub(r"[-_\s]+", "", name).lower()


def resolve_name(name: str, candidates: list[str]) -> str | None:
    """解析名称到候选列表中的标准名称

    对应 TS resolveName()。支持大小写不敏感和规范化匹配。
    """
    if name in candidates:
        return name

    lower = name.lower()
    case_match = next((c for c in candidates if c.lower() == lower), None)
    if case_match:
        return case_match

    key = canonical(name)
    return next((c for c in candidates if canonical(c) == key), None)


def schema_property_keys(schema: dict) -> list[str]:
    """获取 JSON Schema 的属性键列表

    对应 TS schemaPropertyKeys()。
    """
    if not isinstance(schema.get("properties"), dict):
        return []
    return list(schema["properties"].keys())


def _combined_schemas(schema: dict) -> list[dict]:
    """获取组合 schema (allOf/anyOf/oneOf)"""
    out: list[dict] = []
    for key in ("allOf", "anyOf", "oneOf"):
        branch = schema.get(key)
        if isinstance(branch, list):
            for entry in branch:
                if isinstance(entry, dict):
                    out.append(entry)
    return out


def _normalize_value(value: Any, schema: dict | None) -> Any:
    """递归规范化值"""
    if schema is None:
        return value

    if isinstance(value, list):
        items = schema.get("items")
        item_schema = items if isinstance(items, dict) else None
        if item_schema:
            return [_normalize_value(v, item_schema) for v in value]
        return value

    if isinstance(value, dict):
        return normalize_input(value, schema)

    return value


def normalize_input(input_data: Any, schema: dict) -> Any:
    """规范化输入对象的键名到 schema 中的标准属性名

    对应 TS normalizeInput()。精确匹配优先，别名（大小写/分隔符差异）其次。
    """
    if not isinstance(input_data, dict):
        return input_data

    property_keys = schema_property_keys(schema)
    combined_branches = _combined_schemas(schema)
    if not property_keys and not combined_branches:
        return input_data

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}

    by_canonical = {canonical(key): key for key in property_keys}
    property_key_set = set(property_keys)
    exact_keys: set[str] = set()
    normalized: dict[str, Any] = {}

    def _child_schema(key: str) -> dict | None:
        ps = properties.get(key)
        return ps if isinstance(ps, dict) else None

    # Pass 1: 精确匹配
    for key, value in input_data.items():
        if key not in property_key_set:
            continue
        normalized[key] = _normalize_value(value, _child_schema(key))
        exact_keys.add(key)

    # Pass 2: 别名匹配（仅填充精确未占的槽）
    for key, value in input_data.items():
        if key in property_key_set:
            continue
        resolved = by_canonical.get(canonical(key))
        if resolved and resolved not in exact_keys and resolved not in normalized:
            normalized[resolved] = _normalize_value(value, _child_schema(resolved))
            continue
        normalized[key] = value

    # 递归进入组合分支
    result: dict[str, Any] = normalized
    for branch in combined_branches:
        next_result = normalize_input(result, branch)
        if isinstance(next_result, dict):
            result = next_result

    return result


def _repair_unicode_escapes(text: str) -> str:
    """修复被空白割裂的 Unicode 转义序列

    对应 TS repairUnicodeEscapes()。
    """
    if "\\u" not in text:
        return text

    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        if i + 1 >= len(text):
            out.append(ch)
            i += 1
            continue

        next_ch = text[i + 1]
        if next_ch == "\\":
            out.append("\\\\")
            i += 2
            continue
        if next_ch != "u":
            out.append(ch)
            i += 1
            continue

        # 收集 \\u 后的 4 位十六进制数字
        j = i + 2
        hex_digits: list[str] = []
        while j < len(text) and len(hex_digits) < 4:
            c = text[j]
            if re.match(r"[0-9a-fA-F]", c):
                hex_digits.append(c)
                j += 1
            elif c.isspace():
                j += 1
            else:
                break

        if len(hex_digits) == 4:
            out.append("\\u" + "".join(hex_digits))
            i = j
        else:
            out.append(ch)
            i += 1

    return "".join(out)


def parse_tool_input(input_str: str) -> Any:
    """解析工具输入字符串

    对应 TS parseToolInput()。尝试 JSON 解析，失败时修复 Unicode 转义后重试。
    """
    stripped = input_str.strip()
    if not stripped:
        return {}

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        repaired = _repair_unicode_escapes(stripped)
        if repaired != stripped:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return stripped
        return stripped


def stringify_tool_input(input_data: Any) -> str:
    """将工具输入转换为字符串

    对应 TS stringifyToolInput()。
    """
    if isinstance(input_data, str):
        return input_data
    return json.dumps(input_data)


class ToolRepairInput:
    """工具调用修复输入"""
    def __init__(
        self,
        tool_name: str,
        input_str: str,
        tool_names: list[str],
        get_schema_fn=None,
    ):
        self.tool_name = tool_name
        self.input = input_str
        self.tool_names = tool_names
        self.get_schema = get_schema_fn


class RepairedToolCall:
    """修复后的工具调用"""
    def __init__(self, tool_name: str, input_str: str):
        self.tool_name = tool_name
        self.input = input_str


async def repair_tool_call(
    input_data: ToolRepairInput,
) -> RepairedToolCall | None:
    """修复工具名称和参数键名

    对应 TS repairToolCall()。修复大小写/分隔符差异。
    """
    resolved = resolve_name(input_data.tool_name, input_data.tool_names)
    if not resolved:
        return None

    schema = {}
    if input_data.get_schema:
        schema = await input_data.get_schema(resolved) if hasattr(input_data.get_schema, "__call__") else {}

    parsed = parse_tool_input(input_data.input)
    normalized = normalize_input(parsed, schema)
    repaired_input = stringify_tool_input(normalized)

    if resolved == input_data.tool_name and repaired_input == input_data.input:
        return None

    return RepairedToolCall(tool_name=resolved, input_str=repaired_input)
