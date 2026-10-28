"""Small real-PluginState contention controls; no native launch or network."""
import contextlib
from contextvars import copy_context
import copy
import threading
import time
import unittest
from unittest.mock import patch

from test_controller import ControllerTests, OWNER, BRIEF, OBSERVED
from friday_controller_test.associations import AssociationLockBusy


class CurrentLaunchLockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.store = self.fixture.controller.associations
        self.fixture.adapter.store = self.store
        self.threads = []
        self.addCleanup(self.join_threads)

    def join_threads(self):
        for worker in self.threads:
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def hold_after_unknown(self, seconds=.35, change=None):
        begin = self.store.begin_submission
        ready = threading.Event()
        failures = []
        def held():
            try:
                with self.store._thread_lock:
                    ready.set()
                    threading.Event().wait(seconds)
                    if change is not None:
                        change()
            except BaseException as error:
                failures.append(error)
        def claimed(*args):
            row = begin(*args)
            thread = threading.Thread(target=copy_context().run, args=(held,))
            self.threads.append(thread)
            thread.start()
            self.assertTrue(ready.wait(3))
            return row
        self.store.begin_submission = claimed
        self.addCleanup(lambda: self.assertEqual(failures, []))

    def test_original_quarter_second_allowance_reproduces_failure(self):
        self.hold_after_unknown()
        with patch.object(self.store, "submission_budget", lambda row: contextlib.nullcontext()):
            with self.assertRaises(AssociationLockBusy):
                self.fixture.start()
        self.assertEqual(self.fixture.adapter.submits, 0)
        self.assertIsNone(self.store._lock_allowance.get())

    def test_healthy_owned_contention_then_fresh_read_submits_once(self):
        self.hold_after_unknown()
        before = self.fixture.row()
        result = self.fixture.start()
        self.assertEqual(result, OBSERVED)
        self.assertEqual(self.fixture.adapter.submits, 1)
        row = self.fixture.row()
        self.assertEqual(row["deadline_unix"], before["deadline_unix"])
        self.assertEqual(row["budget_seconds"], before["budget_seconds"])
        self.assertIsNone(self.store._lock_allowance.get())

    def test_cancel_written_by_holder_is_current_and_never_submits(self):
        self.hold_after_unknown(change=lambda: self.store.request_stop("task", OWNER, "cancel"))
        with self.assertRaisesRegex(RuntimeError, "retained_stop_or_deadline"):
            self.fixture.start()
        self.assertEqual(self.fixture.adapter.submits, 0)
        self.assertEqual(self.fixture.row()["stop_intent"], "cancel")
        self.assertIsNone(self.store._lock_allowance.get())

    def test_original_job_expiry_during_contention_never_submits(self):
        self.hold_after_unknown(change=lambda: setattr(self.fixture, "clock", 1061))
        with self.assertRaises(TimeoutError):
            self.fixture.start()
        self.assertEqual(self.fixture.adapter.submits, 0)
        self.assertIsNone(self.store._lock_allowance.get())

    def test_owned_contention_is_still_capped_and_cleanup_is_ordinary(self):
        self.hold_after_unknown(seconds=2.3)
        cleanup = []
        original = self.fixture.controller.bindings["dsh"].emergency_stop
        from friday_controller_test.controller import WorkerBinding
        def stop(row):
            cleanup.append(self.store._lock_allowance.get())
            return original(row)
        self.fixture.controller.bindings["dsh"] = WorkerBinding(self.fixture.adapter, stop)
        began = time.monotonic()
        with self.assertRaises(AssociationLockBusy):
            self.fixture.start()
        elapsed = time.monotonic() - began
        self.assertGreater(elapsed, 1.7)
        self.assertLess(elapsed, 2.25)
        self.assertEqual(cleanup, [None])
        self.assertEqual(self.fixture.adapter.submits, 0)

    def test_foreign_admission_lock_still_refuses_immediately(self):
        import fcntl
        row = self.fixture.row()
        with (self.store.state.data_dir / "admission.lock").open("r+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            began = time.monotonic()
            with self.store.submission_budget(row):
                with self.assertRaisesRegex(RuntimeError, "admission_busy"):
                    self.store.get("task", OWNER)
            self.assertLess(time.monotonic() - began, .25)

    def test_caller_cutoff_is_rechecked_after_slow_work(self):
        row = self.fixture.row()
        class Caller:
            end = time.monotonic() + 2
            def check(self, *args, **kwargs):
                pass
        span = Caller()
        with patch("hermes_cli.friday_cli_caller.current", return_value=span):
            with self.store.submission_budget(row):
                span.end = time.monotonic() - .01
                with self.assertRaisesRegex(TimeoutError, "lock_deadline"):
                    self.store.get("task", OWNER)
        self.assertIsNone(self.store._lock_allowance.get())

    def test_job_cutoff_after_slow_work_never_restores_acquisition_time(self):
        row = self.fixture.row()
        row["deadline_unix"] = self.fixture.clock + .02
        with self.store.submission_budget(row):
            threading.Event().wait(.03)
            with self.assertRaisesRegex(TimeoutError, "submission_lock_deadline"):
                self.store.get("task", OWNER)

    def test_invalid_current_clock_during_scope_is_not_authority(self):
        row = self.fixture.row()
        with self.store.submission_budget(row):
            self.fixture.clock = float("nan")
            with self.assertRaisesRegex(RuntimeError, "invalid_budget"):
                self.store.get("task", OWNER)

    def test_submission_scope_preserves_same_thread_requirement(self):
        row = self.fixture.row()
        from contextvars import copy_context
        result = []
        with self.store.submission_budget(row):
            def read():
                try:
                    self.store.get("task", OWNER)
                except BaseException as error:
                    result.append(error)
            context = copy_context()
            worker = threading.Thread(target=context.run, args=(read,))
            self.threads.append(worker)
            worker.start()
            worker.join(3)
        self.assertEqual(len(result), 1)
        self.assertRegex(str(result[0]), "sequential same-thread")


if __name__ == "__main__":
    unittest.main()
