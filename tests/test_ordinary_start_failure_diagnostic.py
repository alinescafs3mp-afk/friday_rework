"""Owned isolated fixtures only; no native subprocess, service or credential access."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import friday_start as start, friday_native as native, friday_install as entry
from scripts import install_containment as containment
from scripts.dsh_prepare import CommandFailed, StopUnconfirmed

SECRET = 'PRIVATE_TOKEN_DO_NOT_ECHO'

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home/'hermes-agent'
        self.launcher = self.source/'.hermes/bin/hermes'
        self.launcher.parent.mkdir(parents=True)
        import shlex
        self.launcher.write_text('#!/bin/sh\nexec '+shlex.join([sys.executable,'-I','-c','SAFE'])+' "$@"\n')
        self.launcher.chmod(0o700)
        self.unit = self.home/'hermes.service';self.unit.touch()
        self.value = {'home':str(self.home),'containment':{},'bootstrap_python':{'path':sys.executable},'seconds':30}
        self.calls=[];self.preflights=0;self.snapshots=0;self.fault=None
        modules={}
        def module(name,**values):
            m=types.ModuleType(name);m.__dict__.update(values);modules[name]=m;return m
        gateway=module('gateway');gateway.__path__=[]
        gateway.host_rendezvous=module('gateway.host_rendezvous')
        hermes=module('hermes_cli');hermes.__path__=[]
        self.gw=module('hermes_cli.gateway',get_systemd_linger_status=lambda:(True,None),
             _read_systemd_unit_properties=lambda **kw:{'ActiveState':'inactive','MainPID':'0'},
             find_gateway_pids=lambda:[],get_service_name=lambda:'hermes')
        module('hermes_cli.friday_ordinary_gateway',check=lambda home:None)
        module('hermes_cli.friday_credential_admission',bootstrap=lambda home:None,
             scoped=lambda home:contextlib.nullcontext(),route_inputs=lambda:None,
             channel_inputs=lambda:({},None))
        module('hermes_cli._launchers',_launcher_script=lambda *a:'SAFE',resolve_store_python=lambda *a,**kw:Path(sys.executable))
        module('hermes_constants',get_hermes_home=lambda:self.home)
        pm=module('pm');pm.__path__=[]
        module('pm.paths',repo_root=lambda:self.source)
        module('pm.environments',project_python=lambda source:Path(sys.executable))
        self.enterContext(patch.dict(sys.modules,modules))
        self.enterContext(patch.object(start,'snapshot',lambda *a:{}))
        def unchanged(*a):
            self.snapshots+=1
            if self.fault=='input_snapshot' and self.snapshots==2:raise entry.Refused('native_start_input_changed')
        self.enterContext(patch.object(start,'unchanged',unchanged))
        def preflight(*a):
            self.preflights+=1
            if self.preflights==3:
                if self.fault=='gateway_preflight':raise entry.Refused('foreign_or_changed_gateway_unit')
                if self.fault=='gateway_owner':return self.unit,object()
            return self.unit,None
        self.enterContext(patch.object(start,'gateway_preflight',preflight))
        def observe(*a):
            self.calls.append('observe')
            if self.fault=='gateway_observation':raise entry.Refused('native_gateway_start_not_observed')
        self.enterContext(patch.object(start,'gateway_observation',observe))
        owner=self
        class Custody:
            def __init__(self,*a):pass
            def probe(self,*a):owner.calls.append('probe')
            def run(self,argv,cwd,**kw):
                stage='gateway_install' if 'install' in argv else 'native_unit_start'
                owner.calls.append(stage)
                if owner.fault==stage:raise owner.failure
                return '',{'returncode':0,'timeout':False,'reaped':True}
        self.enterContext(patch.object(containment,'Containment',Custody))
        self.enterContext(patch.object(entry,'clean_environment',lambda home:{}))
        class Bus:
            def lstat(self):return types.SimpleNamespace(st_mode=stat.S_IFSOCK,st_uid=os.getuid(),st_nlink=1)
            def __str__(self):return '/synthetic/bus'
        class Runtime:
            def __truediv__(self,key):return Bus()
            def __str__(self):return '/synthetic/runtime'
        def directory(*a):
            if self.fault=='user_bus':raise OSError(13,SECRET)
            return Runtime()
        self.enterContext(patch.object(entry,'directory',directory))
        self.failure=CommandFailed({'returncode':7,'timeout':False,'reaped':True,'reason':'command_nonzero_exit',
            'stdout':SECRET,'stderr':SECRET,'argv':[SECRET],'env':{'token':SECRET}})

    def run_start(self):return start.ordinary_start(self.value,containment.Budget(30))

    def test_source_defined_stages_and_original_custody(self):
        for stage in ('gateway_install','input_snapshot','gateway_preflight','gateway_owner','user_bus','native_unit_identity','native_unit_start','gateway_observation'):
            with self.subTest(stage=stage):
                self.calls=[];self.preflights=0;self.snapshots=0;self.fault=stage
                if stage=='gateway_install':self.unit.unlink()
                elif not self.unit.exists():self.unit.touch()
                self.gw.get_service_name=lambda:'foreign' if self.fault=='native_unit_identity' else 'hermes'
                with self.assertRaises(StopUnconfirmed) as result:self.run_start()
                exc=result.exception
                self.assertIs(exc.friday_custody_primary,exc.__cause__)
                self.assertEqual(exc.friday_custody_state,'UNCONFIRMED')
                self.assertEqual(exc.friday_diagnostic['phase'],'ordinary_'+stage)
                self.assertNotIn(SECRET,json.dumps(exc.friday_diagnostic))
                self.assertLessEqual(self.calls.count('native_unit_start'),1)
                self.assertLessEqual(self.calls.count('gateway_install'),1)

    def test_command_observation_retained_without_raw_values(self):
        self.fault='native_unit_start'
        with self.assertRaises(StopUnconfirmed) as result:self.run_start()
        exc=result.exception
        self.assertIs(exc.friday_custody_primary,self.failure)
        self.assertEqual(exc.friday_diagnostic['returncode'],7)
        self.assertIs(exc.friday_diagnostic['timeout'],False)
        self.assertIs(exc.friday_diagnostic['reaped'],True)
        self.assertEqual(self.calls,['probe','native_unit_start'])
        self.assertNotIn(SECRET,json.dumps(exc.friday_diagnostic))

    def test_nested_uncertainty_keeps_observation_and_primary(self):
        self.fault='native_unit_start'
        inner=StopUnconfirmed(SECRET)
        inner.friday_custody_primary=self.failure
        inner.observation={'returncode':3,'timeout':False,'reaped':True,'argv':[SECRET]}
        self.failure=inner
        with self.assertRaises(StopUnconfirmed) as caught:self.run_start()
        exc=caught.exception
        self.assertIs(exc.friday_custody_primary,inner)
        self.assertEqual(exc.friday_diagnostic['reason'],'stop_unconfirmed')
        self.assertEqual(exc.friday_diagnostic['cessation'],'UNCONFIRMED')
        self.assertEqual(exc.friday_diagnostic['returncode'],3)
        self.assertEqual(self.calls,['probe','native_unit_start'])
        result,text=self.cli(exc)
        self.assertEqual(result.code,3)
        self.assertNotIn(SECRET,text)

    def test_timeout_is_reported_without_retry_or_new_budget(self):
        self.fault='native_unit_start'
        self.failure=CommandFailed({'returncode':-9,'timeout':True,'reaped':True,'reason':'command_timeout'})
        budget=containment.Budget(30)
        deadline=budget.deadline
        with self.assertRaises(StopUnconfirmed) as caught:start.ordinary_start(self.value,budget)
        self.assertEqual(budget.deadline,deadline)
        self.assertEqual(self.calls,['probe','native_unit_start'])
        self.assertTrue(caught.exception.friday_diagnostic['timeout'])

    def test_success_has_one_handoff_and_existing_result(self):
        result=self.run_start()
        self.assertEqual(result['state'],'ORDINARY_NATIVE_GATEWAY_OBSERVED')
        self.assertIs(result['ready'],False)
        self.assertIs(result['workers_enabled'],False)
        self.assertEqual(self.calls,['probe','native_unit_start','observe'])

    def cli(self,exc,output_failure=False,expected=entry.InstallerExit):
        stderr=io.StringIO();input_path=self.home/'input.json';input_path.write_text('{}');input_path.chmod(0o600)
        with patch.object(sys,'argv',['friday_native.py','start-telegram','--input',str(input_path),'--deadline',str(time.monotonic()+20)]), \
             patch.object(sys,'path',list(sys.path)), \
             patch.object(entry,'read_json',side_effect=lambda path:self.value if path==input_path else {}), \
             patch.object(entry,'spec_checked',return_value=(self.home,{'hermes':{}})), \
             patch.object(entry,'inspect'),patch.object(entry,'composition_checked'),patch.object(entry,'native_packages'), \
             patch.object(start,'ordinary_start',side_effect=exc),contextlib.redirect_stderr(stderr):
            if output_failure:
                with patch.object(native.SafeParser,'exit',side_effect=OSError(5,SECRET)):
                    with self.assertRaises(expected) as result:native.main()
            else:
                with self.assertRaises(expected) as result:native.main()
        return result.exception,stderr.getvalue()

    def test_cli_exact_firstline_exit3_no_retry_and_cause(self):
        self.fault='native_unit_start'
        with self.assertRaises(StopUnconfirmed) as caught:self.run_start()
        exc=caught.exception
        result,text=self.cli(exc)
        self.assertEqual(result.code,3)
        self.assertIs(result.friday_custody_primary,exc)
        self.assertIs(result.__cause__,exc)
        lines=text.splitlines()
        self.assertEqual(lines[0],'STOP_UNCONFIRMED: native ordinary gateway ownership requires reconciliation; do not retry')
        self.assertIn('phase=ordinary_native_unit_start reason=command_nonzero_exit child_exit=7 timeout=false reaped=true',lines[1])
        self.assertNotIn(SECRET,text)
        self.assertEqual(self.calls,['probe','native_unit_start'])

    def test_cli_formatting_failure_still_prints_firstline(self):
        exc=StopUnconfirmed(SECRET)
        with patch.object(entry,'diagnostic_text',side_effect=RuntimeError(SECRET)):
            result,text=self.cli(exc)
        self.assertEqual(result.code,3)
        self.assertIs(result.friday_custody_primary,exc)
        self.assertTrue(text.startswith('STOP_UNCONFIRMED: native ordinary gateway ownership requires reconciliation; do not retry\n'))
        self.assertIn('phase=ordinary_handoff reason=diagnostic_unavailable',text)
        self.assertNotIn(SECRET,text)

    def test_existing_cli_refusal_message_and_exit2(self):
        result,text=self.cli(ValueError(SECRET),expected=SystemExit)
        self.assertEqual(result.code,2)
        self.assertEqual(text,'Friday native ordinary start refused: installed admission is incomplete\n')
        self.assertEqual(self.calls,[])

    def test_admission_refusal_prevents_handoff(self):
        import hermes_cli.friday_ordinary_gateway as admission
        with patch.object(admission,'check',side_effect=entry.Refused('native_start_generation_mismatch')):
            with self.assertRaises(entry.Refused):self.run_start()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.preflights,0)

    def test_interrupt_after_effect_keeps_uncertainty(self):
        self.fault='native_unit_start';self.failure=KeyboardInterrupt(SECRET)
        with self.assertRaises(StopUnconfirmed) as caught:self.run_start()
        self.assertIs(caught.exception.__cause__,self.failure)
        self.assertIs(caught.exception.friday_custody_primary,self.failure)
        result,text=self.cli(caught.exception)
        self.assertEqual(result.code,3)
        self.assertEqual(self.calls,['probe','native_unit_start'])
        self.assertNotIn(SECRET,text)

    def test_cli_output_failure_cannot_replace_original(self):
        exc=StopUnconfirmed(SECRET)
        exc.friday_diagnostic={'phase':'ordinary_gateway_observation','reason':'native_gateway_start_not_observed'}
        result,text=self.cli(exc,output_failure=True)
        self.assertEqual(result.code,3)
        self.assertIs(result.friday_custody_primary,exc)
        self.assertIsInstance(result.friday_custody_secondary[0],OSError)
        self.assertNotIn(SECRET,text)

    def test_diagnostic_failure_cannot_replace_handoff(self):
        self.fault='native_unit_start'
        with patch.object(entry,'safe_diagnostic',side_effect=RuntimeError(SECRET)):
            with self.assertRaises(StopUnconfirmed) as caught:self.run_start()
        exc=caught.exception
        self.assertIs(exc.__cause__,self.failure)
        self.assertIs(exc.friday_custody_primary,self.failure)
        self.assertIsInstance(exc.friday_secondary_failures[0],RuntimeError)
        result,text=self.cli(exc)
        self.assertEqual(result.code,3)
        self.assertNotIn(SECRET,text)

if __name__=='__main__':unittest.main(verbosity=2)
