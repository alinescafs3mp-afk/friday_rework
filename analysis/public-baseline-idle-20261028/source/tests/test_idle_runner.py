"""Exercise the real runner/store with three explicitly fixture tasks."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from qpb.endpoint import load_endpoint
from qpb.paths import tool_root
from qpb.prepare import identity_for
from qpb.profile import load_profile
from qpb.runner import IdleRunner
from qpb.idle import POLICY
from qpb.errors import OutcomeUnknownError


class TinyCorpus:
    order = {"ifbench": ["1"], "gpqa": ["2"], "lcb": ["3"]}
    pilot = order
    tasks = {b: {ids[0]: {"messages": [{"role": "user", "content": "FIXTURE"}]}} for b, ids in order.items()}


class IdleRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-runner-idle-")
        self.addCleanup(self.tmp.cleanup)
        self.root = tool_root()
        self.endpoint = dict(load_endpoint(self.root / "config/endpoint.json"),
                             base_url="http://127.0.0.1:9/v1", kind="fixture", api_key_env="QPB_FIXTURE_KEY")
        self.profile = load_profile(self.root / "config/public-core-v1.yaml")
        self.identity = identity_for(self.root, self.endpoint)
        self.env = patch.dict(os.environ, {"QPB_FIXTURE_KEY": "fixture-only"})
        self.env.start(); self.addCleanup(self.env.stop)
        self.corpus = patch("qpb.runner.get_corpus", return_value=TinyCorpus())
        self.corpus.start(); self.addCleanup(self.corpus.stop)

    def runner(self, handler, run="fixture", command="run", policy=None):
        class Transport:
            def post(transport, base, headers, body, timeout, mark):
                mark()
                transport.sent_event.set()
                return handler(body)
        runner = IdleRunner(self.root, Path(self.tmp.name), run, self.profile, self.endpoint, self.identity,
                     allow_live=True, pilot_only=False, window_hours=None,
                     transport_factory=Transport, command=command,
                     policy=dict(POLICY, idle_grace_seconds=0, **(policy or {})))
        if runner.coordinator.snapshot()["blocks"]:
            runner.coordinator.certify(coverage={"all_clients": True, "whole_tasks": True, "embeddings": True},
                         cancellation={"installed_source": "FIXTURE", "rid_before_prefill": True,
                                       "terminal_evidence": "FIXTURE", "live_handoff": "FIXTURE"})
        return runner

    def test_complete_saved_then_resume_only_next_id_and_same_expiry(self):
        seen = []
        runner = None
        def handler(body):
            seen.append(body["rid"])
            runner.store.set_control(pause=True, stop=False)
            return {"finish_reason": "length", "content": "fixture", "wall_s": .01, "truncated": True}
        runner = self.runner(handler)
        self.assertEqual(runner.execute(), 0)
        expiry = runner.store.manifest()["authorization_expires_epoch"]
        self.assertTrue(runner.store.prediction_complete("ifbench", "1"))
        self.assertEqual(runner.store.manifest()["state"], "MANUAL_PAUSED")
        runner = self.runner(handler, command="resume")
        self.assertEqual(runner.execute(), 0)
        self.assertTrue(runner.store.prediction_complete("gpqa", "2"))
        self.assertEqual(runner.store.manifest()["authorization_expires_epoch"], expiry)
        self.assertEqual(len(set(seen)), 2)
        self.assertEqual(len(list(runner.store.predictions.glob("*.json"))), 2)

    def test_unknown_prevents_same_and_different_run(self):
        seen = []
        def handler(body):
            seen.append(body["rid"])
            raise OutcomeUnknownError("fixture socket lost")
        runner = self.runner(handler)
        self.assertEqual(runner.execute(), 2)
        other = self.runner(handler, run="other")
        self.assertEqual(other.execute(), 2)
        resumed = self.runner(handler, command="resume")
        self.assertEqual(resumed.execute(), 2)
        self.assertEqual(len(seen), 1)

    def test_stop_and_pause_after_reservation_prevent_post(self):
        for stopping in (False, True):
            with self.subTest(stop=stopping):
                seen = []
                runner = self.runner(lambda body: seen.append(body), run="control-" + str(stopping))
                original = runner.coordinator.reserve
                def reserve(*args, **kwargs):
                    permit = original(*args, **kwargs)
                    runner.store.set_control(pause=not stopping, stop=stopping)
                    return permit
                with patch.object(runner.coordinator, "reserve", side_effect=reserve):
                    self.assertEqual(runner.execute(), 0)
                self.assertEqual(seen, [])
                self.assertIsNone(runner.coordinator.snapshot()["inflight"])
                self.assertEqual(runner.store.manifest()["state"], "STOPPED" if stopping else "MANUAL_PAUSED")

    def test_three_interruptions_defer_every_id_with_full_denominator(self):
        import time
        from qpb.idle_transport import monitored_post
        seen = []
        pending = []
        runner = None
        def handler(body):
            seen.append(body["rid"])
            token = runner.coordinator.foreground_begin("fixture-Friday", "task")
            pending.append(token)
            while pending:
                time.sleep(.001)
            return {"finish_reason": "abort", "wall_s": .001, "content": "partial"}
        def cancel(c, permit, base, headers, timeout):
            c.cancellation(permit)
            c.foreground_end(pending.pop())
        def post(*args, **kwargs):
            return monitored_post(*args, **kwargs, cancel=cancel)
        runner = self.runner(handler)
        with patch("qpb.idle_transport.monitored_post", side_effect=post):
            self.assertEqual(runner.execute(), 0)
        self.assertEqual(runner.store.manifest()["state"], "NEEDS_QUIET_WINDOW")
        self.assertEqual(len(seen), 9)
        self.assertEqual(len(set(seen)), 9)
        self.assertEqual(runner.store.progress()["expected"], 673)
        self.assertEqual(len(runner.store.manifest()["deferred_ids"]), 3)
        self.assertEqual(list(runner.store.predictions.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
