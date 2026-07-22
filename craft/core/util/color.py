import re


def is_valid_hex(hex_str: str | None) -> bool:
    """检查是否为有效 hex 颜色 — 移植自 color.ts isValidHex"""
    if not hex_str:
        return False
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", hex_str))


def hex_to_rgb(hex_str: str) -> dict:
    """hex 转 RGB — 移植自 color.ts hexToRgb"""
    r = int(hex_str[1:3], 16)
    g = int(hex_str[3:5], 16)
    b = int(hex_str[5:7], 16)
    return {"r": r, "g": g, "b": b}


def hex_to_ansi_bold(hex_str: str | None) -> str | None:
    """hex 转 ANSI 粗体颜色 — 移植自 color.ts hexToAnsiBold"""
    if not is_valid_hex(hex_str):
        return None
    rgb = hex_to_rgb(hex_str)
    return f"\x1b[38;2;{rgb['r']};{rgb['g']};{rgb['b']}m\x1b[1m"
