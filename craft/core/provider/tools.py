"""Tool preparation utilities for OpenAI-compatible providers"""

from __future__ import annotations

from typing import Any


def prepare_tools(
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
) -> tuple[
    list[dict[str, Any]] | None,
    dict[str, Any] | str | None,
    list[dict[str, str]],
]:
    """Port of prepareTools"""
    warnings: list[dict[str, str]] = []

    if not tools:
        return None, None, warnings

    openai_tools: list[dict[str, Any]] = []
    for tool in tools:
        ttype = tool.get("type")
        if ttype == "provider":
            warnings.append({
                "type": "unsupported",
                "feature": f"tool type: {ttype}",
            })
        else:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description"),
                    "parameters": tool.get("inputSchema", tool.get("parameters", {})),
                },
            })

    if tool_choice is None:
        return openai_tools if openai_tools else None, None, warnings

    if isinstance(tool_choice, str):
        if tool_choice in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tool_choice, warnings

    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type")
        if tc_type in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tc_type, warnings
        if tc_type == "tool":
            return (
                openai_tools if openai_tools else None,
                {
                    "type": "function",
                    "function": {"name": tool_choice.get("toolName", "")},
                },
                warnings,
            )

    return openai_tools if openai_tools else None, tool_choice, warnings


def prepare_responses_tools(
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
    strict_json_schema: bool = False,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | str | None, list[dict]]:
    """Port of prepareResponsesTools"""
    warnings: list[dict] = []

    if not tools:
        return None, None, warnings

    openai_tools: list[dict[str, Any]] = []
    for tool in tools:
        ttype = tool.get("type")
        if ttype == "function":
            openai_tools.append({
                "type": "function",
                "name": tool.get("name", ""),
                "description": tool.get("description"),
                "parameters": tool.get(
                    "inputSchema", tool.get("parameters", {})
                ),
                "strict": strict_json_schema,
            })

        elif ttype == "provider":
            tool_id = tool.get("id", "")
            args = tool.get("args", {}) or {}

            if tool_id == "openai.web_search":
                openai_tools.append({
                    "type": "web_search",
                    "filters": (
                        {"allowed_domains": args.get("filters", {}).get("allowedDomains")}
                        if args.get("filters")
                        else None
                    ),
                    "search_context_size": args.get("searchContextSize"),
                    "user_location": args.get("userLocation"),
                })

            elif tool_id == "openai.web_search_preview":
                openai_tools.append({
                    "type": "web_search_preview",
                    "search_context_size": args.get("searchContextSize"),
                    "user_location": args.get("userLocation"),
                })

            elif tool_id == "openai.code_interpreter":
                container = args.get("container")
                if container is None:
                    container_val: Any = {"type": "auto", "file_ids": None}
                elif isinstance(container, str):
                    container_val = container
                else:
                    container_val = {
                        "type": "auto",
                        "file_ids": container.get("fileIds") if isinstance(container, dict) else None,
                    }
                openai_tools.append({
                    "type": "code_interpreter",
                    "container": container_val,
                })

            elif tool_id == "openai.file_search":
                openai_tools.append({
                    "type": "file_search",
                    "vector_store_ids": args.get("vectorStoreIds", []),
                    "max_num_results": args.get("maxNumResults"),
                    "ranking_options": (
                        {
                            "ranker": args["ranking"]["ranker"],
                            "score_threshold": args["ranking"]["scoreThreshold"],
                        }
                        if args.get("ranking")
                        else None
                    ),
                })

            elif tool_id == "openai.image_generation":
                openai_tools.append({
                    "type": "image_generation",
                    "background": args.get("background"),
                    "input_fidelity": args.get("inputFidelity"),
                    "model": args.get("model"),
                    "quality": args.get("quality"),
                    "size": args.get("size"),
                    "output_format": args.get("outputFormat"),
                })

            elif tool_id == "openai.local_shell":
                openai_tools.append({"type": "local_shell"})

            else:
                warnings.append({
                    "type": "unsupported",
                    "feature": f"tool id: {tool_id}",
                })

        else:
            warnings.append({"type": "unsupported", "feature": "tool type"})

    # Handle tool_choice
    if tool_choice is None:
        return openai_tools if openai_tools else None, None, warnings

    if isinstance(tool_choice, str):
        if tool_choice in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tool_choice, warnings

    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type")
        if tc_type in ("auto", "none", "required"):
            return openai_tools if openai_tools else None, tc_type, warnings

        if tc_type == "tool":
            tool_name = tool_choice.get("toolName", "")
            if tool_name in (
                "code_interpreter",
                "file_search",
                "image_generation",
                "web_search_preview",
                "web_search",
            ):
                tc_result: dict[str, Any] = {"type": tool_name}
            else:
                tc_result = {"type": "function", "name": tool_name}
            return openai_tools if openai_tools else None, tc_result, warnings

    return openai_tools if openai_tools else None, tool_choice, warnings
