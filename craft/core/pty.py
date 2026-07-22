"""Craft PTY — 真正的伪终端（forkpty + pyte ANSI 模拟）

移植自 packages/opencode/src/pty/
MiMo-Code 使用 node-pty，这里用纯 Python 实现：
  - os.forkpty() → 创建真实的伪终端
  - pyte → 解析 ANSI 转义序列，剥离颜色代码
  - asyncio → 非阻塞读写循环

效果与 MiMo-Code 一致：
  - 程序以为自己在终端里（有颜色、有交互）
  - 支持 stdin 写入（可交互）
  - 支持终端 resize
  - 支持信号发送
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty as pty_module
import signal
import struct
import termios
from typing import Callable

import pyte

logger = logging.getLogger(__name__)


class PTYProcess:
    """真正的伪终端进程 — 使用 forkpty() + pyte ANSI 模拟器

    和 node-pty 一样，程序会认为自己在一个真实的终端中运行，
    从而启用颜色输出、交互模式、进度条等。
    """

    def __init__(
        self,
        command: str,
        cwd: str | None = None,
        env: dict | None = None,
        cols: int = 120,
        rows: int = 40,
    ):
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = env or {}
        self.cols = cols
        self.rows = rows
        self.pid: int | None = None
        self.fd: int | None = None

        # pyte 终端模拟器
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

        self._exit_code: int | None = None
        self._data_callbacks: list[Callable[[str], None]] = []
        self._finished = False

    # ── 回调 ──────────────────────────────────────────

    def on_data(self, callback: Callable[[str], None]):
        """注册数据回调（每当 PTY 有输出时调用）"""
        self._data_callbacks.append(callback)

    def _emit_data(self, data: str):
        for cb in self._data_callbacks:
            try:
                cb(data)
            except Exception:
                logger.exception("data callback failed")

    # ── 生命周期 ──────────────────────────────────────

    def start(self):
        """forkpty() 创建真实伪终端，子进程执行命令

        与 MiMo-Code 的 node-pty.spawn() 行为一致：
        - 子进程获得真实 /dev/ttysXXX
        - 程序 isatty() = True
        - 颜色、交互、信号全部正常工作
        """
        pid, fd = pty_module.fork()

        if pid == 0:  # ── 子进程 ──
            try:
                # 设置环境变量
                for k, v in self.env.items():
                    os.environ[k] = v
                # 切换目录
                if self.cwd:
                    os.chdir(self.cwd)
                # 通过 shell 执行命令
                os.execvp("/bin/sh", ["/bin/sh", "-c", self.command])
            except Exception:
                pass
            os._exit(1)  # 不应到达这里

        # ── 父进程 ──
        self.pid = pid
        self.fd = fd

        # 设置终端大小
        self._set_window_size(self.cols, self.rows)

        # 设为非阻塞模式
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        logger.info(
            "PTY spawned: pid=%d fd=%d cmd=%s", pid, fd, self.command[:80]
        )

    def _set_window_size(self, cols: int, rows: int):
        """通过 ioctl TIOCSWINSZ 设置终端窗口大小"""
        if self.fd is not None:
            size = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, size)

    def resize(self, cols: int, rows: int):
        """调整终端大小（与 node-pty resize() 对应）"""
        self.cols = cols
        self.rows = rows
        self._set_window_size(cols, rows)
        self._screen.resize(rows, cols)

    def close(self):
        """关闭 PTY"""
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        self._finished = True

    # ── 读写 ──────────────────────────────────────────

    def write(self, data: str):
        """向 PTY 写入数据（发送到子进程的 stdin）

        与 node-pty 的 proc.write() 对应。
        用于向交互式程序发送输入。
        """
        if self.fd is not None and not self._finished:
            try:
                os.write(self.fd, data.encode())
            except OSError as e:
                logger.error("PTY write error: %s", e)

    def writeline(self, data: str):
        """写入一行数据（自动加 \\n）"""
        self.write(data + "\n")

    def read(self, max_bytes: int = 65536) -> str:
        """读取 PTY 可用数据，经过 pyte 解析 ANSI 后返回

        Returns:
            原始文本（含 ANSI）。用 get_display() 获取纯文本。
        """
        if self.fd is None:
            return ""
        try:
            data = os.read(self.fd, max_bytes)
            if not data:  # EOF
                return ""
            decoded = data.decode(errors="replace")
            # 交给 pyte 解析 ANSI 转义序列
            self._stream.feed(decoded)
            self._emit_data(decoded)
            return decoded
        except BlockingIOError:
            return ""
        except OSError as e:
            logger.error("PTY read error: %s", e)
            return ""

    def drain(self) -> str:
        """排空 PTY 缓冲区中的所有数据"""
        chunks = []
        while True:
            chunk = self.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return "".join(chunks)

    # ── 终端内容 ──────────────────────────────────────

    def get_display(self) -> str:
        """获取当前终端屏幕内容（纯文本，ANSI 已剥离）

        对应 node-pty 读取后经过 xterm.js 渲染的文本。
        pyte 维护了一个 Screen 缓冲区，记录了当前终端的
        每一行显示内容。
        """
        return "\n".join(self._screen.display)

    def get_display_lines(self) -> list[str]:
        """获取终端每一行的内容"""
        return list(self._screen.display)

    # ── 异步读取循环 ──────────────────────────────────

    async def read_loop(
        self,
        callback: Callable[[str], None] | None = None,
        interval: float = 0.01,
    ) -> str:
        """异步循环读取 PTY 输出，直到子进程退出

        Args:
            callback: 每行输出回调（用于流式输出）
            interval: 轮询间隔

        Returns:
            所有输出拼接的完整文本
        """
        if self.fd is None:
            return ""

        all_output: list[str] = []

        while not self._finished:
            # 检查子进程是否已退出
            try:
                wpid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                self._finished = True
                break

            if wpid != 0:  # 子进程已退出
                # 解析退出码
                if os.WIFEXITED(status):
                    self._exit_code = os.WEXITSTATUS(status)
                elif os.WIFSIGNALED(status):
                    self._exit_code = -os.WTERMSIG(status)
                else:
                    self._exit_code = 0
                self._finished = True

                # 排空剩余数据
                remaining = self.drain()
                if remaining:
                    all_output.append(remaining)
                    if callback:
                        callback(remaining)
                break

            # 读取可用数据
            data = self.read(4096)
            if data:
                all_output.append(data)
                if callback:
                    callback(data)

            await asyncio.sleep(interval)

        # 关闭 fd
        self.close()

        return "".join(all_output)

    # ── 信号控制 ──────────────────────────────────────

    def kill(self, sig: int = signal.SIGTERM):
        """向子进程发送信号

        与 node-pty 的 proc.kill(signal) 对应。
        """
        if self.pid and not self._finished:
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                self._finished = True

    def interrupt(self):
        """发送 Ctrl+C (SIGINT)"""
        self.write("\x03")

    # ── 属性 ──────────────────────────────────────────

    @property
    def return_code(self) -> int | None:
        return self._exit_code

    @property
    def is_alive(self) -> bool:
        if self.pid is None or self._finished:
            return False
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def __del__(self):
        self.close()


class TerminalManager:
    """终端管理器 — 支持一次性执行和交互式会话"""

    def __init__(self):
        self._sessions: dict[str, PTYProcess] = {}

    # ── 一次性执行 ────────────────────────────────────

    async def execute(self, command: str, cwd: str | None = None) -> dict:
        """在真实 PTY 中执行命令，返回完整输出

        Returns:
            dict: {output, display, return_code, command}
              - output:  原始输出（含 ANSI 颜色码）
              - display: 纯文本（ANSI 已剥离）
        """
        proc = PTYProcess(command, cwd)
        proc.start()
        output_text = await proc.read_loop()

        return {
            "output": output_text,
            "display": proc.get_display(),
            "return_code": proc.return_code,
            "command": command,
        }

    async def execute_shell(self, command: str, timeout: float = 30) -> dict:
        """带超时控制的命令执行

        Returns:
            dict: {output, display, error, return_code}
        """
        proc = PTYProcess(command)
        proc.start()
        all_output = []
        try:

            async def collect(data: str):
                all_output.append(data)

            output_text = await asyncio.wait_for(
                proc.read_loop(callback=collect), timeout=timeout
            )
            return {
                "output": output_text,
                "display": proc.get_display(),
                "return_code": proc.return_code,
            }
        except asyncio.TimeoutError:
            proc.kill()
            output_text = "".join(all_output)
            return {
                "output": output_text,
                "display": proc.get_display(),
                "error": f"命令超时 ({timeout}s)",
                "return_code": -1,
            }

    # ── 交互式会话 ────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        command: str,
        cwd: str | None = None,
    ) -> PTYProcess:
        """创建交互式 PTY 会话（类似 tmux 面板）"""
        proc = PTYProcess(command, cwd)
        proc.start()
        self._sessions[session_id] = proc
        return proc

    def get_session(self, session_id: str) -> PTYProcess | None:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str):
        proc = self._sessions.pop(session_id, None)
        if proc:
            proc.kill(signal.SIGKILL)
            proc.close()

    async def read_session(self, session_id: str) -> str:
        """读取交互式会话的可用输出"""
        proc = self._sessions.get(session_id)
        if not proc:
            return ""
        return proc.read()

    def write_session(self, session_id: str, data: str):
        """向交互式会话写入输入"""
        proc = self._sessions.get(session_id)
        if proc:
            proc.write(data)


# 全局单例
terminal_manager = TerminalManager()
