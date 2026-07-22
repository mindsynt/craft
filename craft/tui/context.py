"""
上下文管理 — 移植 context/ 系列
快捷键配置、同步、项目、思考指示器、本地存储
"""

from __future__ import annotations

import json

from textual.widgets import Static

from craft.config import CONFIG_DIR


# ─── 思考指示器 ──────────────────────────────────────
class ThinkingIndicator(Static):
    """显示 Agent 思考状态"""

    def __init__(self, **kw):
        super().__init__("", **kw)
        self._active = False

    def start(self, agent: str = "Build"):
        self._active = True
        self.update(f"[yellow]⏳ {agent} 思考中...[/]")
        self.styles.animate("opacity", 0.3, duration=0.5)

    def stop(self):
        self._active = False
        self.update("")


# ─── 快捷键管理器 ──────────────────────────────────────
class KeybindManager:
    """可定制的快捷键系统"""

    def __init__(self):
        self._bindings: dict[str, str] = {
            "enter": "submit",
            "tab": "complete",
            "up": "history_prev",
            "down": "history_next",
            "escape": "focus_input",
            "f5": "new_session",
            "ctrl+d": "toggle_sidebar",
            "ctrl+p": "command_palette",
            "ctrl+n": "new_session",
        }
        self._load()

    def _load(self):
        try:
            f = CONFIG_DIR / "keybinds.json"
            if f.exists():
                self._bindings.update(json.loads(f.read_text()))
        except Exception:
            pass

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "keybinds.json").write_text(json.dumps(self._bindings, indent=2))

    def get(self, key: str) -> str | None:
        return self._bindings.get(key)

    def set(self, key: str, action: str):
        self._bindings[key] = action
        self.save()

    def list(self) -> dict[str, str]:
        return dict(self._bindings)


keybinds = KeybindManager()


# ─── 退出确认 ──────────────────────────────────────
class ExitHandler:
    def __init__(self):
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self):
        self._dirty = True

    def mark_clean(self):
        self._dirty = False


exit_handler = ExitHandler()
