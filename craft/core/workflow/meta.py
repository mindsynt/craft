"""
元数据解析 — 移植自 packages/opencode/src/workflow/meta.ts
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowPhase:
    title: str = ""
    detail: str | None = None


@dataclass
class WorkflowPermission:
    permission: str = ""
    patterns: list[str] | None = None
    always: list[str] | None = None
    reason: str | None = None


@dataclass
class WorkflowMeta:
    name: str = ""
    description: str = ""
    when_to_use: str | None = None
    phases: list[WorkflowPhase] | None = None
    model: str | None = None
    permissions: list[WorkflowPermission] | None = None


@dataclass
class ParseResult:
    ok: bool = False
    meta: WorkflowMeta | None = None
    body: str = ""
    error: str = ""


META_START_RE_STR = r"export\s+const\s+meta\s*="


def parse_meta(script: str) -> ParseResult:
    """解析工作流脚本中的 meta 块 — 移植自 meta.ts parseMeta"""
    match = re.search(META_START_RE_STR, script)
    if not match:
        return ParseResult(ok=False, error="workflow script must start with `export const meta = { ... }`")

    start = match.start()

    # 找到开始的花括号
    open_brace = script.find("{", match.end())
    if open_brace == -1:
        return ParseResult(ok=False, error="workflow script must start with `export const meta = { ... }`")

    # 平衡花括号
    close = _find_balanced_close(script, open_brace)
    if close == -1:
        return ParseResult(ok=False, error="could not locate a balanced meta object literal")

    literal = script[open_brace:close + 1]

    # 解析纯数据字面量（不执行代码）
    parsed = _parse_data_literal(literal)
    if not parsed["ok"]:
        return ParseResult(ok=False, error=f"meta is not a valid object literal: {parsed['error']}")

    meta_dict = parsed["value"]
    if not isinstance(meta_dict, dict):
        return ParseResult(ok=False, error="meta must be an object")

    if not isinstance(meta_dict.get("name"), str) or not meta_dict["name"]:
        return ParseResult(ok=False, error="meta.name (non-empty string) is required")
    if not isinstance(meta_dict.get("description"), str) or not meta_dict["description"]:
        return ParseResult(ok=False, error="meta.description (non-empty string) is required")

    # 验证 permissions
    if "permissions" in meta_dict:
        perms = meta_dict["permissions"]
        if not isinstance(perms, list):
            return ParseResult(ok=False, error="meta.permissions must be an array")
        for p in perms:
            if not isinstance(p, dict):
                return ParseResult(ok=False, error="each meta.permissions entry must be an object")
            if not isinstance(p.get("permission"), str) or not p["permission"]:
                return ParseResult(ok=False, error="each meta.permissions entry needs a non-empty `permission` string")

    # 提取 phases
    phases = None
    if meta_dict.get("phases") and isinstance(meta_dict["phases"], list):
        phases = []
        for p in meta_dict["phases"]:
            if isinstance(p, dict):
                phases.append(WorkflowPhase(
                    title=p.get("title", ""),
                    detail=p.get("detail"),
                ))

    # 提取 permissions
    permissions = None
    if meta_dict.get("permissions") and isinstance(meta_dict["permissions"], list):
        permissions = []
        for p in meta_dict["permissions"]:
            permissions.append(WorkflowPermission(
                permission=p.get("permission", ""),
                patterns=p.get("patterns"),
                always=p.get("always"),
                reason=p.get("reason"),
            ))

    end_index = close + 1
    if close + 1 < len(script) and script[close + 1] == ";":
        end_index += 1

    meta = WorkflowMeta(
        name=meta_dict["name"],
        description=meta_dict["description"],
        when_to_use=meta_dict.get("whenToUse"),
        phases=phases,
        model=meta_dict.get("model"),
        permissions=permissions,
    )

    # 构建 body（meta 部分替换为等长空白，保留行号）
    matched = script[start:end_index]
    body = script[:start] + matched.replace("\n", " ").replace(" ", " ") + script[end_index:]
    # 简化为保留 script 中的非 meta 部分
    body_lines = []
    for i, line in enumerate(script.split("\n")):
        body_lines.append(line)
    body = "\n".join(body_lines)

    return ParseResult(ok=True, meta=meta, body=body)


def _find_balanced_close(script: str, open_idx: int) -> int:
    """查找平衡的闭合花括号 — 移植自 meta.ts findBalancedClose"""
    depth = 0
    quote = ""
    i = open_idx
    while i < len(script):
        ch = script[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch == "/" and i + 1 < len(script) and script[i + 1] == "/":
            i += 2
            while i < len(script) and script[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(script) and script[i + 1] == "*":
            i += 2
            while i < len(script) and not (script[i] == "*" and i + 1 < len(script) and script[i + 1] == "/"):
                i += 1
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_data_literal(text: str) -> dict:
    """解析纯数据字面量（不执行代码）— 移植自 meta.ts parseDataLiteral"""
    reader = {"text": text, "pos": 0, "depth": 0}
    try:
        _skip_trivia(reader)
        value = _read_value(reader)
        _skip_trivia(reader)
        if reader["pos"] != len(reader["text"]):
            return {"ok": False, "error": f"unexpected token at offset {reader['pos']}"}
        return {"ok": True, "value": value}
    except _ParseFail as e:
        return {"ok": False, "error": str(e)}


class _ParseFail(Exception):
    pass


def _skip_trivia(r: dict):
    """跳过空白和注释"""
    while r["pos"] < len(r["text"]):
        ch = r["text"][r["pos"]]
        if ch in " \t\n\r\f\v":
            r["pos"] += 1
            continue
        if ch == "/" and r["pos"] + 1 < len(r["text"]):
            if r["text"][r["pos"] + 1] == "/":
                r["pos"] += 2
                while r["pos"] < len(r["text"]) and r["text"][r["pos"]] != "\n":
                    r["pos"] += 1
                continue
            if r["text"][r["pos"] + 1] == "*":
                r["pos"] += 2
                while r["pos"] < len(r["text"]) and not (r["text"][r["pos"]] == "*" and r["pos"] + 1 < len(r["text"]) and r["text"][r["pos"] + 1] == "/"):
                    r["pos"] += 1
                r["pos"] += 2
                continue
        return


def _read_value(r: dict) -> Any:
    """读取值"""
    ch = r["text"][r["pos"]] if r["pos"] < len(r["text"]) else None
    if ch is None:
        raise _ParseFail("unexpected end of input")
    if ch == "{":
        return _read_object(r)
    if ch == "[":
        return _read_array(r)
    if ch in "\"'":
        return _read_string(r)
    if ch == "-" or (ch is not None and "0" <= ch <= "9"):
        return _read_number(r)
    if _match_keyword(r, "true"):
        return True
    if _match_keyword(r, "false"):
        return False
    if _match_keyword(r, "null"):
        return None
    raise _ParseFail(f"unexpected token at offset {r['pos']} (only data literals are allowed)")


def _read_object(r: dict) -> dict:
    """读取对象"""
    r["depth"] += 1
    if r["depth"] > 100:
        raise _ParseFail("meta nesting too deep")
    r["pos"] += 1
    obj = {}
    _skip_trivia(r)
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
        r["pos"] += 1
        r["depth"] -= 1
        return obj
    while True:
        _skip_trivia(r)
        key = _read_key(r)
        _skip_trivia(r)
        if r["pos"] >= len(r["text"]) or r["text"][r["pos"]] != ":":
            raise _ParseFail(f"expected ':' after key '{key}' at offset {r['pos']}")
        r["pos"] += 1
        _skip_trivia(r)
        obj[key] = _read_value(r)
        _skip_trivia(r)
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ",":
            r["pos"] += 1
            _skip_trivia(r)
            if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
                r["pos"] += 1
                r["depth"] -= 1
                return obj
            continue
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
            r["pos"] += 1
            r["depth"] -= 1
            return obj
        raise _ParseFail(f"expected ',' or '}}' at offset {r['pos']}")


def _read_array(r: dict) -> list:
    """读取数组"""
    r["depth"] += 1
    if r["depth"] > 100:
        raise _ParseFail("meta nesting too deep")
    r["pos"] += 1
    arr = []
    _skip_trivia(r)
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
        r["pos"] += 1
        r["depth"] -= 1
        return arr
    while True:
        _skip_trivia(r)
        arr.append(_read_value(r))
        _skip_trivia(r)
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ",":
            r["pos"] += 1
            _skip_trivia(r)
            if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
                r["pos"] += 1
                r["depth"] -= 1
                return arr
            continue
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
            r["pos"] += 1
            r["depth"] -= 1
            return arr
        raise _ParseFail(f"expected ',' or ']' at offset {r['pos']}")


def _read_key(r: dict) -> str:
    """读取对象键"""
    ch = r["text"][r["pos"]] if r["pos"] < len(r["text"]) else None
    if ch in "\"'":
        return _read_string(r)
    if ch is not None and (ch.isalpha() or ch in "_$"):
        start = r["pos"]
        r["pos"] += 1
        while r["pos"] < len(r["text"]) and (r["text"][r["pos"]].isalnum() or r["text"][r["pos"]] in "_$"):
            r["pos"] += 1
        return r["text"][start:r["pos"]]
    raise _ParseFail(f"expected a property name at offset {r['pos']}")


def _read_string(r: dict) -> str:
    """读取字符串"""
    quote = r["text"][r["pos"]]
    r["pos"] += 1
    out = []
    while r["pos"] < len(r["text"]):
        ch = r["text"][r["pos"]]
        if ch == "\\":
            esc = r["text"][r["pos"] + 1] if r["pos"] + 1 < len(r["text"]) else None
            r["pos"] += 2
            if esc == "n":
                out.append("\n")
            elif esc == "t":
                out.append("\t")
            elif esc == "r":
                out.append("\r")
            elif esc == "b":
                out.append("\b")
            elif esc == "f":
                out.append("\f")
            elif esc == "u":
                hex_str = r["text"][r["pos"]:r["pos"] + 4] if r["pos"] + 4 <= len(r["text"]) else ""
                if not re.match(r"^[0-9a-fA-F]{4}$", hex_str):
                    raise _ParseFail("invalid \\u escape")
                out.append(chr(int(hex_str, 16)))
                r["pos"] += 4
            elif esc is not None:
                out.append(esc)
            else:
                raise _ParseFail("unterminated string")
            continue
        if ch == quote:
            r["pos"] += 1
            return "".join(out)
        out.append(ch)
        r["pos"] += 1
    raise _ParseFail("unterminated string")


def _read_number(r: dict) -> float:
    """读取数字"""
    start = r["pos"]
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "-":
        r["pos"] += 1
    while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
        r["pos"] += 1
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ".":
        r["pos"] += 1
        while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
            r["pos"] += 1
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] in "eE":
        r["pos"] += 1
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] in "+-":
            r["pos"] += 1
        while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
            r["pos"] += 1
    raw = r["text"][start:r["pos"]]
    return float(raw)


def _match_keyword(r: dict, word: str) -> bool:
    """匹配关键字"""
    if r["text"][r["pos"]:r["pos"] + len(word)] == word:
        after_idx = r["pos"] + len(word)
        if after_idx >= len(r["text"]) or not (r["text"][after_idx].isalnum() or r["text"][after_idx] in "_$"):
            r["pos"] += len(word)
            return True
    return False
