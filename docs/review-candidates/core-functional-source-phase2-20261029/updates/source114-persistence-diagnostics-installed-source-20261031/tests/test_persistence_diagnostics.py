import ast
import builtins
import hashlib
import json
import re
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
B150 = ROOT / "basis/b150/hermes_cli/friday_user_scope.py"


def extract(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return tree


class DB:
    def __init__(self):
        self.calls = []
        self.error = None

    def append_messages_batch(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(kwargs)


class Log:
    def __init__(self):
        self.rows = []

    def warning(self, fmt, *args, **kwargs):
        self.rows.append(fmt % args)


class PersistenceDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence = SOURCE / "agent/session_persistence.py"
        user_scope = SOURCE / "hermes_cli/friday_user_scope.py"
        turn_context = SOURCE / "agent/turn_context.py"
        cls.ns = dict(
            __name__="agent.session_persistence",
            hashlib=hashlib,
            json=json,
            re=re,
            Any=Any,
            Dict=Dict,
            List=List,
            Optional=Optional,
        )
        names = [
            "_db_exception_metadata",
            "_db_flush_failure_metadata",
            "_db_flush_seed_ids",
            "_db_flush_scan_start",
            "_db_flush_collect",
            "_db_flush_write",
            "_db_flush_failed",
        ]
        extract(persistence, names, cls.ns)
        tree = ast.parse(persistence.read_text(encoding="utf-8"))
        cls_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SessionPersistenceMixin"
        )
        method = next(
            node
            for node in cls_node.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_flush_messages_to_session_db_unlocked"
        )
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(persistence), "exec"), cls.ns)
        cls.persistence_module = types.ModuleType("agent.session_persistence")
        cls.persistence_module._db_exception_metadata = cls.ns["_db_exception_metadata"]
        sys.modules["agent.session_persistence"] = cls.persistence_module

        class ScopeDenied(PermissionError):
            def __init__(self):
                super().__init__("product_user_scope_refused")

        cls.ScopeDenied = ScopeDenied
        cls.scope = dict(
            __name__="hermes_cli.friday_user_scope", json=json, ScopeDenied=ScopeDenied
        )
        extract(
            user_scope,
            ["guard_generated_reply", "guard_generated_rows", "generated_public_tool_payload"],
            cls.scope,
        )
        cls.scope_module = types.ModuleType("hermes_cli.friday_user_scope")
        cls.scope_module.guard_generated_rows = cls.scope["guard_generated_rows"]
        cls.scope_module.ordinary_presentation = lambda: True
        sys.modules["hermes_cli.friday_user_scope"] = cls.scope_module
        classification = types.ModuleType("agent.tool_result_classification")
        classification.tool_effects_unknown = lambda *args, **kwargs: False
        classification.tool_call_identity = lambda call: call["id"]
        sys.modules["agent.tool_result_classification"] = classification
        state = types.ModuleType("hermes_state")
        state.StateDbCorruptError = type("StateDbCorruptError", (Exception,), {})
        state.StateDbReplacedError = type("StateDbReplacedError", (Exception,), {})
        state.classify_persistence_error = lambda error: "unknown"
        state.divert_session_transcript_jsonl = lambda *args: None
        errors = types.ModuleType("hermes_state_errors")
        errors.CompressionSessionClosedError = type(
            "CompressionSessionClosedError", (Exception,), {}
        )
        sys.modules["hermes_state"] = state
        sys.modules["hermes_state_errors"] = errors
        helpers = types.ModuleType("agent.agent_runtime_helpers")
        helpers.note_turn_start = lambda *args: None
        sys.modules["agent.agent_runtime_helpers"] = helpers
        cls.turn = dict(
            __name__="agent.turn_context", Any=Any, Optional=Optional, Tuple=Tuple
        )
        extract(turn_context, ["_bind_turn_identity"], cls.turn)

    def setUp(self):
        self.agent = types.SimpleNamespace()
        self.agent.session_id = "fixture-session"
        self.agent._persist_user_message_platform_id = "424242"
        self.agent._session_db = DB()
        self.agent._session_db_created = True
        self.agent._last_flushed_db_idx = 0
        self.agent._friday_reply_withheld = False
        self.agent._flush_messages_to_session_db_unlocked = self.ns[
            "_flush_messages_to_session_db_unlocked"
        ].__get__(self.agent)
        self.agent._ensure_db_session = lambda: setattr(
            self.agent, "_session_db_created", True
        )
        self.log = Log()
        self.ns.update(
            logger=self.log,
            _DB_PERSISTED_MARKER="_durable",
            _PERSIST_AFTER_ADMISSION_INTERRUPT="_persist_interrupt",
            _is_ephemeral_scaffolding=lambda message: False,
            _db_flush_row=lambda agent, message, call: dict(message),
            sync_flushed_message_markers=self.markers,
            _newest_checkpoint_carrier=lambda *args: -1,
            drop_shadowed_checkpoints=lambda *args: None,
            tool_call_uid_from_history=lambda *args: None,
            TOOL_CALL_UID="_tool_uid",
            _db_flush_seed_ids=self.original_seed,
        )
        self.persistence_module._db_exception_metadata = self.ns["_db_exception_metadata"]
        self.scope.update(
            managed_reply_stream=lambda agent: True,
            _restricted_reply_values=lambda agent: (object(), ("private-fixture-root",)),
            _public_reply_media=lambda content, values: values,
            _self_claim_texts=lambda values: [],
            self_deployment_claim_spans=lambda values: [],
            _public_file_delivery_text=lambda values: values,
            _withheld_reply_copy=lambda agent: "withheld",
            _retain_private_reply=lambda *args, **kwargs: None,
            _public_file_call_paths=lambda calls: calls,
            generated_public_payload=lambda row: {"content": row.get("content")},
        )

    @classmethod
    def markers(cls, messages, rows):
        for message in messages:
            message["_durable"] = True

    @classmethod
    def original_seed(cls, agent):
        current_session_id = getattr(agent, "session_id", None)
        same = getattr(agent, "_flushed_db_message_session_id", None) == current_session_id
        seed = (
            getattr(agent, "_flushed_db_message_ids", None)
            if same and agent._last_flushed_db_idx != 0
            else None
        )
        agent._flushed_db_message_session_id = current_session_id
        return seed if isinstance(seed, set) else set()

    def call(self, arguments="{}"):
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "fixture-call",
                    "function": {"name": "read_file", "arguments": arguments},
                }
            ],
        }

    def flush(self, message):
        return self.agent._flush_messages_to_session_db_unlocked([message])

    def test_success_persists_once_and_dedups(self):
        message = self.call()
        self.assertTrue(self.flush(message))
        self.assertTrue(message["_durable"])
        self.assertTrue(self.flush(message))
        self.assertEqual(len(self.agent._session_db.calls), 1)

    def test_restricted_call_fails_before_append_with_safe_metadata(self):
        message = self.call('{"path":"private-fixture-root/secret"}')
        self.assertFalse(self.flush(message))
        self.assertEqual(self.agent._session_db.calls, [])
        self.assertNotIn("_durable", message)
        details = self.agent._last_persistence_failure
        self.assertEqual(details["phase"], "guard_generated_rows")
        self.assertEqual(details["reply_boundary_reason"], "restricted_deployment_value")
        self.assertNotIn("secret", json.dumps(details))
        self.assertNotIn("private-fixture-root", str(self.log.rows))

    def test_ensure_session_phase(self):
        self.agent._session_db_created = False
        self.agent._ensure_db_session = lambda: (_ for _ in ()).throw(
            RuntimeError("DO-NOT-LOG-ENSURE")
        )
        self.assertFalse(self.flush(self.call()))
        self.assertEqual(self.agent._last_persistence_failure["phase"], "ensure_session")
        self.assertNotIn("DO-NOT-LOG", str(self.log.rows))

    def test_collect_rows_phase(self):
        self.ns["_db_flush_seed_ids"] = lambda agent: (_ for _ in ()).throw(
            ValueError("DO-NOT-LOG-COLLECT")
        )
        self.assertFalse(self.flush(self.call()))
        self.assertEqual(self.agent._last_persistence_failure["phase"], "collect_rows")

    def test_build_row_phase(self):
        self.ns["_db_flush_row"] = lambda *args: (_ for _ in ()).throw(
            ValueError("DO-NOT-LOG-BUILD")
        )
        self.assertFalse(self.flush(self.call()))
        self.assertEqual(self.agent._last_persistence_failure["phase"], "build_row")

    def test_append_phase_and_unknown_classifier(self):
        self.agent._session_db.error = RuntimeError("DO-NOT-LOG-APPEND")
        message = self.call()
        self.assertFalse(self.flush(message))
        self.assertEqual(
            self.agent._last_persistence_failure["phase"], "append_messages_batch"
        )
        self.assertEqual(self.agent._last_persistence_error_cause, "unknown")
        self.assertNotIn("_durable", message)

    def test_sync_phase_after_append(self):
        self.ns["sync_flushed_message_markers"] = lambda *args: (_ for _ in ()).throw(
            RuntimeError("DO-NOT-LOG-SYNC")
        )
        message = self.call()
        self.assertFalse(self.flush(message))
        self.assertEqual(len(self.agent._session_db.calls), 1)
        self.assertEqual(
            self.agent._last_persistence_failure["phase"], "sync_flushed_markers"
        )
        self.assertNotIn("_durable", message)

    def test_checkpoint_drop_phase(self):
        self.ns["_newest_checkpoint_carrier"] = lambda *args: 0
        self.ns["drop_shadowed_checkpoints"] = lambda *args: (_ for _ in ()).throw(
            RuntimeError("DO-NOT-LOG-DROP")
        )
        self.assertFalse(self.flush(self.call()))
        self.assertEqual(
            self.agent._last_persistence_failure["phase"], "drop_shadowed_checkpoints"
        )

    def test_guard_import_failure_has_guard_phase(self):
        original_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "hermes_cli.friday_user_scope":
                raise ImportError("DO-NOT-LOG-GUARD-IMPORT")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=blocked):
            self.assertFalse(self.flush(self.call()))
        self.assertEqual(
            self.agent._last_persistence_failure["phase"], "guard_generated_rows"
        )
        self.assertEqual(self.agent._session_db.calls, [])
        self.assertNotIn("DO-NOT-LOG", str(self.log.rows))

    def test_checkpoint_inspection_has_drop_phase(self):
        self.ns["_newest_checkpoint_carrier"] = lambda *args: (_ for _ in ()).throw(
            RuntimeError("DO-NOT-LOG-INSPECT")
        )
        self.assertFalse(self.flush(self.call()))
        self.assertEqual(
            self.agent._last_persistence_failure["phase"], "drop_shadowed_checkpoints"
        )

    def test_durable_history_is_not_reguarded(self):
        message = self.call('{"path":"private-fixture-root"}')
        message["_durable"] = True
        self.assertTrue(self.flush(message))
        self.assertEqual(self.agent._session_db.calls, [])

    def test_direct_scope_context_chain(self):
        def fail(calls):
            try:
                raise AttributeError("DO-NOT-LOG-INNER")
            except Exception:
                raise self.ScopeDenied() from None

        self.scope["_public_file_call_paths"] = fail
        self.assertFalse(self.flush(self.call()))
        chain = self.agent._last_persistence_failure["exception_chain"]
        self.assertEqual(
            [item["exception_class"].split(".")[-1] for item in chain],
            ["ScopeDenied", "AttributeError"],
        )
        self.assertNotIn("DO-NOT-LOG", str(self.log.rows))

    def test_exception_metadata_never_stringifies_and_bounds_chain(self):
        class Unsafe(Exception):
            def __str__(self):
                raise AssertionError("must not stringify")

        errors = [Unsafe("DO-NOT-LOG") for _ in range(7)]
        for index in range(1, 7):
            errors[index].__cause__ = errors[index - 1]
        details = self.ns["_db_exception_metadata"](errors[-1])
        self.assertEqual(len(details), 4)
        self.assertNotIn("DO-NOT-LOG", json.dumps(details))

    def test_exception_metadata_handles_context_cycle(self):
        first, second = ValueError("first"), RuntimeError("second")
        first.__context__ = second
        second.__context__ = first
        self.assertEqual(len(self.ns["_db_exception_metadata"](first)), 2)

    def test_exception_site_is_deepest_frame(self):
        def leaf():
            raise ValueError("DO-NOT-LOG-LEAF")

        try:
            leaf()
        except ValueError as error:
            details = self.ns["_db_exception_metadata"](error)
        self.assertEqual(details[0]["place"]["function"], "leaf")
        self.assertIsInstance(details[0]["place"]["line"], int)

    def test_correlation_matches_documented_integer_recipe(self):
        self.agent._persist_user_message_platform_id = 424242
        details = self.ns["_db_flush_failure_metadata"](self.agent, ValueError())
        expected = hashlib.sha256(b'["fixture-session","424242"]').hexdigest()
        self.assertEqual(details["request_correlation_sha256"], expected)
        self.assertNotIn("fixture-", json.dumps(details))

    def test_correlation_rejects_missing_or_wrong_types(self):
        cases = [
            ("", "424242"),
            (123, "424242"),
            ("fixture-session", ""),
            ("fixture-session", None),
            ("fixture-session", True),
            ("x" * 513, "424242"),
        ]
        for session_id, platform_id in cases:
            with self.subTest(
                session_type=type(session_id).__name__,
                platform_type=type(platform_id).__name__,
                session_length=len(session_id) if isinstance(session_id, str) else None,
            ):
                self.agent.session_id = session_id
                self.agent._persist_user_message_platform_id = platform_id
                details = self.ns["_db_flush_failure_metadata"](self.agent, ValueError())
                self.assertIsNone(details["request_correlation_sha256"])

    def test_guard_import_failure_preserves_fail_closed_and_clears_stale(self):
        def missing(agent):
            raise AttributeError("DO-NOT-LOG-GUARD")

        self.scope["_restricted_reply_values"] = missing
        self.agent._friday_reply_boundary_failure = [{"stale": "do-not-reuse"}]
        original_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "agent.session_persistence":
                raise ImportError("DO-NOT-LOG-IMPORT")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=blocked):
            public, withheld = self.scope["guard_generated_reply"](
                self.agent, "ordinary text"
            )
        self.assertEqual((public, withheld), ("withheld", True))
        self.assertEqual(
            self.agent._friday_reply_withheld_reason, "privacy_boundary_unavailable"
        )
        self.assertIsNone(self.agent._friday_reply_boundary_failure)

    def test_guard_collection_failure_preserves_fail_closed_and_clears_stale(self):
        self.scope["_restricted_reply_values"] = lambda agent: (_ for _ in ()).throw(
            AttributeError("DO-NOT-LOG")
        )
        self.persistence_module._db_exception_metadata = lambda error: (
            _ for _ in ()
        ).throw(ValueError("DO-NOT-LOG-COLLECTION"))
        self.agent._friday_reply_boundary_failure = [{"stale": "do-not-reuse"}]
        public, withheld = self.scope["guard_generated_reply"](self.agent, "ordinary text")
        self.assertEqual((public, withheld), ("withheld", True))
        self.assertIsNone(self.agent._friday_reply_boundary_failure)

    def test_guard_successful_diagnostic_retains_class_site_without_message(self):
        def missing_api(agent):
            raise AttributeError("DO-NOT-LOG-API")

        self.scope["_restricted_reply_values"] = missing_api
        public, withheld = self.scope["guard_generated_reply"](self.agent, "ordinary text")
        self.assertEqual((public, withheld), ("withheld", True))
        chain = self.agent._friday_reply_boundary_failure
        self.assertEqual(chain[0]["exception_class"], "builtins.AttributeError")
        self.assertEqual(chain[0]["place"]["function"], "missing_api")
        self.assertNotIn("DO-NOT-LOG", json.dumps(chain))

    def test_new_turn_resets_diagnostics_and_binds_inbound(self):
        self.agent._friday_reply_boundary_failure = [{"stale": "do-not-reuse"}]
        self.agent._last_persistence_failure = {"stale": "do-not-reuse"}
        self.agent._relay_pending_turn_id = "offline-next-turn"
        self.turn["_bind_turn_identity"](
            self.agent, "offline-task", None, None, None, "next-inbound"
        )
        self.assertIsNone(self.agent._friday_reply_boundary_failure)
        self.assertIsNone(self.agent._last_persistence_failure)
        self.assertEqual(self.agent._persist_user_message_platform_id, "next-inbound")

    def test_diagnostic_import_is_failure_only_no_top_level_cycle(self):
        tree = ast.parse(
            (SOURCE / "hermes_cli/friday_user_scope.py").read_text(encoding="utf-8")
        )
        guard = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "guard_generated_reply"
        )
        handlers = [node for node in ast.walk(guard) if isinstance(node, ast.ExceptHandler)]
        imports = [
            node
            for handler in handlers
            for node in ast.walk(handler)
            if isinstance(node, ast.ImportFrom)
            and node.module == "agent.session_persistence"
        ]
        self.assertTrue(imports)
        persistence_tree = ast.parse(
            (SOURCE / "agent/session_persistence.py").read_text(encoding="utf-8")
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Import)
                and any(alias.name == "hermes_cli.friday_user_scope" for alias in node.names)
                for node in persistence_tree.body
            )
        )

    def test_b150_guidance_and_all_unrelated_ast_preserved(self):
        expected = B150.read_text(encoding="utf-8")
        actual = (SOURCE / "hermes_cli/friday_user_scope.py").read_text(encoding="utf-8")
        self.assertIn("Sheet freeze=A2 freezes row 1", actual)
        self.assertIn("print_area=A1:G5", actual)
        self.assertIn("number_format=0.00", actual)
        left, right = ast.parse(expected), ast.parse(actual)

        def unrelated(tree):
            return [
                ast.dump(node, include_attributes=False)
                for node in tree.body
                if not (
                    isinstance(node, ast.FunctionDef)
                    and node.name == "guard_generated_reply"
                )
            ]

        self.assertEqual(unrelated(left), unrelated(right))


if __name__ == "__main__":
    unittest.main(verbosity=2)
