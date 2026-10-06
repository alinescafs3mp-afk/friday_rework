"""Real PluginState with deterministic native-boundary failure injection.

These tests prove metadata/callback ordering, not actual worker execution.
"""
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_controller_test", root / "__init__.py",
                                             submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_controller_test.controller import Controller, ControllerError, WorkerBinding, KEY
from friday_controller_test.associations import Associations, KEY as ASSOCIATIONS_KEY
from friday_controller_test.adapters.contract import PreparedNative, NativeObservation, VerifiedInput
from friday_controller_test.boundary import WorkBrief
from friday_controller_test.supervision import UnitObservation
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from utils import atomic_json_write

OWNER = dict(bot_id="bot", user_id="user", chat_id="chat", thread_id="topic",
             message_id="message", session_key="key", session_id="session", profile="")
PRINCIPAL = {k: OWNER[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "profile")}
BRIEF = WorkBrief("dsh", "repair fixture", "unchanged test passes")
PREPARED = PreparedNative("owned-home", "owned-preparation-receipt")
OBSERVED = NativeObservation("1" * 32, "actual-session", "owned-event-receipt", 1, "running")


class Adapter:
    def __init__(self, store):
        self.store = store
        self.prepares = self.submits = self.observes = self.stops = 0
        self.before_prepare = self.before_callback = None
        self.value = OBSERVED

    def prepare(self, row, brief, inputs):
        self.prepares += 1
        if self.before_prepare:
            self.before_prepare()
        return PREPARED

    def submit(self, row, brief, inputs, prepared, callback):
        self.submits += 1
        # Read with a NEW native state object: UNKNOWN is on disk before effect.
        reopened = Associations(PluginState("friday_controller"), clock=self.store.clock)
        assert reopened.get("task", OWNER)["submission_observation"] == "UNKNOWN"
        if self.before_callback:
            self.before_callback()
        callback(self.value)
        return self.value

    def observe(self, row, prepared):
        self.observes += 1
        return self.value

    def stop(self, row, prepared, intent):
        self.stops += 1
        assert intent in {"cancel", "pause", "deadline"}
        return replace(self.value, state="stopped")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        token = set_hermes_home_override(Path(self.temp.name))
        self.addCleanup(reset_hermes_home_override, token)
        self.clock = 1000
        self.state = PluginState("friday_controller")
        self.store = Associations(self.state, clock=lambda: self.clock)
        self.args = dict(task_id="task", admission_key="admission", owner=OWNER, brief=BRIEF,
                         workspace_reference="owned-workspace", budget_seconds=60, deadline_unix=1060,
                         supervisor={"scope": "user", "unit": "friday-rework-worker-" + "a" * 32 + ".service"})
        self.store.claim(**self.args)
        self.adapter = Adapter(self.store)
        self.emergencies = []
        self.controller = self.reopen()

    def emergency(self, row):
        self.emergencies.append(copy.deepcopy(row))
        return UnitObservation(row["supervisor"]["unit"], (row["native"] or {}).get("invocation_id", ""),
                               "inactive", "dead", "success", 0, "", False)

    def reopen(self):
        store = Associations(PluginState("friday_controller"), clock=lambda: self.clock)
        return Controller(store, {"dsh": WorkerBinding(self.adapter, self.emergency)})

    def prepare(self):
        return self.controller.prepare("task", OWNER, BRIEF, ())

    def start(self):
        return self.controller.start("task", OWNER, BRIEF, ())

    def row(self):
        return self.store.get("task", OWNER)

    def test_preparation_reopen_and_duplicate_no_reexecution(self):
        self.assertEqual(self.prepare(), PREPARED)
        self.controller = self.reopen()
        self.assertEqual(self.prepare(), PREPARED)
        self.assertEqual(self.adapter.prepares, 1)
        self.assertEqual(self.adapter.submits, 0)

    def test_preparation_reservation_precedes_adapter_and_releases_lock(self):
        def inspect():
            self.assertIsNone(PluginState("friday_controller").get(KEY)["jobs"]["task"]["prepared"])
            self.assertEqual(self.row()["submission_observation"], "NOT_SUBMITTED")
            self.assertIs(self.row()["preparation_reserved"], True)
        self.adapter.before_prepare = inspect
        self.prepare()

    def test_failed_preparation_never_automatically_repeats(self):
        self.adapter.before_prepare = lambda: (_ for _ in ()).throw(OSError("prepare failure"))
        with self.assertRaises(OSError):
            self.prepare()
        self.controller = self.reopen()
        with self.assertRaisesRegex(ControllerError, "reconciliation"):
            self.prepare()
        with self.assertRaisesRegex(ControllerError, "reconciliation"):
            self.start()
        self.assertEqual((self.adapter.prepares, self.adapter.submits), (1, 0))

    def test_preparation_changed_brief_or_input_denied(self):
        self.prepare()
        with self.assertRaisesRegex(ControllerError, "brief_changed"):
            self.controller.prepare("task", OWNER, replace(BRIEF, brief="different"), ())
        item = VerifiedInput("/owned/file", "/input/file", 2, "a" * 64, "ingress")
        with self.assertRaisesRegex(ControllerError, "inputs_changed"):
            self.controller.prepare("task", OWNER, BRIEF, (item,))
        self.assertEqual(self.adapter.prepares, 1)

    def test_unready_or_foreign_owner_never_gets_preparation(self):
        self.controller = Controller(self.store, {})
        with self.assertRaisesRegex(ControllerError, "worker_not_admitted"):
            self.prepare()
        with self.assertRaisesRegex(RuntimeError, "foreign"):
            self.controller.prepare("task", {**OWNER, "user_id": "other"}, BRIEF, ())
        self.assertEqual(self.adapter.prepares, 0)

    def test_unknown_precedes_launch_native_record_and_duplicate_observe(self):
        self.prepare()
        self.assertEqual(self.start(), OBSERVED)
        self.controller = self.reopen()
        self.assertEqual(self.start(), OBSERVED)
        self.assertEqual((self.adapter.submits, self.adapter.observes), (1, 1))
        row = self.row()
        self.assertEqual(row["native"]["worker_reference"], "actual-session")
        self.assertEqual((row["goal_verification"], row["delivery"]), ("NOT_RUN", "NOT_RUN"))
        self.assertEqual((row["budget_seconds"], row["deadline_unix"]), (60, 1060))

    def test_ambiguous_launch_recovery_never_resubmits(self):
        self.prepare()
        self.adapter.before_callback = lambda: (_ for _ in ()).throw(TimeoutError("uncertain native RPC"))
        with self.assertRaises(TimeoutError) as error:
            self.start()
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))
        self.assertEqual(self.row()["submission_observation"], "UNKNOWN")
        self.controller = self.reopen()
        self.adapter.value = replace(OBSERVED, invocation_id="", worker_reference="", state="unknown")
        self.assertEqual(self.start().state, "unknown")
        self.assertEqual(self.row()["submission_observation"], "UNKNOWN")
        self.assertEqual(self.adapter.submits, 1)

    def test_callback_write_failure_stops_actual_identity_without_state_read(self):
        self.prepare()
        def fail(*args):
            self.assertEqual(args[2]["invocation_id"], OBSERVED.invocation_id)
            raise OSError("identity write failed")
        with patch.object(self.controller.associations, "attach_native", side_effect=fail):
            with self.assertRaisesRegex(OSError, "identity write failed") as error:
                self.start()
        self.assertEqual(self.emergencies[-1]["native"]["invocation_id"], OBSERVED.invocation_id)
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))
        self.assertEqual(self.row()["submission_observation"], "UNKNOWN")

    def test_write_committed_then_directory_failure_retains_no_replay(self):
        self.prepare()
        real = self.controller.associations.attach_native
        def fail_after(*args):
            real(*args)
            raise OSError("directory durability uncertain")
        with patch.object(self.controller.associations, "attach_native", side_effect=fail_after):
            with self.assertRaises(OSError):
                self.start()
        self.assertEqual(self.row()["native"]["invocation_id"], OBSERVED.invocation_id)
        self.controller = self.reopen()
        self.start()
        self.assertEqual(self.adapter.submits, 1)

    def test_late_cancel_during_submit_is_retained_and_stopped(self):
        self.prepare()
        self.adapter.before_callback = lambda: self.store.request_stop("task", OWNER, "cancel")
        with self.assertRaisesRegex(ControllerError, "retained_stop"):
            self.start()
        self.assertEqual(self.row()["stop_intent"], "cancel")
        self.assertEqual(len(self.emergencies), 1)
        self.controller = self.reopen()
        self.assertEqual(self.start().state, "stopped")
        self.assertEqual(self.adapter.submits, 1)

    def test_cancel_during_prepare_preserves_reference_but_blocks_submission(self):
        self.adapter.before_prepare = lambda: self.store.request_stop("task", OWNER, "cancel")
        self.assertEqual(self.prepare(), PREPARED)
        with self.assertRaisesRegex(RuntimeError, "stopped_or_expired"):
            self.start()
        self.assertEqual(self.adapter.submits, 0)

    def test_stop_persistence_failure_still_attempts_native_stop(self):
        self.prepare(); self.start()
        with patch.object(self.controller.associations, "request_stop", side_effect=OSError("stop write failed")):
            with self.assertRaisesRegex(OSError, "stop write failed") as error:
                self.controller.stop("task", PRINCIPAL, "cancel")
        self.assertEqual(len(self.emergencies), 1)
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))
        self.assertIsNone(self.row()["stop_intent"])

    def test_cancelled_then_pause_cannot_change_terminal_intent(self):
        self.prepare(); self.start()
        self.assertEqual(self.controller.stop("task", PRINCIPAL, "cancel").state, "stopped")
        self.controller.stop("task", PRINCIPAL, "pause")
        self.assertEqual(self.row()["stop_intent"], "cancel")

    def test_cross_bot_user_chat_topic_profile_control_denied(self):
        self.prepare(); self.start()
        for key in PRINCIPAL:
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "foreign"):
                self.controller.stop("task", {**PRINCIPAL, key: "other"}, "cancel")
        self.assertEqual((self.adapter.stops, len(self.emergencies)), (0, 0))

    def test_recovery_record_failure_stops_last_actual_identity(self):
        self.prepare(); self.start()
        with patch.object(self.controller.associations, "observe", side_effect=OSError("evidence write failed")):
            with self.assertRaises(OSError) as error:
                self.controller.reconcile("task", OWNER)
        self.assertEqual(self.emergencies[-1]["native"]["worker_reference"], "actual-session")
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))

    def test_changed_native_identity_is_not_adopted_for_stop(self):
        self.prepare(); self.start()
        self.adapter.value = replace(OBSERVED, invocation_id="2" * 32)
        with self.assertRaisesRegex(ControllerError, "identity_changed"):
            self.controller.reconcile("task", OWNER)
        self.assertEqual(self.emergencies[-1]["native"]["invocation_id"], "1" * 32)

    def test_deadline_reconciliation_calls_stop_without_observe_or_reset(self):
        self.prepare(); self.start(); self.clock = 1061
        self.assertEqual(self.controller.reconcile("task", OWNER).state, "stopped")
        self.assertEqual(self.adapter.observes, 0)
        self.assertEqual(self.row()["deadline_unix"], 1060)

    def test_corrupt_preparation_never_prevents_emergency_stop(self):
        self.prepare(); self.start()
        self.state.set(KEY, {"corrupt": True})
        with self.assertRaisesRegex(ControllerError, "invalid_preparation_store") as error:
            self.controller.stop("task", PRINCIPAL, "cancel")
        self.assertEqual(self.row()["stop_intent"], "cancel")
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))

    def test_failed_emergency_stop_is_never_reported_confirmed(self):
        self.prepare()
        self.adapter.before_callback = lambda: (_ for _ in ()).throw(OSError("original failure"))
        for stop in (lambda _: (_ for _ in ()).throw(OSError("native stop unavailable")),
                     lambda _: UnitObservation("unit", "", "active", "running", "success", 5, "/group", True)):
            self.controller.bindings["dsh"] = WorkerBinding(self.adapter, stop)
            if self.row()["submission_observation"] == "NOT_SUBMITTED":
                action = self.start
            else:
                action = lambda: self.controller.stop("task", PRINCIPAL, "cancel")
                self.adapter.stop = lambda *args: (_ for _ in ()).throw(OSError("original failure"))
            with self.assertRaisesRegex(OSError, "original failure") as error:
                action()
            self.assertIn("STOP_UNCONFIRMED", " ".join(error.exception.__notes__))

    def test_completion_does_not_assert_goal_or_delivery(self):
        self.prepare(); self.adapter.value = replace(OBSERVED, state="completed")
        self.assertEqual(self.start().state, "completed")
        self.assertEqual((self.row()["goal_verification"], self.row()["delivery"]), ("NOT_RUN", "NOT_RUN"))

    def test_duplicate_with_lost_preparation_stops_without_second_launch(self):
        self.prepare(); self.start()
        self.state.set(KEY, {"schema_version": 1, "jobs": {}})
        with self.assertRaisesRegex(ControllerError, "missing_or_foreign") as error:
            self.start()
        self.assertEqual(self.adapter.submits, 1)
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))

    def test_consumed_budget_stops_despite_wall_clock_regression(self):
        self.prepare(); self.start()
        self.store.observe("task", OWNER, native=self.row()["native"],
                           evidence_reference="native-later-observation", elapsed_seconds=61)
        self.clock = 999
        self.assertEqual(self.controller.reconcile("task", OWNER).state, "stopped")
        self.assertEqual(self.adapter.observes, 0)
        self.assertEqual(self.row()["elapsed_seconds"], 61)

    def test_malformed_observation_cannot_bypass_stop_or_claim_completion(self):
        self.prepare(); self.start()
        for delta in ({"elapsed_seconds": float("nan")}, {"elapsed_seconds": True},
                      {"state": "invented"}, {"worker_reference": 0},
                      {"invocation_id": "", "state": "completed"}):
            with self.subTest(delta=delta):
                self.adapter.value = replace(OBSERVED, **delta)
                count = len(self.emergencies)
                with self.assertRaises(RuntimeError):
                    self.controller.reconcile("task", OWNER)
                self.assertEqual(len(self.emergencies), count + 1)
        self.assertEqual(self.row()["goal_verification"], "NOT_RUN")

    def test_lost_preparation_key_or_row_cannot_repeat_prepare(self):
        self.prepare()
        data = json.loads(self.state.path.read_text())
        del data[KEY]
        atomic_json_write(self.state.path, data, mode=0o600)
        self.controller = self.reopen()
        with self.assertRaisesRegex(ControllerError, "reconciliation"):
            self.prepare()
        self.state.set(KEY, {"schema_version": 1, "jobs": {}})
        with self.assertRaisesRegex(ControllerError, "reconciliation"):
            self.prepare()
        self.assertEqual(self.adapter.prepares, 1)

    def test_reservation_survives_auxiliary_write_failure(self):
        real = self.controller.associations.state.set
        def fail(key, value):
            if key == KEY:
                raise OSError("auxiliary reservation write failed")
            return real(key, value)
        with patch.object(self.controller.associations.state, "set", side_effect=fail):
            with self.assertRaisesRegex(OSError, "auxiliary"):
                self.prepare()
        self.assertIs(self.row()["preparation_reserved"], True)
        self.controller = self.reopen()
        with self.assertRaisesRegex(ControllerError, "reconciliation"):
            self.prepare()
        self.assertEqual(self.adapter.prepares, 0)

    def test_missing_identity_refreshes_concurrent_cancel_or_pause(self):
        self.prepare()
        self.adapter.value = replace(OBSERVED, invocation_id="", worker_reference="", state="unknown")
        self.adapter.before_callback = lambda: self.store.request_stop("task", OWNER, "cancel")
        with self.assertRaisesRegex(ControllerError, "retained_stop") as error:
            self.start()
        self.assertEqual(self.row()["stop_intent"], "cancel")
        self.assertIn("STOP_CONFIRMED", " ".join(error.exception.__notes__))
        self.assertEqual(self.row()["submission_observation"], "UNKNOWN")

    def test_owner_stop_during_identity_free_submission_cannot_be_ignored(self):
        self.prepare()
        self.adapter.value = replace(OBSERVED, invocation_id="", worker_reference="", state="unknown")
        self.adapter.before_callback = lambda: self.controller.stop("task", PRINCIPAL, "pause")
        with self.assertRaisesRegex(ControllerError, "retained_stop"):
            self.start()
        self.assertEqual(self.row()["stop_intent"], "pause")
        self.assertEqual((self.adapter.stops, len(self.emergencies)), (1, 1))

    def test_missing_reservation_marker_is_not_silently_migrated(self):
        data = self.state.get(ASSOCIATIONS_KEY)
        del data["jobs"]["task"]["preparation_reserved"]
        self.state.set(ASSOCIATIONS_KEY, data)
        with self.assertRaisesRegex(RuntimeError, "invalid_association_store"):
            self.prepare()
        self.assertEqual(self.adapter.prepares, 0)


if __name__ == "__main__":
    unittest.main()
