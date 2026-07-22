import asyncio
import os
import subprocess


class RunFailedError(Exception):
    """进程运行失败错误 — 移植自 process.ts RunFailedError"""

    def __init__(self, cmd: list[str], code: int, stdout: bytes, stderr: bytes):
        text = stderr.decode().strip()
        msg = f"Command failed with code {code}: {' '.join(cmd)}"
        if text:
            msg += f"\n{text}"
        self.cmd = list(cmd)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(msg)


def spawn_process(cmd: list[str], cwd: str | None = None,
                  env: dict | None = None, shell: bool = False,
                  timeout: float | None = None) -> subprocess.Popen:
    """生成进程 — 移植自 process.ts spawn"""
    if not cmd:
        raise ValueError("Command is required")
    proc_env = os.environ.copy()
    if env is not None:
        proc_env.update(env)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


async def run_process(cmd: list[str], cwd: str | None = None,
                      env: dict | None = None, shell: bool = False,
                      nothrow: bool = False) -> dict:
    """运行进程并获取输出 — 移植自 process.ts run"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env={**os.environ, **(env or {})} if env else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        code = proc.returncode or 0
        if code != 0 and not nothrow:
            raise RunFailedError(cmd, code, stdout, stderr)
        return {
            "code": code,
            "stdout": stdout,
            "stderr": stderr,
            "text": stdout.decode() if stdout else "",
        }
    except Exception as e:
        if not nothrow:
            raise
        return {
            "code": 1,
            "stdout": b"",
            "stderr": str(e).encode(),
            "text": str(e),
        }


async def run_text(cmd: list[str], cwd: str | None = None,
                   env: dict | None = None, shell: bool = False) -> str:
    """运行进程并获取文本输出 — 移植自 process.ts text"""
    result = await run_process(cmd, cwd=cwd, env=env, shell=shell)
    return result["text"]


async def run_lines(cmd: list[str], cwd: str | None = None,
                    env: dict | None = None, shell: bool = False) -> list[str]:
    """运行进程并获取行输出 — 移植自 process.ts lines"""
    text = await run_text(cmd, cwd=cwd, env=env, shell=shell)
    return [line for line in text.split("\n") if line]


def stop_process(proc: subprocess.Popen):
    """停止进程 — 移植自 process.ts stop"""
    if proc.returncode is not None:
        return
    proc.terminate()
