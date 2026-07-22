"""
对话系列 — 移植 component/dialog-* 系列全部弹窗
Provider配置、模型选择、MCP管理、命令面板、暂存、技能、标签、主题、徽标、权限相关

使用 Textual ModalScreen / PopScreen 模式，连接到 craft.core 的现有模块。
"""

from __future__ import annotations

from typing import Any, Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Select, Static, TextArea

from craft.core.permission import Rule, evaluate, from_config, forward_ref

# ────────────────────────────────────────────────────────────────
# 基础可复用弹窗工具
# ────────────────────────────────────────────────────────────────


class DialogAlert(ModalScreen[None]):
    """告警弹窗 (移植 ui/dialog-alert.tsx)"""

    def __init__(self, title: str = "", message: str = "", on_confirm: Callable | None = None, **kw):
        super().__init__(**kw)
        self._title = title
        self._message = message
        self._on_confirm = on_confirm

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self._title or '提示'}[/]", id="dlg-title"),
            Static(self._message, id="dlg-message"),
            Horizontal(
                Button("确定", variant="primary", id="confirm-btn"),
                id="dlg-buttons",
            ),
            id="dialog", classes="dialog alert-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if self._on_confirm:
            self._on_confirm()
        self.dismiss()


class DialogConfirm(ModalScreen[bool | None]):
    """确认对话框 (移植 ui/dialog-confirm.tsx)"""

    def __init__(self, title: str = "", message: str = "",
                 confirm_label: str = "确认", cancel_label: str = "取消",
                 on_confirm: Callable | None = None, on_cancel: Callable | None = None,
                 **kw):
        super().__init__(**kw)
        self._title = title
        self._message = message
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self._title or '确认'}[/]", id="dlg-title"),
            Static(self._message, id="dlg-message"),
            Horizontal(
                Button(self._cancel_label, id="cancel-btn"),
                Button(self._confirm_label, variant="primary", id="confirm-btn"),
                id="dlg-buttons",
            ),
            id="dialog", classes="dialog confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            if self._on_confirm:
                self._on_confirm()
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            if self._on_cancel:
                self._on_cancel()
            self.dismiss(False)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            self.dismiss(True)


class DialogPrompt(ModalScreen[str | None]):
    """输入提示框 (移植 ui/dialog-prompt.tsx)"""

    def __init__(self, title: str = "", placeholder: str = "",
                 value: str = "", description: str = "",
                 busy: bool = False, busy_text: str = "",
                 on_confirm: Callable[[str], None] | None = None,
                 on_cancel: Callable | None = None,
                 **kw):
        super().__init__(**kw)
        self._title = title
        self._placeholder = placeholder
        self._value = value
        self._description = description
        self._busy = busy
        self._busy_text = busy_text
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self._title or '输入'}[/]", id="dlg-title"),
            Static(self._description, id="dlg-desc") if self._description else Label(""),
            Input(value=self._value, placeholder=self._placeholder, id="prompt-input"),
            Horizontal(
                Button("取消", id="cancel-btn"),
                Button("确定", variant="primary", id="confirm-btn"),
                id="dlg-buttons",
            ),
            id="dialog", classes="dialog prompt-dialog",
        )

    def on_input_submitted(self, event: Input.Submitted):
        if self._on_confirm:
            self._on_confirm(event.value)
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            val = self.query_one("#prompt-input", Input).value
            if self._on_confirm:
                self._on_confirm(val)
            self.dismiss(val)
        elif event.button.id == "cancel-btn":
            if self._on_cancel:
                self._on_cancel()
            self.dismiss(None)


class DialogSelect(ModalScreen[Any]):
    """通用选择对话框 (移植 ui/dialog-select.tsx 简化版)"""

    def __init__(self, title: str = "", options: list[tuple[str, Any, str | None]] | None = None,
                 placeholder: str = "搜索...", on_select: Callable[[Any], None] | None = None,
                 **kw):
        super().__init__(**kw)
        self._title = title
        self._options = options or []
        self._placeholder = placeholder
        self._on_select = on_select

    def compose(self):
        opts = [ListItem(Label(f"  {t}"), id=f"opt_{i}") for i, (t, v, d) in enumerate(self._options)]
        yield Vertical(
            Label(f"[bold]{self._title}[/]", id="dlg-title"),
            Input(placeholder=self._placeholder, id="sel-filter"),
            ListView(*opts, id="sel-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog select-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1])
            _title, value, _desc = self._options[idx]
            if self._on_select:
                self._on_select(value)
            self.dismiss(value)

    def on_input_changed(self, event: Input.Changed):
        query = event.value.lower()
        lst = self.query_one("#sel-list", ListView)
        for i, (t, v, d) in enumerate(self._options):
            w = lst.query_one(f"#opt_{i}", ListItem)
            if query in t.lower() or (d and query in d.lower()):
                w.display = True
            else:
                w.display = False

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


# ────────────────────────────────────────────────────────────────
# Provider / 提供商
# ────────────────────────────────────────────────────────────────


class ProviderDialog(ModalScreen[dict | None]):
    """提供商配置对话框 (移植 dialog-provider.tsx)"""

    def compose(self):
        yield Vertical(
            Label("[bold]🔌 提供商配置[/]", id="dlg-title"),
            Label("提供商:"),
            Select([("OpenAI", "openai"), ("Anthropic", "anthropic"),
                    ("Ollama", "ollama"), ("OpenCode", "opencode"),
                    ("OpenCode Go", "opencode-go")], id="sel-provider"),
            Label("API Key:"), Input(placeholder="sk-...", id="inp-key", password=True),
            Label("Base URL:"), Input(placeholder="https://api.openai.com/v1", id="inp-url"),
            Horizontal(
                Button("✅ 保存", variant="primary", id="save-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            self.dismiss({
                "provider": self.query_one("#sel-provider", Select).value,
                "api_key": self.query_one("#inp-key", Input).value,
                "base_url": self.query_one("#inp-url", Input).value,
            })
        else:
            self.dismiss(None)


class ModelDialog(ModalScreen[str | None]):
    """模型选择对话框 (移植 dialog-model.tsx)"""

    def __init__(self, models: list[str] | None = None, provider_id: str | None = None, **kw):
        super().__init__(**kw)
        self._provider_id = provider_id
        self._models = models or ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4",
                                  "claude-opus-4-6", "llama3", "deepseek-v3",
                                  "mimo-auto", "mimo-v2.5-pro"]

    def compose(self):
        provider_label = f" — {self._provider_id}" if self._provider_id else ""
        yield Vertical(
            Label(f"[bold]🤖 选择模型{provider_label}[/]", id="dlg-title"),
            Input(placeholder="搜索模型...", id="model-filter"),
            ListView(*[ListItem(Label(f"  {m}")) for m in self._models], id="model-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog model-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            label = str(event.item.children[0].renderable) if event.item.children else ""
            self.dismiss(label.strip())

    def on_input_changed(self, event: Input.Changed):
        query = event.value.lower()
        lst = self.query_one("#model-list", ListView)
        for child in lst.children:
            child.display = query in str(child.renderable).lower() if isinstance(child, ListItem) else True

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class CommandPalette(ModalScreen[str | None]):
    """命令面板 (移植 dialog-command.tsx)"""

    def compose(self):
        yield Vertical(
            Label("[bold]⌨️ 命令面板[/]", id="dlg-title"),
            Input(placeholder="输入命令...", id="cmd-input"),
            ListView(
                ListItem(Label("  /help    查看帮助")),
                ListItem(Label("  /new     新建对话")),
                ListItem(Label("  /tools   工具列表")),
                ListItem(Label("  /clear   清屏")),
                ListItem(Label("  /diff    查看代码变更")),
                ListItem(Label("  /memory  记忆管理")),
                ListItem(Label("  /model   切换模型")),
                ListItem(Label("  /agent   切换Agent")),
                ListItem(Label("  /theme   切换主题")),
                ListItem(Label("  /exit    退出")),
                id="cmd-list",
            ),
            id="dialog", classes="dialog cmd-dialog",
        )

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            self.dismiss(str(event.item.children[0].renderable).split()[0].strip())


class StashDialog(ModalScreen[dict | None]):
    """暂存管理 (移植 dialog-stash.tsx)"""

    def __init__(self, stashes: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._stashes = stashes or []

    def compose(self):
        items = self._stashes or []
        yield Vertical(
            Label("[bold]📦 暂存管理[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {s.get('name','?')[:50]}")) for s in items], id="stash-list") if items else Static("  (无暂存内容)", classes="sidebar-item"),
            Horizontal(
                Button("恢复", variant="primary", id="restore-btn"),
                Button("删除", id="delete-btn"),
                Button("关闭", id="close-btn"),
            ) if items else Horizontal(Button("关闭", id="close-btn")),
            id="dialog", classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "restore-btn":
            lst = self.query_one("#stash-list", ListView)
            if lst.index is not None and lst.index < len(self._stashes):
                self.dismiss({"action": "restore", "item": self._stashes[lst.index]})
        elif event.button.id == "delete-btn":
            lst = self.query_one("#stash-list", ListView)
            if lst.index is not None and lst.index < len(self._stashes):
                self.dismiss({"action": "delete", "item": self._stashes[lst.index]})
        else:
            self.dismiss(None)


class SkillDialog(ModalScreen[str | None]):
    """技能选择 (移植 component/dialog-skill.tsx)"""

    def __init__(self, skills: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._skills = skills or []

    def compose(self):
        items = self._skills or []
        yield Vertical(
            Label("[bold]📚 技能选择[/]", id="dlg-title"),
            Input(placeholder="搜索技能...", id="skill-filter"),
            ListView(*[ListItem(Label(f"  {s.get('name','?')}  — {s.get('description','')[:40]}")) for s in items], id="skill-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog skill-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._skills):
                self.dismiss(self._skills[idx]["name"])
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class McpDialog(ModalScreen[str | None]):
    """MCP 管理对话框 (移植 component/dialog-mcp.tsx)"""

    def __init__(self, mcps: list[dict] | None = None, on_toggle: Callable[[str], None] | None = None, **kw):
        super().__init__(**kw)
        self._mcps = mcps or []
        self._on_toggle = on_toggle

    def compose(self):
        yield Vertical(
            Label("[bold]🔌 MCP 服务管理[/]", id="dlg-title"),
            Input(placeholder="搜索MCP...", id="mcp-filter"),
            ListView(*[ListItem(Label(f"  {m.get('name','?')}  [{'✓' if m.get('enabled') else '○'}]")) for m in self._mcps], id="mcp-list"),
            Horizontal(
                Button("启用/禁用", id="toggle-btn"),
                Button("关闭", id="close-btn"),
            ),
            id="dialog", classes="dialog mcp-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._mcps) and self._on_toggle:
                self._on_toggle(self._mcps[idx]["name"])
                # Re-compose to update state — in a real app use reactive patching
                self.dismiss(None)
            else:
                self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "toggle-btn":
            lst = self.query_one("#mcp-list", ListView)
            if lst.index is not None and lst.index < len(self._mcps) and self._on_toggle:
                self._on_toggle(self._mcps[lst.index]["name"])
        self.dismiss(None)


class AgentDialog(ModalScreen[str | None]):
    """Agent 选择 (移植 component/dialog-agent.tsx)"""

    def __init__(self, agents: list[dict] | None = None, current: str = "", **kw):
        super().__init__(**kw)
        self._agents = agents or [{"name": "build", "description": "开发者"},
                                  {"name": "plan", "description": "分析师"},
                                  {"name": "explore", "description": "研究员"}]
        self._current = current

    def compose(self):
        yield Vertical(
            Label("[bold]🤖 Agent 选择[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {'●' if a['name']==self._current else '○'} {a['name']}  — {a.get('description','')}")) for a in self._agents], id="agent-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog agent-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._agents):
                self.dismiss(self._agents[idx]["name"])
            else:
                self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class ThemeListDialog(ModalScreen[str | None]):
    """主题列表 (移植 component/dialog-theme-list.tsx)"""

    def __init__(self, themes: list[str] | None = None, current: str = "",
                 on_move: Callable[[str], None] | None = None, **kw):
        super().__init__(**kw)
        self._themes = themes or ["tokyo-night", "dracula", "monokai", "one-dark", "light"]
        self._current = current
        self._on_move = on_move
        self._confirmed = False

    def compose(self):
        yield Vertical(
            Label("[bold]🎨 主题选择[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {'●' if t==self._current else '○'} {t}")) for t in self._themes], id="theme-list"),
            Horizontal(
                Button("应用", variant="primary", id="apply-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog theme-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._themes):
                val = self._themes[idx]
                if self._on_move:
                    self._on_move(val)
                self._confirmed = True
                self.dismiss(val)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "apply-btn":
            lst = self.query_one("#theme-list", ListView)
            if lst.index is not None and lst.index < len(self._themes):
                val = self._themes[lst.index]
                self._confirmed = True
                self.dismiss(val)
        else:
            self.dismiss(None)


class VariantDialog(ModalScreen[str | None]):
    """模型变体选择 (移植 component/dialog-variant.tsx)"""

    def __init__(self, variants: list[str] | None = None, current: str = "default", **kw):
        super().__init__(**kw)
        self._variants = variants or ["default"]
        self._current = current

    def compose(self):
        yield Vertical(
            Label("[bold]📌 模型变体选择[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {'●' if v==self._current else '○'} {v}")) for v in self._variants], id="variant-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog variant-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._variants):
                self.dismiss(self._variants[idx])

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class LogoDesignDialog(ModalScreen[str | None]):
    """徽标设计选择 (移植 component/dialog-logo-design.tsx)"""

    def __init__(self, logos: dict[str, str] | None = None, current: str = "thin", **kw):
        super().__init__(**kw)
        self._logos = logos or {"thin": "简约", "bold": "粗体", "retro": "复古", "minimal": "极简"}
        self._current = current

    def compose(self):
        yield Vertical(
            Label("[bold]🖌️ 徽标样式[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {'●' if k==self._current else '○'} {v} ({k})")) for k, v in self._logos.items()], id="logo-list"),
            Horizontal(
                Button("应用", variant="primary", id="apply-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog logo-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._logos):
                self.dismiss(list(self._logos.keys())[idx])

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "apply-btn":
            lst = self.query_one("#logo-list", ListView)
            if lst.index is not None and lst.index < len(self._logos):
                self.dismiss(list(self._logos.keys())[lst.index])
        else:
            self.dismiss(None)


class ImageListDialog(ModalScreen[str | None]):
    """背景图片选择 (移植 component/dialog-image-list.tsx)"""

    def __init__(self, images: list[str] | None = None, current: str | None = None,
                 on_import: Callable | None = None, **kw):
        super().__init__(**kw)
        self._images = images or []
        self._current = current
        self._on_import = on_import

    def compose(self):
        items = [ListItem(Label("  📥 导入图片"), id="opt_import")]
        for i, img in enumerate(self._images):
            items.append(ListItem(Label(f"  {'●' if img==self._current else '○'} {img}"), id=f"opt_{i}"))
        items.append(ListItem(Label("  ❌ 无背景"), id="opt_none"))
        yield Vertical(
            Label("[bold]🖼️ 背景图片[/]", id="dlg-title"),
            ListView(*items, id="image-list"),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog image-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            if event.item.id == "opt_import":
                if self._on_import:
                    self._on_import()
                self.dismiss("__import__")
            elif event.item.id == "opt_none":
                self.dismiss(None)
            else:
                idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else -1
                if 0 <= idx < len(self._images):
                    self.dismiss(self._images[idx])

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


class TagDialog(ModalScreen[str | None]):
    """标签/自动补全 (移植 component/dialog-tag.tsx)"""

    def __init__(self, files: list[str] | None = None, **kw):
        super().__init__(**kw)
        self._files = files or []

    def compose(self):
        yield Vertical(
            Label("[bold]🏷️ 自动补全[/]", id="dlg-title"),
            Input(placeholder="输入文件路径...", id="tag-filter"),
            ListView(*[ListItem(Label(f"  {f}")) for f in self._files], id="tag-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog tag-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._files):
                self.dismiss(self._files[idx])
            else:
                self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class TokenPlanDialog(ModalScreen[None]):
    """Token 套餐提示 (移植 component/dialog-token-plan.tsx)"""

    def __init__(self, on_close: Callable | None = None, **kw):
        super().__init__(**kw)
        self._on_close = on_close

    def compose(self):
        yield Vertical(
            Label("[bold]💎 Token 套餐[/]", id="dlg-title"),
            Static("免费模型已达到使用限制。"),
            Static("订阅 MiMo 套餐以获得持续访问。"),
            Static("详情请访问: platform.xiaomimimo.com/token-plan"),
            Horizontal(
                Button("知道了", variant="primary", id="ok-btn", classes="center-btn"),
            ),
            id="dialog", classes="dialog token-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if self._on_close:
            self._on_close()
        self.dismiss()


class ModalitiesDialog(ModalScreen[dict[str, bool] | None]):
    """模型多模态配置 (移植 component/dialog-modalities.tsx)"""

    def __init__(self, model_name: str = "", initial: dict[str, bool] | None = None,
                 on_save: Callable[[dict[str, bool]], None] | None = None, **kw):
        super().__init__(**kw)
        self._model_name = model_name
        self._modalities = initial or {"image": False, "audio": False, "video": False, "pdf": False}
        self._on_save = on_save
        self._active = 0
        self._modality_keys = ["image", "audio", "video", "pdf"]

    def compose(self):
        items = []
        for i, m in enumerate(self._modality_keys):
            checked = self._modalities.get(m, False)
            items.append(ListItem(Label(f"  {'[x]' if checked else '[ ]'} {m}"), id=f"mod_{i}"))
        yield Vertical(
            Label(f"[bold]📎 多模态配置 — {self._model_name}[/]", id="dlg-title"),
            ListView(*items, id="mod-list"),
            Static("  space: 切换  enter: 保存", classes="hint"),
            Horizontal(
                Button("保存", variant="primary", id="save-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog mod-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1])
            key = self._modality_keys[idx]
            self._modalities[key] = not self._modalities.get(key, False)
            # Rebuild list view
            self.dismiss(None)  # Just close on tap; save via button

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            if self._on_save:
                self._on_save(self._modalities)
            self.dismiss(self._modalities)
        else:
            self.dismiss(None)


class AgreementDialog(ModalScreen[bool | None]):
    """用户协议 (移植 component/dialog-agreement.tsx)"""

    def __init__(self, on_confirm: Callable | None = None, **kw):
        super().__init__(**kw)
        self._on_confirm = on_confirm

    def compose(self):
        yield Vertical(
            Label("[bold]📜 用户协议[/]", id="dlg-title"),
            Static("使用前请阅读并同意以下条款："),
            Static("• 用户协议: platform.xiaomimimo.com/docs/terms/user-agreement"),
            Static("• 隐私政策: privacy.mi.com/XiaomiMiMoPlatform"),
            Static(""),
            Static("使用免费模型即表示您同意上述条款。"),
            Horizontal(
                Button("拒绝", id="cancel-btn"),
                Button("同意并继续", variant="primary", id="confirm-btn"),
            ),
            id="dialog", classes="dialog agreement-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            if self._on_confirm:
                self._on_confirm()
            self.dismiss(True)
        else:
            self.dismiss(False)


class MimoLoginDialog(ModalScreen[None]):
    """MiMo 登录流 (移植 component/dialog-mimo-login.tsx)"""

    def compose(self):
        yield Vertical(
            Label("[bold]🔑 MiMo 登录[/]", id="dlg-title"),
            Static("选择登录方式："),
            Select([
                ("小米账号 (推荐)", "xiaomi"),
                ("导入 Claude 配置", "import_claude"),
                ("API Key", "api"),
            ], id="login-method"),
            Horizontal(
                Button("继续", variant="primary", id="continue-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog login-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "continue-btn":
            method = self.query_one("#login-method", Select).value
            if method == "xiaomi":
                self.dismiss()
                # In real app: open OAuth URL
                self.app.push_screen(MimoOAuthDialog())
            elif method == "import_claude":
                self.dismiss()
            else:
                self.dismiss()
        else:
            self.dismiss()


class MimoOAuthDialog(ModalScreen[None]):
    """MiMo OAuth 流程"""

    def compose(self):
        yield Vertical(
            Label("[bold]🔑 MiMo OAuth 授权[/]", id="dlg-title"),
            Static("请在浏览器中完成授权："),
            Static("URL: https://platform.xiaomimimo.com/oauth/authorize"),
            Input(placeholder="或粘贴授权码...", id="oauth-code"),
            Horizontal(
                Button("确认", variant="primary", id="confirm-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog oauth-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss()


class WorktreeDialog(ModalScreen[str | None]):
    """工作区管理 (移植 component/dialog-worktree.tsx)"""

    def __init__(self, worktrees: list[str] | None = None, **kw):
        super().__init__(**kw)
        self._worktrees = worktrees or []

    def compose(self):
        items = [ListItem(Label(f"  {w}")) for w in self._worktrees]
        items.append(ListItem(Label("  ✚ 创建新工作区")))
        yield Vertical(
            Label("[bold]📂 工作区管理[/]", id="dlg-title"),
            ListView(*items, id="worktree-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog worktree-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._worktrees):
                self.dismiss(self._worktrees[idx])
            elif idx == len(self._worktrees):
                self.dismiss("__create__")
            else:
                self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class WorkflowsDialog(ModalScreen[str | None]):
    """工作流运行列表 (移植 component/dialog-workflows.tsx)"""

    def __init__(self, runs: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._runs = runs or []

    def compose(self):
        items = self._runs or []
        yield Vertical(
            Label("[bold]⚡ 工作流运行[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {r.get('name','?')}  {r.get('status','')}  ✓{r.get('succeeded',0)} ✗{r.get('failed',0)}")) for r in items], id="wf-list") if items else Static("  (无工作流运行)"),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog wf-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._runs):
                self.dismiss(self._runs[idx].get("runID", ""))

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


class ConsoleOrgDialog(ModalScreen[str | None]):
    """控制台组织切换 (移植 component/dialog-console-org.tsx)"""

    def __init__(self, orgs: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._orgs = orgs or []

    def compose(self):
        items = self._orgs or []
        yield Vertical(
            Label("[bold]🏢 组织切换[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {'●' if o.get('active') else '○'} {o.get('orgName','?')}")) for o in items], id="org-list") if items else Static("  (加载中...)"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog org-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._orgs):
                self.dismiss(self._orgs[idx].get("orgID", ""))

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


class WorkspaceCreateDialog(ModalScreen[str | None]):
    """创建工作区 (移植 component/dialog-workspace-create.tsx)"""

    def __init__(self, adaptors: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._adaptors = adaptors or []

    def compose(self):
        items = [ListItem(Label(f"  {a.get('name','?')}  — {a.get('description','')}")) for a in self._adaptors]
        yield Vertical(
            Label("[bold]🆕 创建工作区[/]", id="dlg-title"),
            ListView(*items, id="ws-list") if items else Static("  (加载工作区适配器...)"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog ws-create-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._adaptors):
                self.dismiss(self._adaptors[idx].get("type", ""))

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


class WorkspaceUnavailableDialog(ModalScreen[str | None]):
    """工作区不可用 (移植 component/dialog-workspace-unavailable.tsx)"""

    def __init__(self, on_restore: Callable | None = None, **kw):
        super().__init__(**kw)
        self._on_restore = on_restore

    def compose(self):
        yield Vertical(
            Label("[bold]⚠️ 工作区不可用[/]", id="dlg-title"),
            Static("此会话关联的工作区已不再可用。"),
            Static("是否尝试将会话恢复到新的工作区？"),
            Horizontal(
                Button("取消", id="cancel-btn"),
                Button("恢复到新工作区", variant="primary", id="restore-btn"),
            ),
            id="dialog", classes="dialog ws-unavail-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "restore-btn" and self._on_restore:
            self._on_restore()
            self.dismiss("restore")
        else:
            self.dismiss(None)


class SessionDeleteFailedDialog(ModalScreen[str | None]):
    """删除会话失败 (移植 component/dialog-session-delete-failed.tsx)"""

    def __init__(self, session_title: str = "", workspace: str = "",
                 on_delete: Callable | None = None, on_restore: Callable | None = None,
                 on_done: Callable | None = None, **kw):
        super().__init__(**kw)
        self._session_title = session_title
        self._workspace = workspace
        self._on_delete = on_delete
        self._on_restore = on_restore
        self._on_done = on_done

    def compose(self):
        yield Vertical(
            Label("[bold]❌ 删除会话失败[/]", id="dlg-title"),
            Static(f'会话 "{self._session_title}" 无法删除，因为工作区 "{self._workspace}" 不可用。'),
            Static("选择恢复方式："),
            ListView(
                ListItem(Label("  删除工作区 — 删除工作区及其所有会话")),
                ListItem(Label("  恢复到新工作区 — 尝试将会话恢复到新工作区")),
                id="recover-list",
            ),
            Horizontal(
                Button("执行", variant="primary", id="exec-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog failed-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "exec-btn":
            lst = self.query_one("#recover-list", ListView)
            if lst.index == 0 and self._on_delete:
                self._on_delete()
                self.dismiss("delete")
            elif lst.index == 1 and self._on_restore:
                self._on_restore()
                self.dismiss("restore")
            else:
                self.dismiss(None)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
        if self._on_done:
            self._on_done()


class GoUpsellDialog(ModalScreen[bool]):
    """Go 订阅推销 (移植 component/dialog-go-upsell.tsx)"""

    def __init__(self, on_close: Callable[[bool], None] | None = None, **kw):
        super().__init__(**kw)
        self._on_close = on_close

    def compose(self):
        yield Vertical(
            Label("[bold]🚀 免费额度已用完[/]", id="dlg-title"),
            Static("订阅 OpenCode Go 以获得持续访问最优秀的开源模型。"),
            Static("起价 $5/月。"),
            Static(""),
            Static("详情: https://opencode.ai/go"),
            Horizontal(
                Button("不再显示", id="dismiss-btn"),
                Button("💎 订阅", variant="primary", id="subscribe-btn"),
            ),
            id="dialog", classes="dialog upsell-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "subscribe-btn":
            if self._on_close:
                self._on_close(False)
            self.dismiss(True)
        elif event.button.id == "dismiss-btn":
            if self._on_close:
                self._on_close(True)
            self.dismiss(False)
        else:
            self.dismiss(False)


class StatusDialog(ModalScreen[None]):
    """状态面板 (移植 component/dialog-status.tsx)"""

    def __init__(self, mcps: list[dict] | None = None, lsps: list[dict] | None = None,
                 formatters: list[dict] | None = None, plugins: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._mcps = mcps or []
        self._lsps = lsps or []
        self._formatters = formatters or []
        self._plugins = plugins or []

    def compose(self):
        mcp_count = len([m for m in self._mcps if m.get("status") == "connected"])
        yield Vertical(
            Label("[bold]📊 状态面板[/]", id="dlg-title"),
            Static(f"[green]●[/] {len(self._mcps)} MCP 服务器 ({mcp_count} 已连接)"),
            Static(f"[green]●[/] {len(self._lsps)} LSP 服务器"),
            Static(f"[green]●[/] {len(self._formatters)} 格式化工具"),
            Static(f"[green]●[/] {len(self._plugins)} 插件"),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog status-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss()


class WorkflowDialog(ModalScreen[dict | None]):
    """工作流选择/创建 (移植 routes/session/dialog-workflow.tsx)"""

    def __init__(self, workflows: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._workflows = workflows or []

    def compose(self):
        items = [ListItem(Label(f"  {w.get('name','?')}  ({w.get('steps',0)} 步)")) for w in self._workflows]
        yield Vertical(
            Label("[bold]⚙️ 工作流[/]", id="dlg-title"),
            ListView(*items, id="wf2-list") if items else Static("  (无可用工作流)"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog workflow-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._workflows):
                self.dismiss(self._workflows[idx])

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


# ────────────────────────────────────────────────────────────────
# CSS
# ────────────────────────────────────────────────────────────────

DIALOGS_CSS = """
.alert-dialog { height: 9; }
.confirm-dialog { height: 10; }
.prompt-dialog { height: 12; }
.select-dialog { height: 18; }
.model-dialog { height: 16; }
.cmd-dialog { height: 14; }
.skill-dialog { height: 16; }
.mcp-dialog { height: 16; }
.agent-dialog { height: 14; }
.theme-dialog { height: 14; }
.variant-dialog { height: 12; }
.logo-dialog { height: 12; }
.image-dialog { height: 14; }
.tag-dialog { height: 14; }
.token-dialog { height: 10; }
.mod-dialog { height: 14; }
.agreement-dialog { height: 12; }
.login-dialog { height: 12; }
.oauth-dialog { height: 10; }
.worktree-dialog { height: 14; }
.wf-dialog { height: 14; }
.org-dialog { height: 14; }
.ws-create-dialog { height: 14; }
.ws-unavail-dialog { height: 10; }
.failed-dialog { height: 14; }
.upsell-dialog { height: 12; }
.status-dialog { height: 12; }
.workflow-dialog { height: 14; }
#model-list { height: 10; }
#cmd-list { height: 8; }
#cmd-input { margin: 0; }
#sel-list { height: 10; }
#skill-list { height: 10; }
#mcp-list { height: 10; }
#theme-list { height: 10; }
#agent-list { height: 8; }
#worktree-list { height: 8; }
#wf-list { height: 8; }
#mod-list { height: 8; }
#wf2-list { height: 8; }
#org-list { height: 8; }
#ws-list { height: 8; }
#recover-list { height: 6; }
#image-list { height: 8; }
#tag-list { height: 8; }
#variant-list { height: 8; }
#logo-list { height: 8; }
.hint { color: #565f89; padding: 0 2; }
.center-btn { align: center middle; }
"""
