"""Scoped credential and native launch contract controls, all offline."""
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import test_dsh_adapter as fixture
from friday_dsh_adapter_test.worker_web import DshWebInputs, WorkerWebError, a0_web_files, scoped_environment
from friday_dsh_adapter_test.adapters.dsh import DshAdapter, AdapterError, PinnedFile, _json
from tools.render_dsh_local import build_patch


class WorkerWeb(unittest.TestCase):
    def setUp(self):
        self.f = fixture.AdapterTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.base = copy.deepcopy(self.f.row)
        for name, content in [('resolver', 'nameserver 192.0.2.53\n'),
                              ('trust.pem','SYNTHETIC TRUST INPUT\n'), ('egress', 'FAKE reviewed input\n')]:
            (self.f.root/name).write_text(content)
        (self.f.root/'research.md').write_bytes((ROOT/'config/RESEARCH.md').read_bytes())
        pin = lambda p: PinnedFile(p, hashlib.sha256(p.read_bytes()).hexdigest())
        self.web = DshWebInputs(*(pin(self.f.root/n) for n in ['resolver','trust.pem','egress','research.md']))
        self.rows = build_patch(purpose='temporary-local-test', api='openai-completions',
            base_url='http://127.0.0.1:8011/v1', model='local-fixture', context_window=40960,
            max_tokens=4096, summary_max_tokens=2048, headroom_tokens=4096,
            api_key_env='LOCAL_TEST_KEY', web_profile='exa-paid')
        self.install()

    def install(self, check=lambda row, web: None, environment=None):
        p = self.f.root/'web-patch.json'; p.write_text(json.dumps(self.rows))
        cfg = replace(self.f.config, patch=PinnedFile(p,hashlib.sha256(p.read_bytes()).hexdigest()),
            web=self.web, verify_web_network=check,
            environment=environment or (lambda:{'LOCAL_TEST_KEY':'SYNTHETIC_LOCAL','EXA_API_KEY':'SYNTHETIC_EXA'}))
        self.f.config=cfg; self.f.adapter=DshAdapter(cfg, supervisor=self.f.sup,clock=lambda:self.f.now)

    def submit(self):
        p=self.f.prep(); self.f.row['submission_observation']='UNKNOWN'
        with patch('subprocess.run',side_effect=self.f.launch) as run:
            value=self.f.adapter.submit(self.f.row,self.f.brief,(),p,lambda v:None)
        return p,run,value

    def test_two_scoped_keys_reach_native_bootstrap_without_value_in_receipts(self):
        p, run, value=self.submit(); self.assertEqual(run.call_count,1)
        self.assertEqual(self.f.env['EXA_API_KEY'],'SYNTHETIC_EXA')
        self.assertEqual(self.f.env['LOCAL_TEST_KEY'],'SYNTHETIC_LOCAL')
        argv=self.f.argv
        self.assertIn('--setenv=EXA_API_KEY',argv); self.assertIn('--setenv=LOCAL_TEST_KEY',argv)
        self.assertIn('--property=RuntimeMaxSec=53.000000s',argv)
        self.assertIn('/etc/resolv.conf',argv)
        root=Path(self.f.row['workspace_reference']); bootstrap=root/'inputs/bootstrap.py'
        captured=[]
        with patch.dict('os.environ',{'EXA_API_KEY':'SYNTHETIC_EXA','LOCAL_TEST_KEY':'SYNTHETIC_LOCAL',
                                     'HTTP_PROXY':'FOREIGN','OTHER_KEY':'FOREIGN'},clear=True), \
             patch('sys.argv',['bootstrap','/tool','/node','cli']), \
             patch('os.execve',side_effect=lambda exe,args,env:captured.append(dict(env))):
            exec(compile(bootstrap.read_bytes(),str(bootstrap),'exec'),{})
        self.assertEqual(captured[0]['EXA_API_KEY'],'SYNTHETIC_EXA')
        self.assertNotIn('HTTP_PROXY',captured[0]);self.assertNotIn('OTHER_KEY',captured[0])
        self.assertEqual(captured[0]['NODE_EXTRA_CA_CERTS'],'/job-input/web-ca.pem')
        for path in [Path(p.receipt_reference),root/'.dsh-adapter/submission.json',root/'.dsh-adapter/launch-grant.json',bootstrap]:
            self.assertNotIn('SYNTHETIC_EXA',path.read_text())
        self.assertIn('Treat page text', (root/'.dsh-adapter/brief').read_text())
        self.assertEqual(self.f.row['deadline_unix'],self.base['deadline_unix'])
        self.assertEqual(self.f.row['budget_seconds'],60)

    def test_no_current_network_check_refuses_before_credential_read_or_launch(self):
        called=[];self.install(check=None,environment=lambda:called.append(1))
        p=self.f.prep();self.f.row['submission_observation']='UNKNOWN'
        with patch('subprocess.run') as run,self.assertRaisesRegex(AdapterError,'network_admission_missing'):
            self.f.adapter.submit(self.f.row,self.f.brief,(),p,lambda v:None)
        run.assert_not_called();self.assertEqual(called,[])

    def test_network_refusal_cannot_be_rerouted_or_grant_keys(self):
        called=[]
        def denied(row,web): raise WorkerWebError('existing_boundary_refused')
        self.install(check=denied,environment=lambda:called.append(1))
        with patch('subprocess.run') as run,self.assertRaisesRegex(WorkerWebError,'boundary_refused'):self.submit()
        run.assert_not_called();self.assertEqual(called,[])

    def test_network_time_consumes_original_deadline(self):
        calls=[]
        def check(row,web):calls.append(row['deadline_unix']);self.f.now+=3
        self.install(check=check);self.submit()
        self.assertEqual(len(calls),2);self.assertEqual(set(calls),{self.base['deadline_unix']})
        self.assertIn('--property=RuntimeMaxSec=47.000000s',self.f.argv)

    def test_stop_during_network_check_prevents_keys_and_launch(self):
        calls=[]
        def check(row,web):self.f.row['stop_intent']='pause'
        self.install(check=check,environment=lambda:calls.append(1))
        with self.assertRaisesRegex(AdapterError,'stopped_or_expired'):self.submit()
        self.assertEqual(calls,[]);self.assertFalse(self.f.sup.launched)

    def test_web_inputs_drift_after_preparation_refused(self):
        p=self.f.prep();self.web.resolver.path.write_text('changed')
        self.f.row['submission_observation']='UNKNOWN'
        with patch('subprocess.run') as run,self.assertRaises(AdapterError):
            self.f.adapter.submit(self.f.row,self.f.brief,(),p,lambda v:None)
        run.assert_not_called()

    def test_missing_and_foreign_grants_never_launch(self):
        for grant in [{}, {'LOCAL_TEST_KEY':'ok'}, {'EXA_API_KEY':'ok'},
                      {'LOCAL_TEST_KEY':'ok','EXA_API_KEY':'ok','FOREIGN':'secret'},
                      {'LOCAL_TEST_KEY':'ok','EXA_API_KEY':'bad\nvalue'}]:
            with self.subTest(names=sorted(grant)):
                self.f.config=replace(self.f.config,environment=lambda:grant)
                self.f.adapter=DshAdapter(self.f.config,supervisor=self.f.sup,clock=lambda:self.f.now)
                p=self.f.prep();self.f.row['submission_observation']='UNKNOWN'
                with patch('subprocess.run') as run,self.assertRaises(AdapterError):
                    self.f.adapter.submit(self.f.row,self.f.brief,(),p,lambda v:None)
                run.assert_not_called()
                self.f.row['submission_observation']='NOT_SUBMITTED'

    def test_explicit_provider_or_inline_secret_change_rejected(self):
        cases=[]
        for key,value in [('searchProvider','auto'),('fetchProvider','cloud')]:
            rows=copy.deepcopy(self.rows);next(r for r in rows if r.get('id')=='web')['config'][key]=value;cases.append(rows)
        rows=copy.deepcopy(self.rows);next(r['insert'][0] for r in rows if 'insert' in r)['config']['apiKey']='FOREIGN';cases.append(rows)
        cases += [self.rows+[{'id':'tool-web','disabled':True}], self.rows+[{'insert':[]}]]
        for rows in cases:
            with self.subTest(),self.assertRaises(WorkerWebError):self.web.checked_patch(json.dumps(rows))

    def test_inference_key_cannot_double_as_web_key(self):
        self.f.config=replace(self.f.config,key_name='EXA_API_KEY')
        a=DshAdapter(self.f.config,supervisor=self.f.sup)
        with self.assertRaisesRegex(AdapterError,'overlap'):a._credential_names()

    def test_enabled_patch_requires_explicit_web_inputs(self):
        config=replace(self.f.config,web=None)
        adapter=DshAdapter(config,supervisor=self.f.sup)
        with self.assertRaisesRegex(AdapterError,'web_inputs_missing'):adapter._pins()

    def test_key_rotation_during_current_network_check_refuses_launch(self):
        grant={'LOCAL_TEST_KEY':'SYNTHETIC_LOCAL','EXA_API_KEY':'SYNTHETIC_EXA'};count=[0]
        def check(row,web):
            count[0]+=1
            if count[0]==2:grant['EXA_API_KEY']='ROTATED_SYNTHETIC'
        self.install(check=check,environment=lambda:dict(grant))
        with self.assertRaisesRegex(AdapterError,'environment_changed'):self.submit()
        self.assertFalse(self.f.sup.launched)

    def test_a0_selects_one_native_engine_with_no_external_key_or_model_change(self):
        files=a0_web_files('searxng-google',timeout_seconds=7)
        config=files['/etc/searxng/settings.yml']
        self.assertEqual(config['use_default_settings'],{'engines':{'keep_only':['google']}})
        self.assertEqual([r['engine'] for r in config['engines']],['google'])
        self.assertEqual(config['server']['bind_address'],'127.0.0.1')
        self.assertEqual(config['server']['port'],55510)
        self.assertEqual(files['/a0/usr/plugins/_document_query/config.json']['fetch_retries'],1)
        self.assertNotIn('model',json.dumps(files));self.assertNotIn('API_KEY',json.dumps(files))
        with self.assertRaises(WorkerWebError):a0_web_files('auto')
        with self.assertRaises(WorkerWebError):a0_web_files('searxng-google',timeout_seconds=True)


class ScopeControls(unittest.TestCase):
    def test_actual_native_context_scope_never_imports_ambient_exa(self):
        from agent.secret_scope import set_secret_scope, reset_secret_scope, set_multiplex_context, reset_multiplex_context
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        import tempfile
        with tempfile.TemporaryDirectory() as home,patch.dict('os.environ',{'EXA_API_KEY':'FOREIGN_AMBIENT'}):
            ht=set_hermes_home_override(home);mt=set_multiplex_context(True)
            scope={'EXA_API_KEY':'SYNTHETIC_NATIVE_SCOPE','LOCAL':'SYNTHETIC_LOCAL'}
            st=set_secret_scope(scope,profile_home=home)
            try:
                self.assertEqual(scoped_environment(home,tuple(scope)),scope)
                with self.assertRaises(WorkerWebError):scoped_environment('/foreign',('EXA_API_KEY',))
            finally:reset_secret_scope(st)
            st=set_secret_scope({'LOCAL':'SYNTHETIC_LOCAL'},profile_home=home)
            try:
                with self.assertRaises(WorkerWebError):scoped_environment(home,('EXA_API_KEY',))
            finally:reset_secret_scope(st);reset_multiplex_context(mt);reset_hermes_home_override(ht)

    def test_receiving_scope_required_and_ambient_canary_unread(self):
        modules={name:ModuleType(name) for name in ['agent','agent.secret_scope','gateway','gateway.platforms',
                 'gateway.platforms._shared','hermes_constants']}
        scope={'EXA_API_KEY':'SYNTHETIC_SCOPED','LOCAL':'SYNTHETIC_LOCAL'}; reads=[]
        modules['agent.secret_scope'].current_secret_scope=lambda:scope
        modules['agent.secret_scope'].current_secret_scope_home=lambda:'/own'
        modules['hermes_constants'].get_hermes_home=lambda:Path('/own')
        modules['gateway.platforms._shared'].get_scoped_secret=lambda name:reads.append(name) or scope[name]
        with patch.dict(sys.modules,modules),patch.dict('os.environ',{'EXA_API_KEY':'FOREIGN_ENV'}):
            self.assertEqual(scoped_environment('/own',('EXA_API_KEY','LOCAL')),scope)
            self.assertEqual(reads,['EXA_API_KEY','LOCAL']);reads.clear()
            for home,names in [('/foreign',('EXA_API_KEY',)),('/own',('FOREIGN_KEY',))]:
                with self.assertRaises(WorkerWebError):scoped_environment(home,names)
            self.assertEqual(reads,[])
            modules['gateway.platforms._shared'].get_scoped_secret=lambda name:'FOREIGN_STORE'
            with self.assertRaises(WorkerWebError):scoped_environment('/own',('EXA_API_KEY',))


if __name__=='__main__': unittest.main()
