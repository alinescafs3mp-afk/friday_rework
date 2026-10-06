"""Content validation and absence of routing authority from model/environment."""
from contextvars import Context, ContextVar
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "friday_boundary_test", Path(__file__).resolve().parents[1] / "plugins/friday_rework/boundary.py")
boundary = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = boundary
spec.loader.exec_module(boundary)

BRIEF = {"worker": "dsh", "brief": "Inspect the owned fixture.", "goal_check": "Report its verified value."}


def bind(identity="fixture-session"):
    fields = dict(PLATFORM="telegram", CHAT_ID="fixture-chat", CHAT_TYPE="dm", THREAD_ID="",
                  USER_ID="fixture-user", KEY="fixture-key", ID=identity,
                  MESSAGE_ID="fixture-message", PROFILE="")
    for key, value in fields.items():
        ContextVar("HERMES_SESSION_" + key).set(value)


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_supply_execution_authority(self):
        for key in ("owner", "chat_id", "workspace", "command", "deadline", "task_id"):
            with self.subTest(key=key):
                result = json.loads(boundary.work_handler({**BRIEF, key: "forged"}))
                self.assertEqual(result, {"accepted": False, "error": "invalid_fields"})

    def test_environment_is_not_bound_context(self):
        with patch.dict(os.environ, {"HERMES_SESSION_ID": "forged", "HERMES_SESSION_CHAT_ID": "forged"}):
            result = Context().run(boundary.work_handler, BRIEF)
        self.assertEqual(json.loads(result)["error"], "missing_bound_owner")

    def test_valid_bound_request_still_cannot_create_job(self):
        def run():
            bind()
            for worker in ("dsh", "a0"):
                result = json.loads(boundary.work_handler({**BRIEF, "worker": worker}, session_id="fixture-session", future_field=1))
                self.assertFalse(result["accepted"])
                self.assertEqual(result["error"], "worker_not_admitted")
                self.assertNotIn("task_id", result)
        Context().run(run)

    def test_cross_session_call_is_rejected(self):
        def run():
            bind()
            return boundary.work_handler(BRIEF, session_id="other-session")
        self.assertEqual(json.loads(Context().run(run))["error"], "session_mismatch")

    def test_context_does_not_leak_to_another_call(self):
        Context().run(bind)
        self.assertEqual(json.loads(Context().run(boundary.work_handler, BRIEF))["error"], "missing_bound_owner")

    def test_text_limits_use_bytes_and_invalid_unicode_fails_closed(self):
        for value in ("", " \t", None, [], "a\x00b", "\ud800", "я" * 4097):
            with self.subTest(value=repr(value)[:30]):
                result = json.loads(boundary.work_handler({**BRIEF, "brief": value}))
                self.assertFalse(result["accepted"])
                self.assertNotEqual(result["error"], "worker_not_admitted")


if __name__ == "__main__":
    unittest.main()
