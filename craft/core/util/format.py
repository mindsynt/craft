import re


def format_number(n: int) -> str:
    """格式化数字（千分位）"""
    return f"{n:,}"


def format_number_short(num: float) -> str:
    """简短格式化数字 — 移植自 locale.ts number"""
    if num >= 1000000:
        return f"{num / 1000000:.1f}M"
    elif num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)


def truncate(text: str, max_len: int = 200) -> str:
    """截断文本"""
    return text[:max_len] + "..." if len(text) > max_len else text


def truncate_middle(text: str, max_len: int = 35) -> str:
    """中间截断文本 — 移植自 locale.ts truncateMiddle"""
    if len(text) <= max_len:
        return text
    ellipsis = "…"
    keep_start = (max_len - len(ellipsis)) // 2 + (max_len - len(ellipsis)) % 2
    keep_end = (max_len - len(ellipsis)) // 2
    return text[:keep_start] + ellipsis + text[-keep_end:]


def pluralize(count: int, singular: str, plural: str) -> str:
    """复数化 — 移植自 locale.ts pluralize"""
    template = singular if count == 1 else plural
    return template.replace("{}", str(count))


def titlecase(s: str) -> str:
    """标题大小写 — 移植自 locale.ts titlecase"""
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), s)


def parse_keybind(spec: str) -> dict:
    """解析键绑定字符串"""
    parts = spec.replace("-", " ").replace("+", " ").split()
    result = {"key": "", "modifiers": []}
    for p in parts:
        p = p.lower()
        if p in ("ctrl", "cmd", "meta", "alt", "shift", "option", "super"):
            result["modifiers"].append(p)
        else:
            result["key"] = p
    return result
