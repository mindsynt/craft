"""
Craft 项目管理 — Kanban 系统
用法: python kanban.py [board|add|move|report]
"""
import json, os, sys, time
from datetime import datetime

KANBAN_FILE = os.path.join(os.path.dirname(__file__), ".kanban.json")
ROLES = {"🎨 UI设计师", "💻 全栈开发1", "💻 全栈开发2", "💻 全栈开发3",
         "👀 Review1", "👀 Review2",
         "🧪 测试1", "🧪 测试2", "🧪 测试3",
         "⚙️ 运维", "🛠️ 打杂"}
COLUMNS = ["📋 Backlog", "📌 To Do", "🔧 In Progress", "👀 Review", "🧪 Testing", "✅ Done"]

def load():
    if os.path.exists(KANBAN_FILE):
        return json.load(open(KANBAN_FILE))
    return {"tasks": [], "next_id": 1}

def save(data):
    json.dump(data, open(KANBAN_FILE, "w"), indent=2, ensure_ascii=False)

def add(title, desc="", assignee="", priority="M"):
    data = load()
    task = {
        "id": data["next_id"],
        "title": title,
        "description": desc,
        "assignee": assignee,
        "priority": priority,
        "status": "📋 Backlog",
        "created": time.time(),
        "comments": [],
    }
    data["tasks"].append(task)
    data["next_id"] += 1
    save(data)
    print(f"📋 [#{task['id']}] {title} → 已添加到 Backlog (assignee: {assignee or '未分配'})")
    return task

def move(task_id, to_column):
    data = load()
    for t in data["tasks"]:
        if t["id"] == task_id:
            if to_column in COLUMNS:
                old = t["status"]
                t["status"] = to_column
                save(data)
                print(f"  [#{task_id}] {old} → {to_column}")
                return
            print(f"  无效状态: {to_column}，可用: {', '.join(COLUMNS)}")
            return
    print(f"  任务 #{task_id} 不存在")

def board():
    data = load()
    print(f"\n{'='*65}")
    print(f"Craft 团队 Kanban — {datetime.now().strftime('%m/%d %H:%M')}")
    print(f"{'='*65}")
    for col in COLUMNS:
        tasks = [t for t in data["tasks"] if t["status"] == col]
        if not tasks:
            continue
        print(f"\n  {col} ({len(tasks)})")
        print(f"  {'-'*55}")
        for t in sorted(tasks, key=lambda x: x["created"]):
            priority = {"H":"🔴","M":"🟡","L":"🟢"}.get(t["priority"],"⚪")
            assign = f" → {t['assignee']}" if t["assignee"] else ""
            title = t["title"][:40]
            print(f"    #{t['id']:2d} {priority} {title:<42} {assign}")
    print(f"\n  总计: {len(data['tasks'])} 个任务")
    print(f"  {'='*55}")

def report():
    data = load()
    done = [t for t in data["tasks"] if t["status"] == "✅ Done"]
    progress = len(done) / max(len(data["tasks"]), 1) * 100
    print(f"\n📊 进度报告")
    print(f"  完成: {len(done)}/{len(data['tasks'])} ({progress:.0f}%)")
    for col in COLUMNS:
        count = len([t for t in data["tasks"] if t["status"] == col])
        bar = "█" * (count * 2) if count else ""
        print(f"  {col}: {count} {bar}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python kanban.py board|add|move|report")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "board":
        board()
    elif cmd == "add" and len(sys.argv) >= 3:
        add(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
            sys.argv[4] if len(sys.argv) > 4 else "",
            sys.argv[5] if len(sys.argv) > 5 else "M")
    elif cmd == "move" and len(sys.argv) >= 4:
        move(int(sys.argv[2]), sys.argv[3])
    elif cmd == "report":
        report()
    else:
        print("用法: python kanban.py board|add|move|report")
