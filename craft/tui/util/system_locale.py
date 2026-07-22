"""
系统语言 — 移植自 util/system-locale.ts

通过环境变量和时区检测系统语言区域设置。
"""

from __future__ import annotations

import os
import re
from typing import Optional

LOCALE_MATCHERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^en"), "en"),
    (re.compile(r"^zh.*(?:hant|tw|hk|mo)"), "zht"),
    (re.compile(r"^zh"), "zh"),
    (re.compile(r"^ko"), "ko"),
    (re.compile(r"^de"), "de"),
    (re.compile(r"^es"), "es"),
    (re.compile(r"^fr"), "fr"),
    (re.compile(r"^da"), "da"),
    (re.compile(r"^ja"), "ja"),
    (re.compile(r"^pl"), "pl"),
    (re.compile(r"^ru"), "ru"),
    (re.compile(r"^ar"), "ar"),
    (re.compile(r"^(?:no|nb|nn)"), "no"),
    (re.compile(r"^pt"), "br"),
    (re.compile(r"^th"), "th"),
    (re.compile(r"^bs"), "bs"),
    (re.compile(r"^tr"), "tr"),
]

CN_TIMEZONES = {
    "Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin",
    "Asia/Urumqi", "Asia/Kashgar",
}
ZHT_TIMEZONES = {"Asia/Hong_Kong", "Asia/Macau", "Asia/Macao", "Asia/Taipei"}
JA_TIMEZONES = {"Asia/Tokyo"}
EN_TIMEZONES = {
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Toronto", "America/Vancouver",
    "Europe/London", "Europe/Dublin", "Australia/Sydney",
    "Australia/Melbourne", "Pacific/Auckland",
}


def _detect_timezone_locale() -> Optional[str]:
    """通过时区检测语言"""
    try:
        import zoneinfo
        tz_name = str(datetime.now().astimezone().tzinfo)
    except Exception:
        return None

    if not tz_name:
        return None
    if tz_name in ZHT_TIMEZONES:
        return "zht"
    if tz_name in CN_TIMEZONES:
        return "zh"
    if tz_name in JA_TIMEZONES:
        return "ja"
    if tz_name in EN_TIMEZONES:
        return "en"
    return None


def detect_system_locale() -> str:
    """检测系统语言区域设置，默认 'en'"""
    from datetime import datetime

    tz = _detect_timezone_locale()
    if tz:
        return tz

    for env_var in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"]:
        value = os.environ.get(env_var)
        if not value:
            continue
        for raw in value.split(":"):
            cleaned = re.sub(r"[.@].*$", "", raw).replace("_", "-").lower()
            if not cleaned or cleaned in ("c", "posix"):
                continue
            for pattern, locale in LOCALE_MATCHERS:
                if pattern.match(cleaned):
                    return locale

    # Try Python's locale module
    try:
        import locale
        intl = locale.getdefaultlocale()[0] or ""
        intl = intl.lower().replace("_", "-")
        for pattern, locale_code in LOCALE_MATCHERS:
            if pattern.match(intl):
                return locale_code
    except Exception:
        pass

    return "en"
