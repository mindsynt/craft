"""
剩余组件汇总 — 移植 ui/home/, routes/session/dialog*, routes/home.tsx, config/
7+ 框架级组件：首页提示、问题面板、配置面板、插件面板、TUI 配置、
加载动画、错误显示、语言/主题选择
"""

from __future__ import annotations

from typing import Any, Callable

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, ListView, ListItem, Select, TextArea


# ─── 首页提示 (移植 ui/home/tips.tsx + tips-view.tsx) ─

class TipsWidget(Vertical):
    """首页提示列表"""

    def compose(self):
        yield Label("提示", classes="sidebar-title")
        tips = [
            "Tab 键自动补全命令",
            "↑↓ 键浏览输入历史",
            "/help 查看全部命令",
            "/diff 查看代码变更",
            "/memory add 保存重要信息",
            "/model 切换模型",
            "/agent 切换 Agent",
            "双击消息弹出操作菜单",
        ]
        for t in tips:
            yield Static(f"  {t}", classes="sidebar-item")


# ─── 问题面板 (移植 routes/session/question.tsx) ──

class QuestionPanel(Vertical):
    """会话问题面板 — 显示当前问题和回答"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._title = Static("问题", classes="sidebar-title")
        self._question = Static("  等待提问...", classes="sidebar-item", id="qtext")
        self._answer = Static("", classes="sidebar-item", id="atext")

    def compose(self):
        yield self._title
        yield self._question
        yield self._answer

    def show(self, question: str):
        self._question.update(f"[yellow]❓ {question}[/]")
        self._answer.update("")

    def answer(self, text: str):
        self._answer.update(f"[green]  {text}[/]")

    def clear(self):
        self._question.update("  等待提问...")
        self._answer.update("")


# ─── 加载动画 (移植 component/spinner.tsx) ──

class SpinnerWidget(Static):
    """文本加载动画"""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = "加载中...", color: str = "blue", **kw):
        super().__init__(**kw)
        self._text = text
        self._color = color
        self._frame = 0
        self._timer = None

    def on_mount(self):
        self._update()

    def _update(self):
        self.update(f"[{self._color}]{self._FRAMES[self._frame % len(self._FRAMES)]}[/] {self._text}")
        self._frame += 1
        self.set_timer(0.1, self._update)


# ─── 错误显示 (移植 component/error-component.tsx) ──

class ErrorComponent(Static):
    """错误信息显示组件"""

    def __init__(self, message: str = "", details: str = "", **kw):
        super().__init__(**kw)
        self._message = message
        self._details = details

    def compose(self):
        yield Label(f"[red]✗ 错误: {self._message}[/]", id="err-title")
        if self._details:
            yield Static(self._details, id="err-details", classes="error-details")
        yield Button("关闭", id="dismiss-btn", classes="error-dismiss")

    def on_button_pressed(self, event):
        if event.button.id == "dismiss-btn":
            self.remove()

    def set_error(self, message: str, details: str = ""):
        self._message = message
        self._details = details
        self.refresh()


# ─── 边界线 (移植 component/border.tsx) ──

class SplitBorder(Horizontal):
    """分割线组件"""

    def __init__(self, label: str = "", char: str = "─", **kw):
        super().__init__(**kw)
        self._label = label
        self._char = char

    def compose(self):
        if self._label:
            yield Label(f" {self._label} ", classes="border-label")
        yield Label(self._char * 50, classes="border-line")


# ─── 任务项 (移植 component/task-item.tsx) ──

class TaskItem(Horizontal):
    """任务项 — 显示待办事项的状态和内容"""

    STATUS_ICONS = {
        "pending": "○",
        "in_progress": "⟳",
        "completed": "✓",
        "failed": "✗",
        "cancelled": "−",
    }

    def __init__(self, task_id: str = "", content: str = "",
                 status: str = "pending", **kw):
        super().__init__(**kw)
        self._task_id = task_id
        self._content = content
        self._status = status

    def compose(self):
        icon = self.STATUS_ICONS.get(self._status, "○")
        color = {
            "pending": "dim",
            "in_progress": "yellow",
            "completed": "green",
            "failed": "red",
            "cancelled": "dim",
        }.get(self._status, "dim")
        yield Label(f"[{color}]{icon}[/] {self._content}", classes="task-item")


# ─── 待办事项 (移植 component/todo-item.tsx) ──

class TodoItem(Horizontal):
    """待办事项 — 可切换状态的待办项"""

    def __init__(self, content: str = "", done: bool = False,
                 on_toggle: Callable | None = None, **kw):
        super().__init__(**kw)
        self._content = content
        self._done = done
        self._on_toggle = on_toggle

    def compose(self):
        cb = "[x]" if self._done else "[ ]"
        yield Label(f"  {cb} {self._content}", classes="todo-item", id="todo-label")

    async def on_click(self):
        self._done = not self._done
        if self._on_toggle:
            self._on_toggle(self._done)
        label = self.query_one("#todo-label", Label)
        cb = "[x]" if self._done else "[ ]"
        label.update(f"  {cb} {self._content}")


# ─── 背景脉冲动画 (移植 component/bg-pulse.tsx) ──

class BgPulse(Static):
    """背景脉冲动画 — 简单的呼吸/脉冲效果"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._visible = True
        self._timer = None

    def on_mount(self):
        self._pulse()

    def _pulse(self):
        self._visible = not self._visible
        self.styles.opacity = 0.3 if self._visible else 0.6
        self.set_timer(1.5, self._pulse)


# ─── 背景图片 (移植 component/background-image.tsx) ──

class BackgroundImage(Static):
    """背景图片占位组件"""

    def __init__(self, image_name: str | None = None, **kw):
        super().__init__(**kw)
        self._image_name = image_name

    def compose(self):
        if self._image_name:
            self.styles.content = self._image_name


# ─── Logo 显示 (移植 component/logo.tsx) ──

class LogoWidget(Static):
    """Craft 徽标显示"""

    def __init__(self, design: str = "default", **kw):
        super().__init__(**kw)
        self._design = design

    def compose(self):
        logo = {
            "default": "[bold blue]Craft[/]",
            "thin": "[blue]Craft[/]",
            "bold": "[bold bright_blue]CRAFT[/]",
            "retro": "[green]C̷r̷a̷f̷t̷[/]",
            "minimal": "[dim]craft[/]",
        }.get(self._design, "[blue]Craft[/]")
        yield Label(logo, classes="logo")


# ─── 星夜空背景 (移植 component/starry-background.tsx) ──

class StarryBackground(Static):
    """星空背景装饰"""

    def compose(self):
        # Simple dots pattern
        stars = "  ·   ·    ·     ·   ·    ·   ·   ·  " * 2
        yield Label(f"[dim]{stars}[/]", classes="stars")


# ─── 启动加载 (移植 component/startup-loading.tsx) ──

class StartupLoading(Vertical):
    """启动加载界面"""

    def __init__(self, message: str = "正在加载 Craft...", **kw):
        super().__init__(**kw)
        self._message = message
        self._version = ""
        try:
            from craft import __version__
            self._version = __version__
        except ImportError:
            pass

    def compose(self):
        yield Vertical(
            Label("[bold blue]Craft AI 助手[/]", id="startup-logo"),
            Label(f"v{self._version}" if self._version else "", id="startup-version"),
            SpinnerWidget(text=self._message, id="startup-spinner"),
            id="startup-container", classes="startup-container",
        )


# ─── 插件缺失指示 (移植 component/plugin-route-missing.tsx) ──

class PluginRouteMissing(Static):
    """插件路由缺失提示"""

    def __init__(self, route: str = "", **kw):
        super().__init__(**kw)
        self._route = route

    def compose(self):
        yield Label(f"[yellow]⚠ 插件路由缺失: {self._route}[/]")
        yield Static("请确保相关插件已安装并启用。", classes="sidebar-item")


# ─── TUI 配置面板 (移植 config/tui.ts) ──

class TUIConfigPanel(VerticalScroll):
    """TUI 配置面板 — 主题、语言、侧栏宽度"""

    def __init__(self, on_theme_change: Callable[[str], None] | None = None, **kw):
        super().__init__(**kw)
        self._on_theme_change = on_theme_change

    def compose(self):
        yield Label("[bold]TUI 配置[/]", classes="panel-title")
        yield Label("主题:")
        yield Select([(t, t) for t in ["tokyo-night", "dracula", "monokai",
                                       "one-dark", "light", "catppuccino"]],
                     value="tokyo-night", id="sel-theme")
        yield Label("语言:")
        yield Select([("中文", "zh"), ("English", "en"), ("日本語", "ja"),
                      ("Français", "fr"), ("Русский", "ru")],
                     value="zh", id="sel-lang")
        yield Label("侧栏宽度:")
        yield Select([("窄 (20)", "20"), ("中 (28)", "28"), ("宽 (36)", "36")],
                     value="28", id="sel-sidebar")
        yield Label("字体大小:")
        yield Select([("小", "small"), ("中", "medium"), ("大", "large")],
                     value="medium", id="sel-font")
        yield Static("  Craft v0.1.0 — MiMo-Code Python Port", classes="sidebar-item")
        yield Button("应用设置", variant="primary", id="apply-config")

    def on_select_changed(self, event: Select.Changed):
        if event.select.id == "sel-theme" and self._on_theme_change:
            self._on_theme_change(str(event.value))


# ─── 插件管理面板 (移植 ui/system/plugins.tsx) ──

class PluginPanel(VerticalScroll):
    """插件管理面板 — 显示已安装插件列表"""

    def compose(self):
        yield Label("[bold]插件管理[/]", classes="panel-title")
        try:
            from craft.core.plugin import plugin_manager
            plugins = plugin_manager.list()
            if plugins:
                for p in plugins:
                    name = p.get("name", p.get("id", "?"))
                    version = p.get("version", "")
                    desc = p.get("description", "")
                    enabled = p.get("enabled", False)
                    status = "[green]✓[/]" if enabled else "[dim]○[/]"
                    yield Static(f"  {status} [cyan]{name}[/] v{version}", classes="sidebar-item")
                    if desc:
                        yield Static(f"    {desc}", classes="sidebar-item")
            else:
                yield Static("  (无已安装插件)", classes="sidebar-item")
                yield Static("  使用 /plugin install <name> 安装", classes="sidebar-item")
        except ImportError:
            yield Static("  (插件系统不可用)", classes="sidebar-item")


# ─── 侧栏 (移植 routes/session/sidebar.tsx) ──

class Sidebar(Vertical):
    """侧栏面板 — 整合各种侧栏组件"""

    def compose(self):
        yield Label("[bold]Craft[/]", classes="panel-title")
        yield Label("  AI 编程助手", classes="sidebar-item")
        yield Label("", classes="sidebar-item")
        # Quick stats
        try:
            from craft.core.session import sessions
            all_sessions = sessions.list(100)
            yield Label(f"  会话: {len(all_sessions)}", classes="sidebar-item")
        except Exception:
            pass
        try:
            from craft.core.metrics import metrics
            m = metrics.summary() if hasattr(metrics, 'summary') else {}
            if m:
                for name, count in list(m.items())[:3]:
                    yield Static(f"  {name}: {int(count)}", classes="sidebar-item")
        except Exception:
            pass
        yield Label("", classes="sidebar-item")
        # Plugin slots
        from craft.tui.plugin_system import HomeSlot, SidebarSlot, SystemSlot
        yield HomeSlot()
        yield SidebarSlot()
        yield SystemSlot()


# ─── CSS ─────────────────────────────────────────────

REMAINING_CSS = """
#timeline-list { height: 10; }
#session-list-view { height: 12; }
#subagent-task { height: 5; }
.error-details { color: #565f89; padding: 0 2; }
.error-dismiss { margin: 1 2; max-width: 10; }
.border-label { color: #565f89; padding: 0 1; }
.border-line { color: #3b4261; }
.task-item { padding: 0 1; }
.todo-item { padding: 0 1; }
.logo { padding: 0 1; text-style: bold; }
.stars { color: #3b4261; padding: 0 1; }
.startup-container { align: center middle; height: 100%; }
#startup-logo { text-style: bold; color: #7dcfff; padding: 0 2; }
#startup-version { color: #565f89; padding: 0 2; }
#startup-spinner { padding: 1 2; }
#sel-theme, #sel-lang, #sel-sidebar, #sel-font { margin: 0 2; }
"""
