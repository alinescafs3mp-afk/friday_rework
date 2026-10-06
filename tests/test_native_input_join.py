"""Actual offline Telegram SDK/cache producer joined to durable input staging."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_native_input_test", root / "__init__.py",
                                            submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_native_input_test.admission import IngressAdmissions, native_call_scope, delivery_route
from friday_native_input_test.artifacts import ArtifactError
from friday_native_input_test.inputs import stage_inputs


class NativeInputJoinTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_own_reply_receipts_reopen_stage_and_detect_cache_change(self):
        import httpx
        from telegram import Bot, Update
        from telegram.request import HTTPXRequest
        from gateway.config import PlatformConfig
        from gateway.platforms import base
        from hermes_cli.plugins_state import PluginState
        from plugins.platforms.telegram.adapter import TelegramAdapter
        from plugins.platforms.telegram.telegram_file_boundary import file_request_class

        class Payload(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"abc"

        def transport(request):
            if request.method == "GET":
                return httpx.Response(200, stream=Payload())
            result = {"id": 123, "is_bot": True, "first_name": "Offline"}
            if request.url.path.endswith("/getFile"):
                result = dict(file_id="f", file_unique_id="u", file_size=3, file_path="docs/test.py")
            return httpx.Response(200, json={"ok": True, "result": result})

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            cache, stage = home / "cache", home / "stage"
            cache.mkdir(mode=0o700); stage.mkdir(mode=0o700)
            adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:offline"))
            request = file_request_class(HTTPXRequest, adapter)(
                httpx_kwargs={"transport": httpx.MockTransport(transport)})
            bot = Bot("123:offline", request=request)
            adapter._bot = bot
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
                    patch.dict(os.environ, HERMES_HOME=str(home)), \
                    patch.object(base, "get_document_cache_dir", return_value=cache):
                try:
                    await bot.initialize()
                    original = dict(message_id=10, date=1, chat=dict(id=77, type="private"),
                                    document=dict(file_id="f", file_unique_id="u", file_size=3,
                                                  file_name="test.py", mime_type="text/x-python"))
                    original["from"] = dict(id=44, is_bot=False, first_name="Offline")
                    update = Update.de_json(dict(update_id=22, message={**original, "message_id": 11,
                                                                      "reply_to_message": original}), bot)
                    event = adapter._build_message_event(update.message, base.MessageType.DOCUMENT, 22)
                    await adapter._cache_inbound_document(update.message, event)
                    await adapter._cache_replied_media(update.message, event)
                    received = adapter.message_provenance(event)
                    self.assertEqual([item["origin"]["message_id"] for item in received["media"]], ["11", "10"])
                    proof = dict(platform="telegram", session_key="native-key", source_profile="",
                                 transport_profile="default", runtime_profile="default", message=received)
                    admission = IngressAdmissions(PluginState("native-input-join"))
                    source = {key: received[key] for key in ("user_id", "chat_id", "thread_id", "message_id")}
                    admission.record(admitted_ingress=proof, session_key="native-key", message_id="11",
                                     source={**source, "profile": "", "chat_type": event.source.chat_type}, platform="telegram")
                    owner = dict(platform="telegram", key="native-key", profile="", id="native-session",
                                 chat_type=event.source.chat_type, **source)
                    call = dict(task_id="native-session", session_id="native-session", turn_id="turn",
                                api_request_id="request", tool_call_id="call")
                    reopened = IngressAdmissions(PluginState("native-input-join"))
                    matched, _ = native_call_scope(tool_name="friday_work", args={},
                        next_call=lambda _: reopened.match(owner, task_id="native-session", session_id="native-session"), **call)
                    from gateway.run_plugin_delivery import freeze_route
                    route = freeze_route(delivery_route(matched))
                    self.assertEqual(route["source"]["chat_type"], "dm")
                    self.assertEqual(route["source"]["message_id"], "11")
                    self.assertEqual(route["source"]["chat_id"], "77")
                    self.assertIsNone(route["source"]["thread_id"])
                    self.assertEqual(route["bot_id"], "123")
                    args = dict(matched_ingress=matched, admitted_reference="native:turn/request/call",
                                cache_roots=(cache,), staging_root=stage, worker_input_root="/job/inputs",
                                max_file_bytes=8, max_total_bytes=16)
                    items = stage_inputs(**args)
                    self.assertEqual(len(items), 2)
                    self.assertNotEqual(items[0].host_path, items[1].host_path)
                    self.assertTrue(all(Path(item.host_path).read_bytes() == b"abc" for item in items))
                    Path(received["media"][0]["local_reference"]).write_bytes(b"xyz")
                    with self.assertRaisesRegex(ArtifactError, "changed_since_receive"):
                        stage_inputs(**args)
                    self.assertTrue(all(Path(item.host_path).read_bytes() == b"abc" for item in items))
                    self.assertNotIn("123:offline", json.dumps(matched))
                finally:
                    await request.shutdown()


if __name__ == "__main__":
    unittest.main()
