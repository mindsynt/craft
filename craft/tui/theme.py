"""
主题系统 — 移植自 packages/opencode/src/cli/cmd/tui/context/theme/
支持多主题切换、自定义颜色
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThemeColors:
    bg: str = "#1a1b26"
    surface: str = "#1f2335"
    sidebar: str = "#16161e"
    border: str = "#2f3340"
    text: str = "#c0caf5"
    text_dim: str = "#565f89"
    text_bright: str = "#a9b1d6"
    accent: str = "#7aa2f7"
    accent_bg: str = "#3b4261"
    success: str = "#9ece6a"
    warning: str = "#e0af68"
    error: str = "#f7768e"
    info: str = "#7dcfff"
    selection: str = "#3b4261"
    line: str = "#2f3340"
    prompt: str = "#73daca"
    agent_build: str = "#7aa2f7"
    agent_plan: str = "#e0af68"
    agent_explore: str = "#9ece6a"


class Theme:
    def __init__(self, name: str, colors: ThemeColors, 
                 dialog_bg: str = "#1f2335",
                 border_style: str = "round"):
        self.name = name
        self.colors = colors
        self.dialog_bg = dialog_bg
        self.border_style = border_style

    def to_css(self) -> str:
        c = self.colors
        return f"""
    Screen {{ background: {c.bg}; color: {c.text}; }}
    .sidebar {{ background: {c.sidebar}; border-right: solid {c.border}; }}
    .sidebar-title {{ color: {c.prompt}; text-style: bold; padding: 0 1; }}
    .sidebar-item {{ color: {c.text_dim}; padding: 0 1 0 2; }}
    .sidebar-item:hover {{ background: {c.selection}; color: {c.text_bright}; }}
    .sidebar-item:focus {{ background: {c.accent_bg}; color: {c.accent}; }}
    .chat-log {{ background: {c.surface}; color: {c.text}; }}
    .chat-input {{ background: {c.sidebar}; color: {c.text}; border: none; }}
    .panel-title {{ color: {c.info}; text-style: bold; background: {c.sidebar}; }}
    .status {{ color: {c.text_dim}; }}
    .accent {{ color: {c.accent}; }}
    .success {{ color: {c.success}; }}
    .warning {{ color: {c.warning}; }}
    .error {{ color: {c.error}; }}
    .info {{ color: {c.info}; }}
    .border {{ border: solid {c.border}; }}
    .selected {{ background: {c.selection}; }}
    .prompt {{ color: {c.prompt}; }}
    .label {{ color: {c.text_dim}; padding: 0 2; }}
    Button {{ background: {c.accent_bg}; color: {c.text}; }}
    Button:hover {{ background: {c.accent}; }}
    Button:focus {{ background: {c.accent}; }}
    Input {{ background: {c.sidebar}; color: {c.text}; border: solid {c.border}; }}
    Input:focus {{ border: solid {c.accent}; }}
    Select {{ background: {c.sidebar}; color: {c.text}; }}
    ListView {{ background: {c.sidebar}; }}
    ListItem {{ color: {c.text_dim}; }}
    ListItem:hover {{ background: {c.selection}; }}
    ListItem:focus {{ background: {c.accent_bg}; color: {c.accent}; }}
    RichLog {{ background: {c.surface}; color: {c.text}; }}
    """


# 内置主题
THEMES = {
    "tokyo-night": Theme("tokyo-night", ThemeColors()),
    "dracula": Theme("dracula", ThemeColors(
        bg="#282a36", surface="#2b2d3e", sidebar="#21222c",
        border="#45475a", text="#f8f8f2", text_dim="#6272a4",
        text_bright="#f8f8f2", accent="#bd93f9", accent_bg="#44475a",
        success="#50fa7b", warning="#f1fa8c", error="#ff5555", info="#8be9fd",
        selection="#44475a", line="#45475a", prompt="#ff79c6",
    )),
    "monokai": Theme("monokai", ThemeColors(
        bg="#272822", surface="#2d2e27", sidebar="#1e1f1c",
        border="#49483e", text="#f8f8f2", text_dim="#75715e",
        text_bright="#f8f8f2", accent="#a6e22e", accent_bg="#3e3d32",
        success="#a6e22e", warning="#e6db74", error="#f92672", info="#66d9ef",
        selection="#3e3d32", line="#49483e", prompt="#fd971f",
    )),
    "light": Theme("light", ThemeColors(
        bg="#ffffff", surface="#f8f9fa", sidebar="#e9ecef",
        border="#dee2e6", text="#212529", text_dim="#868e96",
        text_bright="#343a40", accent="#4263eb", accent_bg="#dbe4ff",
        success="#2b8a3e", warning="#e67700", error="#c92a2a", info="#1971c2",
        selection="#dbe4ff", line="#dee2e6", prompt="#e64980",
    )),
}


# 侧栏 CSS 样式
def sidebar_css(theme: Theme) -> str:
    c = theme.colors
    return f"""
    #sidebar {{ 
        width: 28; 
        background: {c.sidebar}; 
        border-right: solid {c.border}; 
    }}
    """
