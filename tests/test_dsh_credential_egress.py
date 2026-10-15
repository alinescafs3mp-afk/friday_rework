"""Synthetic exact-key egress backstop; no worker/API/network/service effects.

Encoded/split/derived keys intentionally remain outside this guard's claim.
"""
from dataclasses import replace
import asyncio
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import test_dsh_adapter as fixture

pkg='friday_dsh_adapter_test'
dsh=importlib.import_module(pkg+'.adapters.dsh')
art=importlib.import_module(pkg+'.artifacts')
results=importlib.import_module(pkg+'.results')
web=importlib.import_module(pkg+'.worker_web')
KEYS={'LOCAL_TEST_KEY':'sk-SYNTHETIC-INFERENCE-ef739bd5', 'EXA_API_KEY':'exa-SYNTHETIC-PAID-7b250cf1'}


class CredentialEgressTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.AdapterTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.config=replace(self.f.config,environment=lambda:{'LOCAL_TEST_KEY':KEYS['LOCAL_TEST_KEY']})
        self.f.adapter=dsh.DshAdapter(self.f.config,supervisor=self.f.sup,clock=lambda:self.f.now)
        self.prepared=self.f.prep();self.control=Path(self.prepared.receipt_reference).parent
        self.source=Path(self.f.row['workspace_reference'])/'workspace'
        self.staged=self.f.root/'staged';self.staged.mkdir(mode=0o700)
        self.secrets=tuple(v.encode() for v in KEYS.values())

    def stage(self,path,**changes):
        args=dict(source_root=self.source,relative_path=path,staging_root=self.staged,
                  logical_name=Path(path).name,media_type='application/octet-stream',
                  origin_reference='fixture-job',max_bytes=200000,reject_bytes=self.secrets)
        args.update(changes);return art.stage_file(**args)

    def receipt(self, grant=KEYS):
        dsh._write(self.control/'credential-guard.json',dict(schema=1,identity=dsh._identity(self.f.row),
                   keys=dsh.credential_fingerprints(grant)))

    def test_binary_chunk_boundary_and_each_key_rejected_before_first_copy(self):
        for key in self.secrets:
            for offset in (0,65536-len(key)//2,131070):
                data=b'\x00\xff'+b'x'*offset+key+b'\x00tail'
                (self.source/'answer.bin').write_bytes(data)
                with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file') as caught:
                    self.stage('answer.bin')
                self.assertNotIn(key.decode(),str(caught.exception));self.assertEqual(list(self.staged.iterdir()),[])
                self.assertEqual((self.source/'answer.bin').read_bytes(),data)

    def test_empty_clean_and_multiple_file_failure_keep_only_clean_bytes(self):
        for name,data in [('empty.txt',b''),('clean.bin',b'\x00\xffclean'),('bad.txt',self.secrets[1])]:
            (self.source/name).write_bytes(data)
        clean=[self.stage('empty.txt'),self.stage('clean.bin')]
        with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):self.stage('bad.txt')
        for item in clean:
            payload=art.read_staged(staging_root=self.staged,artifact=item,max_bytes=200000,reject_bytes=self.secrets)
            self.assertNotIn(self.secrets[0],payload);self.assertNotIn(self.secrets[1],payload)
        self.assertEqual(len(list(self.staged.iterdir())),2)

    def test_legacy_retained_raw_payload_and_filename_refuse_preview_or_delivery_read(self):
        (self.source/'legacy.txt').write_bytes(self.secrets[0])
        old=self.stage('legacy.txt',reject_bytes=())
        with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):
            art.read_staged(staging_root=self.staged,artifact=old,max_bytes=200000,reject_bytes=self.secrets)
        (self.source/'safe.txt').write_bytes(b'clean')
        with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):
            self.stage('safe.txt',logical_name=KEYS['EXA_API_KEY']+'.txt')

    def test_original_admission_fingerprints_refuse_rotation_missing_or_foreign_evidence(self):
        self.receipt()
        self.assertEqual(dsh.checked_output_credentials(self.f.row,KEYS),self.secrets)
        for grant in ({}, {'LOCAL_TEST_KEY':'rotated','EXA_API_KEY':KEYS['EXA_API_KEY']}):
            with self.assertRaisesRegex(dsh.AdapterError,'unconfirmed'):dsh.checked_output_credentials(self.f.row,grant)
        foreign=copy.deepcopy(self.f.row);foreign['admission_hash']='f'*64
        with self.assertRaisesRegex(dsh.AdapterError,'unconfirmed'):dsh.checked_output_credentials(foreign,KEYS)
        self.assertNotIn(KEYS['LOCAL_TEST_KEY'],(self.control/'credential-guard.json').read_text())

    def test_launch_receipt_redacts_and_native_stdout_stderr_fail_without_secret_errors(self):
        self.f.row['submission_observation']='UNKNOWN'
        def launch(argv,**kw):
            self.f.launch(argv,**kw)
            return subprocess.CompletedProcess(argv,0,self.secrets[0],('invocation ID: '+fixture.INV+'\n'+KEYS['LOCAL_TEST_KEY']).encode())
        with patch('subprocess.run',side_effect=launch):
            self.f.adapter.submit(self.f.row,self.f.brief,(),self.prepared,lambda _:None)
        self.assertNotIn(self.secrets[0],(self.control/'launch.json').read_bytes())
        for filename in ('events.ndjson','stderr'):
            (self.control/filename).write_bytes(self.secrets[0])
            with self.assertRaisesRegex(dsh.AdapterError,'runtime_secret_in_native_output') as caught:
                self.f.adapter.observe(self.f.row,self.prepared)
            self.assertTrue(caught.exception.stop_confirmed)
            self.assertNotIn(KEYS['LOCAL_TEST_KEY'],str(caught.exception))
            (self.control/filename).write_bytes(b'')
        self.f.row['stop_intent']='cancel'
        (self.control/'stderr').write_bytes(self.secrets[0])
        self.assertEqual(self.f.adapter.stop(self.f.row,self.prepared,'cancel').state,'stopped')

    def test_native_both_keys_and_unknown_stop_preserve_failure(self):
        self.receipt()
        self.f.adapter.config=replace(self.f.config,environment=lambda:KEYS)
        self.f.sup.launched=True;self.f.sup.running=True
        for key in self.secrets:
            (self.control/'stderr').write_bytes(key)
            with patch.object(self.f.sup,'stop',side_effect=RuntimeError('synthetic stop unknown')):
                with self.assertRaisesRegex(dsh.AdapterError,'runtime_secret_in_native_output') as caught:
                    self.f.adapter.observe(self.f.row,self.prepared)
            self.assertFalse(caught.exception.stop_confirmed)
            self.assertNotIn(key.decode(),str(caught.exception))
            self.assertTrue(self.f.sup.running)
        self.f.row['stop_intent']='cancel'
        self.assertEqual(self.f.adapter.stop(self.f.row,self.prepared,'cancel').state,'stopped')

    def test_result_collect_inspect_and_presend_use_original_scoped_both_keys(self):
        self.receipt();row=copy.deepcopy(self.f.row)
        row['host']={'binding':{'runtime':{'runtime_home':str(self.f.root/'scope'), 'dsh':{'key_name':'LOCAL_TEST_KEY','web':{'profile':'exa-paid'}},'max_file_bytes':200000,'max_total_bytes':400000,'staging_root':str(self.staged)}},'quiescence':{}}
        class Store:
            def get(self,*_):return copy.deepcopy(row)
        store=Store()
        results.output_root(row).parent.mkdir(mode=0o700)
        with patch.object(web,'scoped_environment',return_value=KEYS),patch.object(results,'require_result_quiescence'):
            self.assertEqual(results._dsh_result_secrets(row),self.secrets)
            (self.source/'bad.txt').write_bytes(self.secrets[1])
            for terminal in (None, {'state':'completed'}, {'state':'failed'}, {'state':'stopped'}):
                row['host']['terminal']=terminal
                with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):
                    results.collect_outputs(store,row,['bad.txt'])
            self.assertNotIn('result',row)
            (self.source/'old.txt').write_bytes(self.secrets[0])
            destination=results.output_root(row);destination.mkdir(mode=0o700,parents=True,exist_ok=True)
            old=art.stage_file(source_root=self.source,relative_path='old.txt',staging_root=destination,logical_name='old.txt',media_type='text/plain',origin_reference=row['existing_task_id'],max_bytes=200000)
            from dataclasses import asdict
            row['result']={'artifacts':[asdict(old)]}
            with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):results.inspect_outputs(row)
            # Call the actual nonlocal delivery path: rejection must precede
            # UNKNOWN reservation, payload send, and receipt processing.
            from types import SimpleNamespace
            from hermes_cli import friday_user_scope, friday_cli_caller
            with patch.object(friday_user_scope,'check_retained_job'), patch.object(friday_cli_caller,'current',return_value=None), patch.object(results,'begin_delivery') as reserve:
                with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):
                    asyncio.run(results.deliver_artifact(SimpleNamespace(),store,row,old.reference))
                reserve.assert_not_called()
        with patch.object(web,'scoped_environment',side_effect=RuntimeError('synthetic missing scope')):
            with self.assertRaisesRegex(results.AssociationError,'unconfirmed'):results._dsh_result_secrets(row)

    def test_cli_presend_guard_precedes_durable_unknown_and_any_native_output(self):
        self.f.row['owner']['platform']='cli'
        self.receipt();row=copy.deepcopy(self.f.row)
        row['host']={'binding':{'runtime':{'runtime_home':str(self.f.root/'scope'),'dsh':{'key_name':'LOCAL_TEST_KEY','web':{'profile':'exa-paid'}},'max_file_bytes':200000,'max_total_bytes':400000,'staging_root':str(self.staged)}}}
        destination=results.output_root(row);destination.mkdir(mode=0o700,parents=True)
        destination.parent.chmod(0o700)
        (self.source/'old.txt').write_bytes(self.secrets[1])
        item=art.stage_file(source_root=self.source,relative_path='old.txt',staging_root=destination,logical_name='old.txt',media_type='text/plain',origin_reference=row['existing_task_id'],max_bytes=200000)
        from dataclasses import asdict
        row['result']={'artifacts':[asdict(item)]}
        class Store:
            def get(self,*_):return copy.deepcopy(row)
            def clock(self):return self_now
        self_now=self.f.now
        class Span:
            def check(self,*_,**__):pass
            def sync(self,_,fn,*args,**kwargs):return fn(*args,**kwargs)
        from hermes_cli import friday_user_scope,friday_cli_caller
        from types import SimpleNamespace
        with patch.object(web,'scoped_environment',return_value=KEYS),patch.object(friday_user_scope,'check_retained_job'),patch.object(friday_cli_caller,'current',return_value=Span()),patch.object(results,'begin_delivery') as reserve:
            with self.assertRaisesRegex(art.ArtifactError,'runtime_secret_in_file'):
                asyncio.run(results.deliver_artifact(SimpleNamespace(),Store(),row,item.reference))
            reserve.assert_not_called()

    def test_encoded_secret_demonstrates_explicit_confidentiality_limit(self):
        import base64
        encoded=base64.b64encode(self.secrets[0])
        (self.source/'encoded.txt').write_bytes(encoded)
        self.assertEqual(self.stage('encoded.txt').size_bytes,len(encoded))
