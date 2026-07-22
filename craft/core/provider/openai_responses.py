"""OpenAI Responses API provider"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from craft.core.provider.base import BaseProvider, ProviderError
from craft.core.provider.openai_config import OpenAICompatibleProviderOptions
from craft.core.provider.tools import prepare_responses_tools
from craft.core.provider.transform import map_openai_responses_finish_reason
from craft.core.provider.models import ResponsesInputItem


class OpenAIResponsesProvider(BaseProvider):
    """
    OpenAI Responses API provider.
    Uses the newer /v1/responses endpoint with built-in tools
    (web_search, code_interpreter, file_search, etc.)
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__("openai-responses", model)
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._http_client = None

    @property
    def _session(self):
        if self._http_client is None:
            import httpx

            key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=300,
            )
        return self._http_client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """Use Responses API for non-streaming requests"""
        return await self._responses_create(messages, tools, stream=False, **kwargs)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        """Use Responses API for streaming requests"""
        async for chunk in self._responses_stream(messages, tools, **kwargs):
            yield chunk

    async def _responses_create(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Call the OpenAI Responses API"""
        from openai import AsyncOpenAI

        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        key = self._api_key or os.environ.get("OPENAI_API_KEY", "")

        # Convert messages to Responses API input format
        input_items = self._convert_to_responses_input(messages)

        # Prepare tools
        responses_tools, tool_choice, _ = prepare_responses_tools(
            tools, kwargs.pop("tool_choice", None)
        )

        body: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "input": input_items,
        }

        if responses_tools:
            body["tools"] = responses_tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        for param in (
            "temperature",
            "top_p",
            "max_output_tokens",
            "instructions",
            "store",
            "metadata",
            "user",
            "parallel_tool_calls",
        ):
            value = kwargs.pop(param, None)
            if value is not None:
                body[param] = value

        if opts.reasoning_effort:
            body["reasoning"] = {"effort": opts.reasoning_effort}

        # Use the standard OpenAI client's responses API if available
        try:
            client = AsyncOpenAI(api_key=key, base_url=self._base_url)
            if hasattr(client, "responses") and hasattr(
                client.responses, "create"
            ):
                resp = await client.responses.create(**body)
            else:
                # Fallback to raw HTTP
                resp = await self._raw_responses_create(body)

            return self._parse_responses_response(resp)
        except Exception as e:
            raise ProviderError(str(e), 500, self.name) from e

    async def _raw_responses_create(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Raw HTTP call to Responses API"""
        response = await self._session.post("/responses", json=body)
        response.raise_for_status()
        return response.json()

    async def _responses_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ):
        """Stream from Responses API"""
        opts = OpenAICompatibleProviderOptions.from_dict(
            kwargs.pop("providerOptions", None)
        )
        input_items = self._convert_to_responses_input(messages)
        responses_tools, tool_choice, _ = prepare_responses_tools(
            tools, kwargs.pop("tool_choice", None)
        )

        body: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "input": input_items,
            "stream": True,
        }

        if responses_tools:
            body["tools"] = responses_tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        for param in (
            "temperature",
            "top_p",
            "max_output_tokens",
            "instructions",
            "store",
            "user",
        ):
            value = kwargs.pop(param, None)
            if value is not None:
                body[param] = value

        if opts.reasoning_effort:
            body["reasoning"] = {"effort": opts.reasoning_effort}

        try:
            async with self._session.stream(
                "POST", "/responses", json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    yield self._process_responses_chunk(chunk)
        except Exception as e:
            yield {"type": "error", "message": str(e)}

    def _convert_to_responses_input(
        self, messages: list[dict]
    ) -> list[ResponsesInputItem]:
        """Convert standard messages to Responses API input format"""
        input_items: list[ResponsesInputItem] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                input_items.append({"role": "system", "content": content})

            elif role == "user":
                parts: list[dict] = []
                if isinstance(content, str):
                    parts.append({"type": "input_text", "text": content})
                elif isinstance(content, list):
                    for part in content:
                        ptype = part.get("type")
                        if ptype == "text":
                            parts.append({"type": "input_text", "text": part["text"]})
                        elif ptype == "image_url":
                            parts.append({
                                "type": "input_image",
                                "image_url": part["image_url"]["url"],
                            })
                        elif ptype == "file":
                            media_type = part.get("mediaType", "")
                            if media_type.startswith("image/"):
                                parts.append({
                                    "type": "input_image",
                                    "image_url": f"data:{media_type};base64,{base64.b64encode(bytes(part['data'])).decode()}",
                                })
                input_items.append({"role": "user", "content": parts})

            elif role == "assistant":
                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    texts = [
                        p["text"]
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    text_content = "".join(texts)
                input_items.append({
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text_content}],
                })

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                output = content if isinstance(content, str) else json.dumps(content)
                input_items.append({
                    "type": "function_call_output",
                    "call_id": tool_call_id,
                    "output": output,
                })

        return input_items

    def _parse_responses_response(
        self, resp: Any
    ) -> dict[str, Any]:
        """Parse a Responses API response into standard format"""
        # Handle both SDK response objects and raw dicts
        if isinstance(resp, dict):
            data = resp
        else:
            # OpenAI SDK response object
            data = resp.to_dict() if hasattr(resp, "to_dict") else resp.model_dump()

        output_text = ""
        tool_calls_list: list[dict] = []
        has_function_call = False

        for item in data.get("output", []):
            if item.get("type") == "message":
                for cp in item.get("content", []):
                    if cp.get("type") == "output_text":
                        output_text += cp.get("text", "")
            elif item.get("type") == "function_call":
                has_function_call = True
                tool_calls_list.append({
                    "id": item.get("call_id", item.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                })

        usage = data.get("usage", {}) or {}
        return {
            "content": output_text,
            "tool_calls": tool_calls_list or None,
            "finish_reason": map_openai_responses_finish_reason(
                data.get("incomplete_details", {}).get("reason"),
                has_function_call=has_function_call,
            ),
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            "metadata": {
                "id": data.get("id"),
                "model": data.get("model"),
                "created": data.get("created_at"),
            },
        }

    def _process_responses_chunk(
        self, chunk: dict[str, Any]
    ) -> dict[str, Any]:
        """Process a streaming Responses API chunk"""
        chunk_type = chunk.get("type", "")

        if chunk_type == "response.output_text.delta":
            return {"type": "content", "content": chunk.get("delta", "")}
        elif chunk_type == "response.output_item.added":
            item = chunk.get("item", {})
            if item.get("type") == "function_call":
                return {
                    "type": "tool-call-start",
                    "id": item.get("call_id", item.get("id")),
                    "name": item.get("name"),
                }
        elif chunk_type == "response.function_call_arguments.delta":
            return {
                "type": "tool-call-delta",
                "id": chunk.get("item_id"),
                "delta": chunk.get("delta", ""),
            }
        elif chunk_type == "response.completed":
            return {"type": "done"}
        elif chunk_type == "response.error":
            return {"type": "error", "message": str(chunk.get("error", ""))}

        return {"type": "other", "data": chunk}
