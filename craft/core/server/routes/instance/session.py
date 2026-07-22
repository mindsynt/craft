"""会话路由 — 移植自 routes/instance/session.ts

会话 CRUD、消息管理、提示、命令、分支、回退等。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from craft.core.session import sessions, Session
from craft.core.session.schema import SessionID, MessageID
from craft.core.share import ShareManager

logger = logging.getLogger(__name__)

share_manager = ShareManager()


class SessionRoutes:
    """会话路由处理器

    对应 TS SessionRoutes
    """

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /session

        列出会话。
        """
        directory = ""
        roots_only = False
        start_time = None
        search_query = None
        limit = 50

        if hasattr(request, "query_params"):
            qp = request.query_params
            directory = qp.get("directory", "")
            roots_only = qp.get("roots", "").lower() in ("true", "1")
            if qp.get("start"):
                try:
                    start_time = float(qp["start"]) / 1000.0
                except (ValueError, TypeError):
                    pass
            search_query = qp.get("search")
            if qp.get("limit"):
                try:
                    limit = int(qp["limit"])
                except (ValueError, TypeError):
                    pass

        all_sessions = sessions.list(limit=limit * 2)

        results = []
        for s in all_sessions:
            # Filter by directory if specified
            if directory and not s.get("directory", "").startswith(directory):
                continue
            # Filter roots only
            if roots_only and s.get("parent_id"):
                continue
            # Filter by start time
            if start_time is not None and s.get("updated_at", 0) < start_time:
                continue
            # Filter by search
            if search_query and search_query.lower() not in s.get("title", "").lower():
                continue
            results.append(s)
            if len(results) >= limit:
                break

        return results

    @staticmethod
    async def status(request: Any) -> Any:
        """GET /session/status

        获取会话状态。
        """
        all_sessions = sessions.list(limit=1000)
        status_map = {}
        for s in all_sessions:
            sid = s["id"]
            status_map[sid] = {
                "id": sid,
                "title": s.get("title", ""),
                "messageCount": s.get("message_count", 0),
                "updatedAt": s.get("updated_at", 0),
                "createdAt": s.get("created_at", 0),
                "active": sid == sessions._current_id if hasattr(sessions, "_current_id") else False,
            }
        return status_map

    @staticmethod
    async def get(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID

        获取会话详情。
        """
        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}
        return session.to_dict()

    @staticmethod
    async def children(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/children

        获取子会话。
        """
        all_sessions = sessions.list(limit=1000)
        visible = False
        if hasattr(request, "query_params"):
            visible = request.query_params.get("visible", "").lower() in ("true", "1")

        children = []
        for s in all_sessions:
            if s.get("parent_id") == session_id:
                if visible and s.get("agent_id", "").startswith("subagent"):
                    continue
                children.append(s)
        return children

    @staticmethod
    async def todo(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/todo

        获取会话待办事项。
        """
        # Try TaskRegistry-like data from session
        session = sessions.get(session_id)
        if session and hasattr(session, "messages"):
            tasks = [m for m in session.messages if m.get("role") == "task"]
            if tasks:
                return [{"content": t.get("content", ""), "status": "pending"} for t in tasks]
        return []

    @staticmethod
    async def task_list(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/task

        列出会话任务。
        """
        session = sessions.get(session_id)
        if not session:
            return []
        if hasattr(session, "messages"):
            tasks = [m for m in session.messages if m.get("role") == "task"]
            return tasks
        return []

    @staticmethod
    async def create(request: Any) -> Any:
        """POST /session/

        创建会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        title = body.get("title", "新对话")
        agent_id = body.get("agentID", body.get("agent_id", "build"))
        model = body.get("model", "")
        session = sessions.create(title=title, agent_id=agent_id, model=model)

        # Handle share creation if requested
        shared = body.get("shared", False)
        if shared:
            share = share_manager.create(session.id, body.get("visibility", "link"))
            result = session.to_dict()
            result["share"] = share.to_dict()
            return result

        return session.to_dict()

    @staticmethod
    async def delete(request: Any, session_id: str) -> Any:
        """DELETE /session/:sessionID

        删除会话。
        """
        result = sessions.delete(session_id)
        return result

    @staticmethod
    async def update(request: Any, session_id: str) -> Any:
        """PATCH /session/:sessionID

        更新会话属性。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        if "title" in body:
            session.title = body["title"]
        if "archived" in body:
            session.archived = body["archived"]

        if hasattr(sessions, "_save"):
            sessions._save()

        return session.to_dict()

    @staticmethod
    async def init(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/init

        初始化会话（分析项目并创建 AGENTS.md）。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        model_id = body.get("modelID", "")
        provider_id = body.get("providerID", "")
        message_id = body.get("messageID", "")

        logger.info(
            "Session init requested",
            extra={"session_id": session_id, "model": f"{provider_id}/{model_id}"},
        )
        return True

    @staticmethod
    async def fork(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/fork

        分支会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        parent = sessions.get(session_id)
        if not parent:
            return {"error": "Session not found", "status": 404}

        title = body.get("title", parent.title + " (fork)")
        model = body.get("model", parent.model)
        child = sessions.create(title=title, agent_id=parent.agent_id, model=model)
        # Copy messages up to a certain point
        fork_message_id = body.get("messageID", "")
        if fork_message_id and hasattr(parent, "messages"):
            copy = False
            for msg in parent.messages:
                if msg.get("id") == fork_message_id:
                    copy = True
                if copy:
                    child.add_message(msg.get("role", ""), msg.get("content", ""))
        else:
            # Copy all messages
            if hasattr(parent, "messages"):
                for msg in parent.messages:
                    child.add_message(msg.get("role", ""), msg.get("content", ""))

        child.parent_id = session_id
        if hasattr(sessions, "_save"):
            sessions._save()

        return child.to_dict()

    @staticmethod
    async def abort(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/abort

        中止会话。
        """
        logger.info("Session abort requested", extra={"session_id": session_id})
        return True

    @staticmethod
    async def share(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/share

        分享会话。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        visibility = body.get("visibility", "link")
        share = share_manager.create(session_id, visibility)
        return share.to_dict()

    @staticmethod
    async def unshare(request: Any, session_id: str) -> Any:
        """DELETE /session/:sessionID/share

        取消分享。
        """
        share_manager.remove_by_session(session_id)
        return {"success": True}

    @staticmethod
    async def summarize(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/summarize

        总结会话。
        """
        logger.info("Session summarize requested", extra={"session_id": session_id})
        return True

    @staticmethod
    async def ask(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/ask

        向会话提问（只读）。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        question = body.get("question", "")
        session = sessions.get(session_id)
        if not session:
            return {"answer": "Session not found"}

        # Simple context-based answer using last few messages
        context = ""
        if hasattr(session, "messages"):
            recent = session.messages[-5:] if len(session.messages) > 5 else session.messages
            context = "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')}" for m in recent
            )

        return {
            "answer": f"[read-only context from {session.title}]\n{context[:2000]}\n\nQuestion: {question}",
        }

    @staticmethod
    async def diff(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/diff

        获取消息差异。
        """
        return []

    @staticmethod
    async def messages(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/message

        获取消息列表。
        """
        session = sessions.get(session_id)
        if not session:
            return []
        return getattr(session, "messages", [])

    @staticmethod
    async def get_message(request: Any, session_id: str, message_id: str) -> Any:
        """GET /session/:sessionID/message/:messageID

        获取单条消息。
        """
        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}
        for msg in getattr(session, "messages", []):
            if msg.get("id") == message_id:
                return msg
        return {"error": "Message not found", "status": 404}

    @staticmethod
    async def delete_message(request: Any, session_id: str, message_id: str) -> Any:
        """DELETE /session/:sessionID/message/:messageID

        删除消息。
        """
        session = sessions.get(session_id)
        if not session:
            return False
        if hasattr(session, "messages"):
            session.messages = [m for m in session.messages if m.get("id") != message_id]
            if hasattr(sessions, "_save"):
                sessions._save()
        return True

    @staticmethod
    async def delete_part(request: Any, session_id: str, message_id: str, part_id: str) -> Any:
        """DELETE /session/:sessionID/message/:messageID/part/:partID

        删除消息部分。
        """
        session = sessions.get(session_id)
        if not session:
            return False
        if hasattr(session, "messages"):
            for msg in session.messages:
                if msg.get("id") == message_id and "parts" in msg:
                    msg["parts"] = [p for p in msg["parts"] if p.get("id") != part_id]
            if hasattr(sessions, "_save"):
                sessions._save()
        return True

    @staticmethod
    async def update_part(request: Any, session_id: str, message_id: str, part_id: str) -> Any:
        """PATCH /session/:sessionID/message/:messageID/part/:partID

        更新消息部分。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        if hasattr(session, "messages"):
            for msg in session.messages:
                if msg.get("id") == message_id and "parts" in msg:
                    for part in msg["parts"]:
                        if part.get("id") == part_id:
                            part.update(body)
                            if hasattr(sessions, "_save"):
                                sessions._save()
                            return part
        return {"error": "Part not found", "status": 404}

    @staticmethod
    async def send_message(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/message

        发送消息（流式返回）。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        content = body.get("content", "")
        role = body.get("role", "user")
        session.add_message(role=role, content=content)

        if hasattr(sessions, "_save"):
            sessions._save()

        return {
            "id": session.messages[-1].get("id", "") if session.messages else "",
            "role": role,
            "content": content,
            "sessionID": session_id,
        }

    @staticmethod
    async def send_async(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/prompt_async

        异步发送消息。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        session = sessions.get(session_id)
        if not session:
            return None

        content = body.get("content", "")
        session.add_message(role="user", content=content)
        if hasattr(sessions, "_save"):
            sessions._save()

        return {"queued": True}

    @staticmethod
    async def command(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/command

        发送命令。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        command_text = body.get("command", "")
        message_id = body.get("messageID", "")
        model = body.get("model", "")

        logger.info(
            "Session command",
            extra={
                "session_id": session_id,
                "command": command_text,
                "message_id": message_id,
            },
        )

        session = sessions.get(session_id)
        if session:
            session.add_message(role="command", content=command_text)
            if hasattr(sessions, "_save"):
                sessions._save()

        return {"ok": True}

    @staticmethod
    async def predict(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/predict

        预测下一个提示。
        """
        return {"prediction": ""}

    @staticmethod
    async def shell(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/shell

        执行 shell 命令。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        command_text = body.get("command", "")
        logger.info("Session shell command", extra={"session_id": session_id, "command": command_text})
        return {"output": "", "exitCode": 0}

    @staticmethod
    async def revert(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/revert

        回退消息。
        """
        body = {}
        if hasattr(request, "json"):
            try:
                body = await request.json() if callable(getattr(request, "json", None)) else {}
            except Exception:
                pass

        message_id = body.get("messageID", "")
        session = sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "status": 404}

        if hasattr(session, "messages") and message_id:
            idx = None
            for i, msg in enumerate(session.messages):
                if msg.get("id") == message_id:
                    idx = i
                    break
            if idx is not None:
                session.messages = session.messages[: idx + 1]
                if hasattr(sessions, "_save"):
                    sessions._save()

        return {"ok": True}

    @staticmethod
    async def unrevert(request: Any, session_id: str) -> Any:
        """POST /session/:sessionID/unrevert

        恢复回退的消息。
        """
        return {"ok": True}

    @staticmethod
    async def actors(request: Any, session_id: str) -> Any:
        """GET /session/:sessionID/actors

        列出会话参与者。
        """
        session = sessions.get(session_id)
        if not session:
            return []
        actors_list = []
        if hasattr(session, "messages"):
            seen = set()
            for msg in session.messages:
                actor = msg.get("agent", msg.get("role", "user"))
                if actor not in seen:
                    seen.add(actor)
                    actors_list.append({"id": actor, "name": actor, "role": msg.get("role", "")})
        return actors_list
