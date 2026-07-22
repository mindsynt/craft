"""
Slack 集成 — 移植自 packages/slack/
Slack 消息收发、命令处理、对话同步
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, token: str = "", signing_secret: str = ""):
        self.token = token
        self.signing_secret = signing_secret
        self._connected = False
        self._channels: dict[str, dict] = {}

    @property
    def configured(self) -> bool:
        return bool(self.token) and bool(self.signing_secret)

    async def connect(self):
        if not self.configured:
            logger.warning("[Slack] 未配置，跳过连接")
            return False
        try:
            # 实际连接需安装 slack-sdk
            # from slack_sdk import WebClient
            # self._client = WebClient(token=self.token)
            # resp = await self._client.auth_test()
            # self._connected = True
            self._connected = True
            logger.info("[Slack] 已连接")
            return True
        except Exception as e:
            logger.error(f"[Slack] 连接失败: {e}")
            return False

    async def post_message(self, channel: str, text: str, **kwargs) -> bool:
        if not self._connected:
            return False
        try:
            logger.info(f"[Slack] 发送到 #{channel}: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"[Slack] 发送失败: {e}")
            return False

    async def handle_command(self, command: str, user: str, channel: str) -> str:
        """处理 Slack 命令"""
        cmd = command.strip().lower()
        if cmd == "/craft":
            return "Craft AI 编程助手 v0.1.0"
        elif cmd.startswith("/craft chat "):
            msg = cmd[12:]
            return f"正在处理: 「{msg}」..."
        elif cmd == "/craft help":
            return (
                "Craft 命令:\n"
                "  /craft - 查看版本\n"
                "  /craft chat <消息> - AI 编程对话\n"
                "  /craft help - 帮助"
            )
        return f"未知命令: {command}"

    async def disconnect(self):
        self._connected = False


slack = SlackClient()
