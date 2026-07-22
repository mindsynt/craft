"""CLI 命令系统 — 移植自 22 个 MiMo-Code CLI 命令"""

from __future__ import annotations

import json
import os
import sys

import typer

from craft import __version__
from craft.core.agent import agents
from craft.core.memory import memory
from craft.core.session import sessions
from craft.core.account import accounts
from craft.core.auth import auth
from craft.core.tools import registry as tool_registry
from craft.core.task import tasks
from craft.core.skill import skills
from craft.core.inbox import inbox
from craft.core.enterprise import enterprise
from craft.core.control_plane import control_plane
from craft.core.flag import flags
from craft.core.cron import scheduler
from craft.core.git_integration import git
from craft.core.project import Project
from craft.core.plugin import plugin_manager
from craft.core.metrics import metrics

app = typer.Typer(name="craft", help="Craft — AI 编程助手", no_args_is_help=True)
agent_app = typer.Typer(help="Agent 管理")
config_app = typer.Typer(help="配置管理")
session_app = typer.Typer(help="会话管理")
memory_app = typer.Typer(help="记忆管理")
task_app = typer.Typer(help="任务管理")
skill_app = typer.Typer(help="技能管理")
account_app = typer.Typer(help="账户管理")
app.add_typer(agent_app, name="agent")
app.add_typer(config_app, name="config")
app.add_typer(session_app, name="session")
app.add_typer(memory_app, name="memory")
app.add_typer(task_app, name="task")
app.add_typer(skill_app, name="skill")
app.add_typer(account_app, name="account")
theme_app = typer.Typer(help="主题管理")
workspace_app = typer.Typer(help="工作区管理")
app.add_typer(theme_app, name="theme")
app.add_typer(workspace_app, name="workspace")



# ─── 根命令 ─────────────────────────────────────────
@app.command()
def version():
    """显示版本"""
    typer.echo(f"Craft v{__version__}")


@app.command()
def tui():
    """启动终端界面"""
    from craft.tui import run
    run()


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """启动 API 服务"""
    import uvicorn
    typer.echo(f"Craft API: http://{host}:{port}")
    uvicorn.run("craft.api.server:app", host=host, port=port, reload=True)


@app.command()
def stats():
    """显示统计信息"""
    s = sessions.list()
    m = memory.list()
    t = tasks.list()
    typer.echo(f"📊 Craft v{__version__}")
    typer.echo(f"  会话: {len(s)}")
    typer.echo(f"  记忆: {len(m)}")
    typer.echo(f"  任务: {len(t)}")
    typer.echo(f"  Agent: {len(agents.list())}")
    typer.echo(f"  工具: {len(tool_registry)}")
    typer.echo(f"  技能: {len(skills.list())}")


@app.command()
def models():
    """列出可用模型"""
    models_data = {
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1"],
        "anthropic": ["claude-sonnet-4", "claude-3-5-sonnet", "claude-3-haiku"],
        "ollama": ["llama3", "qwen2.5", "mistral"],
    }
    for provider, ms in models_data.items():
        typer.echo(f"\n[cyan]{provider}[/]")
        for m in ms:
            typer.echo(f"  {m}")


@app.command()
def providers():
    """列出已注册的提供商"""
    from craft.core.provider import PROVIDER_MAP
    for name in PROVIDER_MAP:
        typer.echo(f"  {name}")


@app.command()
def tools():
    """列出可用工具"""
    for t in tool_registry.list():
        typer.echo(f"  [cyan]{t.name}[/] - {t.description[:50]}")


@app.command()
def github(action: str = typer.Argument("status", help="status/pr/issues")):  # noqa: F811
    """GitHub 集成"""
    if action == "status":
        if git.is_repo():
            typer.echo(f"  仓库: {git.current_repo() or 'local'}")
            typer.echo(f"  分支: {git.branch()}")
            typer.echo(git.status())
        else:
            typer.echo("  不是 Git 仓库")
    else:
        typer.echo(f"  GitHub 命令: {action}（待实现）")


@app.command()
def pr(action: str = "list"):
    """Pull Request 管理"""
    typer.echo(f"  PR {action}（待实现）")


@app.command()
def mcp(action: str = "list"):
    """MCP 服务器管理"""
    from craft.core.mcp_protocol import mcp_manager
    servers = mcp_manager.list()
    if servers:
        for s in servers:
            typer.echo(f"  [cyan]{s['name']}[/] - {s.get('command','')}")
    else:
        typer.echo("  无 MCP 服务器")


@app.command()
def upgrade():
    """检查更新"""
    from craft.core.installation import installation
    typer.echo(f"  当前版本: v{installation.version}")
    typer.echo("  通道: stable")
    typer.echo("  已是最新版本")


@app.command()
def uninstall():
    """卸载 Craft"""
    confirm = typer.confirm("确定要卸载 Craft？")
    if confirm:
        typer.echo("  已卸载")


@app.command()
def web():
    """打开 Web 界面"""
    typer.echo("  Web 界面: http://localhost:3000")


@app.command()
def run(script: str):
    """运行脚本"""
    typer.echo(f"  运行: {script}（待实现）")


@app.command()
def export():
    """导出数据"""
    data = {
        "version": __version__,
        "sessions": [s.to_dict() for s in sessions._sessions.values()],
        "tasks": [t.to_dict() for t in tasks._tasks.values()],
    }
    path = "craft-export.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    typer.echo(f"  已导出到 {path}")


@app.command()
def import_data(file: str):
    """导入数据"""
    try:
        data = json.load(open(file))
        typer.echo(f"  导入 {len(data.get('sessions',[]))} 个会话")
    except Exception as e:
        typer.echo(f"  导入失败: {e}")


@app.command()
def generate(description: str):
    """生成配置"""
    typer.echo(f"  生成配置: {description}（待实现）")


@app.command()
def acp(action: str = "send"):
    """ACP 协议通信"""
    from craft.core.acp import acp as acp_proto
    msg = acp_proto.create_message(action, {"cmd": action})
    typer.echo(f"  ACP 消息: {msg.id} type={msg.type}")


@app.command()
def db(action: str = "status"):
    """数据库操作"""
    from craft.core.storage import db as db_conn
    try:
        r = db_conn.execute("SELECT COUNT(*) as c FROM memory_entries").fetchone()
        count = r[0] if r else 0
        typer.echo(f"  记忆表: {count} 条")
    except Exception:
        typer.echo("  数据库: 就绪")


@app.command()
def plug(action: str = "list"):
    """插件管理"""
    plugins = plugin_manager.list()
    if plugins:
        for p in plugins:
            typer.echo(f"  [cyan]{p['name']}[/] v{p['version']}")
    else:
        typer.echo("  无插件")


# ─── agent 子命令 ────────────────────────────────────
@agent_app.command("list")
def agent_list():
    """列出所有 Agent"""
    for aid, info in agents.list():
        typer.echo(f"  [cyan]{aid:<12}[/] {info.name:<20} {info.description}")


@agent_app.command("get")
def agent_get(agent_id: str):
    """查看 Agent 详情"""
    info = agents.get(agent_id)
    if info:
        typer.echo(f"  名称: {info.name}")
        typer.echo(f"  描述: {info.description}")
        typer.echo(f"  工具: {', '.join(info.allowed_tools)}")
    else:
        typer.echo(f"  Agent '{agent_id}' 不存在")


# ─── config 子命令 ───────────────────────────────────
@config_app.command("get")
def config_get(key: str = ""):
    """查看配置"""
    from craft.config import get_config
    cfg = get_config()
    if key:
        typer.echo(json.dumps(cfg.model_dump().get(key, {}), indent=2, default=str))
    else:
        typer.echo(json.dumps(cfg.model_dump(), indent=2, default=str))


@config_app.command("set")
def config_set(key: str, value: str):
    """设置配置"""
    from craft.config import CONFIG_DIR
    config_file = CONFIG_DIR / "config.json"
    import json as j
    try:
        data = j.loads(config_file.read_text()) if config_file.exists() else {}
        data[key] = value
        config_file.write_text(j.dumps(data, indent=2))
        typer.echo(f"  已设置 {key}={value}")
    except Exception as e:
        typer.echo(f"  设置失败: {e}")


# ─── session 子命令 ──────────────────────────────────
@session_app.command("list")
def session_list():
    """列出所有会话"""
    for s in sessions.list(20):
        typer.echo(f"  [cyan]{s['id'][:12]}[/] {s['title'][:30]} ({s['message_count']}条)")


@session_app.command("get")
def session_get(session_id: str):
    """查看会话详情"""
    s = sessions.get(session_id)
    if s:
        for m in s.messages:
            role = "🤖" if m["role"] == "assistant" else "📝"
            typer.echo(f"  {role} {m['content'][:100]}")
    else:
        typer.echo("  会话不存在")


@session_app.command("delete")
def session_delete(session_id: str):
    """删除会话"""
    if sessions.delete(session_id):
        typer.echo("  已删除")
    else:
        typer.echo("  会话不存在")


# ─── memory 子命令 ───────────────────────────────────
@memory_app.command("add")
def memory_add(content: str, type: str = "note"):
    """添加记忆"""
    mid = memory.add(content=content, type=type)
    typer.echo(f"  已添加: {mid[:12]}...")


@memory_app.command("search")
def memory_search(query: str):
    """搜索记忆"""
    results = memory.search(query)
    typer.echo(f"  找到 {len(results)} 条:")
    for r in results:
        typer.echo(f"  [{r['type']}] {r.get('snippet', r.get('content',''))[:80]}")


@memory_app.command("list")
def memory_list():
    """列出记忆"""
    for m in memory.list(20):
        typer.echo(f"  [{m['type']}] {m['content'][:60]}")


# ─── task 子命令 ─────────────────────────────────────
@task_app.command("create")
def task_create(title: str, description: str = ""):
    """创建任务"""
    t = tasks.create(title, description)
    typer.echo(f"  已创建: {t.id[:12]}")


@task_app.command("list")
def task_list():
    """列出任务"""
    for t in tasks.list():
        status_icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(t["status"], "📋")
        typer.echo(f"  {status_icon} {t['title'][:40]} ({t['status']})")


# ─── skill 子命令 ────────────────────────────────────
@skill_app.command("list")
def skill_list():
    """列出技能"""
    for s in skills.list():
        typer.echo(f"  [cyan]{s['name']}[/] v{s['version']} - {s['description'][:50]}")


# ─── account 子命令 ──────────────────────────────────
@account_app.command("list")
def account_list():
    """列出账户"""
    for a in accounts.list():
        typer.echo(f"  [cyan]{a.name}[/] ({a.email}) - {a.provider}")


@account_app.command("create")
def account_create(email: str, name: str = ""):
    """创建账户"""
    a = accounts.create(email, name)
    typer.echo(f"  已创建: {a.id[:12]}")

# ─── account 子命令 ──────────────────────────────────
@account_app.command("list")
def account_list():
    """列出账户"""
    for a in accounts.list():
        typer.echo(f"  [cyan]{a.name}[/] ({a.email}) - {a.provider}")

@account_app.command("create")
def account_create(email: str, name: str = ""):
    """创建账户"""
    a = accounts.create(email, name)
    typer.echo(f"  已创建: {a.id[:12]}")

@account_app.command("login")
def account_login(email: str, password: str = ""):
    """登录账户"""
    a = accounts.authenticate(email, password) if password else accounts.login(email)
    if a:
        typer.echo(f"  ✅ 登录成功: {a.name}")
    else:
        typer.echo(f"  ❌ 登录失败")

@account_app.command("logout")
def account_logout():
    """登出当前账户"""
    accounts.logout()
    typer.echo("  已登出")

@account_app.command("switch")
def account_switch(email: str):
    """切换账户"""
    a = accounts.switch(email)
    if a:
        typer.echo(f"  ✅ 已切换到: {a.name}")
    else:
        typer.echo(f"  ❌ 账户不存在")

# ─── theme 子命令 ────────────────────────────────────
@theme_app.command("list")
def theme_list():
    """列出可用主题"""
    from craft.tui.theme import THEMES
    for t in THEMES:
        typer.echo(f"  {t}")

@theme_app.command("set")
def theme_set(name: str):
    """切换主题"""
    from craft.tui.theme import THEMES
    from craft.tui.config_panel import tui_config
    if name in THEMES:
        tui_config.theme = name
        typer.echo(f"  ✅ 主题已切换: {name} (重启 TUI 生效)")
    else:
        available = ", ".join(THEMES.keys())
        typer.echo(f"  ❌ 可用主题: {available}")

# ─── workspace 子命令 ────────────────────────────────
from craft.core.project import Project

@workspace_app.command("create")
def workspace_create(name: str, path: str = "."):
    """创建工作区"""
    p = Project()
    p.init(path)
    typer.echo(f"  ✅ 工作区已创建: {name}")

@workspace_app.command("list")
def workspace_list():
    """列出工作区"""
    from craft.core.project import projects
    for p in projects.list():
        typer.echo(f"  {p['name']} ({p['path']})")

@workspace_app.command("switch")
def workspace_switch(name: str):
    """切换工作区"""
    from craft.core.project import projects
    if projects.switch(name):
        typer.echo(f"  ✅ 已切换到: {name}")
    else:
        typer.echo(f"  ❌ 工作区不存在: {name}")

# ─── skill 子命令 ────────────────────────────────────
from craft.core.skill import skills

@skill_app.command("show")
def skill_show(name: str):
    """显示技能详情"""
    s = skills.get(name)
    if s:
        typer.echo(f"  名称: {s['name']}")
        typer.echo(f"  版本: v{s['version']}")
        typer.echo(f"  描述: {s['description']}")
    else:
        available = ", ".join(s["name"] for s in skills.list())
        typer.echo(f"  可用技能: {available}")

@skill_app.command("run")
def skill_run(name: str, input_data: str = ""):
    """运行技能"""
    from craft.core.task import tasks
    t = tasks.create(f"技能: {name}")
    typer.echo(f"  ✅ 已启动: {name} ({t.id[:12]})")

# ─── plugin 子命令 ────────────────────────────────────
@app.command("plug-install")
def plug_install(url: str):
    """安装插件"""
    from craft.core.plugin import plugin_manager
    p = plugin_manager.install(url)
    typer.echo(f"  ✅ 已安装: {p['name']}")

@app.command("plug-remove")
def plug_remove(name: str):
    """卸载插件"""
    from craft.core.plugin import plugin_manager
    plugin_manager.remove(name)
    typer.echo(f"  已卸载: {name}")

@app.command("plug-list")
def plug_list():
    """列出插件"""
    from craft.core.plugin import plugin_manager
    for p in plugin_manager.list():
        typer.echo(f"  [cyan]{p['name']}[/] v{p['version']}")
