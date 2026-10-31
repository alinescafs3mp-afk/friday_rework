"""Finite offline checks of the existing idle runner's attempt wall cap."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import tempfile
import unittest

from qpb.atomic import atomic_write_json
from qpb.cli import _status
from qpb.report import build_report
from qpb.runner import IdleRunner, _attempt_budget
from qpb.store import RunStore


class UnfinishedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-unfinished-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = RunStore(self.root, "fixture")
        self.store.ensure_dirs()

    def record(self, n=1, outcome="technical_loss", wall=5, task="t", **extra):
        value = dict(attempt_id=f"gpqa__{task}__a{n}", attempt_n=n,
                     benchmark="gpqa", task_id=task, outcome=outcome,
                     state=outcome, sent=True, wall_s=wall)
        value.update(extra)
        self.store.save_request(value)
        return value

    def saved(self, record):
        self.store.save_prediction(dict(record, outcome="complete", finish_reason="stop"))

    def test_all_unfinished_outcomes_and_exact_successor_identity(self):
        failed = self.record(wall=5)
        successor = self.record(2, "complete", wall=100)
        self.saved(successor)
        self.record(task="fg", outcome="INTERRUPTED_BY_FOREGROUND", wall=7)
        self.record(task="stop", outcome="CANCELLED_BY_STOP", wall=11)
        self.record(task="unknown", outcome="OUTCOME_UNKNOWN", wall=None,
                    partial_response_timing={"wall_s": 13})
        self.record(task="protocol", outcome="protocol_diagnostic", wall=17)
        interruptions, budget = _attempt_budget(self.store)
        self.assertEqual(interruptions, {("gpqa", "fg"): 1})
        self.assertEqual(budget["interrupted_wall_s"], 18)
        self.assertEqual(budget["unfinished_attempt_wall_s"], 53)
        self.assertEqual(budget["unmeasured_unfinished_attempts"], 0)
        self.assertTrue(budget["unfinished_attempt_wall_complete"])
        # Crash between prediction and request commit: the saved exact attempt
        # is complete despite its stale SENDING/unknown request record.
        self.saved(failed)
        self.assertEqual(_attempt_budget(self.store)[1]["unfinished_attempt_wall_s"], 148)

    def test_dedup_saved_top_and_partial_wall_and_foreground_count(self):
        record = self.record(outcome="INTERRUPTED_BY_FOREGROUND", wall=5,
                             partial_response_timing={"wall_s": 5})
        atomic_write_json(self.store.requests / "duplicate.json", record)
        interruptions, budget = _attempt_budget(self.store)
        self.assertEqual(interruptions, {("gpqa", "t"): 1})
        self.assertEqual(budget["unfinished_attempt_wall_s"], 5)
        self.assertEqual(budget["interrupted_wall_s"], 5)
        # Same B103 recovered timing appears both top-level and in partial timing.
        record.update(outcome="technical_loss", state="LOST_RESPONSE_AFTER_STREAM_FAILURE")
        self.store.save_request(record)
        atomic_write_json(self.store.requests / "duplicate.json", record)
        self.assertEqual(_attempt_budget(self.store)[1]["unfinished_attempt_wall_s"], 5)

    def test_conflicting_observations_are_not_summed_or_underestimated(self):
        record = self.record(wall=3, partial_response_timing={"wall_s": 5})
        atomic_write_json(self.store.requests / "duplicate.json", dict(record, wall_s=7))
        self.assertEqual(_attempt_budget(self.store)[1]["unfinished_attempt_wall_s"], 7)

    def test_unknown_expense_is_not_zero_or_nan_and_not_sent_is_known(self):
        for i, value in enumerate((None, True, -1, float("nan"), float("inf"))):
            self.record(task=str(i), wall=value)
        self.record(task="not-sent", outcome="interrupted_before_send", wall=None, sent=False)
        self.record(task="fallback", wall=True, partial_response_timing={"wall_s": 2})
        _, budget = _attempt_budget(self.store)
        self.assertEqual(budget["unfinished_attempt_wall_s"], 2)
        self.assertEqual(budget["unmeasured_unfinished_attempts"], 5)
        self.assertFalse(budget["unfinished_attempt_wall_complete"])

    def test_partial_copy_of_same_attempt_is_counted_once(self):
        self.record(wall=None)
        (self.store.requests / "gpqa__t__a1.partial.json").write_text("{")
        self.assertEqual(_attempt_budget(self.store)[1]["unmeasured_unfinished_attempts"], 1)

    def runner(self, cap):
        runner = object.__new__(IdleRunner)
        runner.store = self.store
        runner.pilot_only = False
        runner.window_hours = None
        runner.policy = {"max_interrupted_attempt_wall_seconds": cap,
                         "max_foreground_interruptions_per_task": 3}
        order = {"ifbench": [], "gpqa": ["t"], "lcb": []}
        runner.corpus = type("Corpus", (), {"order": order, "pilot": order})()
        self.store.write_manifest({"authorization_expires_epoch": 10**12})
        return runner

    def test_exact_policy_boundary_stops_before_admission_and_is_reported(self):
        self.record(wall=5)
        self.record(2, outcome="OUTCOME_UNKNOWN", wall=None,
                    partial_response_timing={"wall_s": 7})
        runner = self.runner(12)
        # Direct existing loop: no client, network, admission or recovery effect.
        with redirect_stdout(StringIO()):
            self.assertEqual(runner._loop(), 0)
        self.assertEqual(self.store.manifest()["state"], "PAUSED_POLICY")
        self.assertEqual(self.store.manifest()["interrupted_wall_s"], 0)
        self.assertEqual(self.store.manifest()["unfinished_attempt_wall_s"], 12)
        self.assertEqual(self.store.progress()["unfinished_attempt_wall_s"], 12)
        self.assertTrue(self.store.progress()["unfinished_attempt_wall_complete"])

    def test_manual_pause_is_retained_when_cap_is_exhausted(self):
        self.record(wall=5)
        runner = self.runner(5)
        self.store.set_control(pause=True, stop=False)
        with redirect_stdout(StringIO()):
            self.assertEqual(runner._loop(), 0)
        self.assertEqual(self.store.manifest()["state"], "MANUAL_PAUSED")
        self.assertTrue(self.store.control()["pause"])

    def test_below_cap_preserves_unknown_retry_block(self):
        self.record(outcome="OUTCOME_UNKNOWN", wall=5)
        runner = self.runner(6)
        self.assertEqual(runner._loop(), 2)
        self.assertEqual(self.store.manifest()["state"], "RECOVERY_REQUIRED")
        self.assertEqual(self.store.manifest()["unfinished_attempt_wall_s"], 5)

    def test_nearest_status_and_report_recompute_saved_budget(self):
        self.record(wall=5)
        self.store.write_manifest(dict(mode="idle", coordinator_dir=str(self.root / "admission"),
            idle_policy={"max_interrupted_attempt_wall_seconds": 12},
            authorization_expires_epoch=10**12,
            datasets={b: {"ids": []} for b in ("ifbench", "gpqa", "lcb")}))
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(_status(self.root, self.root, "fixture"), 0)
        status = json.loads(output.getvalue().splitlines()[-1])
        report = build_report(self.store)["unfinished_attempt_budget"]
        for value in (status, report):
            self.assertEqual(value["unfinished_attempt_wall_s"], 5)
            self.assertEqual(value["max_interrupted_attempt_wall_seconds"], 12)
            self.assertTrue(value["unfinished_attempt_wall_complete"])


if __name__ == "__main__":
    unittest.main()
