"""Finite offline tests of explicit null cap and retained independent gates."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import test_unfinished_budget as budget_tests
import test_idle_runner as runner_tests
from qpb.cli import _status
from qpb.fingerprints import sha256_obj
from qpb.idle import POLICY
from qpb.report import build_report, render_markdown
from qpb.runner import IdleRunner, _attempt_budget, unfinished_attempt_cap

class NoGlobalCapTests(unittest.TestCase):
    setUp=budget_tests.UnfinishedBudgetTests.setUp
    record=budget_tests.UnfinishedBudgetTests.record
    saved=budget_tests.UnfinishedBudgetTests.saved
    runner=budget_tests.UnfinishedBudgetTests.runner

    def test_explicit_null_finite_zero_and_default_validation(self):
        self.assertEqual(unfinished_attempt_cap(POLICY),7200)
        self.assertIsNone(unfinished_attempt_cap(dict(POLICY,max_interrupted_attempt_wall_seconds=None)))
        for value in (0,1,21600,.1):
            self.assertEqual(unfinished_attempt_cap(dict(POLICY,max_interrupted_attempt_wall_seconds=value)),value)
        for value in (True,False,'none','unlimited',-1,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                unfinished_attempt_cap({'max_interrupted_attempt_wall_seconds':value})
        with self.assertRaises(ValueError): unfinished_attempt_cap({})

    def test_null_does_not_pause_for_known_cost_but_unknown_still_blocks(self):
        self.record(wall=999999)
        self.record(2,outcome='OUTCOME_UNKNOWN',wall=None)
        before=_attempt_budget(self.store)[1]
        r=self.runner(None)
        self.assertEqual(r._loop(),2)
        self.assertEqual(self.store.manifest()['state'],'RECOVERY_REQUIRED')
        self.assertEqual(_attempt_budget(self.store)[1],before)
        self.assertFalse(before['unfinished_attempt_wall_complete'])
        self.assertEqual(before['unmeasured_unfinished_attempts'],1)

    def test_null_retains_three_interruption_deferral(self):
        for n in range(1,4):self.record(n,outcome='INTERRUPTED_BY_FOREGROUND',wall=10000)
        r=self.runner(None)
        with redirect_stdout(StringIO()):self.assertEqual(r._loop(),0)
        self.assertEqual(self.store.manifest()['state'],'NEEDS_QUIET_WINDOW')
        self.assertEqual(self.store.manifest()['deferred_ids'],['gpqa:t'])
        self.assertEqual(_attempt_budget(self.store)[1]['unfinished_attempt_wall_s'],30000)

    def test_null_retains_pause_stop_and_authorization(self):
        for control,state in [({'pause':True,'stop':False},'MANUAL_PAUSED'),({'pause':False,'stop':True},'STOPPED')]:
            r=self.runner(None);self.store.set_control(**control)
            with redirect_stdout(StringIO()):self.assertEqual(r._loop(),0)
            self.assertEqual(self.store.manifest()['state'],state)
        self.store.set_control(pause=False,stop=False)
        r=self.runner(None);m=self.store.manifest();m['authorization_expires_epoch']=0;self.store.write_manifest(m)
        with redirect_stdout(StringIO()):self.assertEqual(r._loop(),0)
        self.assertEqual(self.store.manifest()['state'],'AUTHORIZATION_EXPIRED')

    def test_zero_finite_cap_remains_enabled(self):
        r=self.runner(0)
        with redirect_stdout(StringIO()):self.assertEqual(r._loop(),0)
        self.assertEqual(self.store.manifest()['state'],'PAUSED_POLICY')

    def test_fresh_status_json_and_markdown_explicit_disabled_unknown_retained(self):
        self.record(wall=123)
        self.record(2,outcome='OUTCOME_UNKNOWN',wall=None)
        self.store.write_manifest(dict(mode='idle',coordinator_dir=str(self.root/'admission'),
            idle_policy=dict(POLICY,max_interrupted_attempt_wall_seconds=None),
            authorization_expires_epoch=10**12,datasets={b:{'ids':[]} for b in ('ifbench','gpqa','lcb')}))
        with redirect_stdout(StringIO()) as output:self.assertEqual(_status(self.root,self.root,'fixture'),0)
        status=json.loads(output.getvalue().splitlines()[-1]);report=build_report(self.store)
        for value in (status,report['unfinished_attempt_budget']):
            self.assertIsNone(value['max_interrupted_attempt_wall_seconds'])
            self.assertFalse(value['unfinished_attempt_cap_enabled'])
            self.assertEqual(value['unfinished_attempt_wall_s'],123)
            self.assertEqual(value['unmeasured_unfinished_attempts'],1)
            self.assertFalse(value['unfinished_attempt_wall_complete'])
        self.assertIn('отключён (null)',render_markdown(report))
        json.dumps(report,allow_nan=False)

    def test_paused_policy_same_run_resume_and_original_expiry(self):
        policy=dict(POLICY,max_interrupted_attempt_wall_seconds=None)
        r=object.__new__(IdleRunner);r.policy=policy;r.command='resume';r.pilot_only=False
        m=dict(mode='idle',idle_policy=policy,idle_policy_fingerprint=sha256_obj(policy),
               state='PAUSED_POLICY',authorization_expires_epoch=10**12,pilot_only=False)
        self.assertEqual(r._continue_decision(m),{'pilot_only':False})
        self.assertEqual(m['authorization_expires_epoch'],10**12)
        self.assertIn('error',r._continue_decision(dict(m,authorization_expires_epoch=0)))
        self.assertIn('error',r._continue_decision(dict(m,idle_policy_fingerprint=sha256_obj(POLICY))))

class NoCapExecutingConsumerTests(unittest.TestCase):
    def setUp(self):
        # All identities are invented locally; no deployment config/manifests.
        from qpb.endpoint import alias
        from qpb.paths import tool_root
        from qpb.profile import load_profile
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-public-null-cap-")
        self.addCleanup(self.tmp.cleanup)
        self.root = tool_root()
        self.endpoint = dict(base_url="http://127.0.0.1:9/v1", model="fixture-model",
                             kind="fixture", api_key_env="QPB_FIXTURE_KEY")
        self.profile = load_profile(self.root / "config/public-core-v1.yaml")
        self.identity = dict(endpoint_alias=alias(self.endpoint), datasets={
            b: dict(revision="fixture", sha256="0" * 64,
                    order_sha256=sha256_obj(ids), count=len(ids), ids=ids)
            for b, ids in runner_tests.TinyCorpus.order.items()})
        env = patch.dict(os.environ, {"QPB_FIXTURE_KEY": "fixture-only"})
        env.start(); self.addCleanup(env.stop)
        corpus = patch("qpb.runner.get_corpus", return_value=runner_tests.TinyCorpus())
        corpus.start(); self.addCleanup(corpus.stop)
    def runner(self,handler,run="fixture",command="run",policy=None):
        return runner_tests.IdleRunnerTests.runner(self,handler,run,command,
            dict(policy or {},max_interrupted_attempt_wall_seconds=None))
    def test_null_actual_foreground_cancellation_and_three_interruptions_defer(self):
        runner_tests.IdleRunnerTests.test_three_interruptions_defer_every_id_with_full_denominator(self)
    def test_null_stop_pause_after_reservation_prevent_post(self):
        runner_tests.IdleRunnerTests.test_stop_and_pause_after_reservation_prevent_post(self)
    def test_actual_finite_fixture_loop_all_tasks_null_cap(self):
        seen=[]
        def handler(body):
            seen.append(body['rid'])
            return {'finish_reason':'stop','content':'fixture','wall_s':.01,'truncated':False}
        r=self.runner(handler,policy={'max_interrupted_attempt_wall_seconds':None})
        before_generation=r.fingerprint
        with redirect_stdout(StringIO()):self.assertEqual(r.execute(),0)
        self.assertEqual(r.store.manifest()['state'],'COMPLETE')
        self.assertEqual(len(seen),3)
        self.assertEqual(len(set(seen)),3)
        self.assertIsNone(r.store.manifest()['idle_policy']['max_interrupted_attempt_wall_seconds'])
        self.assertEqual(r.store.manifest()['generation_fingerprint'],before_generation)
        self.assertIsNone(r.coordinator.snapshot()['inflight'])

if __name__=='__main__':unittest.main()
