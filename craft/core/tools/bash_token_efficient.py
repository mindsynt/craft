"""Token-efficient bash output post-processing — 移植自
packages/opencode/src/tool/bash_token_efficient_pipeline.ts
packages/opencode/src/tool/bash_token_efficient_heuristic.ts

Pipeline for cleaning bash tool output: ANSI strip, secret redaction,
long-line elision, progress folding, and heuristic shape-based
command-specific rewriting (git diff, pytest, npm, make, tsc, etc.).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

MAX_LINE_CHARS = int(os.environ.get("MIMOCODE_EXPERIMENTAL_TOKEN_EFFICIENCY_MAX_LINE_CHARS", "500"))
LINE_HEAD_KEEP = int(os.environ.get("MIMOCODE_EXPERIMENTAL_TOKEN_EFFICIENCY_LINE_HEAD_KEEP", "160"))
NEVER_WORSE_MARGIN = int(os.environ.get("MIMOCODE_EXPERIMENTAL_TOKEN_EFFICIENCY_NEVER_WORSE_MARGIN", "0"))

SKIP_MARKERS = ["# nofilter", "# raw"]
ENV_SKIP = os.environ.get("MIMOCODE_BASH_RAW", "") == "1"

# ANSI patterns
ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
ANSI_DCS = re.compile(r"\x1b[PX^_][\s\S]*?\x1b\\")
BACKSPACE = re.compile(r"[^\n]\x08")
CTRL_BYTES = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Redact patterns
REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(Bearer|Token)\s+[A-Za-z0-9._\-+/=]{16,}", re.IGNORECASE), r"\1 <redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "<redacted-jwt>"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "<redacted-aws-key>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<redacted-gh-token>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "<redacted-openai-key>"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "<redacted-anthropic-key>"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), "<redacted-slack-token>"),
    (re.compile(r"\b((?:api|access|refresh|secret|client|auth)[_-]?(?:key|token|secret|password))(\s*[:=]\s*)[\"']?[A-Za-z0-9._\-+/=]{12,}[\"']?", re.IGNORECASE), r"\1\2<redacted>"),
]

PEM_BLOCK = re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----")

# ═══════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════

CleanOptions = dict | None
CleanResult = dict  # {"text": str, "bytesIn": int, "bytesOut": int, "degraded": bool}
CleanPlugin = Callable[[str, CleanOptions], str]


def make_clean_result(text: str, bytes_in: int, bytes_out: int, degraded: bool) -> dict:
    return {"text": text, "bytesIn": bytes_in, "bytesOut": bytes_out, "degraded": degraded}


def _should_skip(command: str | None) -> bool:
    if ENV_SKIP:
        return True
    if not command:
        return False
    return any(marker in command for marker in SKIP_MARKERS)


# ═══════════════════════════════════════════════════════════
# Plugins
# ═══════════════════════════════════════════════════════════

def progress_plugin() -> CleanPlugin:
    """Fold \r-redrawn lines — only the segment after the LAST \r survives."""
    def _apply(text: str, _options: CleanOptions = None) -> str:
        if "\r" not in text:
            return text
        lines = []
        for line in text.split("\n"):
            stripped = line[:-1] if line.endswith("\r") else line
            idx = stripped.rfind("\r")
            lines.append(stripped[idx + 1:] if idx >= 0 else stripped)
        return "\n".join(lines)
    return _apply


def ansi_plugin() -> CleanPlugin:
    """Strip ANSI escapes, backspace overstrike, control bytes."""
    def _apply(text: str, _options: CleanOptions = None) -> str:
        out = ANSI_CSI.sub("", text)
        out = ANSI_OSC.sub("", out)
        out = ANSI_DCS.sub("", out)
        while BACKSPACE.search(out):
            out = BACKSPACE.sub("", out)
        return CTRL_BYTES.sub("", out)
    return _apply


def redact_plugin() -> CleanPlugin:
    """Re-mask common secret shapes."""
    def _apply(text: str, _options: CleanOptions = None) -> str:
        out = PEM_BLOCK.sub("<redacted-pem-block>", text)
        for pattern, replacement in REDACT_PATTERNS:
            out = pattern.sub(replacement, out)
        return out
    return _apply


def long_line_plugin() -> CleanPlugin:
    """Elide lines longer than MAX_LINE_CHARS."""
    def _apply(text: str, _options: CleanOptions = None) -> str:
        if len(text) <= MAX_LINE_CHARS:
            return text
        lines = []
        for line in text.split("\n"):
            if len(line) <= MAX_LINE_CHARS:
                lines.append(line)
            else:
                lines.append(f"{line[:LINE_HEAD_KEEP]}…<elided {len(line) - LINE_HEAD_KEEP} chars>")
        return "\n".join(lines)
    return _apply


def default_plugins() -> list[CleanPlugin]:
    """Default plugin chain: progress → ansi → redact → longline."""
    return [progress_plugin(), ansi_plugin(), redact_plugin(), long_line_plugin()]


# ═══════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════

def create_pipeline(plugins: list[CleanPlugin] | None = None):
    """Pipeline factory. Composes plugins with never-worse guard."""
    if plugins is None:
        plugins = default_plugins()

    def _run(text: str, options: CleanOptions = None) -> dict:
        if options is None:
            options = {}
        bytes_in = len(text.encode("utf-8"))
        if not text or _should_skip(options.get("command")):
            return make_clean_result(text, bytes_in, bytes_in, False)

        out = text
        for plugin in plugins:
            out = plugin(out, options)

        bytes_out = len(out.encode("utf-8"))
        if bytes_out + NEVER_WORSE_MARGIN >= bytes_in:
            return make_clean_result(text, bytes_in, bytes_in, True)
        return make_clean_result(out, bytes_in, bytes_out, False)

    return {"plugins": plugins, "run": _run}


_default_pipeline = create_pipeline()


def clean(text: str, options: CleanOptions = None) -> dict:
    """Public entry point — backward-compatible signature."""
    if options is None:
        options = {}
    return _default_pipeline["run"](text, options)


# ═══════════════════════════════════════════════════════════
# Heuristic shapes (bash_token_efficient_heuristic.ts)
# ═══════════════════════════════════════════════════════════

ShapeContext = dict  # {"command": str, "head4k": str, "tail4k": str}
Shape = dict  # {"id": str, "match": Callable, "apply": Callable}
HEAD_TAIL_BYTES = 4096

# Passthrough patterns — user already asked for machine-readable output
PASSTHROUGH_PATTERNS: list[re.Pattern] = [
    re.compile(r"(^|\s)--json(\s|=|$)"),
    re.compile(r"(^|\s)--format[= ]json(\s|$)"),
    re.compile(r"(^|\s)-o[= ]json(\s|$)"),
    re.compile(r"(^|\s)--no-color(\s|$)"),
    re.compile(r"\|\s*tee(\s|$)"),
    re.compile(r"\|\s*xxd(\s|$)"),
    re.compile(r"\|\s*hexdump(\s|$)"),
]

# Command-name channel
COMMAND_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*pytest(\s|$)"), "pytest"),
    (re.compile(r"^\s*(?:npm|pnpm|yarn)\s+(?:install|i|add)(\s|$)"), "npm"),
    (re.compile(r"^\s*(?:make|cmake|automake)(\s|$)"), "make"),
    (re.compile(r"^\s*git\s+(?:diff|show)(\s|$)"), "gitdiff"),
    (re.compile(r"^\s*tsc(\s|$)"), "tsc"),
    (re.compile(r"^\s*kubectl\s+get\s+pods?(\s|$)"), "kubectl"),
    (re.compile(r"^\s*go\s+test.*-json"), "gostest"),
    (re.compile(r"^\s*gh\s+(?:pr|issue)\s+view(\s|$)"), "md"),
]

# Body-fingerprint channel
BODY_FINGERPRINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^={5,}\s+test session starts\s+={5,}", re.MULTILINE), "pytest"),
    (re.compile(r"^diff --git ", re.MULTILINE), "gitdiff"),
    (re.compile(r"^Traceback \(most recent call last\)", re.MULTILINE), "stacktrace"),
    (re.compile(r"^\s*at .+:\d+:\d+", re.MULTILINE), "stacktrace"),
    (re.compile(r"^error\[E\d+\]:", re.MULTILINE), "stacktrace"),
]

GITDIFF_NOISE_PATHS = re.compile(
    r"(?:^|/)(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock|composer\.lock|"
    r"Cargo\.lock|Gemfile\.lock|poetry\.lock|uv\.lock|.*\.min\.js|.*\.min\.css|"
    r"dist/.*|build/.*|node_modules/.*|.*\.generated\..*)$"
)


def _shape_for(ctx: ShapeContext) -> str | None:
    """Detect shape from command name or body fingerprint."""
    command = ctx.get("command", "")
    for pattern, shape_id in COMMAND_PATTERNS:
        if pattern.search(command):
            return shape_id
    head4k = ctx.get("head4k", "")
    for pattern, shape_id in BODY_FINGERPRINTS:
        if pattern.search(head4k):
            return shape_id
    if re.match(r"^\s*[\{\[]", head4k):
        return "json"
    return None


def _clean_heuristic(text: str, options: CleanOptions = None) -> dict:
    """Run heuristic shape-based post-processing on bash output.

    Public entry point: cleanHeuristic(text, {"command": "..."}).
    Same never-worse contract as the common pipeline.
    """
    if options is None:
        options = {}
    command = options.get("command", "") or ""

    bytes_in = len(text.encode("utf-8"))

    # Passthrough check
    if any(p.search(command) for p in PASSTHROUGH_PATTERNS):
        return make_clean_result(text, bytes_in, bytes_in, False)

    head4k = text[:HEAD_TAIL_BYTES]
    tail4k = text[-HEAD_TAIL_BYTES:] if len(text) > HEAD_TAIL_BYTES else ""

    shape_id = _shape_for({"command": command, "head4k": head4k, "tail4k": tail4k})
    if shape_id is None:
        return make_clean_result(text, bytes_in, bytes_in, False)

    # Apply the matching shape
    shape_appliers: dict[str, Callable[[str], str]] = {
        "gitdiff": _shape_gitdiff,
        "pytest": _shape_pytest,
        "npm": _shape_npm,
        "make": _shape_make,
        "stacktrace": _shape_stacktrace,
        "tsc": _shape_tsc,
        "kubectl": _shape_kubectl,
        "json": _shape_json,
        "md": _shape_md,
        "gostest": _shape_go_test,
    }

    applier = shape_appliers.get(shape_id)
    if applier is None:
        return make_clean_result(text, bytes_in, bytes_in, False)

    out = applier(text)
    bytes_out = len(out.encode("utf-8"))

    if bytes_out + NEVER_WORSE_MARGIN >= bytes_in:
        return make_clean_result(text, bytes_in, bytes_in, True)

    return make_clean_result(out, bytes_in, bytes_out, False)


# --- Shape: git diff / git show ---
def _shape_gitdiff(body: str) -> str:
    files = re.split(r"(?=^diff --git )", body, flags=re.MULTILINE)
    out: list[str] = []
    for file in files:
        if not file.startswith("diff --git"):
            out.append(file)
            continue
        path_match = re.search(r"^diff --git a/(\S+) b/(\S+)", file, re.MULTILINE)
        target_path = path_match.group(2) if path_match else (path_match.group(1) if path_match else "")
        header_lines: list[str] = []
        hunk_lines: list[str] = []
        in_hunk = False
        for line in file.split("\n"):
            if line.startswith("@@"):
                in_hunk = True
                hunk_lines.append(line)
                continue
            if not in_hunk:
                header_lines.append(line)
                continue
            hunk_lines.append(line)

        if target_path and GITDIFF_NOISE_PATHS.search(target_path):
            added = sum(1 for l in hunk_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in hunk_lines if l.startswith("-") and not l.startswith("---"))
            out.append(f"{chr(10).join(header_lines)}\n<hunks suppressed: generated/lockfile — +{added} -{removed}>")
            continue

        # Cap single-hunk length at 100 lines
        capped: list[str] = []
        current_hunk_start = -1
        current_hunk_len = 0
        for i, line in enumerate(hunk_lines):
            if line.startswith("@@"):
                current_hunk_start = len(capped)
                current_hunk_len = 0
                capped.append(line)
                continue
            current_hunk_len += 1
            if current_hunk_len <= 100:
                capped.append(line)
                continue
            if current_hunk_len == 101 and current_hunk_start >= 0:
                capped.append(f"<hunk elided: {len(hunk_lines) - i} more lines>")

        added = sum(1 for l in capped if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in capped if l.startswith("-") and not l.startswith("---"))
        out.append(f"{chr(10).join(header_lines)}\n{chr(10).join(capped)}\n<file summary: +{added} -{removed}>")

    return "".join(out)


# --- Shape: pytest ---
def _shape_pytest(body: str) -> str:
    lines = body.split("\n")
    phase = "header"
    out: list[str] = []
    for line in lines:
        if re.match(r"^={5,}\s+test session starts\s+={5,}", line):
            phase = "header"
            out.append(line)
            continue
        if re.match(r"^={3,}\s+FAILURES\s+={3,}", line):
            phase = "failures"
            out.append(line)
            continue
        if re.match(r"^={3,}\s+short test summary info\s+={3,}", line):
            phase = "summary"
            out.append(line)
            continue
        if re.match(r"^={3,}\s+.*(?:passed|failed|error).*={3,}$", line):
            out.append(line)
            continue
        if phase == "header":
            if re.match(r"^collected \d+ item", line) or re.match(r"^platform |^rootdir:|^plugins:", line):
                out.append(line)
            if re.match(r"\.\.\s+\[\s*\d+%\]$", line) or re.match(r"^\S+\.py\s+[.FEsx]+", line):
                phase = "progress"
            continue
        if phase == "progress":
            if line.startswith("FAILED "):
                out.append(line)
            continue
        if phase == "failures":
            if line.startswith("E ") or line.startswith("E\t"):
                out.append(line)
                continue
            if re.match(r"^[^\s].*\.py:\d+:", line) or re.match(r"^\S+:\d+:", line):
                out.append(line)
                continue
            if line.startswith("FAILED "):
                out.append(line)
            continue
        if phase == "summary":
            out.append(line)
    return "\n".join(out)


# --- Shape: npm / pnpm / yarn install ---
def _shape_npm(body: str) -> str:
    lines = body.split("\n")
    out: list[str] = []
    deprecated: list[str] = []

    def flush_deprecated():
        if not deprecated:
            return
        top = ", ".join(deprecated[:3])
        out.append(f"<[×{len(deprecated)}] deprecation warnings: top: {top}>")
        deprecated.clear()

    deprecation_re = re.compile(r"^(?:npm\s+warn|npm\s+WARN)\s+deprecated\s+([^\s@:]+)")
    for line in lines:
        m = deprecation_re.match(line)
        if m:
            deprecated.append(m.group(1))
            continue
        flush_deprecated()
        if re.search(r"^added \d+ packages?", line):
            out.append(line)
            continue
        if re.search(r"^\s*\d+ vulnerabilit", line) or re.search(r"found \d+ vulnerabilit", line):
            out.append(line)
            continue
        if re.search(r"^\s*\d+ packages? are looking for funding", line):
            out.append(line)
            continue
        if re.match(r"^npm\s+(?:warn|err|WARN|ERR)", line) and not deprecation_re.match(line):
            out.append(line)
            continue
        if not line.strip():
            out.append(line)
    flush_deprecated()
    return "\n".join(out)


# --- Shape: make / cmake / automake ---
def _shape_make(body: str) -> str:
    lines = body.split("\n")
    out: list[str] = []
    for line in lines:
        if re.match(r"^make(?:\[\d+\])?: (?:Entering|Leaving) directory", line):
            continue
        if re.match(r"^(?:cc|gcc|clang|clang\+\+|g\+\+|ld|ar)\b.*(?:-o|-c|-I)", line):
            continue
        if re.match(r"^\s*\^~*\s*$", line):
            continue
        out.append(line)
    return "\n".join(out)


# --- Shape: stacktrace ---
def _shape_stacktrace(body: str) -> str:
    dep_frame_re = re.compile(
        r"(?:site-packages|\.venv/|node_modules/|/dist-packages/|"
        r"python\d+\.\d+/(?:lib|http|urllib|logging|socket|threading|asyncio)/|"
        r"/std/|/rustc/)"
    )
    lines = body.split("\n")
    out: list[str] = []
    dep_run = 0

    def flush():
        nonlocal dep_run
        if dep_run > 0:
            out.append(f"  <[{dep_run} dependency frame(s) suppressed]>")
            dep_run = 0

    for line in lines:
        is_frame = bool(re.match(r'^\s*File "', line) or re.match(r"^\s*at .+:\d+", line) or re.match(r"^\s*\d+:\s*\d+\s+", line))
        if is_frame and dep_frame_re.search(line):
            dep_run += 1
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out)


# --- Shape: tsc ---
def _shape_tsc(body: str) -> str:
    tsc_line_re = re.compile(r"^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)$")
    lines = body.split("\n")
    by_code: dict[str, int] = {}
    by_file: dict[str, int] = {}
    passthrough: list[str] = []
    samples_code: dict[str, str] = {}
    samples_file: dict[str, str] = {}

    for line in lines:
        m = tsc_line_re.match(line)
        if not m:
            if line.strip():
                passthrough.append(line)
            continue
        file = m.group(1)
        code = m.group(4)
        by_code[code] = by_code.get(code, 0) + 1
        if code not in samples_code:
            samples_code[code] = line
        by_file[file] = by_file.get(file, 0) + 1
        if file not in samples_file:
            samples_file[file] = line

    if not by_code:
        return body

    top_codes = sorted(by_code.items(), key=lambda x: -x[1])[:5]
    top_files = sorted(by_file.items(), key=lambda x: -x[1])[:8]

    out: list[str] = []
    out.append("<tsc: top errors by code>")
    for code, count in top_codes:
        out.append(f"  {code} ×{count}  |  {samples_code[code]}")
    out.append("<tsc: top files>")
    for file, count in top_files:
        out.append(f"  {file} ×{count}  |  {samples_file[file]}")
    if passthrough:
        out.append("<tsc: other>")
        out.extend(passthrough[:20])

    return "\n".join(out)


# --- Shape: kubectl get pods ---
def _shape_kubectl(body: str) -> str:
    lines = body.split("\n")
    out: list[str] = []
    run = 0
    buffered_run: list[str] = []
    run_re = re.compile(r"\s+Running\s+.*\s+0\s+")

    def flush():
        nonlocal run
        if run < 2:
            out.extend(buffered_run)
        else:
            out.append(f"<[{run} pods folded — all Running, 0 restarts]>")
        buffered_run.clear()
        run = 0

    for line in lines:
        if run_re.search(line):
            run += 1
            buffered_run.append(line)
            continue
        flush()
        out.append(line)
    flush()
    out.append("<tip: rerun with -o json for a machine-readable projection>")
    return "\n".join(out)


# --- Shape: json ---
JSON_HEAVY_KEYS: set[str] = {
    "embedding", "embeddings", "raw_html", "rawHtml", "body", "content", "base64", "data",
}


def _trim_json_heavy(value: Any) -> Any:
    if isinstance(value, list):
        return [_trim_json_heavy(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            if key in JSON_HEAVY_KEYS and isinstance(sub, str) and len(sub) > 200:
                out[key] = f"<elided {len(sub)} chars>"
                continue
            if key in JSON_HEAVY_KEYS and isinstance(sub, list) and len(sub) > 20:
                out[key] = f"<elided {len(sub)} items>"
                continue
            out[key] = _trim_json_heavy(sub)
        return out
    return value


def _shape_json(body: str) -> str:
    trimmed = body.strip()
    if not trimmed:
        return body
    try:
        parsed = json.loads(trimmed)
        shrunk = _trim_json_heavy(parsed)
        return json.dumps(shrunk, indent=2)
    except (json.JSONDecodeError, TypeError):
        return body


# --- Shape: markdown ---
def _shape_md(body: str) -> str:
    out = body
    out = re.sub(r"<!--[\s\S]*?-->", "", out)
    lines = out.split("\n")
    lines = [l for l in lines if not re.match(r'^!\[.*?\]\(https?://(?:img\.shields\.io|badge\.fury\.io)', l)]
    lines = [l for l in lines if not re.match(r'^!\[[^\]]*\]\([^)]+\)\s*$', l)]
    lines = [l for l in lines if not re.match(r'^\s*-{3,}\s*$', l)]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


# --- Shape: gostest (go test -json) ---
def _shape_go_test(body: str) -> str:
    per: dict[str, dict] = {}
    for raw_line in body.split("\n"):
        if not raw_line.strip():
            continue
        try:
            evt = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue
        pkg = evt.get("Package", "")
        if pkg not in per:
            per[pkg] = {"pass": 0, "fail": 0, "skip": 0, "output": []}
        action = evt.get("Action")
        if action == "pass":
            per[pkg]["pass"] += 1
        elif action == "fail":
            per[pkg]["fail"] += 1
        elif action == "skip":
            per[pkg]["skip"] += 1
        output = evt.get("Output", "")
        if output:
            per[pkg]["output"].append(output.strip())

    parts: list[str] = []
    for pkg, data in per.items():
        parts.append(f"<package {pkg}: +{data['pass']} -{data['fail']} ~{data['skip']}>")
        for line in data["output"][:5]:
            parts.append(f"  {line}")
        if len(data["output"]) > 5:
            parts.append(f"  <{len(data['output']) - 5} more lines>")

    return "\n".join(parts) if parts else body


# Combined clean pipeline — applies basic pipeline then heuristic shapes
def clean_bash_output(text: str, options: CleanOptions = None) -> dict:
    """Full cleaning pipeline: basic clean + heuristic shape.

    Equivalent to running the pipeline then the heuristic cleaner.
    """
    if options is None:
        options = {}

    # Step 1: Basic pipeline (progress, ansi, redact, longline)
    basic = _default_pipeline["run"](text, options)

    # Step 2: Heuristic shapes
    return _clean_heuristic(basic["text"], options)
