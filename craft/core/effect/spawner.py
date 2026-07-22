"""子进程生成器 — CrossSpawnSpawner, ProcessResult"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import threading
from typing import (
    Any,
    Callable,
    NamedTuple,
)


class ProcessResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
    pid: int


class CrossSpawnSpawner:
    """
    子进程生成器 — 对应 cross-spawn-spawner.ts
    使用 Python subprocess 实现跨平台进程生成
    """

    DEFAULT_TIMEOUT: float = 300.0  # 5 分钟

    @staticmethod
    def to_error(err: Any) -> Exception:
        if isinstance(err, Exception):
            return err
        return Exception(str(err))

    @staticmethod
    def to_system_error_tag(err: OSError) -> str:
        errno_map = {
            "ENOENT": "NotFound",
            "EACCES": "PermissionDenied",
            "EEXIST": "AlreadyExists",
            "EISDIR": "BadResource",
            "ENOTDIR": "BadResource",
            "EBUSY": "Busy",
            "ELOOP": "BadResource",
        }
        # Try to find by errno
        import errno as errno_module

        errno_to_tag = {
            errno_module.ENOENT: "NotFound",
            errno_module.EACCES: "PermissionDenied",
            errno_module.EEXIST: "AlreadyExists",
            errno_module.EISDIR: "BadResource",
            errno_module.ENOTDIR: "BadResource",
            errno_module.EBUSY: "Busy",
            errno_module.ELOOP: "BadResource",
        }
        return errno_to_tag.get(err.errno, "Unknown")

    @classmethod
    def spawn(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        extend_env: bool = True,
        shell: bool = False,
        timeout: float | None = None,
        stdin_data: str | None = None,
        detach: bool = False,
        kill_signal: str = "SIGTERM",
        force_kill_after: float | None = None,
    ) -> ProcessResult:
        """
        同步生成子进程 (对应 spawnCommand)
        """
        if isinstance(command, str):
            cmd = command if shell else [command]
        else:
            cmd = command

        if args and not shell:
            cmd = cmd + args
        elif args and shell:
            cmd = cmd + args

        if extend_env and env:
            merged_env = {**os.environ, **env}
        else:
            merged_env = env

        effective_timeout = timeout or cls.DEFAULT_TIMEOUT

        try:
            proc = subprocess.Popen(
                cmd if not shell else " ".join(cmd) if isinstance(cmd, list) else cmd,
                stdin=subprocess.PIPE if stdin_data is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=merged_env,
                shell=shell,
                preexec_fn=os.setsid if detach and sys.platform != "win32" else None,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if detach and sys.platform == "win32"
                else 0,
            )
        except OSError as e:
            tag = cls.to_system_error_tag(e)
            raise OSError(f"[{tag}] Failed to spawn: {e}") from e

        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=stdin_data.encode("utf-8") if stdin_data else None,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            if force_kill_after:
                proc.kill()
                proc.wait(timeout=10)
            else:
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(getattr(signal, kill_signal, signal.SIGTERM))
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            raise

        return ProcessResult(
            returncode=proc.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
            stderr=stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
            pid=proc.pid or 0,
        )

    @classmethod
    async def spawn_async(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        extend_env: bool = True,
        shell: bool = False,
        timeout: float | None = None,
        stdin_data: str | None = None,
    ) -> ProcessResult:
        """
        异步生成子进程
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: cls.spawn(
                command,
                args,
                cwd=cwd,
                env=env,
                extend_env=extend_env,
                shell=shell,
                timeout=timeout,
                stdin_data=stdin_data,
            ),
        )

    @classmethod
    def spawn_with_stream(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdout_callback: Callable[[str], None] | None = None,
        stderr_callback: Callable[[str], None] | None = None,
        shell: bool = False,
        **kwargs: Any,
    ) -> int:
        """
        生成子进程并流式读取输出
        """
        if isinstance(command, str):
            cmd = command if shell else [command]
        else:
            cmd = command

        if args and not shell:
            cmd = cmd + args
        elif args and shell:
            cmd = cmd + args

        if extend_env := kwargs.get("extend_env", True):
            merged_env = {**os.environ, **(env or {})}
        else:
            merged_env = env

        proc = subprocess.Popen(
            cmd if not shell else " ".join(cmd) if isinstance(cmd, list) else cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
            shell=shell,
            bufsize=1,
            universal_newlines=True,
        )

        def _read_stream(stream: Any, callback: Callable[[str], None] | None) -> None:
            for line in stream:
                if callback:
                    callback(line.rstrip("\n"))

        threads = []
        if stdout_callback:
            t = threading.Thread(
                target=_read_stream, args=(proc.stdout, stdout_callback), daemon=True
            )
            t.start()
            threads.append(t)
        if stderr_callback:
            t = threading.Thread(
                target=_read_stream, args=(proc.stderr, stderr_callback), daemon=True
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        proc.wait()
        return proc.returncode or 0


__all__ = [
    "ProcessResult",
    "CrossSpawnSpawner",
]
