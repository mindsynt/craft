"""
格式化 — 移植自 packages/opencode/src/format/
代码格式化、多语言格式化器支持（prettier, ruff, rustfmt, gofmt 等）
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any


# ── 格式化器信息 ────────────────────────────────────────────

class FormatterInfo:
    """格式化器元信息 — 对应 TS formatter.ts 中的 Info 接口"""

    def __init__(self, name: str, extensions: list[str],
                 enabled_func=None, environment: dict[str, str] | None = None):
        self.name = name
        self.extensions = extensions
        self.environment = environment or {}
        self._enabled_func = enabled_func

    async def enabled(self, context: dict) -> list[str] | bool:
        """检测格式化器是否可用

        Args:
            context: {"directory": str, "worktree": str}

        Returns:
            [command, arg, ...] 或 False
        """
        if self._enabled_func:
            return await self._enabled_func(context)
        return False


# ── 辅助 ────────────────────────────────────────────────────

def _which(name: str) -> str | None:
    """查找可执行文件"""
    for p in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(p, name)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
        if os.name == "nt":
            for ext in [".exe", ".cmd", ".bat"]:
                full_ext = full + ext
                if os.path.isfile(full_ext) and os.access(full_ext, os.X_OK):
                    return full_ext
    return None


def _find_up(filename: str, *start_dirs: str) -> list[str]:
    """从起始目录向上查找文件"""
    results: list[str] = []
    seen = set()
    for start in start_dirs:
        current = Path(start).resolve()
        for parent in [current] + list(current.parents):
            if str(parent) in seen:
                break
            seen.add(str(parent))
            candidate = parent / filename
            if candidate.exists():
                results.append(str(candidate))
    return results


def _read_json(path: str) -> dict:
    """读取 JSON 文件"""
    try:
        import json
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """运行命令"""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=cwd, env={**os.environ, **(env or {})},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(cmd, 1, "", "")


# ── 内置格式化器定义 ────────────────────────────────────────
# 对应 TS format/formatter.ts

_formatter_registry: dict[str, FormatterInfo] = {}


def _register(name: str, extensions: list[str], enabled_func, environment: dict | None = None):
    """注册格式化器"""
    _formatter_registry[name] = FormatterInfo(name, extensions, enabled_func, environment)


async def _gofmt_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("gofmt")
    if exe:
        return [exe, "-w", "$FILE"]
    return False

async def _mix_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("mix")
    if exe:
        return [exe, "format", "$FILE"]
    return False

async def _prettier_enabled(ctx: dict) -> list[str] | bool:
    items = _find_up("package.json", ctx.get("directory", ""), ctx.get("worktree", ""))
    for item in items:
        data = _read_json(item)
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "prettier" in deps:
            bin_path = _which("prettier") or _which("npx")
            if bin_path and "prettier" in bin_path:
                return [bin_path, "--write", "$FILE"]
            if _which("npx"):
                return ["npx", "prettier", "--write", "$FILE"]
    return False

async def _biome_enabled(ctx: dict) -> list[str] | bool:
    configs = ["biome.json", "biome.jsonc"]
    for cfg in configs:
        found = _find_up(cfg, ctx.get("directory", ""), ctx.get("worktree", ""))
        if found:
            bin_path = _which("@biomejs/biome") or _which("npx")
            if bin_path:
                if "@biomejs" in bin_path:
                    return [bin_path, "format", "--write", "$FILE"]
                return ["npx", "@biomejs/biome", "format", "--write", "$FILE"]
    return False

async def _zig_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("zig")
    if exe:
        return [exe, "fmt", "$FILE"]
    return False

async def _clang_enabled(ctx: dict) -> list[str] | bool:
    items = _find_up(".clang-format", ctx.get("directory", ""), ctx.get("worktree", ""))
    if items:
        exe = _which("clang-format")
        if exe:
            return [exe, "-i", "$FILE"]
    return False

async def _ktlint_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("ktlint")
    if exe:
        return [exe, "-F", "$FILE"]
    return False

async def _ruff_enabled(ctx: dict) -> list[str] | bool:
    if not _which("ruff"):
        return False
    configs = ["pyproject.toml", "ruff.toml", ".ruff.toml"]
    for cfg in configs:
        found = _find_up(cfg, ctx.get("directory", ""), ctx.get("worktree", ""))
        if found:
            if cfg == "pyproject.toml":
                content = Path(found[0]).read_text(encoding="utf-8")
                if "[tool.ruff]" in content:
                    return ["ruff", "format", "$FILE"]
            else:
                return ["ruff", "format", "$FILE"]
    # Fallback: 检查依赖
    for dep in ["requirements.txt", "pyproject.toml", "Pipfile"]:
        found = _find_up(dep, ctx.get("directory", ""), ctx.get("worktree", ""))
        if found:
            content = Path(found[0]).read_text(encoding="utf-8")
            if "ruff" in content:
                return ["ruff", "format", "$FILE"]
    return False

async def _rustfmt_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("rustfmt")
    if exe:
        return [exe, "$FILE"]
    return False

async def _shfmt_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("shfmt")
    if exe:
        return [exe, "-w", "$FILE"]
    return False

async def _dart_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("dart")
    if exe:
        return [exe, "format", "$FILE"]
    return False

async def _terraform_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("terraform")
    if exe:
        return [exe, "fmt", "$FILE"]
    return False

async def _nixfmt_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("nixfmt")
    if exe:
        return [exe, "$FILE"]
    return False

async def _rubocop_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("rubocop")
    if exe:
        return [exe, "--autocorrect", "$FILE"]
    return False

async def _latexindent_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("latexindent")
    if exe:
        return [exe, "-w", "-s", "$FILE"]
    return False

async def _gleam_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("gleam")
    if exe:
        return [exe, "format", "$FILE"]
    return False

async def _ocamlformat_enabled(ctx: dict) -> list[str] | bool:
    if not _which("ocamlformat"):
        return False
    items = _find_up(".ocamlformat", ctx.get("directory", ""), ctx.get("worktree", ""))
    if items:
        return ["ocamlformat", "-i", "$FILE"]
    return False

async def _ormolu_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("ormolu")
    if exe:
        return [exe, "-i", "$FILE"]
    return False

async def _cljfmt_enabled(ctx: dict) -> list[str] | bool:
    exe = _which("cljfmt")
    if exe:
        return [exe, "fix", "--quiet", "$FILE"]
    return False


# 注册所有内置格式化器
_register("gofmt", [".go"], _gofmt_enabled)
_register("mix", [".ex", ".exs", ".eex", ".heex", ".leex", ".neex", ".sface"], _mix_enabled)
_register("prettier", [
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml",
    ".md", ".mdx", ".graphql", ".gql",
], _prettier_enabled, {"BUN_BE_BUN": "1"})
_register("biome", [
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml",
    ".md", ".mdx", ".graphql", ".gql",
], _biome_enabled, {"BUN_BE_BUN": "1"})
_register("zig", [".zig", ".zon"], _zig_enabled)
_register("clang-format", [".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".h++", ".ino", ".C", ".H"], _clang_enabled)
_register("ktlint", [".kt", ".kts"], _ktlint_enabled)
_register("ruff", [".py", ".pyi"], _ruff_enabled)
_register("rustfmt", [".rs"], _rustfmt_enabled)
_register("shfmt", [".sh", ".bash"], _shfmt_enabled)
_register("dart", [".dart"], _dart_enabled)
_register("terraform", [".tf", ".tfvars"], _terraform_enabled)
_register("nixfmt", [".nix"], _nixfmt_enabled)
_register("rubocop", [".rb", ".rake", ".gemspec", ".ru"], _rubocop_enabled)
_register("latexindent", [".tex"], _latexindent_enabled)
_register("gleam", [".gleam"], _gleam_enabled)
_register("ocamlformat", [".ml", ".mli"], _ocamlformat_enabled)
_register("ormolu", [".hs"], _ormolu_enabled)
_register("cljfmt", [".clj", ".cljs", ".cljc", ".edn"], _cljfmt_enabled)


# ── Formatter 管理器 ────────────────────────────────────────

class Formatter:
    """格式化器 — 对应 TS Format.Service"""

    def __init__(self):
        self._formatters = dict(_formatter_registry)
        self._command_cache: dict[str, list[str] | bool] = {}

    def get_formatter(self, name: str) -> FormatterInfo | None:
        return self._formatters.get(name)

    def all_formatters(self) -> list[FormatterInfo]:
        return list(self._formatters.values())

    async def get_formatters_for_file(self, filepath: str, ctx: dict | None = None) -> list[tuple[FormatterInfo, list[str]]]:
        """获取适用于某文件的所有格式化器"""
        ext = Path(filepath).suffix
        ctx = ctx or {"directory": os.getcwd(), "worktree": os.getcwd()}
        result: list[tuple[FormatterInfo, list[str]]] = []
        for fmt in self._formatters.values():
            if ext in fmt.extensions:
                cmd = await self._check_formatter(fmt, ctx)
                if cmd:
                    result.append((fmt, cmd))
        return result

    async def _check_formatter(self, fmt: FormatterInfo, ctx: dict) -> list[str] | bool:
        if fmt.name in self._command_cache:
            cached = self._command_cache[fmt.name]
            if cached is False:
                return False
            return list(cached)  # type: ignore
        cmd = await fmt.enabled(ctx)
        self._command_cache[fmt.name] = cmd
        return cmd

    async def format_file(self, filepath: str, ctx: dict | None = None) -> bool:
        """格式化单个文件"""
        ctx = ctx or {"directory": os.getcwd(), "worktree": os.getcwd()}
        formatters = await self.get_formatters_for_file(filepath, ctx)
        if not formatters:
            return True

        success = True
        for fmt, cmd in formatters:
            replaced = [p.replace("$FILE", filepath) for p in cmd]
            r = _run(replaced, cwd=ctx.get("directory"))
            if r.returncode != 0:
                success = False
        return success

    # ── 文本处理工具 ──────────────────────────────────────

    @staticmethod
    def trim_lines(text: str, max_lines: int = 100) -> str:
        lines = text.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return text

    @staticmethod
    def strip_ansi(text: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    @staticmethod
    def camel_to_snake(text: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()

    @staticmethod
    def snake_to_camel(text: str) -> str:
        parts = text.split("_")
        return parts[0] + "".join(p.title() for p in parts[1:])

    @staticmethod
    def truncate(text: str, max_len: int = 200) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text

    @staticmethod
    def indent(text: str, level: int = 1, indent_str: str = "  ") -> str:
        prefix = indent_str * level
        return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


formatter = Formatter()
