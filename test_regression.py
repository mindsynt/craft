"""全流程回归测试"""
import sys, asyncio, time
sys.path.insert(0, ".")

from craft.core.session import sessions
from craft.core.memory import memory
from craft.core.task import tasks
from craft.core.control_plane import control_plane
from craft.core.agent import agents
from craft.core.account import accounts
from craft.core.inbox import inbox
from craft.core.enterprise import enterprise
from craft.core.skill import skills
from craft.core.team import team_manager
from craft.core.tools import registry
from craft.core.bus import bus
from craft.core.cron import scheduler
from craft.core.plugin import plugin_manager
from craft.core.share import share_manager
from craft.core.sync import sync_manager
from craft.core.metrics import metrics
from craft.core.file_op import fm
from craft.core.git_integration import git
from craft.core.shell import shell
from craft.core.util import format_bytes, format_duration, generate_id
from craft.core.effect import Effect, Option

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  + {name}")
        passed += 1
    else:
        print(f"  - {name}: FAIL {detail}")
        failed += 1

print("=" * 55)
print("Craft 全流程回归测试")
print("=" * 55)

# ─── 场景1: 完整对话流程 ───
print("\n[场景1] 完整对话流程")
s = sessions.create(title="项目优化讨论")
check("创建会话", s.id is not None)
s.add_message("user", "如何优化数据库查询？")
s.add_message("assistant", "建议:1.分析慢查询 2.加索引 3.缓存")
s.add_message("user", "具体实施步骤？")
s.add_message("assistant", "步骤:1.开启慢查询日志 2.分析执行计划 3.加覆盖索引")
check("对话消息", len(s.messages) == 4, f"got {len(s.messages)}")
s2 = sessions.get(s.id)
check("会话持久化", s2 is not None and len(s2.messages) == 4)
check("会话列表", len(sessions.list()) >= 1)

# ─── 场景2: 知识管理 ───
print("\n[场景2] 知识管理")
m1 = memory.add(content="MySQL 慢查询优化: 使用 EXPLAIN 分析执行计划", type="knowledge")
m2 = memory.add(content="Redis 缓存策略: 缓存穿透/击穿/雪崩", type="knowledge")
m3 = memory.add(content="数据库索引原则: 高选择性列在前", type="knowledge")
check("记忆创建", m1 and m2 and m3)
results = memory.search("MySQL EXPLAIN")
check("记忆搜索", len(results) >= 1, f"found {len(results)}")
all_mem = memory.list(limit=10)
check("记忆列表", len(all_mem) >= 3, f"got {len(all_mem)}")

# ─── 场景3: 任务管理 ───
print("\n[场景3] 任务管理")
t1 = tasks.create("分析慢查询", "开启慢查询日志并分析", agent_id="plan")
t2 = tasks.create("添加数据库索引", "根据分析结果添加覆盖索引", agent_id="build", parent_id=t1.id)
check("任务创建", t1.id and t2.id)
tasks.update_status(t1.id, "completed", "已分析完成")
tasks.update_status(t2.id, "running")
check("任务状态", tasks.get(t2.id).status == "running")
tasks.update_status(t2.id, "completed", "索引添加完成")
check("任务完成", tasks.get(t2.id).is_completed)
check("任务列表", len(tasks.list()) >= 2)

# ─── 场景4: 事件驱动 ───
print("\n[场景4] 事件驱动")
received = []
@bus.on("workflow:complete")
def handler(e):
    received.append(e.data)
async def test_bus():
    await bus.emit("workflow:complete", {"task_id": t1.id, "status": "success"})
    await bus.emit("workflow:complete", {"task_id": t2.id, "status": "success"})
asyncio.run(test_bus())
check("事件发布订阅", len(received) == 2, f"got {len(received)}")

# ─── 场景5: 控制平面调度 ───
print("\n[场景5] 控制平面")
control_plane.register_agent("build")
control_plane.register_agent("plan")
avail = control_plane.available_agents()
check("Agent注册", "build" in avail and "plan" in avail)
cp_task = control_plane.create_task("build", "优化首页加载速度")
check("控制平面任务", cp_task.id is not None)

# ─── 场景6: 定时调度 ───
print("\n[场景6] 定时调度")
jid = scheduler.add("每日代码审查", cron_expr="0 9 * * *")
check("定时任务", jid is not None)
check("任务列表", len(scheduler.list()) >= 1)

# ─── 场景7: 企业协作 ───
print("\n[场景7] 企业协作")
acc = accounts.create("lead@craft.ai", "技术主管")
acc2 = accounts.create("dev@craft.ai", "开发工程师")
check("账户创建", acc.id and acc2.id)
team = enterprise.create_team("后端组", acc.id)
enterprise.add_member(team.id, acc2.id)
check("团队管理", len(team.members) == 1)
enterprise.audit("code.review", "lead", "pr#42", "通过了数据库优化PR")
logs = enterprise.get_audit_log()
check("审计日志", len(logs) >= 1, f"got {len(logs)}")
check("企业统计", enterprise.get_usage_stats()["total_users"] >= 1)

# ─── 场景8: 通知收件箱 ───
print("\n[场景8] 通知系统")
inbox.add("success", "CI通过", "PR #42 所有检查通过")
inbox.add("error", "部署失败", "生产环境部署超时")
check("通知创建", inbox.unread_count() >= 2)
inbox.mark_all_read()
check("全部已读", inbox.unread_count() == 0, f"unread={inbox.unread_count()}")

# ─── 场景9: 技能系统 ───
print("\n[场景9] 技能系统")
check("内置技能", len(skills.list()) >= 3, f"got {len(skills.list())}")
skill_names = [s["name"] for s in skills.list()]
check("Dream技能", "dream" in skill_names, f"names={skill_names}")
check("CodeReview技能", "code-review" in skill_names)

# ─── 场景10: 工具系统 ───
print("\n[场景10] 工具系统")
check("工具注册", len(registry) >= 2, f"got {len(registry)}")
tool_names = [t.name for t in registry.list()]
check("read_file", "read_file" in tool_names)
check("write_file", "write_file" in tool_names)

# ─── 场景11: 分享与同步 ───
print("\n[场景11] 分享与同步")
share = share_manager.export_session(s.id)
check("会话导出", "messages" in share, f"keys={list(share.keys())}")
check("导出消息数", len(share["messages"]) == 4)
sync_manager.set("theme", "dark")
check("同步存储", sync_manager.get("theme") == "dark")

# ─── 场景12: 指标收集 ───
print("\n[场景12] 指标")
metrics.count("session.created")
metrics.count("message.sent")
metrics.count("task.completed")
check("指标统计", metrics.summary().get("session.created", 0) >= 1)

# ─── 场景13: Effect / Util ───
print("\n[场景13] 工具函数")
check("format_bytes", "KB" in format_bytes(2048))
check("format_duration", "m" in format_duration(120))
check("generate_id", len(generate_id()) > 0)
check("Effect.succeed", Effect.succeed(42).unwrap() == 42)
check("Option.some", Option.is_some(Option.some("v")))
check("Option.none", Option.is_none(Option.none()))

# ─── 场景14: 文件系统 ───
print("\n[场景14] 文件系统")
fm.write("/tmp/_craft_test.txt", "回归测试数据")
check("文件写入", fm.read("/tmp/_craft_test.txt") == "回归测试数据")
fm.delete("/tmp/_craft_test.txt")
check("文件删除", not fm.exists("/tmp/_craft_test.txt"))

# ─── 场景15: Shell/Git ───
print("\n[场景15] Shell & Git")
check("shell_quote", shell.quote("hello") == "hello")
check("git_check", hasattr(git, "is_repo"))

# ─── 场景16: 团队/ACP ───
print("\n[场景16] 团队 & ACP")
from craft.core.team import team_manager as tm2
from craft.core.acp import acp
tm = tm2.create("AI平台组")
check("创建团队", tm.name == "AI平台组")
msg = acp.create_message("task.assign", {"task": "优化模型"}, sender="lead", target="dev")
check("ACP消息", msg.type == "task.assign" and msg.sender == "lead")

# ─── 场景17: 工作流 ───
print("\n[场景17] 工作流引擎")
from craft.core.workflow import workflow_engine
wf = workflow_engine.create("CI/CD Pipeline")
check("工作流创建", wf.id is not None)
from craft.core.workflow import WorkflowStep
wf.add_step(WorkflowStep("构建", task="npm run build"))
wf.add_step(WorkflowStep("测试", task="npm test", depends_on=["构建"]))
check("工作流步骤", len(wf.steps) == 2, f"got {len(wf.steps)}")

# ─── 总结 ───
print(f"\n{'='*55}")
print(f"回归测试: {passed} 通过, {failed} 失败 / 共 {passed+failed} 项")
if failed:
    print("*** 有测试失败 ***")
    sys.exit(1)
else:
    print("*** 全部通过 ✅ ***")
