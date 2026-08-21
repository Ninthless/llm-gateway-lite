import hashlib
import json
from typing import Any, Literal, Optional, Union

from litellm.caching.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.llms.openai.responses.transformation import OpenAIResponsesAPIConfig
from litellm.proxy._types import UserAPIKeyAuth

_orig_transform_response_api_response = OpenAIResponsesAPIConfig.transform_response_api_response


class _JsonWithCreatedAt:
    def __init__(self, response):
        self._response = response

    def json(self, *args, **kwargs):
        data = self._response.json(*args, **kwargs)
        if isinstance(data, dict) and "created_at" not in data:
            data["created_at"] = 0
        return data

    def __getattr__(self, name):
        return getattr(self._response, name)


def _transform_response_api_response(self, model, raw_response, logging_obj):
    return _orig_transform_response_api_response(
        self, model, _JsonWithCreatedAt(raw_response), logging_obj
    )


OpenAIResponsesAPIConfig.transform_response_api_response = _transform_response_api_response

MAX_CALL_ID = 64


def _truncate(call_id: str) -> str:
    if len(call_id) <= MAX_CALL_ID:
        return call_id
    suffix = hashlib.md5(call_id.encode()).hexdigest()[:8]
    return f"{call_id[:55]}_{suffix}"


def _tool_result_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(parts)
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text") or ""
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _normalize_cursor_messages(messages: list) -> list:
    out = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        content = msg.get("content")
        if msg.get("role") != "user":
            out.append(msg)
            continue
        if isinstance(content, dict):
            new_msg = dict(msg)
            new_msg["content"] = _tool_result_to_text(content)
            out.append(new_msg)
            continue
        if not isinstance(content, list):
            out.append(msg)
            continue

        tool_msgs = []
        kept = []
        changed = False
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                changed = True
                tool_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.get("tool_use_id")
                        or item.get("id")
                        or "tool",
                        "content": _tool_result_to_text(item.get("content")),
                    }
                )
            elif isinstance(item, dict) and item.get("type") == "text":
                kept.append(item)
            elif isinstance(item, str):
                kept.append({"type": "text", "text": item})
            else:
                kept.append(
                    {
                        "type": "text",
                        "text": _tool_result_to_text(item),
                    }
                )
                changed = True

        if not changed:
            out.append(msg)
            continue

        out.extend(tool_msgs)
        if not kept:
            continue
        if all(isinstance(p, dict) and p.get("type") == "text" for p in kept):
            text = "".join((p.get("text") or "") for p in kept)
            if text:
                new_msg = dict(msg)
                new_msg["content"] = text
                out.append(new_msg)
            continue
        new_msg = dict(msg)
        new_msg["content"] = kept
        out.append(new_msg)
    return out


class CallIdSanitizer(CustomLogger):
    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "pass_through_endpoint",
            "rerank",
        ],
    ) -> Optional[Union[Exception, str, dict]]:
        messages = data.get("messages") or []
        if isinstance(messages, list):
            messages = _normalize_cursor_messages(messages)

        changed = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                if isinstance(tc, dict) and isinstance(tc.get("id"), str):
                    new_id = _truncate(tc["id"])
                    if new_id != tc["id"]:
                        tc["id"] = new_id
                        changed = True
            call_id = msg.get("tool_call_id")
            if isinstance(call_id, str):
                new_id = _truncate(call_id)
                if new_id != call_id:
                    msg["tool_call_id"] = new_id
                    changed = True
        if changed or messages is not data.get("messages"):
            data["messages"] = messages
        return data


proxy_handler_instance = CallIdSanitizer()
