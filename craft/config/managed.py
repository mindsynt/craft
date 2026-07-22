"""托管配置 — 对应 managed.ts"""

from __future__ import annotations

import json
import os
from pathlib import Path

MANAGED_PLIST_DOMAIN = "ai.craft.managed"
PLIST_META_KEYS = {
    "PayloadDisplayName", "PayloadIdentifier", "PayloadType",
    "PayloadUUID", "PayloadVersion", "_manualProfile",
}


def system_managed_config_dir() -> str:
    """获取系统托管配置目录"""
    import platform
    system = platform.system()
    if system == "Darwin":
        return "/Library/Application Support/craft"
    elif system == "Windows":
        return os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "craft")
    else:
        return "/etc/craft"


def managed_config_dir() -> str:
    """获取托管配置目录（可被测试覆盖）"""
    return os.environ.get("CRAFT_TEST_MANAGED_CONFIG_DIR") or system_managed_config_dir()


def parse_managed_plist(json_text: str) -> str:
    """解析托管 plist JSON，去除元数据键"""
    raw = json.loads(json_text)
    for key in list(raw.keys()):
        if key in PLIST_META_KEYS:
            del raw[key]
    return json.dumps(raw)


def read_managed_preferences() -> dict | None:
    """读取 macOS MDM 托管的 plist 配置"""
    import platform
    if platform.system() != "Darwin":
        return None

    import subprocess
    import plistlib

    username = os.environ.get("USER") or os.environ.get("USERNAME", "")
    paths = [
        f"/Library/Managed Preferences/{username}/{MANAGED_PLIST_DOMAIN}.plist",
        f"/Library/Managed Preferences/{MANAGED_PLIST_DOMAIN}.plist",
    ]

    for plist_path in paths:
        if not Path(plist_path).exists():
            continue
        try:
            result = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", plist_path],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                continue
            return {
                "source": f"mobileconfig:{plist_path}",
                "text": parse_managed_plist(result.stdout),
            }
        except Exception:
            continue
    return None
