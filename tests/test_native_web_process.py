"""Real namespace children and native handlers; systemd/DNS/HTTP seams synthetic.

This proves registry integration, finite child custody and significant negative
controls offline. It does not qualify actual transient units or live providers.
"""
import asyncio
import contextvars
import json
import os
from pathlib import Path
import subprocess
import signal
import runpy
import sys
import threading
import time
from types import SimpleNamespace

import pytest

E=Path(os.environ['FRIDAY_FIXTURE_EVIDENCE'])
N=Path(os.environ.get('FRIDAY_FIXTURE_NATIVE',str(E/'native')))
from agent.web_call_context import WebTurn,WebCall,bind_web_call,make_web_call
from tools.process_registry import ProcessRegistry,ProcessSession
from tools import process_registry as pr
from tools import process_registry_web as boundary
from tools.registry import registry
from tools import web_tools


@pytest.fixture
def native_child(tmp_path,monkeypatch):
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    home=tmp_path/'profile';home.mkdir(mode=0o700)
    (home/'config.yaml').write_text('web:\n  backend: exa\n  keyless_fallback: true\n  cache_enabled: true\n  provider_tier:\n    exa: free\n')
    (home/'config.yaml').chmod(0o600)
    token=set_hermes_home_override(home);secret=set_secret_scope({},profile_home=home)
    r=ProcessRegistry();monkeypatch.setattr(pr,'process_registry',r)
    actual_popen=subprocess.Popen;children=[];plans=[];shown={};receipts=[];custody={}
    namespace_exit=runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/install_containment.py"))["namespace_exit"]
    def status(proc, *, complete=False):
        item=custody[proc.pid]
        try:item["raw"]+=os.read(item["reader"],4097)
        except BlockingIOError:pass
        assert len(item["raw"])<=4096
        rows=[json.loads(line) for line in item["raw"].splitlines() if line.strip()]
        if rows and item["init_fd"] is None:
            item["init_pid"]=rows[0]["child-pid"]
            try:item["init_fd"]=os.pidfd_open(item["init_pid"])
            except ProcessLookupError:pass
        if complete:
            assert namespace_exit(item["raw"],{"returncode":proc.returncode,"timeout":False,"reaped":True}),item
            item["verified"]=True
        return rows
    def settle(proc, *, stop=False):
        if stop and proc.poll() is None:
            until=time.monotonic()+1
            while not status(proc) and time.monotonic()<until:time.sleep(.005)
            item=custody[proc.pid]
            assert item["init_fd"] is not None,"namespace init ownership unconfirmed"
            try:signal.pidfd_send_signal(item["init_fd"],signal.SIGKILL)
            except ProcessLookupError:pass
        proc.wait(timeout=2)
        status(proc,complete=True)
        return custody[proc.pid]
    def popen(argv,**kwargs):
        assert argv[0].endswith('systemd-run') and '--pipe' in argv and '--wait' in argv
        unit=next(a.split('=',1)[1] for a in argv if a.startswith('--unit='))
        s=next(s for s in r._running.values() if s.systemd_unit==unit)
        assert any(row['session_id']==s.id for row in json.loads((home/'processes.json').read_text()))
        assert s.process is None and s.web_custody and s.task_id=='owned-task'
        plans.append({'argv':list(argv),'env':dict(kwargs['env']),'registered_before_popen':True})
        reader,writer=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        cmd=['/usr/bin/bwrap','--json-status-fd',str(writer),'--unshare-all','--die-with-parent','--new-session','--as-pid-1',
             '--ro-bind','/','/','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
             '--bind',str(home),str(home),'--chdir',str(home),'--',sys.executable,'-I','-B',str(E/'child_guard.py')]
        # No service is created. Only the launch seam is replaced with the
        # already-reviewed PID-namespace boundary; the registry path stays real.
        kwargs["pass_fds"]=(writer,)
        try:proc=actual_popen(cmd,**kwargs)
        finally:os.close(writer)
        children.append(proc);custody[proc.pid]={"reader":reader,"raw":b"","init_fd":None,"init_pid":None,"verified":False}
        until=time.monotonic()+1
        while not status(proc) and time.monotonic()<until:time.sleep(.005)
        assert custody[proc.pid]["init_fd"] is not None
        shown[s.id]={'Id':unit,'Description':'Hermes web '+s.id,'InvocationID':'a'*32,
                     'KillMode':'control-group','SendSIGKILL':'yes','Restart':'no','RemainAfterExit':'no',
                     'ExitType':'main','NoNewPrivileges':'yes','ProtectControlGroups':'yes','Delegate':'no',
                     'RuntimeRandomizedExtraUSec':'0','ActiveEnterTimestampMonotonic':str(int(time.monotonic()*1e6)),
                     'ControlGroup':'/offline-fixture/'+unit,
                     'RuntimeMaxUSec':next(a.split('=',2)[2] for a in argv if a.startswith('--property=RuntimeMaxSec=')),
                     'TimeoutStopUSec':'1s','ActiveState':'active','SubState':'running'}
        return proc
    monkeypatch.setattr(subprocess,'Popen',popen)
    def show(s,timeout=1):
        value=dict(shown[s.id]);value['MainPID']=str(s.pid if s.process.poll() is None else 0);return value
    monkeypatch.setattr(r,'_web_show',show)
    monkeypatch.setattr(r,'_web_capture_cgroup',lambda s:setattr(s,'web_cgroup_identity',[1,2]))
    def populated(s):
        if s.process.poll() is None:return True
        settle(s.process);return False
    monkeypatch.setattr(r,'_web_populated',populated)
    def command(argv,timeout):
        assert argv[1:3]==['--user','stop']
        s=next(s for s in r._running.values() if s.systemd_unit==argv[3])
        item=settle(s.process,stop=True)
        receipts.append({'session_id':s.id,'namespace_init_exit_verified':item['verified'],'real_child_reaped':True,'init_pid':item['init_pid'],'native_monitor_status':item['raw'].decode()})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(r,'_web_command',command)
    monkeypatch.setattr(boundary.shutil,'which',lambda name:'/usr/bin/'+name)
    def rows():
        p=home/'observations.jsonl'
        return [json.loads(row) for row in p.read_text().splitlines()] if p.exists() else []
    def call(seconds=15):return WebCall(WebTurn(),time.monotonic()+seconds,'owned-task','owned-session','owned-call')
    yield SimpleNamespace(registry=r,home=home,plans=plans,children=children,receipts=receipts,rows=rows,call=call,shown=shown)
    # Test cleanup is explicit and separate from the product's stop observation.
    for proc in children:
        settle(proc,stop=proc.poll() is None)
        for stream in (proc.stdin,proc.stdout,proc.stderr):
            if stream is not None and not stream.closed:stream.close()
    assert all(p.poll() is not None for p in children)
    with (E/'child-executions.jsonl').open('a') as record:
        for proc in children:
            item=custody[proc.pid]
            record.write(json.dumps({'attempt':'corrected-custody','test':os.environ.get('PYTEST_CURRENT_TEST'),'pid':proc.pid,'init_pid':item['init_pid'],'returncode':proc.returncode,'reaped':True,'namespace_init_exit_verified':item['verified'],'native_monitor_status':item['raw'].decode(),'guard':str(E/'child_guard.py'),'fixture_seams':['systemd unit/clock/cgroup metadata','DNS','HTTP/SDK'],'AS_limit':512<<20,'CPU_limit':8,'network_namespace':'unshare-all'})+'\n')
            os.close(item['reader'])
            if item['init_fd'] is not None:os.close(item['init_fd'])
    reset_secret_scope(secret);reset_hermes_home_override(token)


def dispatch(call,name,args):
    with bind_web_call(call):return json.loads(registry.dispatch(name,args,task_id=call.task_id,session_id=call.session_id))


def test_normal_registered_search_real_child_result_and_native_handle(native_child):
    f=native_child;c=f.call()
    result=dispatch(c,'web_search',{'query':'fixture normal','limit':2})
    assert result.get('success') is True,result
    assert f.rows()[0]['pid']!=os.getpid()
    assert c.session.web_settled and c.session.web_tool_call_id=='owned-call'
    assert not f.registry._running and c.session.id in f.registry._finished
    assert not c.turn.calls and c.session.process.poll()==0
    assert c.receipt['native_child_exit_zero'] is True
    assert 'native web child'==c.session.command
    assert all('EXA_API_KEY' not in row['env'] for row in f.plans)


def test_normal_registered_extract_native_async_body_spill_cache(native_child):
    f=native_child;c=f.call()
    result=dispatch(c,'web_extract',{'urls':['https://docs.example/api'],'char_limit':2000})
    assert result.get('results') and not result['results'][0].get('error'),result
    assert len(result['results'][0]['content'])<3500
    assert list((f.home/'cache/web').glob('*'))
    c2=f.call();result2=dispatch(c2,'web_extract',{'urls':['https://docs.example/api'],'char_limit':2000})
    assert result2.get('results') and not result2['results'][0].get('error'),result2
    assert sum(row['kind']=='http' for row in f.rows())==1


def test_search_memo_and_single_flight_preserved_across_real_execs(native_child):
    f=native_child
    assert dispatch(f.call(),'web_search',{'query':'cache-only','limit':2})['success']
    assert dispatch(f.call(),'web_search',{'query':' CACHE-ONLY ','limit':2})['success']
    assert sum(r['kind']=='http' for r in f.rows())==1


@pytest.mark.parametrize('name,args,phase',[
    ('web_search',{'query':'headers-slow','limit':2},'http'),
    ('web_extract',{'urls':['https://dns-slow.example/a','https://docs.example/b']},'dns'),
    ('web_extract',{'urls':['https://extract-slow.example/a','https://docs.example/b']},'http'),
])
def test_stop_real_slow_dns_headers_extract_and_no_late_url(native_child,name,args,phase):
    f=native_child;c=f.call();results=[]
    ctx=contextvars.copy_context()
    thread=threading.Thread(target=lambda:ctx.run(lambda:results.append(dispatch(c,name,args))))
    thread.start()
    until=time.monotonic()+6
    while time.monotonic()<until and not any(row['kind']==phase for row in f.rows()):time.sleep(.01)
    assert any(row['kind']==phase for row in f.rows()),f.rows()
    receipt=c.turn.stop();thread.join(timeout=4)
    assert not thread.is_alive() and receipt['status']=='QUIESCENT',receipt
    assert results and results[0].get('error')=='web_native_boundary_refused',results
    assert f.receipts and all(r['namespace_init_exit_verified'] for r in f.receipts)
    assert not f.registry._running and not c.turn.calls
    assert not any(row['kind']=='http' and 'https://docs.example/b' in json.dumps(row) for row in f.rows())
    before=len(f.children);result=dispatch(c,name,args)
    assert result.get('error') and len(f.children)==before  # sticky same-turn stop


def test_actual_original_deadline_times_out_and_reaps_real_child(native_child):
    f=native_child;c=f.call(9)
    began=time.monotonic();result=dispatch(c,'web_search',{'query':'deadline-slow','limit':2})
    assert result.get('error')=='web_timeout',result
    assert time.monotonic()-began<9
    assert c.session.web_settled and not f.registry._running
    assert f.receipts[-1]['namespace_init_exit_verified']
    assert c.session.web_deadline==c.base_deadline


@pytest.mark.parametrize('deadline',[None,float('inf'),float('nan'),-1])
def test_no_new_or_unbounded_caller_clock_admitted(native_child,deadline):
    f=native_child;c=f.call();c.base_deadline=deadline
    result=dispatch(c,'web_search',{'query':'must not run'})
    assert result.get('error') and not f.children


def test_missing_caller_context_refuses_registered_handler(native_child):
    result=json.loads(registry.dispatch('web_search',{'query':'x'},task_id='owned-task',session_id='owned-session'))
    assert result['detail']=='web_caller_context_required' and not native_child.children


def test_owner_identity_mismatch_refuses_before_spawn(native_child):
    f=native_child;c=f.call()
    with bind_web_call(c):result=json.loads(registry.dispatch('web_search',{'query':'x'},task_id='other',session_id=c.session_id))
    assert result.get('error') and not f.children


def test_stop_before_launch_fences_registration_and_input(native_child):
    f=native_child;c=f.call();c.turn.stop()
    assert dispatch(c,'web_search',{'query':'x'}).get('error') and not f.children


def test_stop_lands_inside_launch_fence_and_never_releases_input(native_child,monkeypatch):
    f=native_child;c=f.call();original=f.registry.spawn_web
    def launch(call):
        session=original(call);c.turn.stopped.set();return session
    monkeypatch.setattr(f.registry,'spawn_web',launch)
    result=dispatch(c,'web_search',{'query':'never release'})
    assert result.get('error') and not f.rows()
    assert c.session.web_settled and f.receipts[-1]['namespace_init_exit_verified']


def test_failed_stop_is_unknown_keeps_exact_registry_handle_blocks_replacement(native_child,monkeypatch):
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    monkeypatch.setattr(f.registry,'_web_command',lambda *a,**k:SimpleNamespace(returncode=1))
    receipt=c.stop()
    assert receipt['status']=='STOP_UNCONFIRMED' and c.session.id in f.registry._running
    assert not c.session.web_settled and c.session.web_unconfirmed
    with pytest.raises(RuntimeError,match='STOP_UNCONFIRMED'):
        with c.turn.lock:f.registry.spawn_web(f.call())
    assert len(f.children)==1


def test_checkpoint_failure_withholds_payload_and_retains_launch_custody(native_child,monkeypatch):
    f=native_child;c=f.call()
    old=f.registry._web_checkpoint
    def checkpoint(s):
        old(s)
        if s.process is not None:raise RuntimeError('fixture persistence failure')
    monkeypatch.setattr(f.registry,'_web_checkpoint',checkpoint)
    result=dispatch(c,'web_search',{'query':'never release'})
    assert result.get('error') and not f.rows()
    assert c.session is not None and c.session.web_settled


def test_ambient_and_foreign_profile_secrets_never_enter_child_env_or_checkpoint(native_child,monkeypatch):
    f=native_child;monkeypatch.setenv('EXA_API_KEY','FORBIDDEN_SIBLING');monkeypatch.setenv('OPENAI_API_KEY','FORBIDDEN_MODEL')
    result=dispatch(f.call(),'web_search',{'query':'synthetic'})
    assert result['success'],result
    assert 'FORBIDDEN' not in json.dumps(f.plans)
    assert 'FORBIDDEN' not in (f.home/'processes.json').read_text()


@pytest.mark.parametrize('key',['SYNTHETIC_PAID_SECRET_123456789','SYNTHETIC_PAID_SECRET_QUOTE\"SLASH\\123456789','SYNTHETIC_PAID_SECRET_КЛЮЧ_123456789'])
def test_paid_active_scope_key_is_private_and_redacted(native_child,key):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    f=native_child
    (f.home/'config.yaml').write_text('web:\n  backend: exa\n  provider_tier:\n    exa: paid\n')
    token=set_secret_scope({'EXA_API_KEY':key},profile_home=f.home)
    try:result=dispatch(f.call(),'web_search',{'query':'paid fixture','limit':2})
    finally:reset_secret_scope(token)
    assert result.get('success') is True,result
    assert 'redacted' in json.dumps(result) and 'SYNTHETIC_PAID_SECRET' not in json.dumps(result)
    assert any(row['kind']=='paid' and row['has_key'] for row in f.rows())
    assert 'SYNTHETIC_PAID_SECRET' not in json.dumps(f.plans)


def test_search_cache_never_aliases_different_profile(native_child):
    from tools.web_result_cache import search_memo
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    f=native_child;assert dispatch(f.call(),'web_search',{'query':'isolation'})['success']
    other=f.home.parent/'other';other.mkdir(mode=0o700)
    token=set_hermes_home_override(other)
    try:
        assert search_memo.lookup('exa','isolation',5) is None
        assert search_memo.export_query('isolation',5)==[]
    finally:reset_hermes_home_override(token)


def test_original_run_budget_caps_call_and_approval_wait_never_resets_origin():
    agent=SimpleNamespace(session_id='s',_current_turn_id='turn-g',_web_run_deadline=150,_interrupt_requested=False)
    gate=SimpleNamespace(excluded_seconds=lambda:12)
    call=make_web_call(agent,100,'t','call',gate)
    assert call.deadline()==112 and call.turn_id=='turn-g'
    gate.excluded_seconds=lambda:80
    assert call.deadline()==150 and call.base_deadline==100
    agent._web_run_deadline=None
    disabled=make_web_call(agent,100,'t','other',gate)
    assert disabled.deadline()==180  # no invented overall run limit


@pytest.mark.parametrize('field,value',[('InvocationID','b'*32),('KillMode','process'),('SendSIGKILL','no'),
                                       ('Restart','always'),('RemainAfterExit','yes'),('ExitType','cgroup'),
                                       ('Description','someone else'),('Id','another.service'),
                                       ('NoNewPrivileges','no'),('ProtectControlGroups','no'),
                                       ('Delegate','yes'),('RuntimeRandomizedExtraUSec','1s')])
def test_actual_native_unit_parser_refuses_identity_policy_drift(field,value,monkeypatch):
    r=ProcessRegistry();s=ProcessSession(id='proc_test',command='native web child',systemd_unit='hermes-worker-web-proc_test.service',web_custody=True,web_invocation='a'*32)
    data={'Id':s.systemd_unit,'Description':'Hermes web '+s.id,'InvocationID':'a'*32,'KillMode':'control-group',
          'SendSIGKILL':'yes','Restart':'no','RemainAfterExit':'no','ExitType':'main','NoNewPrivileges':'yes',
          'ProtectControlGroups':'yes','Delegate':'no','RuntimeRandomizedExtraUSec':'0'};data[field]=value
    monkeypatch.setattr(boundary.shutil,'which',lambda n:'/usr/bin/'+n)
    monkeypatch.setattr(r,'_web_command',lambda *a:SimpleNamespace(returncode=0,stdout='\n'.join(k+'='+v for k,v in data.items()).encode()))
    with pytest.raises(RuntimeError):r._web_show(s)


@pytest.mark.parametrize('value,expected',[('1s',1000000),('1.5ms',1500),('1min 2s 3us',62000003),('500',500)])
def test_systemctl_timespan_property_formats(value,expected):assert boundary._usec(value)==expected


@pytest.mark.parametrize('value',['infinity','-1s','1.2us','garbage',''])
def test_unsupported_native_property_format_refuses(value):
    with pytest.raises(ValueError):boundary._usec(value)


@pytest.mark.parametrize('failure',['late_activation','population_unknown'])
def test_native_clock_and_complete_cgroup_are_required(native_child,monkeypatch,failure):
    f=native_child;c=f.call();original=f.registry._web_show
    if failure=='late_activation':
        def late(s,*a):
            data=original(s,*a);data['ActiveEnterTimestampMonotonic']=str(int((time.monotonic()+4)*1e6));return data
        monkeypatch.setattr(f.registry,'_web_show',late)
    else:
        monkeypatch.setattr(f.registry,'_web_populated',lambda s:True)
    result=dispatch(c,'web_search',{'query':'normal'})
    if failure=='late_activation':
        assert result.get('error') and not f.rows() and c.session.web_settled
    else:
        assert result.get('error')=='STOP_UNCONFIRMED' and c.session.id in f.registry._running
        assert not c.session.web_settled


def executor_agent(monkeypatch):
    helper=runpy.run_path(str(N/'tests/agent/test_concurrent_interrupt.py'))
    agent=helper['_make_agent'](monkeypatch)
    agent.session_id='owned-session';agent._current_turn_id='actual-turn';agent._web_turn=WebTurn()
    agent._web_run_deadline=None;agent.valid_tool_names={'web_search','web_extract'}
    from agent.tool_guardrails import ToolCallGuardrailController
    agent._tool_guardrails=ToolCallGuardrailController()
    return agent


def test_ordinary_sequential_executor_carries_original_caller_into_real_child(native_child,monkeypatch):
    from agent import tool_executor as te
    f=native_child;agent=executor_agent(monkeypatch)
    monkeypatch.setattr(te,'_resolve_sequential_tool_timeout',lambda:15)
    began=time.monotonic()
    result=te._run_sequential_tool_execution_middleware(agent,function_name='web_search',
        function_args={'query':'executor normal','limit':2},effective_task_id='owned-task',
        tool_call_id='real-call',execute=lambda args:registry.dispatch('web_search',args,task_id='owned-task',session_id='owned-session'))
    assert json.loads(result.result)['success']
    handle=next(iter(f.registry._finished.values()))
    assert handle.web_tool_call_id=='real-call' and handle.web_turn_id=='actual-turn'
    assert began+15<=handle.web_deadline<=began+15.1
    assert not agent._web_turn.calls and not f.registry._running


def test_ordinary_concurrent_executor_uses_one_batch_deadline_and_real_children(native_child,monkeypatch):
    from agent import tool_executor as te
    helper=runpy.run_path(str(N/'tests/agent/test_concurrent_interrupt.py'))
    f=native_child;agent=executor_agent(monkeypatch);messages=[]
    monkeypatch.setattr(te,'_resolve_concurrent_tool_timeout',lambda:15)
    agent._invoke_tool=lambda name,args,task,call,**kw:registry.dispatch(name,args,task_id=task,session_id=agent.session_id)
    calls=[helper['_FakeToolCall']('web_search',json.dumps({'query':q,'limit':2}),call_id='actual-'+q) for q in ('batch-a','batch-b')]
    batch=te._ConcurrentBatch(agent,messages,'owned-task',[te._parse_tool_call(agent,c) for c in calls],15)
    batch.run()
    assert len(batch.results)==2 and all(json.loads(r.result)['success'] for r in batch.results),batch.results
    handles=list(f.registry._finished.values())
    assert len(handles)==2 and handles[0].web_deadline==handles[1].web_deadline
    assert {s.web_tool_call_id for s in handles}=={'actual-batch-a','actual-batch-b'}
    assert all(s.web_turn_id=='actual-turn' and s.web_settled for s in handles)
    assert not f.registry._running and not agent._web_turn.calls


def test_native_agent_interrupt_consumes_real_settlement_and_latch_survives_clear(native_child,monkeypatch):
    f=native_child;agent=executor_agent(monkeypatch)
    c=make_web_call(agent,time.monotonic()+15,'owned-task','actual-stop');results=[]
    ctx=contextvars.copy_context()
    thread=threading.Thread(target=lambda:ctx.run(lambda:results.append(dispatch(c,'web_search',{'query':'headers-slow'}))))
    thread.start();until=time.monotonic()+6
    while not any(row['kind']=='http' for row in f.rows()) and time.monotonic()<until:time.sleep(.01)
    assert any(row['kind']=='http' for row in f.rows())
    try:
        agent.interrupt('fixture stop')
        assert agent._web_stop_receipt['status']=='QUIESCENT'
    finally:agent.clear_interrupt()
    thread.join(timeout=3)
    assert not thread.is_alive() and c.turn.stopped.is_set() and not f.registry._running
    assert results[0].get('error') and f.receipts[-1]['namespace_init_exit_verified']


def test_expired_recovered_handle_closes_only_with_empty_pinned_cgroup_and_wrapper_fate(native_child,monkeypatch):
    f=native_child;c=f.call();assert dispatch(c,'web_search',{'query':'recovery'})['success']
    old=c.session
    s=ProcessSession(id='proc_recovered',command='native web child',web_custody=True,web_invocation=old.web_invocation,
        web_cgroup=old.web_cgroup,web_cgroup_identity=old.web_cgroup_identity,web_deadline=time.monotonic()-100,
        web_boot_id=old.web_boot_id,systemd_unit=old.systemd_unit,task_id='owned-task',session_key='owned-session',detached=True,pid=old.pid,host_start_time=old.host_start_time)
    f.registry._running[s.id]=s
    monkeypatch.setattr(f.registry,'_web_populated',lambda s:False)
    monkeypatch.setattr(f.registry,'_web_show',lambda *a,**k:(_ for _ in ()).throw(AssertionError('no post-deadline service effects')))
    monkeypatch.setattr(f.registry,'_detached_host_fate',lambda *a:'running')
    assert f.registry.settle_web(s,stop=True)['status']=='STOP_UNCONFIRMED'
    monkeypatch.setattr(f.registry,'_detached_host_fate',lambda *a:'gone')
    assert f.registry.settle_web(s,stop=True)['status']=='QUIESCENT' and s.web_settled


@pytest.mark.parametrize('name',['_busy_stop_command','_busy_new_command'])
def test_actual_gateway_commands_do_not_claim_stop_or_reset_on_unknown_custody(monkeypatch,name):
    from gateway.run import GatewayRunner
    helper=runpy.run_path(str(N/'tests/gateway/test_busy_command.py'))
    runner=helper['_make_runner']();event=helper['_make_event']('/stop' if name=='_busy_stop_command' else '/new')
    async def unsettled(*a,**k):return {'status':'STOP_UNCONFIRMED'}
    runner._interrupt_and_clear_session=unsettled
    async def reset(*a,**k):raise AssertionError('replacement after unconfirmed cessation')
    runner._handle_reset_command=reset
    method=getattr(GatewayRunner,name)
    # Existing native-control decorator policy is covered by its separate gate;
    # exercise the actual command body with an already-authorized control here.
    while hasattr(method,'__wrapped__'):method=method.__wrapped__
    reply=asyncio.run(method(runner,event,'session',event.source))
    assert 'unconfirmed' in str(reply).lower() and 'pending' in str(reply).lower()


def test_checkpoint_recovery_adopts_dead_wrapper_intent_without_replay(native_child,monkeypatch):
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    retained=json.loads((f.home/'processes.json').read_text());assert len(retained)==1
    retained[0]['pid']=None
    (f.home/'processes.json').write_text(json.dumps(retained))
    other=ProcessRegistry()
    monkeypatch.setattr(other,'_detached_host_fate',lambda *a:(_ for _ in ()).throw(AssertionError('PID absence is not cessation')))
    assert other.recover_from_checkpoint()==1
    session=other._running[c.session.id]
    assert session.web_custody and session.web_unconfirmed and session._scope_stop_pending
    assert session.web_tool_call_id==c.call_id and session.web_deadline==c.base_deadline
    assert session.web_invocation==c.session.web_invocation and session.process is None
    assert len(f.children)==1
    assert c.stop()['status']=='QUIESCENT'


def test_cli_stop_reports_unknown_native_custody_instead_of_cleanup_count(native_child,monkeypatch,capsys):
    from hermes_cli.cli_commands_mixin import CLICommandsMixin
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    monkeypatch.setattr(f.registry,'_web_command',lambda *a,**k:SimpleNamespace(returncode=1))
    monkeypatch.setattr('hermes_cli.cli_commands_mixin._probe',lambda *a:0)
    CLICommandsMixin._handle_stop_command(SimpleNamespace())
    assert 'cessation is unconfirmed' in capsys.readouterr().out
    assert f.registry.web_custody_receipt()['status']=='STOP_UNCONFIRMED'


def test_process_stop_rpc_exposes_actual_unknown_settlement(native_child,monkeypatch):
    from tui_gateway import methods_tools
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    monkeypatch.setattr(f.registry,'_web_command',lambda *a,**k:SimpleNamespace(returncode=1))
    monkeypatch.setattr(methods_tools,'_tools_mod',lambda name:SimpleNamespace(process_registry=f.registry))
    result=methods_tools._stop_processes({})
    assert result['status']=='STOP_UNCONFIRMED' and result['sessions']==[c.session.id] and result['killed']==0


def test_real_native_agent_loop_uses_registered_children_without_model_or_provider_network(native_child,monkeypatch):
    f=native_child
    Q=Path(__file__).resolve().parents[1]
    build=runpy.run_path(str(Q/'tools/configure_local_test.py'))['build_config']
    config=build(base_url='http://127.0.0.1:8011/v1',model='offline-native-fixture',key_env='FRIDAY_FIXTURE_KEY',
        context=40960,max_input=40954,main_output=4096,summary_output=2048,margin=1024,template_overhead=2048,web_profile='exa-keyless')
    driver=runpy.run_path(str(Q/'validation/web_runtime.py'))
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.config import atomic_config_replace
    config=driver['validation_profile'](config,DEFAULT_CONFIG)
    atomic_config_replace(f.home/'config.yaml',config)
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    token=set_secret_scope({'FRIDAY_FIXTURE_KEY':'SYNTHETIC_MODEL_KEY_123456789'},profile_home=f.home)
    import httpx
    responses=[('web_search',{'query':'real agent loop','limit':2}),('web_extract',{'urls':['https://docs.example/api']})]
    requests_seen=[]
    def send(client,request,**kw):
        assert str(request.url)=='http://127.0.0.1:8011/v1/chat/completions'
        body=json.loads(request.content);requests_seen.append(body)
        n=len(requests_seen)
        if n<=2:
            name,args=responses[n-1]
            message={'role':'assistant','content':None,'tool_calls':[{'id':'real-agent-'+str(n),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
            finish='tool_calls'
        else:
            assert n==3
            message={'role':'assistant','content':'Synthetic final response'};finish='stop'
        value={'id':'fixture'+str(n),'created':1,'object':'chat.completion','model':'offline-native-fixture',
            'choices':[{'index':0,'finish_reason':finish,'message':message}],
            'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
        if body.get('stream'):
            if message.get('tool_calls'):
                for i,c in enumerate(message['tool_calls']):c['index']=i
            chunk=dict(value,object='chat.completion.chunk',choices=[{'index':0,'delta':message,'finish_reason':finish}])
            data=('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=data,request=request)
        return httpx.Response(200,json=value,request=request)
    monkeypatch.setattr(httpx.Client,'send',send)
    from run_agent import AIAgent
    agent=None
    try:
        agent=AIAgent(model='offline-native-fixture',base_url='http://127.0.0.1:8011/v1',api_key='SYNTHETIC_MODEL_KEY_123456789',
            provider='custom',api_mode='chat_completions',requested_provider='custom:friday-local',max_iterations=4,enabled_toolsets=['web'],
            skip_context_files=True,skip_memory=True,skip_background_review=True,quiet_mode=True,session_db=None,
            save_trajectories=False,verbose_logging=False,session_id='owned-session',run_budget_seconds=60,fallback_model={},cwd=str(f.home))
        result=agent.run_conversation('Read the synthetic fixture.',task_id='owned-task')
        assert result['final_response']=='Synthetic final response' and len(requests_seen)==3,result
        assert len(f.children)==2 and not f.registry._running and not agent._web_turn.calls
        handles=list(f.registry._finished.values())
        assert {s.web_tool_call_id for s in handles}=={'real-agent-1','real-agent-2'}
        assert all(s.web_deadline<=agent._web_run_deadline for s in handles)
        assert len([r for r in f.rows() if r['kind']=='http'])==2
        assert 'SYNTHETIC_MODEL_KEY' not in json.dumps(f.plans)
        assert not (f.home/'state.db').exists()
    finally:
        if agent is not None:
            close=getattr(agent,'close',None)
            if close:close()
        reset_secret_scope(token)


def test_unscoped_legacy_caller_cannot_hydrate_credentials_outside_owned_boundary(native_child,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope,set_multiplex_context,reset_multiplex_context
    from tools.web_process import _scope_payload
    f=native_child
    token=set_secret_scope(None);mt=set_multiplex_context(False)
    monkeypatch.setattr('agent.secret_scope._MULTIPLEX_ACTIVE',False)
    monkeypatch.setattr('agent.secret_scope.serves_routed_profile',lambda:False)
    calls=[]
    monkeypatch.setattr('agent.secret_scope.build_profile_secret_scope',lambda home:(calls.append(home) or {'EXA_API_KEY':'SYNTHETIC_PROFILE_ONLY','OPENAI_API_KEY':'SYNTHETIC_MODEL_MUST_NOT_TRANSFER'}))
    monkeypatch.setenv('EXA_API_KEY','SYNTHETIC_AMBIENT_MUST_NOT_TRANSFER')
    try:
        with pytest.raises(RuntimeError,match='web_profile_scope_required'):_scope_payload(f.home)
        assert calls==[]
    finally:reset_multiplex_context(mt);reset_secret_scope(token)


def test_multiplex_missing_explicit_scope_cannot_hydrate_or_inherit_ambient(native_child,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope,set_multiplex_context,reset_multiplex_context
    from tools.web_process import _scope_payload
    f=native_child;token=set_secret_scope(None);mt=set_multiplex_context(True)
    monkeypatch.setattr('agent.secret_scope.build_profile_secret_scope',lambda home:(_ for _ in ()).throw(AssertionError('scope bypass')))
    try:
        with pytest.raises(RuntimeError,match='web_profile_scope_required'):_scope_payload(f.home)
    finally:reset_multiplex_context(mt);reset_secret_scope(token)



def test_paid_extract_echo_is_redacted_before_native_cache_and_spill(native_child):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    f=native_child
    (f.home/'config.yaml').write_text('web:\n  backend: exa\n  provider_tier:\n    exa: paid\n')
    key='SYNTHETIC_EXTRACT_SECRET_123456789'
    token=set_secret_scope({'EXA_API_KEY':key},profile_home=f.home)
    try:result=dispatch(f.call(),'web_extract',{'urls':['https://docs.example/api'],'char_limit':2000})
    finally:reset_secret_scope(token)
    assert result.get('results') and not result['results'][0].get('error'),result
    files=list((f.home/'cache/web').glob('*'))
    assert any(p.suffix=='.md' for p in files)
    assert key not in json.dumps(result)
    assert all(key.encode() not in p.read_bytes() for p in files if p.is_file())

# Independent review R01-R07: real native consumers and launch interleavings.
def command_body(cls, name):
    method=getattr(cls,name)
    while hasattr(method,'__wrapped__'):method=method.__wrapped__
    return method


@pytest.mark.parametrize('lane',['pending','running','fallback','idle'])
def test_ordinary_stop_retains_unknown_for_every_lane(native_child,monkeypatch,lane):
    from gateway.run import GatewayRunner,_AGENT_PENDING_SENTINEL
    from gateway.session import SessionSource
    from gateway.config import Platform
    from gateway.platforms.event import MessageEvent
    from gateway.platforms.base import EphemeralReply
    source=SessionSource(platform=Platform.TELEGRAM,chat_id='chat',user_id='user',chat_type='dm')
    event=MessageEvent(text='/stop',source=source)
    r=SimpleNamespace();entry=SimpleNamespace(session_key='route',session_id='durable')
    async def entry_for(*a):return entry
    r.async_session_store=SimpleNamespace(get_or_create_session=entry_for)
    r._running_agents={'route':_AGENT_PENDING_SENTINEL if lane=='pending' else object()} if lane in ('pending','running') else {}
    calls=[]
    async def stop(key,*a,**k):calls.append(key);return {'status':'STOP_UNCONFIRMED'}
    r._interrupt_and_clear_session=stop;r._settle_session_web_custody=stop
    r._same_chat_runs=lambda *a:[];r._sibling_thread_run_keys=lambda *a:[]
    r._chat_scoped_run_keys=lambda *a:['fallback-one','fallback-two'] if lane=='fallback' else []
    r._is_user_authorized_for_source=lambda *a:True
    reply=asyncio.run(command_body(GatewayRunner,'_handle_stop_command')(r,event))
    assert isinstance(reply,EphemeralReply) and 'pending' in str(reply).lower() and 'unconfirmed' in str(reply).lower()
    assert calls==(['fallback-one','fallback-two'] if lane=='fallback' else ['route'])


@pytest.mark.parametrize('phase',['intent','popen','identity-checkpoint','payload'])
@pytest.mark.parametrize('surface',['registry','rpc','cli'])
def test_native_stop_latches_before_launch_and_stdin(native_child,monkeypatch,phase,surface,capsys):
    f=native_child;c=f.call();stops=[]
    def stop():
        if surface=='registry':stops.append(f.registry.kill_process(c.session.id))
        elif surface=='rpc':
            from tui_gateway.methods_tools import _stop_processes
            stops.append(_stop_processes({}))
        else:
            from hermes_cli.cli_commands_mixin import CLICommandsMixin
            CLICommandsMixin._handle_stop_command(SimpleNamespace())
            stops.append(f.registry.web_custody_receipt())
        assert c.stopped.is_set() and c.session.web_stop_requested
    if phase in ('intent','identity-checkpoint'):
        original=f.registry._web_checkpoint
        def checkpoint(s):
            original(s)
            if (s.process is None if phase=='intent' else bool(s.web_invocation)) and not stops:stop()
        monkeypatch.setattr(f.registry,'_web_checkpoint',checkpoint)
    elif phase=='popen':
        original=subprocess.Popen
        def launch(*a,**kw):
            p=original(*a,**kw);stop();return p
        monkeypatch.setattr(subprocess,'Popen',launch)
    else:
        original=f.registry.web_exchange
        def exchange(s,payload,call):stop();return original(s,payload,call)
        monkeypatch.setattr(f.registry,'web_exchange',exchange)
    result=dispatch(c,'web_search',{'query':'input never released'})
    assert result.get('error') and stops and not f.rows()
    before=len(f.children);assert dispatch(c,'web_search',{'query':'second launch'}).get('error') and len(f.children)==before
    if phase=='intent':
        assert not f.children and c.session.id in f.registry._running and c.session.web_unconfirmed
        rows=json.loads((f.home/'processes.json').read_text());assert rows[0]['web_stop_requested'] is True
    else:
        assert f.children and c.session.web_settled and not f.registry._running


@pytest.mark.parametrize('command',['/new','/reset'])
def test_ordinary_reset_preserves_durable_session_and_owner_on_unknown(native_child,command):
    from gateway.run import GatewayRunner
    from gateway.platforms.event import MessageEvent
    from gateway.config import Platform
    from gateway.session import SessionSource
    r=object.__new__(GatewayRunner);r._session_key_for_source=lambda *a:'route'
    touched=[]
    async def unknown(*a):return {'status':'STOP_UNCONFIRMED'}
    r._settle_session_web_custody=unknown
    for name in ['_invalidate_session_run_generation','_release_running_agent_state','_evict_cached_agent','_clear_conversation_scope']:
        setattr(r,name,lambda *a,**kw:touched.append((a,kw)))
    event=MessageEvent(text=command,source=SessionSource(platform=Platform.TELEGRAM,chat_id='chat',user_id='user'))
    reply=asyncio.run(command_body(GatewayRunner,'_handle_reset_command')(r,event))
    assert 'pending' in str(reply).lower() and not touched


def test_routing_key_durable_identity_and_recovery_are_distinct(native_child,monkeypatch):
    from tools.approval_context import set_current_session_key,reset_current_session_key
    f=native_child;token=set_current_session_key('agent:profile:telegram:dm:chat')
    try:c=make_web_call(SimpleNamespace(session_id='durable-conversation'),time.monotonic()+15,'owned-task','owned-call')
    finally:reset_current_session_key(token)
    with c.turn.lock:f.registry.spawn_web(c)
    s=c.session
    assert s.session_key=='agent:profile:telegram:dm:chat' and s.parent_session_id==c.session_id=='durable-conversation'
    assert f.registry.has_active_for_session(s.session_key)
    other=ProcessRegistry();assert other.recover_from_checkpoint()==1
    recovered=other.get(s.id);assert recovered.session_key==s.session_key and recovered.parent_session_id==s.parent_session_id
    receipt=f.registry.stop_web_for_session(s.session_key,parent_session_id=s.parent_session_id,profile_home=str(f.home))
    assert receipt['status']=='QUIESCENT' and receipt['newly_settled']==1
    assert not f.registry.has_active_for_session(s.session_key)


def test_idle_recovered_scope_stops_only_matching_profile_and_conversation(native_child,monkeypatch):
    f=native_child
    for sid,key,home,parent in [('same','route',str(f.home),'durable'),('sibling','other',str(f.home),'other-durable'),('otherprofile','route',str(f.home/'other'),'durable')]:
        f.registry._running[sid]=ProcessSession(id=sid,command='native web child',web_custody=True,cwd=home,session_key=key,parent_session_id=parent)
    called=[]
    def settle(s,**kw):
        assert s.web_stop_requested;called.append(s.id);return {'status':'STOP_UNCONFIRMED','session_id':s.id}
    monkeypatch.setattr(f.registry,'settle_web',settle)
    receipt=f.registry.stop_web_for_session('route',parent_session_id='durable',profile_home=str(f.home))
    assert receipt['status']=='STOP_UNCONFIRMED' and called==['same']
    assert not f.registry._running['sibling'].web_stop_requested and not f.registry._running['otherprofile'].web_stop_requested


def test_approved_gateway_endpoints_consume_scope_and_exclude_ambient(native_child,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope,set_multiplex_context,reset_multiplex_context
    from tools.managed_tool_gateway import build_vendor_gateway_url
    f=native_child
    monkeypatch.setenv('FIRECRAWL_GATEWAY_URL','https://sibling.invalid')
    for scope,expected in [({'FIRECRAWL_GATEWAY_URL':'https://approved.invalid/'},'https://approved.invalid'),({'TOOL_GATEWAY_DOMAIN':'approved.invalid','TOOL_GATEWAY_SCHEME':'http'},'http://firecrawl-gateway.approved.invalid'),({},'https://firecrawl-gateway.nousresearch.com')]:
        st=set_secret_scope(scope,profile_home=f.home);mt=set_multiplex_context(True)
        try:assert build_vendor_gateway_url('firecrawl')==expected
        finally:reset_multiplex_context(mt);reset_secret_scope(st)


def test_parent_transfer_prunes_expired_queries_profiles_and_preserves_ttl(native_child,monkeypatch):
    from tools.web_result_cache import SearchMemo
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    f=native_child;m=SearchMemo();m.store('exa','expired',5,{'success':True});m.store('exa','live',5,{'success':True})
    key=m._key('exa','expired',5);m._store[key]=(time.monotonic()-1,m._store[key][1])
    token=set_hermes_home_override(f.home/'other')
    try:m.store('exa','other-profile-expired',5,{'success':True});other=m._key('exa','other-profile-expired',5);m._store[other]=(time.monotonic()-1,m._store[other][1])
    finally:reset_hermes_home_override(token)
    rows=m.export_query('live',5);expiry=rows[0][1]
    assert key not in m._store and other not in m._store and len(m._store)==1
    m.import_query(rows,'live',5);assert m.export_query('live',5)[0][1]==expiry
    m._store[key]=(time.monotonic()-1,{'success':True});m.import_query([], 'new',5);assert key not in m._store


def test_kill_all_counts_real_web_settlement_once_and_mixed_legacy(native_child,monkeypatch):
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    original=f.registry.kill_process;legacy=ProcessSession(id='legacy',command='ordinary',owner_task_id='owned-task');f.registry._running[legacy.id]=legacy
    def kill(sid,**kw):
        if sid=='legacy':legacy.exited=True;return {'status':'killed'}
        return original(sid,**kw)
    monkeypatch.setattr(f.registry,'kill_process',kill)
    assert f.registry.kill_all(source='process.stop')==2
    assert c.session.web_settled and c.stopped.is_set()
    assert f.registry.kill_all(source='process.stop')==0


def test_actual_idle_gateway_stop_and_reset_reconcile_retained_web_owner(native_child,monkeypatch):
    from gateway.run import GatewayRunner
    from gateway.config import GatewayConfig,Platform
    from gateway.session import SessionSource
    from gateway.platforms.event import MessageEvent
    f=native_child
    monkeypatch.setattr('gateway.run._write_runtime_status_quiet',lambda **kw:None)
    monkeypatch.setattr('gateway.status.publish_runtime_status',lambda **kw:0)
    monkeypatch.setattr('gateway.status.write_runtime_status',lambda **kw:True)
    runner=GatewayRunner(config=GatewayConfig())
    monkeypatch.setattr(runner,'_persist_active_agents',lambda:None)
    source=SessionSource(platform=Platform.TELEGRAM,chat_id='actual-chat',user_id='actual-user',chat_type='dm')
    entry=runner.session_store.get_or_create_session(source)
    c=f.call();c.session_key=entry.session_key;c.session_id=entry.session_id
    with c.turn.lock:f.registry.spawn_web(c)
    s=c.session;sid=entry.session_id
    command=f.registry._web_command
    monkeypatch.setattr(f.registry,'_web_command',lambda *a,**kw:SimpleNamespace(returncode=1))
    stop=command_body(GatewayRunner,'_handle_stop_command');reset=command_body(GatewayRunner,'_handle_reset_command')
    reply=asyncio.run(stop(runner,MessageEvent(text='/stop',source=source)))
    assert 'pending' in str(reply).lower() and s.id in f.registry._running
    assert runner._session_web_pending(entry.session_key)
    assert runner._release_running_agent_state(entry.session_key) is False
    reply=asyncio.run(reset(runner,MessageEvent(text='/new',source=source)))
    assert 'pending' in str(reply).lower() and runner.session_store._entries[entry.session_key].session_id==sid
    monkeypatch.setattr(f.registry,'_web_command',command)
    reply=asyncio.run(stop(runner,MessageEvent(text='/stop',source=source)))
    assert 'stopped' in str(reply).lower() and not f.registry._running and s.web_settled
    receipt=asyncio.run(runner._settle_session_web_custody(entry.session_key))
    assert receipt['status']=='QUIESCENT' and receipt['newly_settled']==0
    # After positive custody reconciliation, use the actual ordinary reset body
    # and real SessionStore. Notice/observer hooks have no bearing on custody.
    async def observer(*a,**kw):return None
    monkeypatch.setattr(runner,'_fire_session_reset_hooks',observer)
    monkeypatch.setattr(runner,'_reset_notice_session_info',lambda *a:'')
    monkeypatch.setattr(runner,'_telegram_topic_new_header',lambda *a:None)
    monkeypatch.setattr(runner,'_is_telegram_topic_lane',lambda *a:False)
    reply=asyncio.run(reset(runner,MessageEvent(text='/new',source=source)))
    assert 'pending' not in str(reply).lower()
    assert runner.session_store._entries[entry.session_key].session_id!=sid


def test_approved_endpoints_survive_actual_scoped_child_transfer(native_child,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    f=native_child;token=set_secret_scope({'FIRECRAWL_GATEWAY_URL':'https://approved-fire.invalid','PERPLEXITY_GATEWAY_URL':'https://approved-search.invalid'},profile_home=f.home)
    monkeypatch.setenv('FIRECRAWL_GATEWAY_URL','https://ambient.invalid')
    try:result=dispatch(f.call(),'web_search',{'query':'managed endpoint transfer'})
    finally:reset_secret_scope(token)
    assert result['success']
    row=next(r for r in f.rows() if r['kind']=='http')
    assert row['firecrawl_origin']=='https://approved-fire.invalid' and row['perplexity_origin']=='https://approved-search.invalid'
    assert all('FIRECRAWL_GATEWAY_URL' not in row['env'] for row in f.plans)


def test_native_process_stop_rpc_success_count_is_one_then_zero(native_child):
    from tui_gateway.methods_tools import _stop_processes
    f=native_child;c=f.call()
    with c.turn.lock:f.registry.spawn_web(c)
    result=_stop_processes({});assert result['status']=='QUIESCENT' and result['killed']==1
    assert c.session.web_settled and c.session.web_stop_requested
    result=_stop_processes({});assert result['status']=='QUIESCENT' and result['killed']==0


@pytest.mark.parametrize('surface',['rpc','cli'])
def test_native_operator_stop_during_actual_web_call_observes_cessation(native_child,surface,capsys):
    f=native_child;c=f.call();results=[];ctx=contextvars.copy_context()
    thread=threading.Thread(target=lambda:ctx.run(lambda:results.append(dispatch(c,'web_search',{'query':'headers-slow'}))))
    thread.start()
    try:
        until=time.monotonic()+6
        while time.monotonic()<until and not any(r['kind']=='http' for r in f.rows()):time.sleep(.01)
        assert any(r['kind']=='http' for r in f.rows())
        if surface=='rpc':
            from tui_gateway.methods_tools import _stop_processes
            receipt=_stop_processes({});assert receipt['status']=='QUIESCENT' and receipt['killed']==1
        else:
            from hermes_cli.cli_commands_mixin import CLICommandsMixin
            CLICommandsMixin._handle_stop_command(SimpleNamespace())
            assert 'unconfirmed' not in capsys.readouterr().out.lower()
        thread.join(timeout=4)
        assert not thread.is_alive() and c.stopped.is_set() and c.session.web_settled
        assert results and results[0].get('error')=='web_native_boundary_refused'
        assert all(r['namespace_init_exit_verified'] for r in f.receipts) and not f.registry._running
    finally:
        c.stop();thread.join(timeout=4)
        assert not thread.is_alive()


@pytest.mark.parametrize('owner',['named','default','missing'])
def test_gateway_retained_custody_resolves_native_owner_home(native_child,monkeypatch,owner):
    from gateway.run import GatewayRunner
    f=native_child;s=ProcessSession(id='retained',command='native web child',web_custody=True,cwd=str(f.home),session_key='route',parent_session_id='durable')
    f.registry._running[s.id]=s;seen=[]
    def settle(session,**kw):
        from hermes_constants import get_hermes_home
        seen.append(str(get_hermes_home()));return {'status':'STOP_UNCONFIRMED','session_id':session.id}
    monkeypatch.setattr(f.registry,'settle_web',settle)
    monkeypatch.setattr('agent.secret_scope.is_multiplex_active',lambda:True)
    store=SimpleNamespace(_entries={'route':SimpleNamespace(session_id='durable')},
                          _profile_home_for_key=lambda key:f.home if owner=='named' else None,
                          _named_profile_for_key=lambda key:None if owner=='default' else 'named',
                          _routing_home=f.home)
    runner=SimpleNamespace(config=SimpleNamespace(multiplex_profiles=True),session_store=store,
                           _peek_session_state=lambda key:None,_cached_agent_for=lambda key:None)
    receipt=asyncio.run(GatewayRunner._settle_session_web_custody(runner,'route'))
    assert receipt['status']=='STOP_UNCONFIRMED' and s.id in f.registry._running
    assert seen==([] if owner=='missing' else [str(f.home)])
    assert GatewayRunner._session_web_pending(runner,'route') is True
