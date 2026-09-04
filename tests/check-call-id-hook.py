import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class OpenAIResponsesAPIConfig:
    transform_response_api_response = staticmethod(lambda *args, **kwargs: None)


_stub("litellm")
_stub("litellm.caching")
_stub("litellm.caching.caching", DualCache=object)
_stub("litellm.integrations")
_stub("litellm.integrations.custom_logger", CustomLogger=object)
_stub("litellm.llms")
_stub("litellm.llms.openai")
_stub("litellm.llms.openai.responses")
_stub(
    "litellm.llms.openai.responses.transformation",
    OpenAIResponsesAPIConfig=OpenAIResponsesAPIConfig,
)
_stub("litellm.proxy")
_stub("litellm.proxy._types", UserAPIKeyAuth=object)

HOOK_PATH = Path(__file__).resolve().parents[1] / "litellm" / "call_id_hook.py"
spec = importlib.util.spec_from_file_location("call_id_hook", HOOK_PATH)
hook = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(hook)


class NormalizeCursorMessagesTests(unittest.TestCase):
    def test_plain_string_content_unchanged(self):
        messages = [{"role": "user", "content": "hello"}]
        self.assertIs(hook._normalize_cursor_messages(messages), messages)

    def test_non_user_roles_unchanged(self):
        messages = [
            {"role": "system", "content": [{"type": "tool_result", "content": "x"}]},
            {"role": "assistant", "content": [{"type": "image_url", "image_url": {"url": "x"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ]
        self.assertIs(hook._normalize_cursor_messages(messages), messages)

    def test_keeps_image_url_blocks(self):
        image = {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc"},
        }
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what color"},
                    image,
                ],
            }
        ]
        out = hook._normalize_cursor_messages(messages)
        self.assertIs(out, messages)
        self.assertEqual(out[0]["content"][1], image)

    def test_keeps_input_image_and_input_file(self):
        image = {"type": "input_image", "image_url": "data:image/png;base64,abc"}
        file_part = {"type": "input_file", "filename": "a.pdf", "file_data": "AAA"}
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe"},
                    image,
                    file_part,
                ],
            }
        ]
        out = hook._normalize_cursor_messages(messages)
        self.assertIs(out, messages)
        self.assertEqual(out[0]["content"][1], image)
        self.assertEqual(out[0]["content"][2], file_part)

    def test_keeps_typed_user_content_object(self):
        messages = [
            {
                "role": "user",
                "content": {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            }
        ]
        self.assertIs(hook._normalize_cursor_messages(messages), messages)

    def test_still_lifts_tool_result(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "done",
                    },
                ],
            }
        ]
        out = hook._normalize_cursor_messages(messages)
        self.assertEqual(out[0]["role"], "tool")
        self.assertEqual(out[0]["tool_call_id"], "call_1")
        self.assertEqual(out[1]["content"], "ok")

    def test_image_survives_tool_result_split(self):
        image = {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,abc"},
        }
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "see"},
                    image,
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "done",
                    },
                ],
            }
        ]
        out = hook._normalize_cursor_messages(messages)
        self.assertEqual(out[0]["role"], "tool")
        self.assertEqual(out[1]["content"][1], image)

    def test_unknown_content_types_are_kept(self):
        audio = {"type": "input_audio", "input_audio": {"data": "AAA", "format": "wav"}}
        extra = {"type": "encrypted_content", "encrypted_content": "zzz"}
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "x"},
                    audio,
                    extra,
                ],
            }
        ]
        self.assertIs(hook._normalize_cursor_messages(messages), messages)

    def test_responses_input_items_without_role_are_kept(self):
        messages = [
            {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": "ok"},
            {"type": "reasoning", "encrypted_content": "abc"},
            "plain text input",
        ]
        self.assertIs(hook._normalize_cursor_messages(messages), messages)

    def test_untyped_user_content_object_becomes_text(self):
        messages = [{"role": "user", "content": {"foo": "bar"}}]
        out = hook._normalize_cursor_messages(messages)
        self.assertEqual(out[0]["content"], '{"foo": "bar"}')

    def test_tool_result_as_user_content_object(self):
        messages = [
            {
                "role": "user",
                "content": {
                    "type": "tool_result",
                    "tool_use_id": "call_1",
                    "content": "done",
                },
            }
        ]
        out = hook._normalize_cursor_messages(messages)
        self.assertEqual(out, [{"role": "tool", "tool_call_id": "call_1", "content": "done"}])


class PreCallHookTests(unittest.TestCase):
    def _run(self, data):
        return asyncio.run(
            hook.proxy_handler_instance.async_pre_call_hook(
                user_api_key_dict=object(),
                cache=object(),
                data=data,
                call_type="completion",
            )
        )

    def test_truncates_tool_call_ids_on_messages(self):
        long_id = "c" * 80
        data = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [{"id": long_id, "type": "function", "function": {"name": "f"}}],
                },
                {"role": "tool", "tool_call_id": long_id, "content": "ok"},
            ]
        }
        out = self._run(data)
        new_id = out["messages"][0]["tool_calls"][0]["id"]
        self.assertLessEqual(len(new_id), 64)
        self.assertEqual(out["messages"][1]["tool_call_id"], new_id)

    def test_truncates_call_id_on_responses_input(self):
        long_id = "c" * 80
        data = {
            "input": [
                {"type": "function_call", "call_id": long_id, "name": "f", "arguments": "{}"},
                {"type": "function_call_output", "call_id": long_id, "output": "ok"},
            ]
        }
        out = self._run(data)
        self.assertLessEqual(len(out["input"][0]["call_id"]), 64)
        self.assertEqual(out["input"][0]["call_id"], out["input"][1]["call_id"])

    def test_keeps_images_on_both_messages_and_input(self):
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
        payload = [{"role": "user", "content": [{"type": "text", "text": "see"}, image]}]
        out = self._run({"messages": payload, "input": payload})
        self.assertEqual(out["messages"][0]["content"][1], image)
        self.assertEqual(out["input"][0]["content"][1], image)


if __name__ == "__main__":
    unittest.main()
