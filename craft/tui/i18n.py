"""
多语言 — 移植自 packages/opencode/src/cli/cmd/tui/i18n/
支持 en/zh 双语
"""

from __future__ import annotations


ZH: dict[str, str] = {
    "app.title": "Craft — AI 编程助手",
    "nav.chat": "对话",
    "nav.sessions": "会话",
    "nav.models": "模型",
    "nav.providers": "提供商",
    "nav.memory": "记忆",
    "nav.skills": "技能",
    "nav.accounts": "账户",
    "nav.inbox": "通知",
    "nav.enterprise": "企业版",
    "nav.settings": "设置",
    "panel.chat": "对话",
    "panel.models": "模型管理",
    "panel.providers": "提供商管理",
    "panel.memory": "记忆管理",
    "panel.skills": "技能管理",
    "panel.accounts": "账户管理",
    "panel.inbox": "通知收件箱",
    "panel.enterprise": "企业版",
    "panel.settings": "设置",
    "sidebar.agents": "Agent",
    "sidebar.sessions": "会话",
    "input.placeholder": "输入消息... (Enter发送  /help查看命令)",
    "help.title": "命令",
    "help.exit": "退出",
    "help.agent": "切换Agent",
    "help.model": "切换模型",
    "help.diff": "查看Git变更",
    "help.commit": "Git提交",
    "help.tools": "工具列表",
    "help.session": "会话信息",
    "help.new": "新建对话",
    "help.clear": "清屏",
    "help.memory_add": "添加记忆",
    "help.memory_search": "搜索记忆",
    "status.agent": "Agent",
    "status.model": "模型",
    "status.messages": "消息",
    "status.session": "会话",
    "welcome": "欢迎！输入消息开始对话。\n输入 /help 查看命令。",
    "memory.added": "已添加记忆",
    "memory.found": "找到",
    "memory.items": "条",
    "session.created": "新建会话",
    "session.switched": "已切换",
    "agent.switched": "已切换到",
    "agent.available": "可用",
    "model.switched": "模型已切换",
    "git.clean": "工作区干净",
    "git.not_repo": "不是 Git 仓库",
    "error.unknown_cmd": "未知命令",
    "error.provider": "LLM 初始化失败",
    "save": "保存",
    "cancel": "取消",
    "confirm": "确认",
    "delete": "删除",
    "create": "创建",
    "close": "关闭",
    "new_session": "新建对话",
}

EN: dict[str, str] = {
    "app.title": "Craft — AI Coding Assistant",
    "nav.chat": "Chat",
    "nav.sessions": "Sessions",
    "nav.models": "Models",
    "nav.providers": "Providers",
    "nav.memory": "Memory",
    "nav.skills": "Skills",
    "nav.accounts": "Accounts",
    "nav.inbox": "Inbox",
    "nav.enterprise": "Enterprise",
    "nav.settings": "Settings",
    "panel.chat": "Chat",
    "panel.models": "Models",
    "panel.providers": "Providers",
    "panel.memory": "Memory",
    "panel.skills": "Skills",
    "panel.accounts": "Accounts",
    "panel.inbox": "Notifications",
    "panel.enterprise": "Enterprise",
    "panel.settings": "Settings",
    "sidebar.agents": "Agents",
    "sidebar.sessions": "Sessions",
    "input.placeholder": "Type a message... (Enter to send  /help for commands)",
    "help.title": "Commands",
    "help.exit": "Exit",
    "help.agent": "Switch Agent",
    "help.model": "Switch model",
    "help.diff": "Show Git diff",
    "help.commit": "Git commit",
    "help.tools": "List tools",
    "help.session": "Session info",
    "help.new": "New conversation",
    "help.clear": "Clear screen",
    "help.memory_add": "Add memory",
    "help.memory_search": "Search memory",
    "status.agent": "Agent",
    "status.model": "Model",
    "status.messages": "Messages",
    "status.session": "Session",
    "welcome": "Welcome! Start typing to chat.\nType /help for available commands.",
    "memory.added": "Memory added",
    "memory.found": "Found",
    "memory.items": "items",
    "session.created": "New session created",
    "session.switched": "Switched to",
    "agent.switched": "Switched to",
    "agent.available": "Available",
    "model.switched": "Model switched to",
    "git.clean": "Working tree clean",
    "git.not_repo": "Not a git repository",
    "error.unknown_cmd": "Unknown command",
    "error.provider": "LLM initialization failed",
    "save": "Save",
    "cancel": "Cancel",
    "confirm": "Confirm",
    "delete": "Delete",
    "create": "Create",
    "close": "Close",
    "new_session": "New Session",
}


class I18n:
    def __init__(self, lang: str = "zh"):
        self.lang = lang
        self._strings = ZH if lang == "zh" else EN

    def t(self, key: str, *args, **kwargs) -> str:
        text = self._strings.get(key, key)
        if args:
            text = text % args
        elif kwargs:
            text = text % kwargs
        return text

    def set_lang(self, lang: str):
        self.lang = lang
        self._strings = ZH if lang == "zh" else EN


i18n = I18n("zh")
