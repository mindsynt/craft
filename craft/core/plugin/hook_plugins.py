"""Hook 插件 — 移植自 subagent-progress-checker.ts, checkpoint-splitover.ts"""

from __future__ import annotations

import asyncio
import logging
import os
import re as _re
import time
from typing import Any

from craft.config import CONFIG_DIR

from .shared import (
    async_plugin_hook,
    _async_read_text,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Subagent Progress Checker
# ──────────────────────────────────────────────

def make_subagent_progress_checker_plugin() -> dict[str, Any]:
    """子代理进度检查插件"""
    required_sections = [
        "## §1 Task identity",
        "## §2 Subagent intent",
        "## §3 Files and code sections",
        "## §4 Verbatim commands",
        "## §5 Outcome and discoveries",
    ]

    return {
        "name": "subagent-progress-checker",
        "actor.postStop": {
            "matcher": {
                "agentType": {
                    "excludeOnly": [
                        "checkpoint-writer",
                        "title",
                        "summary",
                        "dream",
                        "distill",
                        "compaction",
                        "main",
                    ],
                },
            },
            "run": async_plugin_hook(lambda input_data, output: _check_progress(input_data, output, required_sections)),
        },
    }


async def _check_progress(input_data: dict, output: dict, required_sections: list[str]) -> dict:
    """检查子代理进度"""
    task_id = input_data.get("task_id")
    if not task_id:
        return output  # no-op

    if input_data.get("canWrite") is False:
        return output

    file_path = _progress_path(input_data.get("sessionID", ""), task_id)

    body = None
    try:
        body = await _async_read_text(file_path)
    except Exception:
        body = None

    if body is None:
        output["continue"] = True
        output["reason"] = _build_progress_feedback("missing", task_id, file_path, required_sections=required_sections)
        return output

    missing = [s for s in required_sections if s not in body]
    if missing:
        output["continue"] = True
        output["reason"] = _build_progress_feedback("incomplete", task_id, file_path, missing=missing, required_sections=required_sections)
        return output

    # Inject frontmatter
    try:
        now = int(time.time() * 1000)
        frontmatter = f"---\nwritten-at: {now}\n---\n"
        # Replace existing frontmatter if present
        if _re.match(r"^---\n", body):
            body = _re.sub(r"^---\n.*?\n---\n", frontmatter, body, count=1, flags=_re.DOTALL)
        else:
            body = frontmatter + body
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(body)
    except Exception as e:
        logger.error(f"frontmatter injection failed: {e}")

    return output


def _progress_path(session_id: str, task_id: str) -> str:
    """获取进度文件路径"""
    state_dir = CONFIG_DIR / "state"
    return str(state_dir / "sessions" / session_id / "progress" / f"{task_id}.md")


PROGRESS_TEMPLATE = """## §1 Task identity
- task_id: {task_id}
- short summary: <one line>

## §2 Subagent intent
What this subagent was asked to do (one paragraph).

## §3 Files and code sections
- path/to/file.ext: <what you did with it>

## §4 Verbatim commands
Exact commands you ran or commands the user/task asked to be runnable later. Keep BACKTICK-FENCED for grep-ability.
```
<command>
```

## §5 Outcome and discoveries
- Outcome (success/partial/failed): <reason>
- Discoveries that may matter for other tasks: <bullets>
"""


def _build_progress_feedback(
    kind: str,
    task_id: str,
    file_path: str,
    missing: list[str] | None = None,
    required_sections: list[str] | None = None,
) -> str:
    """构建进度反馈消息"""
    if kind == "missing":
        return (
            f"Before terminating, write the task progress journal to:\n"
            f"  {file_path}\n\n"
            f"Required structure (5 sections, headings exact):\n\n"
            f"{PROGRESS_TEMPLATE.replace('{task_id}', task_id)}\n\n"
            f"Write the file now using the Write tool, then terminate normally."
        )

    lines = [
        f"tasks/{task_id}/progress.md exists but is missing required sections:",
    ]
    if missing:
        lines.extend(f"  - {s}" for s in missing)
    lines.extend([
        "",
        "Add the missing sections. For reference, the full required template is:",
        "",
        PROGRESS_TEMPLATE.replace("{task_id}", task_id),
        "",
        "Re-write the file using Write tool, then terminate normally.",
    ])
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Checkpoint Splitover
# ──────────────────────────────────────────────

def make_checkpoint_splitover_plugin() -> dict[str, Any]:
    """检查点拆分插件"""
    return {
        "name": "checkpoint-splitover",
        "actor.preStop": {
            "matcher": {"agentType": {"include": ["checkpoint-writer"]}},
            "run": async_plugin_hook(_run_checkpoint_splitover),
        },
    }


async def _run_checkpoint_splitover(input_data: dict, output: dict) -> dict:
    """运行检查点拆分"""
    session_id = input_data.get("parentSessionID", input_data.get("sessionID", ""))
    actor_id = input_data.get("actorID", "")

    try:
        project_id = input_data.get("project", {}).get("id", "")
        violations = await _run_validators_for_checkpoint(
            session_id,
            project_id=project_id,
        )
        if not violations:
            return output

        extract_required = [v for v in violations if v.get("severity") == "extract-required"]
        if extract_required:
            output["continue"] = True
            output["reason"] = _build_extraction_reflection(extract_required)
            return output

        errors = [v for v in violations if v.get("severity") == "error"]
        if errors:
            output["continue"] = True
            output["reason"] = _build_reflection_message(errors, session_id, project_id)
            return output

    except Exception as e:
        logger.error(f"checkpoint-splitover hook failed: {e}")

    return output


async def _run_validators_for_checkpoint(
    session_id: str,
    prior_titles: set[str] | None = None,
    expected_revisions: list[str] | None = None,
    project_id: str = "",
) -> list[dict]:
    """运行检查点验证器"""
    violations: list[dict] = []
    # Simplified validation logic
    if not session_id:
        violations.append({
            "type": "missing_session",
            "severity": "error",
            "message": "Session ID is required for checkpoint",
        })
    return violations


def _build_extraction_reflection(violations: list[dict]) -> str:
    """构建提取反射消息"""
    parts = ["The following checkpoint validations require extraction:"]
    for v in violations:
        parts.append(f"- {v.get('message', 'Unknown validation')}")
    return "\n".join(parts)


def _build_reflection_message(errors: list[dict], session_id: str, project_id: str) -> str:
    """构建反射消息"""
    parts = ["Checkpoint validation errors:"]
    for e in errors:
        parts.append(f"- {e.get('message', 'Unknown error')}")
    return "\n".join(parts)
