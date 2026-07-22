"""工作流路由 — 移植自 routes/instance/workflows.ts

动态工作流运行列表、恢复、转录、结构。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from craft.core.session.schema import SessionID

logger = logging.getLogger(__name__)

# In-memory workflow runtime storage
_workflow_runs: dict[str, dict[str, Any]] = {}
_workflow_runtime_active = False


class WorkflowRoutes:
    """工作流路由处理器

    对应 TS WorkflowRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /workflows/

        列出工作流运行。
        """
        session_id = ""
        if hasattr(request, "query_params"):
            session_id = request.query_params.get("sessionID", "")

        if not session_id:
            return {"error": "sessionID is required", "status": 400}

        if not _workflow_runtime_active:
            return []

        runs = []
        for run_id, run in _workflow_runs.items():
            if run.get("sessionID") == session_id:
                runs.append(run)
        return runs

    @staticmethod
    async def resume(request: Any, run_id: str) -> Any:
        """POST /workflows/:runID/resume

        恢复工作流。
        """
        # Validate run_id format
        if not re.match(r"^wf_[0-9A-Za-z]{26}$", run_id):
            return {"runID": run_id, "resumed": False}

        if not _workflow_runtime_active:
            return {"runID": run_id, "resumed": False}

        run = _workflow_runs.get(run_id)
        if not run:
            return {"runID": run_id, "resumed": False}

        run["status"] = "resumed"
        return {"runID": run_id, "resumed": True}

    @staticmethod
    async def transcript(request: Any, run_id: str) -> Any:
        """GET /workflows/:runID/transcript

        获取工作流转录。
        """
        # Accept wider run_id format for read-only routes
        if not re.match(r"^wf_(?:[0-9A-Za-z]{26}|[0-9a-f]{64})$", run_id):
            return {"runID": run_id, "transcript": []}

        if not _workflow_runtime_active:
            return {"runID": run_id, "transcript": []}

        run = _workflow_runs.get(run_id)
        if not run:
            return {"runID": run_id, "transcript": []}

        return {"runID": run_id, "transcript": run.get("transcript", [])}

    @staticmethod
    async def structure(request: Any, run_id: str) -> Any:
        """GET /workflows/:runID/structure

        获取工作流结构树。
        """
        if not re.match(r"^wf_(?:[0-9A-Za-z]{26}|[0-9a-f]{64})$", run_id):
            return {"runID": run_id, "nodes": []}

        if not _workflow_runtime_active:
            return {"runID": run_id, "nodes": []}

        run = _workflow_runs.get(run_id)
        if not run:
            return {"runID": run_id, "nodes": []}

        return {"runID": run_id, "nodes": run.get("nodes", [])}
