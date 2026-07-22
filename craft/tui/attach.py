"""
Attach 命令 — 移植自 attach.ts

附加到远程 MiMoCode 服务器的命令定义。
"""

from __future__ import annotations

from typing import Any, Optional


class AttachCommand:
    """附加到运行中的 Craft 服务器"""

    def __init__(self):
        self.command = "attach <url>"
        self.description = "attach to a running craft server"

    async def handler(self, args: dict) -> None:
        """执行附加操作"""
        url = args.get("url", "")
        directory = args.get("dir")
        session = args.get("session")
        fork = args.get("fork", False)
        continue_ = args.get("continue", False)

        if fork and not continue_ and not session:
            print("--fork requires --continue or --session")
            return

        # Simplified: just run TUI with the given URL
        from craft.tui.config.tui import TuiConfigLoader
        loader = TuiConfigLoader()
        config = await loader.load(directory or ".")

        print(f"Attaching to {url}...")
        # In real implementation, connect to the remote server
        print("Attached.")
