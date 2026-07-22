"""
拼音输入 — 移植自 util/pinyin.ts

为 CJK 文本构建罗马化搜索字符串，支持全拼/单字拼音/首字母匹配。
需要 pypinyin 库。
"""

from __future__ import annotations

import re
from typing import Optional

from pypinyin import lazy_pinyin, Style

CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
_cache: dict[str, str] = {}


def pinyin_search(text: Optional[str]) -> str:
    """为 CJK 文本构建拼音搜索字符串"""
    if not text or not CJK_RE.search(text):
        return ""
    cached = _cache.get(text)
    if cached is not None:
        return cached

    syllables = lazy_pinyin(text, style=Style.TONE3, neutral_tone_with_five=True)
    initials = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER))

    result = f"{''.join(syllables)} {' '.join(syllables)} {initials}".lower()
    _cache[text] = result
    return result
