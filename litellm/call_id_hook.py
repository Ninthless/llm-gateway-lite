import hashlib
from typing import Literal, Optional, Union

from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.caching.caching import DualCache

MAX_CALL_ID = 64


def _truncate(call_id: str) -> str:
    if len(call_id) <= MAX_CALL_ID:
        return call_id
    suffix = hashlib.md5(call_id.encode()).hexdigest()[:8]
    return f"{call_id[:55]}_{suffix}"


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
        if changed:
            data["messages"] = messages
        return data


proxy_handler_instance = CallIdSanitizer()
