"""A0-specific recovery controls, copied independent assertions plus regressions.

No native/model/network effect. The exact independent redaction scenario now
refuses in ready() before its former assertion; its unchanged run is retained
privately, and KeyBindingRegressions verifies that refusal and native redaction.
"""
import os, sys, json, pathlib, unittest, copy
from dataclasses import replace
from unittest.mock import patch
import test_a0_adapter as t

class BoundaryRegressions(unittest.TestCase):
 setUp=t.AdapterTests.setUp
 prepare=t.AdapterTests.prepare
 start=t.AdapterTests.start
 input=t.AdapterTests.input
 def assert_stopped(self):self.assertFalse(self.native.running,'owned native environment left running after failure')
 def test_begin_submission_persistence_failure_stops_prepared_environment(self):
  self.prepare()
  with patch.object(self.store,'begin_submission',side_effect=OSError('independent injected persistence failure')):
   with self.assertRaises(OSError):self.start()
  self.assert_stopped()
 def test_missing_preparation_journal_stops_prepared_environment(self):
  self.prepare()
  with patch.object(self.controller,'_load',side_effect=t.ControllerError('independent unreadable preparation journal')):
   with self.assertRaises(t.ControllerError):self.start()
  self.assert_stopped()
 def test_changed_input_declaration_stops_prepared_environment(self):
  self.prepare()
  with self.assertRaises(t.ControllerError):self.start((self.input(),))
  self.assert_stopped()
 def test_observation_failure_via_controller_stops_environment(self):
  self.prepare();self.adapter.inflight=True
  self.native.log_hook=lambda result:{**result,'context_id':'foreign'}
  with self.assertRaises(t.A0Error):self.controller.reconcile('task',t.OWNER)
  self.assert_stopped()
 def test_context_receipt_persistence_failure_has_no_task_replay(self):
  orig=sys.modules['friday_a0_test.adapters.a0']._write
  def injected(path,data):
   if path.name=='a0-prepared.json':raise OSError('independent receipt persistence failure')
   return orig(path,data)
  with patch('friday_a0_test.adapters.a0._write',side_effect=injected):
   with self.assertRaises(OSError):self.prepare()
  self.assert_stopped()
  with self.assertRaises(t.ControllerError):self.prepare()
  self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]),1)
 def test_partial_bootstrap_response_stops_and_no_replay(self):
  orig=self.native.request
  def partial(*args):orig(*args);return {'context_id':'actual-created-context'}
  self.native.request=partial
  with self.assertRaises(t.A0Error):self.prepare()
  self.assert_stopped()
  with self.assertRaises(t.ControllerError):self.prepare()
  self.assertEqual(len(self.native.calls),1)
 def test_response_persistence_failure_after_task_never_replays(self):
  self.prepare();orig=sys.modules['friday_a0_test.adapters.a0']._write
  def injected(path,data):
   if path.name=='worker-response.json':raise OSError('independent response persistence failure')
   return orig(path,data)
  with patch('friday_a0_test.adapters.a0._write',side_effect=injected):
   with self.assertRaises(OSError):self.start()
  self.assert_stopped();self.assertEqual(self.start().state,'unknown')
  self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]),2)
 def test_stale_file_identity_different_from_api_rejected(self):
  p=self.native.local(self.outputs[0].worker_path);p.parent.mkdir(parents=True);p.write_bytes(b'first')
  self.native.file_hook=lambda result:{k:t.base64.b64encode(b'other').decode() for k in result}
  with self.assertRaises(t.A0Error):self.adapter._verified_files(self.row,(self.outputs[0].worker_path,))
 def test_uploaded_file_removed_before_dependent_task_is_rejected(self):
  v=self.input();self.prepare((v,));self.native.local(v.worker_path).unlink()
  with self.assertRaises((t.A0Error,OSError)):self.start((v,))
  self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]),1)
 def test_result_manifest_cannot_drop_expected_artifacts(self):
  prepared=self.prepare();self.start();p=self.job/'a0-result.json'
  result=json.loads(p.read_text());result['artifacts']=[];p.write_text(json.dumps(result))
  with self.assertRaises((t.A0Error,ValueError)):self.adapter.artifacts(self.store.get('task',t.OWNER),prepared)

class NativeRegressions(unittest.TestCase):
 setUp=t.NativeConfigTests.setUp
 def test_nonnumeric_positive_cpu_period_not_accepted(self):
  self.fields['RuntimeMaxUSec']='20s garbage'
  with self.assertRaises(t.A0Error):self.boundary.admit(self.row)
 def test_wrong_supervisor_invocation_is_not_admitted(self):
  self.supervisor.observe=lambda row:t.UnitObservation(t.UNIT,'f'*32,'active','running','success',123,'/mock',True)
  with self.assertRaises(t.A0Error):self.boundary.admit(self.row)
 def test_native_grant_cannot_be_rebound_to_foreign_context(self):
  row={**self.row,'native':{'invocation_id':t.INV,'worker_reference':'a0:'+'c'*64+':ctx'}}
  with self.assertRaises(t.A0Error):self.boundary.inspect(row)
 def test_exec_cleanup_extra_command_refused(self):
  self.fields['ExecStopPost']+=' { path=/bin/true ; argv[]=/bin/true ; ignore_errors=no ; }'
  with self.assertRaises(t.A0Error):self.boundary.admit(self.row)
 def test_foreign_native_network_after_start_keeps_stop_uncertainty(self):
  self.obj['HostConfig']['NetworkMode']='host'
  with self.assertRaises(t.A0Error):self.boundary.stop(self.row)
  self.assertEqual(self.native_stops,1)

class AdditionalEvidence(unittest.TestCase):
 setUp=t.AdapterTests.setUp
 prepare=t.AdapterTests.prepare
 start=t.AdapterTests.start
 input=t.AdapterTests.input
 def test_real_handler_silently_skipped_upload_stops_before_task(self):
  v=self.input();method=self.native.handlers['/api/api_message'].process
  with patch.dict(method.__func__.__globals__,{'safe_filename':lambda name:''}):
   with self.assertRaises((t.A0Error,OSError)):self.prepare((v,))
  self.assertFalse(self.native.running)
  self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]),1)
 def test_aggregate_outputs_overflow_refused(self):
  self.adapter.config=replace(self.config,max_file_bytes=4,max_response_bytes=32)
  second=replace(self.outputs[0],worker_path=self.outputs[0].worker_path.replace('-output.txt','-second.txt'))
  self.outputs=(self.outputs[0],second)
  for v in self.outputs:
   p=self.native.local(v.worker_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'abc')
  with self.assertRaisesRegex(t.A0Error,'outputs_too_large'):self.adapter._verified_files(self.row,tuple(v.worker_path for v in self.outputs))
 def test_post_unknown_retained_as_observed_without_reexecution(self):
  self.prepare();orig=self.native.request
  def injected(*args):
   result=orig(*args)
   if args[2].endswith('api_message'):return {'context_id':'foreign','response':'partial'}
   return result
  self.native.request=injected
  with self.assertRaisesRegex(t.A0Error,'task_outcome_unknown'):self.start()
  before=len(self.native.calls);self.assertEqual(self.start().state,'unknown');self.assertEqual(len(self.native.calls),before)
 def test_native_file_replacement_same_bytes_rejected(self):
  p=self.native.local(self.outputs[0].worker_path);p.parent.mkdir(parents=True);p.write_bytes(b'original')
  def change(result):
   q=p.with_suffix('.new');q.write_bytes(p.read_bytes());q.replace(p);return result
  self.native.file_hook=change
  with self.assertRaisesRegex(t.A0Error,'mutable_or_mismatched'):self.adapter._verified_files(self.row,(self.outputs[0].worker_path,))
 def test_worker_input_replacement_does_not_allow_task(self):
  v=self.input();self.prepare((v,));self.native.local(v.worker_path).write_bytes(b'bad input')
  try:self.start((v,))
  except (t.A0Error,OSError):pass
  self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]),1,'effectful task submitted with changed worker input')
 def test_manifest_empty_cannot_reconcile_completed(self):
  self.prepare();self.start();p=self.job/'a0-result.json';v=json.loads(p.read_text());v['artifacts']=[];p.write_text(json.dumps(v))
  try:value=self.start()
  except Exception:return
  self.assertNotEqual(value.state,'completed','empty retained manifest still reconciled as completed')
 def test_manifest_duplicates_are_not_complete(self):
  prepared=self.prepare();self.start();p=self.job/'a0-result.json';v=json.loads(p.read_text());v['artifacts']*=2;p.write_text(json.dumps(v))
  try:result=self.adapter.artifacts(self.store.get('task',t.OWNER),prepared)
  except Exception:return
  self.assertEqual(len(result),1,'duplicate retained artifact accepted')
 def test_key_ready_rejects_duplicate_overriding_key(self):
  with self.env.open('a') as f:f.write('API_KEY_OPENAI=independent-synthetic-other-key\n')
  with self.assertRaises(t.A0Error):self.keys.ready()


class RecoveryRegressions(unittest.TestCase):
    setUp = t.AdapterTests.setUp
    prepare = t.AdapterTests.prepare
    start = t.AdapterTests.start
    input = t.AdapterTests.input

    def test_committed_unknown_with_failed_ack_stops_without_replay(self):
        self.prepare(); original = self.store.begin_submission
        def failed_ack(*args):
            original(*args)
            raise OSError('synthetic lost UNKNOWN acknowledgement')
        with patch.object(self.store, 'begin_submission', side_effect=failed_ack):
            with self.assertRaises(OSError): self.start()
        row = self.store.get('task', t.OWNER)
        self.assertEqual(row['submission_observation'], 'UNKNOWN')
        self.assertFalse(self.native.running)
        self.assertEqual(self.start().state, 'unknown')
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 1)
        self.assertEqual((row['budget_seconds'], row['deadline_unix']), (60, 1060))

    def test_brief_change_after_bootstrap_stops(self):
        self.prepare()
        with self.assertRaises(t.ControllerError):
            self.controller.start('task', t.OWNER, replace(t.BRIEF, brief='changed'), ())
        self.assertFalse(self.native.running)
        self.assertEqual(len(self.native.calls), 1)

    def test_first_state_read_failure_after_prepare_uses_last_checked_row(self):
        self.prepare()
        with patch.object(self.store, 'get', side_effect=OSError('synthetic unreadable association')):
            with self.assertRaises(OSError): self.start()
        self.assertFalse(self.native.running)
        self.assertEqual(len(self.native.calls), 1)

    def test_first_reconcile_read_failure_also_stops(self):
        self.prepare()
        with patch.object(self.store, 'get', side_effect=OSError('synthetic unreadable association')):
            with self.assertRaises(OSError): self.controller.reconcile('task', t.OWNER)
        self.assertFalse(self.native.running)

    def test_foreign_principal_does_not_use_cached_owned_stop(self):
        self.prepare()
        with self.assertRaises(Exception):
            self.controller.start('task', {**t.OWNER, 'user_id':'foreign'}, t.BRIEF, ())
        self.assertTrue(self.native.running)
        self.assertEqual(self.native.stops, 0)

    def test_missing_receipt_direct_submit_stops(self):
        prepared = self.prepare(); self.store.begin_submission('task', t.OWNER)
        (self.job / 'a0-prepared.json').unlink()
        with self.assertRaises(Exception):
            self.adapter.submit(self.store.get('task', t.OWNER), t.BRIEF, (), prepared, lambda v:None)
        self.assertFalse(self.native.running)
        self.assertEqual(len(self.native.calls), 1)

    def test_input_changed_by_native_observation_callback_refuses_task(self):
        value = self.input(); self.prepare((value,)); original = self.controller._record
        def changed(row, observed):
            result = original(row, observed)
            self.native.local(value.worker_path).write_bytes(b'replaced after callback')
            return result
        with patch.object(self.controller, '_record', side_effect=changed):
            with self.assertRaises(t.A0Error): self.start((value,))
        self.assertFalse(self.native.running)
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 1)

    def test_handoff_symlink_and_transfer_mutation_refuse_without_second_post(self):
        for mode in ('symlink', 'mutation'):
            with self.subTest(mode=mode):
                self.setUp(); value = self.input(); self.prepare((value,))
                path = self.native.local(value.worker_path)
                if mode == 'symlink':
                    path.unlink(); path.symlink_to(pathlib.Path(value.host_path))
                else:
                    def changed(result): path.write_bytes(b'transfer mutation'); return result
                    self.native.file_hook = changed
                with self.assertRaises((t.A0Error, OSError)): self.start((value,))
                self.assertFalse(self.native.running)
                self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 1)

    def test_worker_bytes_are_checked_twice_before_dependent_post(self):
        value = self.input(); self.prepare((value,)); self.start((value,))
        reads = [c for c in self.native.calls if c[1].endswith('api_files_get')]
        self.assertEqual(len(reads), 3)  # prepare, handoff, returned output
        self.assertEqual(reads[0][2], reads[1][2])
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 2)

    def test_reload_controller_retains_original_unknown_and_no_replay(self):
        value = self.input(); self.prepare((value,)); self.native.local(value.worker_path).unlink()
        with self.assertRaises(OSError): self.start((value,))
        reloaded = t.A0Controller(self.store, {'a0':self.binding})
        self.assertEqual(reloaded.start('task', t.OWNER, t.BRIEF, (value,)).state, 'unknown')
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 1)
        self.assertEqual(self.store.get('task', t.OWNER)['deadline_unix'], 1060)

    def test_failed_stop_keeps_uncertainty_and_original_failure(self):
        self.prepare()
        with patch.object(self.native, 'stop', side_effect=t.A0Error('STOP_UNCONFIRMED')):
            with patch.object(self.controller, '_load', side_effect=OSError('synthetic journal failure')):
                with self.assertRaises(OSError) as caught: self.start()
        self.assertTrue(self.native.running)
        self.assertTrue(any('STOP_UNCONFIRMED' in v for v in caught.exception.__notes__))

    def test_manifest_schema_origin_completeness_and_foreign_labels(self):
        prepared = self.prepare(); self.start(); path = self.job / 'a0-result.json'
        original = json.loads(path.read_text())
        changes = [lambda v:v.update(identity={}), lambda v:v.update(outputs=[]),
                   lambda v:v.update(extra=True), lambda v:v.update(context_id='foreign'),
                   lambda v:v['artifacts'][0].update(complete=False),
                   lambda v:v['artifacts'][0].update(complete=1),
                   lambda v:v['artifacts'][0].update(verification='unverified'),
                   lambda v:v['artifacts'][0].update(logical_name='foreign'),
                   lambda v:v['artifacts'][0].update(media_type='foreign'),
                   lambda v:v['artifacts'][0].update(origin_reference='/foreign/job/response.json'),
                   lambda v:v['artifacts'][0].update(size_bytes=True),
                   lambda v:v['artifacts'][0].update(extra=True),
                   lambda v:v.update(artifacts={})]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                value = copy.deepcopy(original); change(value); path.write_text(json.dumps(value))
                with self.assertRaises((t.A0Error, ValueError)):
                    self.adapter.artifacts(self.store.get('task', t.OWNER), prepared)
                with self.assertRaises(Exception): self.start()
        path.write_text(json.dumps(original))
        self.assertEqual(self.start().state, 'completed')
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 2)

    def test_multiple_expected_outputs_are_complete_unique_and_ordered(self):
        second = replace(self.outputs[0], worker_path=self.outputs[0].worker_path.replace('-output.txt','-second.txt'),
                         logical_name='second.txt')
        self.outputs = (self.outputs[0], second)
        prepared = self.prepare(); self.start(); row = self.store.get('task', t.OWNER)
        self.assertEqual(len(self.adapter.artifacts(row, prepared)), 2)
        path = self.job / 'a0-result.json'; original = json.loads(path.read_text())
        for replacement in (original['artifacts'][:1], original['artifacts'][::-1],
                            [original['artifacts'][0], original['artifacts'][0]]):
            with self.subTest(count=len(replacement)):
                value = copy.deepcopy(original); value['artifacts'] = replacement; path.write_text(json.dumps(value))
                with self.assertRaises(t.A0Error): self.adapter.artifacts(row, prepared)
        path.write_text(json.dumps(original)); self.assertEqual(self.start().state, 'completed')

    def test_duplicate_expected_logical_labels_are_refused(self):
        self.outputs = (self.outputs[0], replace(self.outputs[0],
            worker_path=self.outputs[0].worker_path.replace('-output.txt','-second.txt')))
        with self.assertRaises(t.A0Error): self.prepare()
        self.assertFalse(self.native.running)
        self.assertEqual(self.native.calls, [])


class KeyBindingRegressions(unittest.TestCase):
    setUp = t.AdapterTests.setUp
    prepare = t.AdapterTests.prepare
    start = t.AdapterTests.start
    input = t.AdapterTests.input

    def script(self, body=None, mutate_runtime=None, mutate_response=None):
        helpers = t.types.ModuleType('helpers'); helpers.__path__ = []
        files = t.types.ModuleType('helpers.files'); files.get_abs_path = lambda _:str(self.env)
        module = t.types.ModuleType('helpers.dotenv'); module.__package__ = 'helpers'
        source = (pathlib.Path(os.environ['FRW_A0_DONOR'])/'helpers/dotenv.py').read_text()
        with patch.dict(sys.modules, {'helpers':helpers,'helpers.files':files,'helpers.dotenv':module}):
            exec(compile(source, 'actual-donor/helpers/dotenv.py', 'exec'), module.__dict__)
        helpers.dotenv = module
        helpers.runtime = t.NS(initialize=mutate_runtime or (lambda:None))
        helpers.settings = t.NS(get_settings=lambda:{'mcp_server_token':'synthetic-native-token'})
        calls = []
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                if mutate_response: mutate_response()
                return body or json.dumps({'response':list(self.keys.admitted().values())}).encode()
        response = Response()
        response.keys = self.keys
        class Opener:
            def open(self, request, timeout): calls.append(request); return response
        payload = {'method':'POST','path':'/api/api_message','payload':{'message':'fixture'},
                   'admitted_keys':self.keys.admitted(),'timeout':1,'max_bytes':4096}
        output = t.io.StringIO(); error = None
        with patch.dict(sys.modules, {'helpers':helpers}), patch.dict(os.environ), \
             patch('sys.stdin', t.io.StringIO(json.dumps(payload))), \
             patch('urllib.request.build_opener', return_value=Opener()), t.contextlib.redirect_stdout(output):
            try: exec(compile(t.API_SCRIPT, 'actual-native-api-script', 'exec'), {})
            except SystemExit as caught: error = caught
        return output.getvalue(), calls, error

    def test_original_duplicate_redaction_trigger_now_refuses_before_effect(self):
        original = self.keys.admitted()['API_KEY_OPENAI']
        with self.env.open('a') as f:f.write('API_KEY_OPENAI=independent-synthetic-other-key\n')
        with self.assertRaises(t.A0Error): self.keys.ready()
        before = self.env.read_bytes()
        output, calls, error = self.script(json.dumps({'response':original}).encode())
        self.assertIsNotNone(error); self.assertEqual(calls, [])
        self.assertEqual(output.strip(), '{"ok":false}')
        self.assertNotIn(original, output)
        with self.assertRaises(t.A0Error): self.keys.remove(cessation_confirmed=True)
        self.assertEqual(self.env.read_bytes(), before)

    def test_actual_donor_parser_positive_redacts_original_keys(self):
        output, calls, error = self.script()
        self.assertIsNone(error); self.assertEqual(len(calls), 1)
        raw = t.decode_file(t.strict_json(output)['body'], 4096)
        self.assertEqual(json.loads(raw)['response'], ['[redacted]','[redacted]'])
        self.assertTrue(all(v.encode() not in raw for v in self.keys.admitted().values()))

    def test_json_escaped_secret_is_redacted_after_decoding(self):
        secret = self.keys.admitted()['API_KEY_OPENAI']
        body = ('{"response":"'+''.join('\\u%04x'%ord(c) for c in secret)+'"}').encode()
        output, calls, error = self.script(body)
        self.assertIsNone(error); self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(t.decode_file(t.strict_json(output)['body'], 4096))['response'], '[redacted]')

    def test_runtime_mutation_refuses_before_mocked_http(self):
        def mutate():
            with self.env.open('a') as f:f.write("export 'API_KEY_OPENAI' = 'synthetic-override'\n")
        output, calls, error = self.script(mutate_runtime=mutate)
        self.assertIsNotNone(error); self.assertEqual(calls, [])
        self.assertEqual(output.strip(), '{"ok":false}')

    def test_key_change_after_mocked_response_refuses_all_stdout_bytes(self):
        secret = self.keys.admitted()['API_KEY_OPENAI']
        def mutate():
            self.env.write_text(self.env.read_text().replace(secret, 'synthetic-changed'))
        output, calls, error = self.script(json.dumps({'response':secret}).encode(), mutate_response=mutate)
        self.assertIsNotNone(error); self.assertEqual(len(calls), 1)
        self.assertEqual(output.strip(), '{"ok":false}')
        self.assertNotIn(secret, output)

    def test_real_dotenv_syntax_variants_refuse_ready_and_preserve_cleanup(self):
        original = self.env.read_bytes(); secret = self.keys.admitted()['API_KEY_OPENAI']
        variants = [f"'API_KEY_OPENAI'='{secret}'\n", f'export API_KEY_OPENAI="{secret}"\n',
                    f"export 'API_KEY_OPENAI' = '{secret}' # duplicate\n", 'API_KEY_OPENAI\n',
                    'API_KEY_OTHER=synthetic-other\n', 'API_KEY_OPENAI="unterminated\n']
        for variant in variants:
            with self.subTest(variant=variant.split('=')[0]):
                altered = original + variant.encode(); self.env.write_bytes(altered)
                with self.assertRaises(t.A0Error): self.keys.ready()
                with self.assertRaises(t.A0Error): self.keys.remove(cessation_confirmed=True)
                self.assertEqual(self.env.read_bytes(), altered)
        self.env.write_bytes(original); self.keys.ready()

    def test_existing_quoted_export_or_valueless_keys_are_not_owned(self):
        for value in ("'API_KEY_OPENAI'=synthetic\n", "export 'API_KEY_OTHER'=synthetic\n", 'API_KEY_OPENAI\n'):
            with self.subTest(value=value.split('=')[0]):
                self.env.write_text('AUTH_LOGIN=retained\n'+value); before = self.env.read_bytes()
                with self.assertRaises(t.A0Error): t.prepare_keys(self.usr, lambda _:self.fail('resolver must not run'))
                self.assertEqual(self.env.read_bytes(), before)

    def test_changed_binding_prevents_native_file_reads_and_dependent_task(self):
        value = self.input(); self.prepare((value,))
        with self.env.open('a') as f:f.write('API_KEY_OPENAI=synthetic-override\n')
        with patch.object(self.native, 'file', side_effect=AssertionError('no native file reads allowed')):
            with self.assertRaises(t.A0Error): self.start((value,))
        self.assertFalse(self.native.running)
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith('api_message')]), 1)
        self.assertIn('synthetic-override', self.env.read_text())

    def test_partial_removal_is_unknown_cleanup_and_preserves_foreign_fields(self):
        before = self.env.read_bytes().replace(self.keys.introduced[0], b'') + b'A0_GENERATED_STATE=keep\n'
        self.env.write_bytes(before)
        with self.assertRaises(t.A0Error): self.keys.remove(cessation_confirmed=True)
        self.assertEqual(self.env.read_bytes(), before)
        self.env.write_bytes(b'AUTH_LOGIN=fixture\nA0_GENERATED_STATE=keep\n')
        self.keys.remove(cessation_confirmed=True)
        self.assertEqual(self.env.read_bytes(), b'AUTH_LOGIN=fixture\nA0_GENERATED_STATE=keep\n')

    def test_oversized_and_hardlinked_key_files_are_refused(self):
        original = self.env.read_bytes(); self.env.write_bytes(original+b'#'+b'x'*1048576)
        with self.assertRaises(t.A0Error): self.keys.ready()
        self.env.write_bytes(original); link = self.usr/'linked'; os.link(self.env, link)
        with self.assertRaises(Exception): self.keys.ready()
        link.unlink(); self.keys.ready()


class NativeKeyBoundaryRegressions(unittest.TestCase):
    setUp = t.NativeConfigTests.setUp

    def test_duplicate_key_prevents_api_and_native_file_execution(self):
        with self.keys.path.open('a') as f:f.write("export 'API_KEY_OTHER'=synthetic-override\n")
        with self.assertRaises(t.A0Error):
            self.boundary.request(self.row, 'POST', '/api/api_message', {'message':'fixture'}, 10, 4096)
        with self.assertRaises(t.A0Error):
            self.boundary.file(self.row, '/a0/usr/uploads/task-input.txt', 4096, 10)
        self.assertEqual(self.commands, [])

    def test_missing_or_foreign_material_refuses_before_docker_inspection(self):
        for material in (None, replace(self.keys, prepared_monotonic=98)):
            with self.subTest(material_present=material is not None):
                self.boundary.key_material = material
                with self.assertRaises(t.A0Error):
                    self.boundary.request(self.row, 'POST', '/api/api_message', {'message':'fixture'}, 10, 4096)
        self.assertEqual(self.commands, [])

    def test_original_keys_only_in_private_helper_stdin(self):
        self.boundary.request(self.row, 'POST', '/api/api_message', {'message':'fixture'}, 10, 4096)
        argv, data, timeout = self.commands[-1]; payload = json.loads(data)
        self.assertEqual(payload['admitted_keys'], self.keys.admitted())
        self.assertEqual(payload['payload'], {'message':'fixture'})
        self.assertTrue(all(secret not in str(argv) for secret in self.keys.admitted().values()))
