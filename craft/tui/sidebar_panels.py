"""
侧栏面板 — 移植 ui/sidebar/ 系列 (10文件)
文件树、LSP、MCP、任务、待办、目标、TPS、目录、指令
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static, ListView, ListItem, Tree


# ─── 文件树面板 ──────────────────────────────────────
class FileTreePanel(Vertical):
    def __init__(self, root: str = ".", **kw):
        super().__init__(**kw)
        self._root = root

    def compose(self):
        yield Label("文件", classes="sidebar-title")
        self._tree = Tree(".")
        yield self._tree

    def on_mount(self):
        self._refresh()

    def _refresh(self, path: str = "."):
        self._tree.clear()
        try:
            entries = sorted(os.listdir(path))
            for e in entries[:30]:
                full = os.path.join(path, e)
                if os.path.isdir(full) and not e.startswith("."):
                    branch = self._tree.root.add(e)
                elif not e.startswith("."):
                    self._tree.root.add(e)
        except Exception:
            pass


# ─── LSP 状态面板 ──────────────────────────────────────
class LSPStatusPanel(Vertical):
    def compose(self):
        yield Label("LSP", classes="sidebar-title")
        yield Static("  Python: idle", classes="sidebar-item")
        yield Static("  TypeScript: idle", classes="sidebar-item")


# ─── MCP 状态面板 ──────────────────────────────────────
class MCPStatusPanel(Vertical):
    def compose(self):
        yield Label("MCP", classes="sidebar-title")
        self._items: list[Static] = []
        for name in ["filesystem", "github", "terminal"]:
            s = Static(f"  {name}: ○", classes="sidebar-item")
            self._items.append(s)
            yield s

    def set_status(self, name: str, connected: bool):
        for item in self._items:
            if name in str(item.renderable):
                icon = "●" if connected else "○"
                item.update(f"  {name}: {icon}")


# ─── 任务面板 ──────────────────────────────────────────
class TaskPanel(Vertical):
    def compose(self):
        yield Label("任务", classes="sidebar-title")
        self._label = Static("  无活跃任务", classes="sidebar-item")
        yield self._label

    def update_tasks(self, tasks: list[dict]):
        if not tasks:
            self._label.update("  无活跃任务")
        else:
            text = "\n".join(f"  {'⏳🔄✅❌'[['pending','running','completed','failed'].index(t['status'])]} {t['title'][:20]}" for t in tasks[:5])
            self._label.update(text)


# ─── TPS 速度面板 ──────────────────────────────────────
class TPSPanel(Vertical):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._tokens = 0
        self._start = time.time()

    def compose(self):
        yield Label("速度", classes="sidebar-title")
        self._tps = Static("  0 T/s", classes="sidebar-item")
        yield self._tps

    def add_tokens(self, count: int):
        self._tokens += count
        elapsed = time.time() - self._start
        if elapsed > 0:
            tps = self._tokens / elapsed
            self._tps.update(f"  {tps:.0f} T/s")

    def reset(self):
        self._tokens = 0
        self._start = time.time()
        self._tps.update("  0 T/s")


# ─── 当前目录面板 ──────────────────────────────────────
class CWDPanel(Vertical):
    def compose(self):
        yield Label("目录", classes="sidebar-title")
        self._cwd = Static(f"  {Path.cwd().name}", classes="sidebar-item")
        yield self._cwd

    def update_cwd(self, path: str):
        self._cwd.update(f"  {Path(path).name}")


# ─── 目标面板 ──────────────────────────────────────────
class GoalPanel(Vertical):
    def compose(self):
        yield Label("目标", classes="sidebar-title")
        self._goal = Static("  (无)", classes="sidebar-item")
        yield self._goal

    def set_goal(self, text: str):
        self._goal.update(f"  {text[:30]}")
