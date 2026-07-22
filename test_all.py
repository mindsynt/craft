"""Craft 功能完整性测试"""
import sys, asyncio
sys.path.insert(0, ".")

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1

# ═══════════════════════════════════════════════════════════
# Agent 系统
# ═══════════════════════════════════════════════════════════
from craft.core.agent import agents

def t_agent():
    assert agents.get("build") is not None
    assert agents.get("build").name == "Build"
    assert agents.get("plan") is not None
    assert agents.check_tool("build", "read_file")
    assert not agents.check_tool("plan", "terminal")
    assert not agents.check_tool("plan", "write_file")
    assert len(agents.list()) >= 2
test("Agent系统", t_agent)

# ═══════════════════════════════════════════════════════════
# 记忆系统
# ═══════════════════════════════════════════════════════════
from craft.core.memory import memory

def t_memory():
    id1 = memory.add(content="测试数据")
    assert id1 is not None
    id2 = memory.add(content="Python 3.11 async/await", type="knowledge")
    assert id2 is not None
    results = memory.search("Python")
    assert len(results) >= 1
    assert len(memory.list(limit=10)) >= 2
test("记忆系统", t_memory)

# ═══════════════════════════════════════════════════════════
# 会话系统
# ═══════════════════════════════════════════════════════════
from craft.core.session import sessions

def t_session():
    s = sessions.create(title="测试", agent_id="build")
    assert s.id is not None
    assert s.title == "测试"
    s.add_message("user", "hello")
    s.add_message("assistant", "world")
    assert len(s.messages) == 2
    s2 = sessions.get(s.id)
    assert s2 is not None and len(s2.messages) >= 1
    assert len(sessions.list()) >= 2
test("会话系统", t_session)

# ═══════════════════════════════════════════════════════════
# 工具系统
# ═══════════════════════════════════════════════════════════
from craft.core.tools import registry

def t_tools():
    assert len(registry) >= 2
    names = [t.name for t in registry.list()]
    assert "read_file" in names
test("工具系统", t_tools)

# ═══════════════════════════════════════════════════════════
# 事件总线
# ═══════════════════════════════════════════════════════════
from craft.core.bus import bus

async def t_bus_async():
    received = []
    @bus.on("test:event")
    def h(e):
        received.append(e.data)
    await bus.emit("test:event", {"msg": "hello"})
    assert len(received) == 1
    assert received[0]["msg"] == "hello"

def t_bus():
    asyncio.run(t_bus_async())
test("事件总线", t_bus)

# ═══════════════════════════════════════════════════════════
# Actor 系统
# ═══════════════════════════════════════════════════════════
from craft.core.actor import Actor, ActorMessage, actor_system

async def t_actor_async():
    class TestActor(Actor):
        def __init__(self):
            super().__init__("test")
            self.last_msg = None
        async def handle(self, msg):
            self.last_msg = msg
    a = TestActor()
    actor_system.register(a)
    await a.start()
    await a.send(ActorMessage("ping", {"data": 1}))
    await asyncio.sleep(0.1)
    await a.stop()
    assert a.last_msg is not None
    assert a.last_msg.type == "ping"

def t_actor():
    asyncio.run(t_actor_async())
test("Actor系统", t_actor)

# ═══════════════════════════════════════════════════════════
# 其他核心模块
# ═══════════════════════════════════════════════════════════
from craft.core.flag import flags
test("特性开关", lambda: (
    assert len(flags.list()) >= 1
))

from craft.core.account import accounts
test("账户系统", lambda: (
    a := accounts.create("test@craft.ai", "测试用户"),
    assert a.id is not None and a.email == "test@craft.ai"
))

from craft.core.cron import scheduler
test("定时任务", lambda: (
    jid := scheduler.add("test", interval_seconds=3600),
    assert scheduler.get(jid) is not None
))

from craft.core.task import tasks
test("任务管理", lambda: (
    t := tasks.create("测试任务", "描述"),
    assert t.id is not None,
    tasks.update_status(t.id, "completed"),
    assert tasks.get(t.id).is_completed
))

from craft.core.control_plane import control_plane
test("控制平面", lambda: (
    control_plane.register_agent("test"),
    assert "test" in [control_plane.available_agents()]
))

from craft.core.skill import skills
test("技能系统", lambda: assert len(skills.list()) >= 3)

from craft.core.enterprise import enterprise
test("企业版", lambda: (
    t := enterprise.create_team("测试团队", "admin"),
    assert t.name == "测试团队"
))

from craft.core.inbox import inbox
test("收件箱", lambda: (
    iid := inbox.add("info", "测试通知"),
    assert inbox.unread_count() >= 1
))

from craft.core.patch import patcher
test("补丁系统", lambda: assert patcher.apply("_nonexist.txt", "a", "b") == False)

from craft.core.share import share_manager
from craft.core.session import sessions as ss
test("分享系统", lambda: (
    s := ss.create(),
    share := share_manager.share(s.id),
    assert share.id.startswith("share_")
))

from craft.core.sync import sync_manager
test("同步系统", lambda: (
    sync_manager.set("k", "v"),
    assert sync_manager.get("k") == "v"
))

from craft.core.metrics import metrics
test("指标系统", lambda: (
    metrics.count("test.event"),
    assert metrics.summary().get("test.event", 0) >= 1
))

from craft.core.effect import Effect, Option
test("Effect适配", lambda: (
    assert Effect.succeed(42).unwrap() == 42,
    assert Option.is_some(Option.some("val")),
    assert Option.is_none(Option.none())
))

from craft.core.team import team_manager
test("团队管理", lambda: (
    t := team_manager.create("研发组"),
    assert t.name == "研发组"
))

from craft.core.acp import acp
test("ACP协议", lambda: (
    msg := acp.create_message("ping", sender="a1"),
    assert msg.type == "ping"
))

from craft.core.installation import installation
test("安装管理", lambda: assert installation.version is not None)

from craft.core.workflow import workflow_engine
test("工作流引擎", lambda: (
    wf := workflow_engine.create("test"),
    assert wf.id is not None
))

from craft.core.file_op import fm
test("文件操作", lambda: (
    fm.write("_test.tmp", "hello"),
    assert fm.read("_test.tmp") == "hello",
    fm.delete("_test.tmp"),
    assert not fm.exists("_test.tmp")
))

from craft.core.util import format_bytes, format_duration, generate_id
test("工具函数", lambda: (
    assert "KB" in format_bytes(1024),
    assert "m" in format_duration(65),
    assert len(generate_id()) > 0
))

from craft.core.global_state import GlobalPaths
test("全局状态", lambda: assert GlobalPaths.config is not None)

from craft.core.server import ServerEvent
test("服务端", lambda: assert ServerEvent("test").to_json() is not None)

from craft.core.storage import Migration
test("数据库迁移", lambda: assert hasattr(Migration(), "apply"))

from craft.core.project import Project
test("项目管理", lambda: assert Project(".").name is not None)

from craft.core.command import command_registry
test("命令系统", lambda: (
    cmd := Command("hello", "测试"),
    command_registry.register(cmd),
    assert command_registry.get("hello") is not None
))

from craft.core.git_integration import git
test("Git集成", lambda: assert hasattr(git, "is_repo"))

from craft.core.pty import terminal_manager
test("PTY终端", lambda: assert hasattr(terminal_manager, "execute"))

from craft.core.shell import shell
test("Shell集成", lambda: assert shell.quote("test") == "test")

from craft.core.npm import npm
test("NPM集成", lambda: assert hasattr(npm, "install"))

from craft.core.lsp import lsp_manager
test("LSP集成", lambda: assert lsp_manager.list() is not None)

# ═══════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════
print(f"\n总计: {passed} 通过, {failed} 失败")
if failed > 0:
    print("❌ 部分测试失败")
    sys.exit(1)
else:
    print("✅ 全部功能测试通过")
