"""
主对话视图 — 集成 PromptBar
"""

from __future__ import annotations

import os
import subprocess

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, RichLog, Static, Label

from craft import __version__
from craft.core.agent import agents
from craft.core.provider import get_provider, ProviderError
from craft.core.memory import memory
from craft.core.session import sessions, Session
from craft.core.tools import registry as tool_registry
from craft.core.task import tasks as task_mgr
from craft.tui.prompt import PromptInput


class SidePanel(Vertical):
    pass


class SessionScreen(Screen):
    BINDINGS = [
        ("escape", "focus_input", "聚焦输入"),
        ("f5", "new_session", "新建对话"),
        ("ctrl+d", "toggle_sidebar", "侧栏"),
        ("ctrl+p", "show_prompt", "命令面板"),
        ("tab", "complete", "自动补全"),
        ("up", "history_prev", "上一条"),
        ("down", "history_next", "下一条"),
    ]

    def __init__(self):
        super().__init__()
        self._session: Session | None = None
        self._messages: list[dict] = []
        self._current_agent = "build"
        self._current_model = "gpt-4o"
        self.sidebar_visible = True

    def compose(self):
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar", classes="sidebar") as self._sidebar:
                yield Static(f"[bold blue]Craft[/] v{__version__}", classes="sidebar-title")
                yield Label("Agent", classes="sidebar-title")
                for aid, info in agents.list():
                    yield Static(f"  {aid}", classes="sidebar-item")
                yield Label("会话", classes="sidebar-title")
                self._session_info = Static("  无活跃会话", classes="sidebar-item")
                yield self._session_info
                yield Label("文件", classes="sidebar-title")
                yield Static("  (cd /file)", classes="sidebar-item")

            with Vertical(id="main-area"):
                with Horizontal(id="toolbar", classes="border"):
                    yield Static("[bold]对话[/]", classes="panel-title")
                    yield Static(f"[dim]  {self._current_agent} | {self._current_model}[/]", classes="status")
                self._chat_log = RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                yield self._chat_log
                with Horizontal(id="input-row", classes="border"):
                    yield Static("[bold blue]>>[/]", id="prompt-indicator")
                    self._input = PromptInput(placeholder="输入消息... (Enter发送  Tab补全  ↑↓历史)", id="chat-input")
                    yield self._input
                    yield Static(f"[dim]{self._current_agent} | {self._current_model}[/]", id="prompt-label")
        yield Footer()

    def on_mount(self):
        self._chat_log.write("[bold blue]Craft — AI 编程助手[/]")
        self._chat_log.write("[dim]欢迎使用！输入 /help 查看命令[/]")
        self._chat_log.write("─" * 50)
        self._session = sessions.create()
        self._input.focus()

    async def action_focus_input(self):
        self._input.focus()

    def action_new_session(self):
        self._session = sessions.create()
        self._messages = []
        self._chat_log.clear()
        self._chat_log.write("[bold]新建对话[/]")
        self._session_info.update("  0 条消息")
        self._input.focus()

    def action_toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self.query_one("#sidebar").styles.width = 28 if self.sidebar_visible else 0

    def action_show_prompt(self):
        self._input.focus()
        self._input.value = "/"
        self._input.cursor_position = 1

    async def action_complete(self):
        await self._input.complete()
        self._input.focus()

    async def action_history_prev(self):
        val = self._input.history.prev()
        if val is not None:
            self._input.value = val
            self._input.cursor_position = len(val)

    async def action_history_next(self):
        val = self._input.history.next()
        if val is not None:
            self._input.value = val
            self._input.cursor_position = len(val)

    async def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        self._input.value = ""
        self._input.disabled = True
        if text.startswith("/"):
            await self._handle_command(text)
            self._input.disabled = False
            self._input.focus()
            return
        if not self._session:
            self._session = sessions.create()
        self._chat_log.write(f"\n[bold blue]你[/]: {text}")
        self._messages.append({"role": "user", "content": text})
        self._session.add_message("user", text)
        self._session_info.update(f"  {len(self._messages)} 条消息")
        self._stream(text)

    @work
    async def _stream(self, text: str):
        try:
            llm = get_provider(model=self._current_model)
            agent = agents.get(self._current_agent)
            msgs = [{"role": "system", "content": agent.prompt}] + self._messages
            self._chat_log.write(f"\n[bold green]{agent.name}[/]: ")
            full = ""
            async for chunk in llm.chat_stream(messages=msgs):
                if chunk.get("type") == "content":
                    full += chunk["content"]
                    self._chat_log.write(chunk["content"])
                elif chunk.get("type") == "error":
                    self._chat_log.write(f"\n[red]✗ {chunk['message']}[/]")
            self._messages.append({"role": "assistant", "content": full})
            if self._session:
                self._session.add_message("assistant", full)
        except ProviderError as e:
            self._chat_log.write(f"\n[red]✗ 提供商错误: {e}[/]")
        except Exception as e:
            self._chat_log.write(f"\n[red]✗ {e}[/]")
        finally:
            self._chat_log.write("")
            self._input.disabled = False
            self._input.focus()

    async def _handle_command(self, text: str):
        cmd = text.split()[0].lower()
        args = text[len(cmd):].strip()
        if cmd in ("/exit", "/quit"):
            self.app.exit()
        elif cmd == "/help":
            self._chat_log.write("[bold]命令列表[/]:")
            cmds = [
                ("/agent <id>", "切换Agent"),
                ("/model <m>", "切换模型"),
                ("/diff", "查看Git变更"),
                ("/commit <msg>", "Git提交"),
                ("/tools", "列出工具"),
                ("/session", "会话信息"),
                ("/memory add|search", "记忆管理"),
                ("/skill", "技能列表"),
                ("/task", "任务列表"),
                ("/file <path>", "文件浏览"),
                ("/mcp", "MCP状态"),
                ("/account", "账户管理"),
                ("/workspace", "工作区管理"),
                ("/theme", "主题切换"),
                ("/plugin", "插件管理"),
                ("/new", "新建对话"),
                ("/clear", "清屏"),
                ("/exit", "退出"),
            ]
            for c, d in cmds:
                self._chat_log.write(f"  {c:20s} {d}")
        elif cmd == "/agent" and args:
            a = agents.get(args)
            if a:
                self._current_agent = args
                self._chat_log.write(f"[green]已切换: {a.name}[/]")
            else:
                self._chat_log.write(f"[yellow]可用: {', '.join(a[0] for a in agents.list())}[/]")
        elif cmd == "/model" and args:
            self._current_model = args
            self._chat_log.write(f"[green]模型: {args}[/]")
        elif cmd == "/diff":
            try:
                r = subprocess.run(["git","diff","--stat"], capture_output=True,text=True,timeout=10)
                self._chat_log.write(r.stdout or "[green]无变更[/]")
            except:
                self._chat_log.write("[yellow]不是Git仓库[/]")
        elif cmd.startswith("/commit"):
            msg = args or "update"
            try:
                subprocess.run(["git","add","-A"], capture_output=True,timeout=10)
                r = subprocess.run(["git","commit","-m",msg], capture_output=True,text=True,timeout=10)
                self._chat_log.write(f"[green]{r.stdout.strip() or r.stderr.strip()}[/]")
            except:
                self._chat_log.write("[yellow]不是Git仓库[/]")
        elif cmd == "/tools":
            for t in tool_registry.list():
                self._chat_log.write(f"  [cyan]{t.name}[/] - {t.description[:50]}")
        elif cmd == "/session":
            self._chat_log.write(f"[bold]会话[/]: {self._session.id[:16] if self._session else 'N/A'}")
            self._chat_log.write(f"  消息数: {len(self._messages)}")
        elif cmd == "/clear":
            self._chat_log.clear()
        elif cmd == "/new":
            self.action_new_session()
        elif cmd.startswith("/memory"):
            if args.startswith("add "):
                mid = memory.add(content=args[4:])
                self._chat_log.write(f"[green]✓ 已添加: {mid[:12]}...[/]")
            elif args.startswith("search "):
                results = memory.search(args[7:])
                self._chat_log.write(f"找到 {len(results)} 条:")
                for r in results:
                    self._chat_log.write(f"  [{r['type']}] {r['snippet'][:80]}")
        elif cmd == "/file":
            self._chat_log.write("[bold]文件[/]:")
            path = args or "."
            try:
                for e in sorted(os.listdir(path))[:20]:
                    icon = "📁" if os.path.isdir(os.path.join(path,e)) else "📄"
                    self._chat_log.write(f"  {icon} {e}")
            except Exception as e:
                self._chat_log.write(f"[red]{e}[/]")
        elif cmd == "/mcp":
            from craft.core.mcp_protocol import mcp_manager
            self._chat_log.write("[bold]MCP[/]:")
            for s in mcp_manager.list():
                self._chat_log.write(f"  {'●' if s.get('connected') else '○'} {s['name']}")
        elif cmd == "/skill":
            from craft.core.skill import skills
            self._chat_log.write("[bold]技能[/]:")
            for s in skills.list():
                self._chat_log.write(f"  [cyan]{s['name']}[/] v{s['version']} - {s['description'][:40]}")
        elif cmd == "/task":
            for t in task_mgr.list():
                icon = {"pending":"⏳","running":"🔄","completed":"✅","failed":"❌"}.get(t["status"],"📋")
                self._chat_log.write(f"  {icon} {t['title'][:40]}")
        elif cmd == "/account":
            from craft.core.account import accounts
            sub = args.split()[0] if args else "list"
            if sub == "list":
                for a in accounts.list():
                    self._chat_log.write(f"  {a.name} ({a.email})")
            elif sub == "create" and len(args.split()) > 1:
                a = accounts.create(args.split()[1])
                self._chat_log.write(f"[green]已创建: {a.id[:12]}[/]")
        elif cmd == "/theme":
            from craft.tui.theme import THEMES
            sub = args.strip()
            if sub == "list":
                for t in THEMES:
                    self._chat_log.write(f"  {t}")
            elif sub in THEMES:
                from craft.tui.config_panel import tui_config
                tui_config.theme = sub
                self._chat_log.write(f"[green]主题: {sub} (重启生效)[/]")
        elif cmd == "/plugin":
            from craft.core.plugin import plugin_manager
            self._chat_log.write("[bold]插件[/]:")
            for p in plugin_manager.list():
                self._chat_log.write(f"  [cyan]{p['name']}[/] v{p['version']}")
        elif cmd == "/workspace":
            from craft.core.project import projects
            sub = args.split()[0] if args else "list"
            if sub == "list":
                for p in projects.list():
                    self._chat_log.write(f"  {p['name']} ({p['path']})")
        else:
            self._chat_log.write(f"[yellow]未知命令: {text} (输入 /help 查看)[/]")
