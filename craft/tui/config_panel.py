"""
TUI 配置 — 移植 config/ 系列
tui.json 配置、迁移、模式设置
"""

from __future__ import annotations

import json

from craft.config import CONFIG_DIR
from craft.tui.i18n import i18n


class TUIConfig:
    """TUI 配置管理器 (移植 config/tui.ts)"""
    def __init__(self):
        self._path = CONFIG_DIR / "tui.json"
        self._data: dict = {"theme": "tokyo-night", "language": "zh", "sidebar_width": 28}
        self._load()

    def _load(self):
        try:
            if self._path.exists():
                self._data.update(json.loads(self._path.read_text()))
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    @property
    def theme(self) -> str:
        return self._data.get("theme", "tokyo-night")
    @theme.setter
    def theme(self, v: str):
        self._data["theme"] = v
        self._save()

    @property
    def language(self) -> str:
        return self._data.get("language", "zh")
    @language.setter
    def language(self, v: str):
        self._data["language"] = v
        i18n.set_lang(v)
        self._save()

    @property
    def sidebar_width(self) -> int:
        return self._data.get("sidebar_width", 28)
    @sidebar_width.setter
    def sidebar_width(self, v: int):
        self._data["sidebar_width"] = v
        self._save()


tui_config = TUIConfig()
