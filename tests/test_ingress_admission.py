"""Actual PluginState receipts, native correlation scope and replay isolation."""
from contextvars import Context
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_ingress_test", root / "__init__.py", submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_ingress_test.admission import IngressAdmissions, native_call_scope, delivery_route, KEY
from hermes_cli.plugins_state import PluginState

PROOF = {"platform": "telegram", "session_key": "native-key", "source_profile": "",
         "chat_type": "group",
         "transport_profile": "default", "runtime_profile": "default",
         "message": dict(bot_id="9001", user_id="111", chat_id="-1001", thread_id="17",
                         message_id="501", platform_update_id="701", reply_to_message_id="", media=[])}
OWNER = dict(platform="telegram", key="native-key", profile="", id="native-session",
             chat_type="group", user_id="111", chat_id="-1001", thread_id="17", message_id="501")
CALL = dict(task_id="native-session", session_id="native-session", turn_id="native-turn",
            api_request_id="native-request", tool_call_id="native-call")


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, HERMES_HOME=self.temp.name)
        env.start(); self.addCleanup(env.stop)
        self.state = PluginState("friday_ingress_test")
        self.admission = IngressAdmissions(self.state)

    def record(self, proof=None, **source_changes):
        proof = copy.deepcopy(PROOF if proof is None else proof)
        source = {k: proof["message"][k] for k in ("user_id", "chat_id", "thread_id", "message_id")}
        source.update(profile=proof["source_profile"], chat_type=proof.get("chat_type", "group"))
        source.update(source_changes)
        return self.admission.record(admitted_ingress=proof, session_key=proof["session_key"],
                                     message_id=proof["message"]["message_id"], source=source, platform="telegram")

    def match(self, *, owner=None, call=None, admission=None):
        call = CALL if call is None else call
        admission = self.admission if admission is None else admission
        return native_call_scope(tool_name="friday_work", args={"model_text": "cannot supply IDs"},
                                 next_call=lambda _: admission.match(OWNER if owner is None else owner,
                                                                     task_id=call.get("task_id"),
                                                                     session_id=call.get("session_id")), **call)

    def test_real_native_receipt_survives_reopen_without_creating_worker(self):
        self.record()
        value, call = self.match(admission=IngressAdmissions(PluginState("friday_ingress_test")))
        self.assertEqual(value, PROOF)
        self.assertEqual(call, CALL)
        self.assertEqual(self.state.get("associations.v1", None)["jobs"], {})
        before = self.state.path.read_bytes()
        self.record()
        self.assertEqual(before, self.state.path.read_bytes())

    def test_native_call_or_context_alone_is_not_admission(self):
        with self.assertRaisesRegex(ValueError, "missing_admitted"):
            self.match()
        self.record()
        with self.assertRaisesRegex(ValueError, "missing_native"):
            Context().run(self.admission.match, OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])

    def test_unproven_or_mismatched_hook_cannot_persist_authority(self):
        with self.assertRaises(ValueError):
            self.admission.record(admitted_ingress=None, session_key="x", message_id="501", source={}, platform="telegram")
        for field in ("user_id", "chat_id", "thread_id", "message_id", "profile"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.record(**{field: "other"})
        with self.assertRaisesRegex(ValueError, "missing_admitted"):
            self.match()

    def test_cross_owner_topic_profile_and_message_do_not_match(self):
        self.record()
        for key in ("user_id", "chat_id", "thread_id", "profile", "message_id", "id", "key", "chat_type"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.match(owner={**OWNER, key: "other"})

    def test_delivery_route_survives_reopen_and_does_not_borrow_new_message(self):
        self.record()
        original, _ = self.match(admission=IngressAdmissions(PluginState("friday_ingress_test")))
        next_proof = copy.deepcopy(PROOF)
        next_proof["message"].update(message_id="502", platform_update_id="702")
        self.record(next_proof)
        expected = dict(source=dict(platform="telegram", chat_id="-1001", chat_type="group",
                                    user_id="111", thread_id="17", message_id="501"),
                        transport_profile="default", runtime_profile="default", bot_id="9001")
        self.assertEqual(delivery_route(original), expected)
        self.assertEqual(delivery_route(self.match()[0]), expected)

    def test_receiving_hook_requires_actual_native_chat_type(self):
        for value in (None, "", "private", "invented", "dm", {}, []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "mismatch"):
                self.record(chat_type=value)
        self.assertIsNone(self.state.get(KEY))

    def test_historical_receipt_without_chat_type_is_readable_but_cannot_deliver(self):
        self.record()
        document = self.state.get(KEY)
        for value in document["receipts"].values():
            del value["chat_type"]
        self.state.set(KEY, document)
        before = self.state.path.read_bytes()
        matched, _ = self.match()
        with self.assertRaisesRegex(ValueError, "missing_admitted_delivery_route"):
            delivery_route(matched)
        self.assertEqual(before, self.state.path.read_bytes())

    def test_actual_dm_route_keeps_explicit_null_thread(self):
        proof = copy.deepcopy(PROOF)
        proof["chat_type"] = "dm"
        proof["message"]["thread_id"] = ""
        self.record(proof)
        matched, _ = self.match(owner={**OWNER, "chat_type": "dm", "thread_id": ""})
        self.assertIsNone(delivery_route(matched)["source"]["thread_id"])

    def test_same_native_call_id_in_another_turn_retains_full_tuple(self):
        self.record()
        one = self.match()[1]
        two = self.match(call={**CALL, "turn_id": "another-turn", "api_request_id": "another-response"})[1]
        self.assertNotEqual(one, two)
        self.assertEqual(one["tool_call_id"], two["tool_call_id"])

    def test_missing_nested_correlation_never_borrows_outer_scope(self):
        self.record()
        def outer(_):
            def rejection(_):
                with self.assertRaisesRegex(ValueError, "missing_native"):
                    self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])
                return "unproved"
            self.assertEqual(native_call_scope(tool_name="friday_work", args={},
                             next_call=rejection, **{**CALL, "tool_call_id": None}), "unproved")
            return self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])[1]
        self.assertEqual(native_call_scope(tool_name="friday_work", args={}, next_call=outer, **CALL), CALL)
        with self.assertRaisesRegex(ValueError, "missing_native"):
            self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])

    def test_unexpected_nested_validation_and_fallback_never_borrow_outer(self):
        from friday_ingress_test import admission as module
        from hermes_cli.plugins import get_plugin_manager, PluginContext, PluginManifest
        from hermes_cli.middleware import run_tool_execution_middleware
        manager = get_plugin_manager(); manager.discover_and_load()
        ctx = PluginContext(PluginManifest(name="nested_scope", path=str(root)), manager)
        registration = ctx.register_middleware("tool_execution", native_call_scope)
        self.addCleanup(registration.dispose)
        self.record()
        original = module._text
        inner = {**CALL, "turn_id": "inner-turn", "api_request_id": "inner-request", "tool_call_id": "inner-call"}
        def fault(value, *args, **kwargs):
            if value == "inner-call":
                raise MemoryError("offline injected validation fault")
            return original(value, *args, **kwargs)
        def refused(_):
            with self.assertRaisesRegex(ValueError, "missing_native"):
                self.admission.match(OWNER, task_id=inner["task_id"], session_id=inner["session_id"])
            return "no admission"
        def outer(_):
            with patch.object(module, "_text", side_effect=fault):
                return run_tool_execution_middleware("friday_work", {}, refused, **inner)
        self.assertEqual(run_tool_execution_middleware("friday_work", {}, outer, **CALL), "no admission")
        with self.assertRaisesRegex(ValueError, "missing_native"):
            self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])

    def test_native_downstream_exception_is_not_replayed_and_restores_outer(self):
        from hermes_cli.plugins import get_plugin_manager, PluginContext, PluginManifest
        from hermes_cli.middleware import run_tool_execution_middleware
        manager = get_plugin_manager(); manager.discover_and_load()
        ctx = PluginContext(PluginManifest(name="downstream_scope", path=str(root)), manager)
        registration = ctx.register_middleware("tool_execution", native_call_scope)
        self.addCleanup(registration.dispose)
        self.record()
        inner = {**CALL, "turn_id": "inner-turn", "api_request_id": "inner-request", "tool_call_id": "inner-call"}
        calls = []
        def raising(_):
            calls.append(self.admission.match(OWNER, task_id=inner["task_id"], session_id=inner["session_id"])[1])
            raise OSError("offline downstream failure")
        def outer(_):
            with self.assertRaises(OSError):
                run_tool_execution_middleware("friday_work", {}, raising, **inner)
            self.assertEqual(self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])[1], CALL)
        run_tool_execution_middleware("friday_work", {}, outer, **CALL)
        self.assertEqual(calls, [inner])
        with self.assertRaisesRegex(ValueError, "missing_native"):
            self.admission.match(OWNER, task_id=CALL["task_id"], session_id=CALL["session_id"])

    def test_changed_bot_or_update_cannot_replace_same_message(self):
        self.record(); original = self.state.path.read_bytes()
        for field in ("bot_id", "platform_update_id"):
            changed = copy.deepcopy(PROOF); changed["message"][field] = "different"
            with self.assertRaisesRegex(ValueError, "conflict"):
                self.record(changed)
            self.assertEqual(original, self.state.path.read_bytes())

    def test_native_content_receipt_persists_and_cannot_be_rewritten(self):
        proof = copy.deepcopy(PROOF)
        media = dict(local_reference="/native/cache/code.py", mime_type="text/x-python",
                     origin=dict(bot_id="9001", chat_id="-1001", thread_id="17", message_id="501",
                                 file_id="native-file", file_unique_id="native-unique", declared_bytes=3),
                     content=dict(size_bytes=3, sha256="a" * 64))
        proof["message"]["media"] = [media]
        self.record(proof)
        value, _ = self.match(admission=IngressAdmissions(PluginState("friday_ingress_test")))
        self.assertEqual(value, proof)
        before = self.state.path.read_bytes()
        for field, changed in (("size_bytes", 4), ("sha256", "b" * 64)):
            altered = copy.deepcopy(proof)
            altered["message"]["media"][0]["content"][field] = changed
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "conflict"):
                self.record(altered)
            self.assertEqual(before, self.state.path.read_bytes())

    def test_legacy_file_receipt_remains_readable_without_adding_byte_proof(self):
        proof = copy.deepcopy(PROOF)
        proof["message"]["media"] = [dict(local_reference="/native/cache/code.py",
                                          mime_type="text/x-python", origin=None)]
        self.record(proof)
        value, _ = self.match(admission=IngressAdmissions(PluginState("friday_ingress_test")))
        self.assertNotIn("content", value["message"]["media"][0])

    def test_corruption_and_failed_directory_barrier_refuse_match(self):
        self.record()
        with patch("friday_ingress_test.admission._sync_directory", side_effect=OSError("fixture fsync failure")):
            with self.assertRaises(OSError):
                self.match()
        self.state.set(KEY, {"schema_version": 1, "receipts": {"bad": {}}})
        before = self.state.path.read_bytes()
        with self.assertRaises(ValueError):
            self.match()
        self.assertEqual(before, self.state.path.read_bytes())

    def test_native_registered_tool_requires_receipt_and_obeys_native_policy(self):
        from hermes_cli.plugins import get_plugin_manager, PluginContext, PluginManifest
        from gateway.session_context import set_session_vars, clear_session_vars
        from model_tools import handle_function_call
        from agent.tool_executor import _run_agent_tool_execution_middleware
        from types import SimpleNamespace

        manager = get_plugin_manager()
        manager.discover_and_load()
        ctx = PluginContext(PluginManifest(name="friday_ingress_test", path=str(root)), manager)
        package.register(ctx)
        brief = dict(worker="dsh", brief="Read offline fixture", goal_check="Verify fixture")
        tokens = set_session_vars(platform="telegram", chat_id=OWNER["chat_id"],
                                  chat_type="group", thread_id=OWNER["thread_id"],
                                  user_id=OWNER["user_id"], session_key=OWNER["key"],
                                  session_id=OWNER["id"], message_id=OWNER["message_id"], profile="")
        try:
            def dispatch():
                return json.loads(handle_function_call("friday_work", brief, **CALL))
            self.assertEqual(dispatch()["error"], "unproved_admission")
            import asyncio
            from telegram import Bot, User, Update
            from gateway.config import GatewayConfig, Platform, PlatformConfig
            from gateway.platforms.event import MessageType
            from gateway.run import GatewayRunner
            from plugins.platforms.telegram.adapter import TelegramAdapter
            from unittest.mock import AsyncMock, MagicMock
            from telegram.request import BaseRequest
            adapter = TelegramAdapter(PlatformConfig(enabled=True))
            adapter._bot = Bot("9001:OFFLINE_FIXTURE_NOT_A_CREDENTIAL")
            adapter._bot._bot_user = User(9001, "Offline", is_bot=True)
            adapter.send = AsyncMock(side_effect=AssertionError("no delivery in offline join"))
            runner = object.__new__(GatewayRunner)
            runner.config = GatewayConfig(platforms={Platform.TELEGRAM: adapter.config})
            runner.adapters = {Platform.TELEGRAM: adapter}
            runner.pairing_store = MagicMock()
            runner.pairing_store.is_approved.return_value = False
            runner.session_store = MagicMock()
            runner._rescue_orphaned_overflow = lambda *args: None
            runner._enqueue_fifo = MagicMock()
            runner._handle_message_with_agent = AsyncMock(side_effect=AssertionError("no model in offline join"))
            runner._run_post_turn_hooks = AsyncMock()
            adapter.gateway_runner = runner
            update = Update.de_json({"update_id": 701, "message": {
                "message_id": 501, "date": 1791309600,
                "chat": {"id": -1001, "type": "supergroup", "title": "Offline", "is_forum": True},
                "from": {"id": 111, "is_bot": False, "first_name": "Offline"},
                "message_thread_id": 17, "is_topic_message": True, "text": "offline fixture"}}, adapter._bot)
            event = adapter._build_message_event(update.message, MessageType.TEXT, update.update_id)
            # Native adapter ingress pins routing before its gateway callback.
            self.assertIsNotNone(adapter._canonicalize(event.source))
            observed = []
            consumer = ctx.register_hook("post_gateway_admission", lambda **kw:
                observed.append(kw) or {"action": "handled", "reply": "offline join"})
            with patch.dict(os.environ, TELEGRAM_ALLOWED_USERS="111", GATEWAY_ALLOW_ALL_USERS="false"), \
                    patch.object(BaseRequest, "post", side_effect=AssertionError("no Telegram network")):
                self.assertEqual(asyncio.run(runner._handle_message(event)), "offline join")
            consumer.dispose()
            self.assertEqual(observed[0]["admitted_ingress"]["message"], PROOF["message"])
            clear_session_vars(tokens)
            tokens = set_session_vars(platform="telegram", chat_id=OWNER["chat_id"],
                                      chat_type="group", thread_id=OWNER["thread_id"],
                                      user_id=OWNER["user_id"], session_key=observed[0]["session_key"],
                                      session_id=OWNER["id"], message_id=OWNER["message_id"], profile="")
            self.assertEqual(dispatch()["error"], "worker_not_admitted")
            self.assertEqual(self.state.get("associations.v1")["jobs"], {})
            policy = ctx.register_hook("pre_tool_call", lambda **kw:
                {"action": "block", "message": "offline policy refusal"}
                if kw["tool_name"] == "friday_work" else None)
            fake_agent = SimpleNamespace(session_id=CALL["session_id"],
                                         _current_turn_id=CALL["turn_id"],
                                         _current_api_request_id=CALL["api_request_id"])
            def forbidden(_):
                self.fail("native policy refusal reached downstream execution")
            result = _run_agent_tool_execution_middleware(
                fake_agent, function_name="friday_work", function_args=brief,
                effective_task_id=CALL["task_id"], tool_call_id=CALL["tool_call_id"], execute=forbidden)
            self.assertTrue(result.blocked)
            policy.dispose()
            self.assertEqual(dispatch()["error"], "worker_not_admitted")
        finally:
            clear_session_vars(tokens)
        self.assertEqual(json.loads(handle_function_call("friday_work", brief, **CALL))["error"], "unproved_admission")

    def test_native_state_parse_failure_returns_no_private_path(self):
        from gateway.session_context import set_session_vars, clear_session_vars
        self.record()
        self.state.path.write_text("{invalid json")
        tokens = set_session_vars(platform="telegram", chat_id=OWNER["chat_id"],
                                  chat_type="group", thread_id=OWNER["thread_id"],
                                  user_id=OWNER["user_id"], session_key=OWNER["key"],
                                  session_id=OWNER["id"], message_id=OWNER["message_id"], profile="")
        try:
            result = native_call_scope(tool_name="friday_work",
                args=dict(worker="dsh", brief="fixture", goal_check="fixture check"),
                next_call=lambda args: self.admission.handle(args, **CALL), **CALL)
        finally:
            clear_session_vars(tokens)
        self.assertEqual(json.loads(result), {"accepted": False, "error": "unproved_admission"})
        self.assertEqual(self.state.path.read_text(), "{invalid json")

    def test_policy_refusal_is_not_replaced_by_middleware(self):
        self.record(); calls = []
        result = native_call_scope(tool_name="friday_work", args={},
                                   next_call=lambda args: calls.append(args) or "policy-denied", **CALL)
        self.assertEqual(result, "policy-denied")
        self.assertEqual(calls, [{}])


if __name__ == "__main__":
    unittest.main()
