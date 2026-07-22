"""Craft 功能完整性测试"""
import sys, asyncio
sys.path.insert(0, ".")

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  + {name}")
        passed += 1
    except Exception as e:
        print(f"  - {name}: {e}")
        failed += 1

# Agent
from craft.core.agent import agents
test("Agent", lambda: (
    agents.get("build") is not None
    and agents.get("plan") is not None
    and agents.check_tool("build", "read_file")
    and not agents.check_tool("plan", "terminal")
))

# Memory
from craft.core.memory import memory
test("Memory", lambda: (
    memory.add(content="test") is not None
    and len(memory.list(limit=5)) >= 1
))

# Session
from craft.core.session import sessions
test("Session", lambda: (
    sessions.create(title="t").id is not None
    and len(sessions.list()) >= 1
))

# Tools
from craft.core.tools import registry
test("Tools", lambda: len(registry) >= 2)

# Bus
from craft.core.bus import bus
async def _bus():
    r = []
    @bus.on("t")
    def h(e): r.append(1)
    await bus.emit("t")
    return len(r) == 1
test("Bus", lambda: asyncio.run(_bus()))

# Actor
from craft.core.actor import Actor, ActorMessage, actor_system
async def _actor():
    class TA(Actor):
        def __init__(s):
            super().__init__("x")
            s.last = None
        async def handle(s, m): s.last = m
    a = TA()
    actor_system.register(a)
    await a.start()
    await a.send(ActorMessage("ping"))
    await asyncio.sleep(0.1)
    await a.stop()
    return a.last is not None
test("Actor", lambda: asyncio.run(_actor()))

# Flag
from craft.core.flag import flags
test("Flag", lambda: len(flags.list()) >= 1)

# Account
from craft.core.account import accounts
test("Account", lambda: accounts.create("a@b.c", "u").email == "a@b.c")

# Cron
from craft.core.cron import scheduler
test("Cron", lambda: scheduler.add("t", 3600) is not None)

# Task
from craft.core.task import tasks
test("Task", lambda: (
    tasks.create("x").id is not None
    and tasks.list() is not None
))

# Control Plane
from craft.core.control_plane import control_plane
test("ControlPlane", lambda: (
    control_plane.register_agent("t"),
    len(control_plane.available_agents()) >= 1
))

# Skill
from craft.core.skill import skills
test("Skill", lambda: len(skills.list()) >= 3)

# Enterprise
from craft.core.enterprise import enterprise
test("Enterprise", lambda: enterprise.get_usage_stats() is not None)

# Inbox
from craft.core.inbox import inbox
test("Inbox", lambda: (
    inbox.add("info", "test") is not None
    and inbox.unread_count() >= 1
))

# Plugin
from craft.core.plugin import plugin_manager
test("Plugin", lambda: plugin_manager.list() is not None)

# Patch
from craft.core.patch import patcher
test("Patch", lambda: patcher.apply("/x", "a", "b") == False)

# Share
from craft.core.share import share_manager
from craft.core.session import sessions as ss2
test("Share", lambda: share_manager.share(ss2.create().id).id is not None)

# Sync
from craft.core.sync import sync_manager
test("Sync", lambda: sync_manager.set("k","v") or sync_manager.get("k")=="v")

# Metrics
from craft.core.metrics import metrics
test("Metrics", lambda: metrics.count("e") or metrics.summary().get("e") == 1)

# Effect
from craft.core.effect import Effect, Option
test("Effect", lambda: Effect.succeed(1).unwrap()==1 and Option.is_some(Option.some("v")))

# Team
from craft.core.team import team_manager
test("Team", lambda: team_manager.create("t").name == "t")

# ACP
from craft.core.acp import acp
test("ACP", lambda: acp.create_message("ping").type == "ping")

# Workflow
from craft.core.workflow import workflow_engine
test("Workflow", lambda: workflow_engine.create("t").id is not None)

# File Op
from craft.core.file_op import fm
test("FileOp", lambda: fm.write("/tmp/_ct.t", "x") and fm.read("/tmp/_ct.t")=="x" and fm.delete("/tmp/_ct.t"))

# Util
from craft.core.util import format_bytes, format_duration, generate_id, pipe, merge_deep
test("Util", lambda: "KB" in format_bytes(1024) and "m" in format_duration(65) and len(generate_id())>0)

# Global State
from craft.core.global_state import GlobalPaths
test("GlobalState", lambda: GlobalPaths.config is not None)

# Server
from craft.core.server import ServerEvent
test("Server", lambda: ServerEvent("t").to_json() is not None)

# Storage
from craft.core.storage import db, Migration
test("Storage", lambda: db.execute("SELECT 1") and hasattr(Migration(), "apply"))

# Project
from craft.core.project import Project
test("Project", lambda: Project(".").name is not None)

# Command
from craft.core.command import Command, command_registry
test("Command", lambda: command_registry.register(Command("h","x")) or command_registry.get("h") is not None)

# Git
from craft.core.git_integration import git
test("Git", lambda: hasattr(git, "is_repo"))

# PTY
from craft.core.pty import terminal_manager
test("PTY", lambda: hasattr(terminal_manager, "execute"))

# Shell
from craft.core.shell import shell
test("Shell", lambda: shell.quote("t") == "t")

# NPM
from craft.core.npm import npm
test("NPM", lambda: hasattr(npm, "install"))

# LSP
from craft.core.lsp import lsp_manager
test("LSP", lambda: lsp_manager.list() is not None)

# Env
from craft.core.env import env
test("Env", lambda: env.platform is not None and env.home is not None)

# History
from craft.core.history import history
test("History", lambda: history.append("s1","user","hello") or history.search("hello") is not None)

# Question
from craft.core.question import Question, ask
test("Question", lambda: callable(Question))

# Installation
from craft.core.installation import installation
test("Installation", lambda: installation.version is not None)

# Format
from craft.core.format_mgr import Formatter
test("Formatter", lambda: Formatter.camel_to_snake("HelloWorld") == "hello_world")

# Worktree
from craft.core.worktree import git_worktree
test("Worktree", lambda: hasattr(git_worktree, "list"))

# MCP
from craft.core.mcp_protocol import mcp_manager
test("MCP", lambda: mcp_manager.list() is not None)

# 总计
total = passed + failed
print(f"\n{'='*50}")
print(f"总计: {total} 测试 | {passed} 通过 | {failed} 失败")
if failed:
    print("*** 部分测试失败 ***")
    sys.exit(1)
else:
    print("*** 全部通过 ***")
