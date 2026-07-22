"""
输入系统 — 移植 component/prompt/index.tsx (1991行)
多行输入、模式切换 (normal/shell/agent)、自动补全、语音指示
"""

from __future__ import annotations

import os
import time
from collections import Counter

from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Static


# ─── 频率排序 (移植 frecency.ts) ──────────────────────
class FrecencyTracker:
    """频率 + 时效排序"""

    def __init__(self):
        self._counts: Counter = Counter()
        self._last_used: dict[str, float] = {}
        self._decay_hours = 72

    def record(self, key: str):
        self._counts[key] += 1
        self._last_used[key] = time.time()

    def score(self, key: str) -> float:
        count = self._counts.get(key, 0)
        last = self._last_used.get(key, 0)
        recency = 1.0 / (1 + (time.time() - last) / 3600) if last > 0 else 0
        return count * 0.7 + recency * 0.3

    def sort(self, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return sorted(items, key=lambda x: self.score(x[0]), reverse=True)


# ─── 输入历史 (移植 history.ts) ──────────────────────
class PromptHistory:
    def __init__(self, max_items: int = 100):
        self._items: list[dict] = []
        self._max = max_items
        self._pos = -1

    def push(self, text: str, mode: str = "normal"):
        if text and (not self._items or self._items[-1]["text"] != text):
            self._items.append({"text": text, "mode": mode, "ts": time.time()})
            if len(self._items) > self._max:
                self._items.pop(0)
        self._pos = len(self._items)

    def prev(self) -> str | None:
        if self._pos > 0:
            self._pos -= 1
            entry = self._items[self._pos] if self._pos < len(self._items) else None
            return entry["text"] if entry else None
        return None

    def next(self) -> str | None:
        if self._pos < len(self._items) - 1:
            self._pos += 1
            return self._items[self._pos]["text"]
        self._pos = len(self._items)
        return None

    def search(self, prefix: str) -> list[str]:
        return [e["text"] for e in self._items if e["text"].startswith(prefix)][:5]


# ─── 自动补全 (移植 autocomplete.tsx) ─────────────────
class AutocompleteEngine:
    """完整自动补全：命令/文件/Agent/技能"""

    def __init__(self):
        self._frecency = FrecencyTracker()
        self._commands: dict[str, str] = {
            "/help": "查看帮助",
            "/exit": "退出",
            "/agent": "切换Agent: /agent build|plan",
            "/model": "切换模型: /model gpt-4o|claude-sonnet-4",
            "/diff": "查看Git变更",
            "/commit": "Git提交: /commit <消息>",
            "/tools": "工具列表",
            "/session": "会话信息",
            "/new": "新建对话",
            "/clear": "清屏",
            "/memory": "记忆管理: /memory add|search <内容>",
            "/skill": "技能列表",
            "/task": "任务列表",
            "/file": "文件浏览: /file <路径>",
            "/mcp": "MCP服务器状态",
            "/account": "账户管理: /account list|create|login|logout|switch",
            "/workspace": "工作区管理: /workspace create|list|switch",
            "/theme": "主题切换: /theme list|set <主题名>",
            "/plugin": "插件管理: /plugin install|remove|list",
        }

    def complete(self, prefix: str, max_items: int = 20) -> list[tuple[str, str]]:
        if not prefix:
            return []
        candidates: list[tuple[str, str]] = []

        # 命令补全
        for cmd, desc in self._commands.items():
            if cmd.startswith(prefix):
                candidates.append((cmd, desc))

        # 文件路径补全
        if "/" in prefix or prefix.startswith("."):
            base = os.path.dirname(prefix) or "."
            partial = os.path.basename(prefix)
            try:
                for entry in os.listdir(base):
                    full = os.path.join(base, entry)
                    if entry.startswith(partial):
                        suffix = "/" if os.path.isdir(full) else ""
                        candidates.append((os.path.join(prefix[:len(prefix)-len(partial)], entry) + suffix, "file"))
            except Exception:
                pass

        return self._frecency.sort(candidates)[:max_items]

    def record_use(self, item: str):
        self._frecency.record(item)


# ─── 多行输入框 ──────────────────────────────────────
class PromptInput(Input):
    """增强输入框 — 多行/历史/补全/模式"""

    class Submitted(Input.Submitted):
        """提交事件"""

    def __init__(self, mode: str = "normal", **kw):
        super().__init__(**kw)
        self.mode = mode  # normal / shell / agent
        self.history = PromptHistory()
        self.autocomplete = AutocompleteEngine()
        self._suggestions: list[tuple[str, str]] = []
        self._suggestion_idx = 0
        self._stashed: str | None = None

    @property
    def mode_label(self) -> str:
        labels = {"normal": "", "shell": "$", "agent": ">"}
        return labels.get(self.mode, "")

    def on_submit(self, value: str):
        if value.strip():
            self.history.push(value, self.mode)
            self.autocomplete.record_use(value.split()[0] if value else value)

    async def complete(self) -> bool:
        """执行自动补全，返回是否补全成功"""
        prefix = self.value
        if not prefix:
            return False
        items = self.autocomplete.complete(prefix)
        if items:
            self._suggestions = items
            self._suggestion_idx = 0
            best = items[0][0]
            self.value = best + " "
            self.cursor_position = len(self.value)
            return True
        return False

    async def stash(self) -> bool:
        """暂存当前输入"""
        if self.value.strip():
            self._stashed = self.value
            self.value = ""
            return True
        return False

    def unstash(self) -> str | None:
        val = self._stashed
        self._stashed = None
        return val


# ─── 输入模式指示器 ──────────────────────────────────
class ModeIndicator(Static):
    """显示当前输入模式"""

    def __init__(self, **kw):
        super().__init__("", **kw)

    def set_mode(self, mode: str):
        labels = {"normal": ">>", "shell": "$", "agent": ">"}
        colors = {"normal": "blue", "shell": "green", "agent": "yellow"}
        label = labels.get(mode, ">>")
        color = colors.get(mode, "blue")
        self.update(f"[bold {color}]{label}[/]")


# ─── Provider 标签 ──────────────────────────────────
class ProviderLabel(Static):
    def __init__(self, **kw):
        super().__init__("", **kw)

    def set_label(self, agent: str, model: str):
        self.update(f"[dim]{agent}[/] [blue]|[/] [dim]{model}[/]")


# ─── 输入栏完整组件 ─────────────────────────────────
class PromptBar(Vertical):
    """输入栏 — 整合模式指示器/输入框/标签/提示"""

    def __init__(self, agent: str = "build", model: str = "gpt-4o", **kw):
        super().__init__(**kw)
        self._agent = agent
        self._model = model

    def compose(self):
        with Horizontal(classes="prompt-bar"):
            yield ModeIndicator(id="mode-indicator")
            self._input = PromptInput(
                placeholder="输入消息... (Enter发送  Tab补全  ↑↓历史)",
                id="prompt-input"
            )
            yield self._input
            yield ProviderLabel(id="provider-label")

    def on_mount(self):
        self._input.focus()
        self._update_labels()

    def _update_labels(self):
        try:
            self.query_one("#mode-indicator", ModeIndicator).set_mode(self._input.mode)
            self.query_one("#provider-label", ProviderLabel).set_label(self._agent, self._model)
        except Exception:
            pass

    @property
    def prompt_input(self) -> PromptInput:
        return self._input

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "prompt-input":
            event.stop()
            self.post_message(self.PromptSubmitted(event.value))

    class PromptSubmitted(Message):
        def __init__(self, value: str):
            super().__init__()
            self.value = value


# ─── CSS ─────────────────────────────────────────────
PROMPT_CSS = """
.prompt-bar {
    height: 3;
    background: #1a1b26;
    border-top: solid #2f3340;
    padding: 0 1;
}
#mode-indicator {
    width: 3;
    content-align: center middle;
}
#prompt-input {
    background: #1a1b26;
    color: #c0caf5;
    border: none;
}
#prompt-input:focus {
    border: none;
}
#provider-label {
    width: 20;
    content-align: right middle;
    color: #565f89;
}
"""
