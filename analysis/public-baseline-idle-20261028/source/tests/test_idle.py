"""Local events and localhost only; production sockets are forbidden."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from qpb.idle import Coordinator, IdleBlocked, POLICY, foreground, endpoint_key
from qpb.idle_transport import monitored_post, InterruptedByForeground, abort_owned
from qpb.errors import OutcomeUnknownError
from qpb.store import RunStore


class IdleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-idle-")
        self.addCleanup(self.tmp.cleanup)
        self.clock = [1000.0]
        self.c = Coordinator(Path(self.tmp.name) / "admission", clock=lambda: self.clock[0])
        self.c.certify(coverage={"all_clients": True, "whole_tasks": True, "embeddings": True},
                       cancellation={"installed_source": "FIXTURE", "rid_before_prefill": True,
                                     "terminal_evidence": "FIXTURE", "live_handoff": "FIXTURE"})
        self.clock[0] += 61
        self.store = RunStore(Path(self.tmp.name) / "runs", "fixture")
        self.store.ensure_dirs()
        self.store.set_control(pause=False, stop=False)

    def reserve(self, run="fixture"):
        return self.c.reserve(run, "ifbench__1__a1", "hash", "fingerprint")

    def test_foreground_before_permit_and_tool_gap_multiple_clients(self):
        task = self.c.foreground_begin("gateway", "telegram-task")
        child = self.c.foreground_begin("qwen", "call", parent=task)
        embedding = self.c.foreground_begin("memory", "embed", resource="spark-embedding")
        self.c.foreground_end(child)
        self.clock[0] += 10000
        with self.assertRaises(IdleBlocked):
            self.reserve()
        self.c.foreground_end(task)
        with self.assertRaises(IdleBlocked):
            self.reserve()
        self.c.foreground_end(embedding)
        with self.assertRaises(IdleBlocked):
            self.reserve()
        self.clock[0] += 60
        self.reserve()

    def test_foreground_between_permit_and_dispatch_revokes_without_send(self):
        permit = self.reserve()
        self.c.foreground_begin("gateway", "task")
        with self.assertRaises(IdleBlocked):
            self.c.dispatch(permit)
        self.assertIsNone(self.c.snapshot()["inflight"])

    def test_unknown_or_dispatched_blocks_other_run_and_process_restart(self):
        permit = self.reserve()
        self.c.dispatch(permit)
        other = Coordinator(self.c.dir, clock=lambda: self.clock[0] + 1000000)
        with self.assertRaises(IdleBlocked):
            other.reserve("another-run", "new-task", "hash", "fingerprint")
        self.c.unknown(permit, "worker died before server ID could be returned")
        self.assertEqual(other.snapshot()["inflight"]["rid"], permit["rid"])
        with self.assertRaises(IdleBlocked):
            other.reserve("another-run", "new-task", "hash", "fingerprint")

    def test_dispatched_permit_cannot_send_again_or_erase_unknown(self):
        permit = self.reserve()
        self.c.dispatch(permit)
        with self.assertRaises(IdleBlocked):
            self.c.dispatch(permit)
        self.c.unknown(permit, "lost original response")
        self.c.foreground_begin("gateway", "new-task")
        with self.assertRaises(IdleBlocked):
            self.c.dispatch(permit)
        self.assertEqual(self.c.snapshot()["inflight"]["state"], "OUTCOME_UNKNOWN")

    def test_cancel_ownership_and_http_ack_not_terminal(self):
        permit = self.reserve()
        self.c.dispatch(permit)
        with self.assertRaises(IdleBlocked):
            abort_owned(self.c, dict(permit, rid=""), "http://production.invalid/v1", {}, 1)
        self.assertTrue(self.c.cancellation(permit))
        self.assertFalse(self.c.cancellation(permit))
        with self.assertRaises(IdleBlocked):
            self.c.terminal(permit, "cancel-http-200", evidence="ACK")
        with self.assertRaises(IdleBlocked):
            self.reserve("different-run")

    def test_coordinator_fault_foreground_proceeds_background_closed(self):
        (self.c.dir / "state.json").write_text("{")
        self.assertIsNone(self.c.foreground_begin("gateway", "still-runs"))
        self.assertTrue((self.c.dir / "FAULT").exists())

    def test_lost_foreground_response_and_missing_heartbeat_never_release(self):
        token = self.c.foreground_begin("qwen", "request")
        self.c.foreground_end(token, outcome_known=False)
        self.clock[0] += 864000
        with self.assertRaises(IdleBlocked):
            self.reserve()

    def _post(self, *, terminal="abort", send_cancel_response=True, finish_after_cancel=True):
        permit = self.reserve()
        event = threading.Event()
        calls = []
        class Transport:
            def post(transport, base, headers, body, timeout, mark):
                mark()
                transport.sent_event.set()
                self.c.foreground_begin("gateway", "foreground-arrived-during-prefill")
                event.wait(.2)
                return {"finish_reason": terminal, "content": "final", "wall_s": .01}
        def cancel(c, p, base, headers, timeout):
            calls.append(p["rid"])
            c.cancellation(p)
            if finish_after_cancel:
                event.set()
            if not send_cancel_response:
                raise OSError("cancel response lost")
        policy = dict(POLICY, cancel_confirm_timeout_seconds=.06)
        def mark():
            self.c.dispatch(permit)
        return permit, calls, lambda: monitored_post(Transport(), self.c, permit, self.store,
                     "http://127.0.0.1:9/v1", {}, {}, 1, mark, policy, cancel=cancel)

    def test_prefill_cancel_200_but_continues_is_unknown(self):
        permit, calls, invoke = self._post(finish_after_cancel=False)
        with self.assertRaises(OutcomeUnknownError):
            invoke()
        self.c.unknown(permit, "cancel ACK only")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.c.snapshot()["inflight"]["state"], "OUTCOME_UNKNOWN")

    def test_lost_cancel_response_original_terminal_still_proves_interruption(self):
        permit, calls, invoke = self._post(send_cancel_response=False)
        with self.assertRaises(InterruptedByForeground) as caught:
            invoke()
        self.c.terminal(permit, caught.exception.reason, evidence="fixture original SSE abort")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(self.c.snapshot()["inflight"])

    def test_simultaneous_completion_wins_cancel(self):
        permit, calls, invoke = self._post(terminal="stop")
        result = invoke()
        self.assertEqual(result["content"], "final")
        self.c.terminal(permit, "complete", evidence="fixture saved response")
        self.assertEqual(len(calls), 1)

    def test_manual_stop_pause_survive_foreground_completion(self):
        token = self.c.foreground_begin("gateway", "task")
        self.store.set_control(pause=True, stop=True)
        self.c.foreground_end(token)
        self.assertEqual(self.store.control(), {"pause": True, "stop": True})

    def test_endpoint_identity_not_model_or_run(self):
        self.assertEqual(endpoint_key("http://127.0.0.1:30000/v1"), endpoint_key("http://127.0.0.1:30000/other"))

    def test_uncertified_preparation_has_no_live_path(self):
        c = Coordinator(Path(self.tmp.name) / "unverified")
        with self.assertRaises(IdleBlocked):
            c.certify(coverage={"all_clients": True}, cancellation={})
        with self.assertRaises(IdleBlocked):
            c.reserve("run", "task", "hash", "fingerprint")


if __name__ == "__main__":
    unittest.main()
