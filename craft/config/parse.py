"""JSON / JSONC 解析工具 — 对应 parse.ts, variable.ts, entry-name.ts"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .error import ConfigInvalidError, ConfigJsonError


# ═══════════════════════════════════════════════════════════
# 解析工具 (对应 parse.ts)
# ═══════════════════════════════════════════════════════════


def find_project_config(start: str | None = None) -> str | None:
    """从当前目录向上查找项目配置"""
    from .paths import PROJECT_CONFIG_FILES

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
# Config file loading (simple)
# ═══════════════════════════════════════════════════════════


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
