"""MCP Exa search tool — searches the web via the Exa MCP API.

移植自 MiMo-Code packages/opencode/src/tool/mcp-exa.ts
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_EXA_URL = "https://mcp.exa.ai/mcp"
DEFAULT_TIMEOUT = 30.0


def _get_exa_url() -> str:
    """Get the Exa API URL, including API key if available."""
    api_key = os.environ.get("EXA_API_KEY")
    if api_key:
        return f"https://mcp.exa.ai/mcp?exaApiKey={api_key}"
    return DEFAULT_EXA_URL


def _parse_sse(body: str) -> str | None:
    """Parse an SSE response from Exa MCP."""
    for line in body.split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]  # Remove "data: " prefix
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        result = data.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text = content[0].get("text")
            if text:
                return text
    return None


async def search_exa(query: str, num_results: int = 10) -> str:
    """Search Exa for the given query.

    Args:
        query: The search query
        num_results: Number of results to return (default 10)

    Returns:
        Search result text, or error message.
    """
    url = _get_exa_url()
    request_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {
                "query": query,
                "type": "keyword",
                "numResults": num_results,
                "livecrawl": "always",
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                url,
                json=request_body,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            text = response.text
            result = _parse_sse(text)
            if result:
                return result
            # Fallback: try parsing as JSON
            try:
                data = response.json()
                result_obj = data.get("result", {})
                content = result_obj.get("content", [])
                if content:
                    return content[0].get("text", json.dumps(result_obj, ensure_ascii=False))
                return json.dumps(data, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                return text[:50000]

    except httpx.TimeoutException:
        return "[Exa search timed out]"
    except httpx.HTTPStatusError as e:
        return f"[Exa HTTP {e.response.status_code}] {e.response.text[:500]}"
    except Exception as e:
        return f"[Exa search error] {e}"


async def search_exa_code(query: str, num_results: int = 10) -> str:
    """Search Exa for code (specialized code search).

    Args:
        query: Code search query
        num_results: Number of results

    Returns:
        Search result text, or error message.
    """
    url = _get_exa_url()
    request_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "code_search",
            "arguments": {
                "query": query,
                "tokensNum": num_results,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                url,
                json=request_body,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result = _parse_sse(response.text)
            return result or "[No results from Exa code search]"

    except httpx.TimeoutException:
        return "[Exa code search timed out]"
    except httpx.HTTPStatusError as e:
        return f"[Exa HTTP {e.response.status_code}] {e.response.text[:500]}"
    except Exception as e:
        return f"[Exa code search error] {e}"
