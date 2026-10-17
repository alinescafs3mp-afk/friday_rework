"""Real source imports, native dispatch, synthetic provider subprocesses; no network/model."""
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

BASE = Path(os.environ['FRIDAY_NATIVE_SOURCE']).resolve(strict=True)
OVERLAY = BASE
ROOT_TMP = tempfile.TemporaryDirectory(prefix='friday-source90-')
os.environ['HERMES_HOME'] = ROOT_TMP.name
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.path.insert(0,str(BASE))
for package in ('agent','tools','hermes_cli'):
    mod = importlib.import_module(package)
    mod.__path__.insert(0,str(OVERLAY/package))
from agent import web_call_context as wc
from hermes_cli import friday_user_scope as us, friday_product_access as pa
from tools import web_process as wp
import model_tools as mt
from tools.registry import registry
from tools.process_registry import process_registry

PROVIDER_CODE = "import json,sys; p=json.loads(sys.stdin.read()); print(json.dumps({'value':sys.argv[1],'search_memo':[]}))"
OBS = []

class FixtureProcess:
    """Synthetic provider seam; real finite Python children and wait/pipe cleanup."""
    def __init__(self):
        self.body = {'success':False,'error':'synthetic provider unavailable'}
        self.sessions = []
        self.spawns = []
        self.stops = []
    def spawn(self,call):
        call.uses_web = True
        call.check()
        p=subprocess.Popen([sys.executable,'-I','-B','-c',PROVIDER_CODE,json.dumps(self.body)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        s=NS(id=f'fixture-{len(self.sessions)}',process=p,web_deadline=call.deadline(),raw=None)
        self.sessions.append(s);self.spawns.append((call.task_id,call.session_id,call.call_id))
        call.session=s;call.registry=self
        return s
    def exchange(self,s,payload,call):
        call.check()
        out,err=s.process.communicate(json.dumps(payload).encode(),timeout=3)
        if s.process.returncode:raise RuntimeError('fixture child failed')
        s.raw=out.decode();return s.raw
    def settle_web(self,s,stop=False):
        if stop:self.stops.append(s.id)
        if s.process.poll() is None:
            s.process.terminate();s.process.communicate(timeout=3)
        return {'status':'QUIESCENT','native_child_exit_zero':s.process.returncode==0,'session_id':s.id}
    def close(self):
        for s in self.sessions:
            if s.process.poll() is None:s.process.kill()
            if s.process.stdin and not s.process.stdin.closed:s.process.stdin.close()
            if s.process.stdout and not s.process.stdout.closed:s.process.stdout.close()
            if s.process.stderr and not s.process.stderr.closed:s.process.stderr.close()
            s.process.wait(timeout=3)
        assert all(s.process.returncode is not None for s in self.sessions)

class NativeControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='case-',dir=ROOT_TMP.name)
        self.root=Path(self.tmp.name);self.fx=FixtureProcess();self.stack=contextlib.ExitStack()
        self.caps=[]
        for label in ('a','b'):
            home=self.root/label;home.mkdir(mode=0o700)
            for n in ('workspace','memories'):(home/n).mkdir(mode=0o700)
            (home/'config.yaml').write_text(json.dumps({'tools':{'tool_search':{'defer':['web_search','web_extract']}}}));(home/'config.yaml').chmod(0o600)
            principal=('telegram','fixture-transport','fixture-bot',label)
            binding=dict(zip(('platform','transport_profile','account_id','user_id'),principal))|{'runtime_profile':label,'tools':['web_search','web_extract','read_file','write_file','delegate_task','friday_work','friday_result','memory']}
            st=home.stat();cap=us.UserScope(self.root,home,label,principal,binding,(st.st_dev,st.st_ino),admission_generation=1)
            marker={'schema':'friday.user-home.v1','principal':cap.key,'profile':label,'binding_sha256':us._fingerprint(binding)}
            (home/us.MARKER).write_text(json.dumps(marker));(home/us.MARKER).chmod(0o600)
            (home/'workspace'/'safe.txt').write_text('safe unrelated source');(home/'workspace'/'safe.txt').chmod(0o600)
            self.caps.append(cap)
        settings={'user_isolation':{'enabled':True,'bindings':[c.binding for c in self.caps]},'product_access':{'enabled':True,'accounts':[{'platform':'telegram','transport_profile':'fixture-transport','account_id':'fixture-bot','runtime_profiles':['a','b']}]}}
        access={'schema':'product_access.v1','users':{c.key:{'platform':c.principal[0],'transport_profile':c.principal[1],'account_id':c.principal[2],'user_id':c.principal[3],'enabled':True,'role':'user','generation':1} for c in self.caps}}
        self.stack.enter_context(patch.object(pa,'settings',lambda:settings))
        self.stack.enter_context(patch.object(pa,'current_access',lambda:access))
        self.stack.enter_context(patch.object(wp,'_scope_payload',lambda home:{}))
        for name,fn in [('spawn_web',self.fx.spawn),('web_exchange',self.fx.exchange),('settle_web',self.fx.settle_web)]:self.stack.enter_context(patch.object(process_registry,name,fn))
        # Catalog construction is a pure declared capability seam: no provider probes.
        defs=[{'type':'function','function':registry.get_entry(n).schema} for n in ('web_search','web_extract')]
        self.stack.enter_context(patch.object(mt,'get_tool_definitions',lambda *a,**k:defs))
        self.stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('network prohibited')))
        self.stack.enter_context(patch.object(socket,'create_connection',side_effect=AssertionError('network prohibited')))
    def tearDown(self):
        self.stack.close();self.fx.close();self.tmp.cleanup()
    @contextlib.contextmanager
    def active(self,cap=None):
        cap=cap or self.caps[0];token=us._CURRENT.set(cap)
        try:
            with us.authority(cap.home):yield cap
        finally:us._CURRENT.reset(token)
    def call(self,turn=None,session='s-a',task='task-a',name='call'):
        call=wc.WebCall(turn or wc.WebTurn(),time.monotonic()+30,task,session,name)
        call.user_authority=us.delegation_authority()
        return call
    def dispatch(self,call,name,args,path='direct'):
        with wc.bind_web_call(call):
            if path=='registry':return registry.dispatch(name,args,task_id=call.task_id,session_id=call.session_id)
            if path=='lazy':name,args='tool_call',{'calls':[{'name':name,'arguments':args}]}
            return mt.handle_function_call(name,args,call.task_id,tool_call_id=call.call_id,session_id=call.session_id,turn_id='fixture-turn',skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
    def fail_search(self,turn=None,path='direct'):
        call=self.call(turn)
        out=json.loads(self.dispatch(call,'web_search',{'query':'fixture unavailable'},path))
        self.assertIn('success',out,out);self.assertIs(out['success'],False);self.assertIs(out['retry_allowed'],False);self.assertEqual(out['cleanup'],'confirmed')
        self.assertEqual(len(self.fx.spawns),1)
        return call.turn,out
    def test_direct_lazy_registry_same_turn_stop_no_three_url_extract(self):
        for path in ('direct','lazy','registry'):
            with self.subTest(path=path),self.active():
                self.fx.spawns.clear();self.fx.body={'success':False,'error':'outage'}
                turn,out=self.fail_search(path=path)
                result=self.dispatch(self.call(turn,name='later-extract'),'web_extract',{'urls':['https://fixture.test/1','https://fixture.test/2','https://fixture.test/3']},path)
                self.assertIn('error',json.loads(result));self.assertEqual(len(self.fx.spawns),1)
                OBS.append({'control':'same-turn-extract-no-spawn','path':path,'spawns':1,'cleanup':out['cleanup']})
    def test_transport_family_guard_and_scope_capability_restrictions(self):
        with self.active():
            turn,_=self.fail_search()
            with wc.bind_web_call(self.call(turn)):
                for name in us.BROWSER_TOOLS|{'web_search','web_extract','friday_work'}:
                    with self.subTest(name=name),self.assertRaises(us.ScopeDenied):us.guard_tool(name,{})
                for name in ('terminal','execute_code','connectors__x__fetch'):
                    with self.subTest(name=name),self.assertRaises(us.ScopeDenied):us.guard_tool(name,{})
                for name in ('memory','read_file','delegate_task','friday_result'):us.guard_tool(name,{})
    def test_cancellation_stays_sticky_and_delegated_turn_is_shared(self):
        with self.active():
            turn=wc.WebTurn();agent=NS(_friday_delegation={'web_turn':turn},session_id='child',_current_turn_id='child-turn')
            child=wc.make_web_call(agent,time.monotonic()+30,'child-task','child-call')
            self.assertIs(child.turn,turn)
            parent=self.call(turn)
            with wc.bind_web_call(parent):wp._failure('web_provider_failed',call=parent,cleanup='confirmed')
            with wc.bind_web_call(child):
                us.guard_tool('read_file',{})
                with self.assertRaises(us.ScopeDenied):us.guard_tool('web_extract',{})
            child.check() # A safe child is still usable.
            with wc.bind_web_call(child),self.assertRaises(RuntimeError):wc.current_web_call()
            fresh=wc.WebTurn();cancelled=self.call(fresh);fresh.stop()
            with self.assertRaises(RuntimeError):cancelled.check()

    def test_native_concurrent_batch_dispatch_direct_and_lazy(self):
        from agent import tool_executor as te
        for lazy in (False,True):
            with self.subTest(lazy=lazy),self.active() as cap:
                self.fx.spawns.clear();self.fx.body={'success':False,'error':'batch outage'}
                agent=NS(_friday_user_scope=cap,_friday_delegation=None,session_id='batch-session',_current_turn_id='batch-turn',_interrupt_requested=False,_tool_worker_threads_lock=threading.Lock(),_tool_worker_threads=set(),_touch_activity=lambda *a:None,log_prefix='fixture',enabled_toolsets=None,disabled_toolsets=None)
                event=threading.Event()
                def invoke(name,args,task,call_id,**kw):
                    return mt.handle_function_call(name,args,task,tool_call_id=call_id,session_id=agent.session_id,skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
                agent._invoke_tool=invoke
                def managed(agent,*,function_name,function_args,execute,begin_execution=None,**kw):
                    if begin_execution:begin_execution()
                    if function_name in ('web_extract','read_file'):
                        self.assertTrue(event.wait(3),'search did not finish')
                    result=execute(function_args)
                    if function_name=='web_search':event.set()
                    return te._ManagedToolResult(result,function_args,[],False,True)
                requests=[('web_search',{'query':'batch fixture'}),('web_extract',{'urls':['https://fixture.test/1','https://fixture.test/2','https://fixture.test/3']}),('read_file',{'path':'safe.txt'})]
                calls=[]
                for i,(name,args) in enumerate(requests):
                    if lazy and name.startswith('web_'):name,args='tool_call',{'calls':[{'name':name,'arguments':args}]}
                    calls.append(NS(id='batch-'+str(i),function=NS(name=name,arguments=json.dumps(args))))
                parsed=[te._parse_tool_call(agent,c) for c in calls]
                self.assertTrue(all(p.parse_error is None for p in parsed),parsed)
                batch=te._ConcurrentBatch(agent,[],'batch-task',parsed,10)
                with patch.object(te,'_run_agent_tool_execution_middleware',managed),patch.object(te,'_ra',lambda:NS(_set_interrupt=lambda *a,**k:None)):
                    batch.run()
                self.assertEqual(len(self.fx.spawns),1)
                self.assertIs(json.loads(batch.results[0].result)['retry_allowed'],False)
                self.assertIn('error',json.loads(batch.results[1].result))
                self.assertIn('safe unrelated source',json.loads(batch.results[2].result)['content'])
                self.assertFalse(agent._tool_worker_threads)
                OBS.append({'control':'actual-native-concurrent-batch','lazy':lazy,'web_spawns':1,'safe_read':True,'threads_reaped':True,'seam':'presentation/middleware execution wrapper only; native planner/context/threadpool/dispatch real'})

    def test_actual_delegation_record_and_native_turn_reset_preserve_web_lifecycle(self):
        from agent import turn_context as tc
        from hermes_cli import friday_credential_admission as credential
        def agent(cap,**kw):
            return NS(_friday_user_scope=cap,_friday_delegation=None,_tool_guardrails=NS(reset_for_turn=lambda:None),_memory_store=NS(),api_mode='anthropic_messages',_compression_warning=False,max_iterations=10,run_budget_seconds=None,session_id='parent-session',_user_id=cap.principal[3],_session_db=NS(db_path=cap.home/'state.db'),valid_tool_names={'read_file','web_search','web_extract','delegate_task'},iteration_budget=object(),_web_run_deadline=time.monotonic()+30,_run_budget_started_at=time.time(),**kw)
        with self.active() as cap:
            parent=agent(cap);tc._reset_per_turn_agent_state(parent);original=parent._web_turn
            retained_safe=wc.make_web_call(parent,time.monotonic()+30,'parent-task','safe-parent')
            with patch.object(credential,'route_inputs',lambda *a:object()),patch.object(credential,'runtime_checked',lambda *a:None):
                with us.child_construction(parent,{}) as identity:
                    delegated=us._DELEGATION.get();self.assertIs(delegated['web_turn'],original)
                    child=agent(cap);child._friday_delegation=delegated
                    tc._reset_per_turn_agent_state(child)
            self.assertIs(child._web_turn,original)
            child_call=wc.make_web_call(child,time.monotonic()+30,'child-task','web-child')
            child_call.uses_web=True
            child_call.registry=self.fx;child_call.session=NS(id='child-active',process=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(10)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}));self.fx.sessions.append(child_call.session)
            with wc.bind_web_call(retained_safe):out=json.loads(wp._failure('web_provider_failed',call=retained_safe,cleanup='confirmed'))
            self.assertEqual(out['cleanup'],'confirmed');self.assertIsNotNone(child_call.session.process.poll());self.assertFalse(retained_safe.stopped.is_set())
            tc._reset_per_turn_agent_state(child)
            self.assertIs(child._web_turn,original);self.assertIsNotNone(child._web_turn.failure);self.assertFalse(original.stopped.is_set())
            tc._reset_per_turn_agent_state(parent)
            self.assertIsNot(parent._web_turn,original);self.assertIsNone(parent._web_turn.failure)
            self.assertIs(child._friday_delegation['web_turn'],original)
            with us.delegated_agent(child):
                us.guard_tool('read_file',{})
                with self.assertRaises(us.ScopeDenied):us.guard_tool('web_search',{})
            OBS.append({'control':'native-delegation-record-reset-shared-original-turn','child_inflight_web_settled':True,'safe_parent_preserved':True,'fresh_parent_turn_distinct':True})


    def test_cleanup_receipt_exception_retains_unconfirmed_native_ownership(self):
        with self.active():
            call=self.call();call.uses_web=True;call.session=NS(id='receipt-exception')
            def fail_receipt(*a,**k):raise RuntimeError('synthetic receipt observation unavailable')
            call.registry=NS(settle_web=fail_receipt)
            with wc.bind_web_call(call):out=json.loads(wp._failure('web_provider_failed',call=call,cleanup='confirmed'))
            self.assertEqual(out['cleanup'],'unconfirmed');self.assertEqual(call.turn.receipt['status'],'STOP_UNCONFIRMED');self.assertIn(call,call.turn.calls)
            call.registry=NS(settle_web=lambda *a,**k:{'status':'QUIESCENT'});self.assertEqual(call.turn.stop()['status'],'QUIESCENT')
