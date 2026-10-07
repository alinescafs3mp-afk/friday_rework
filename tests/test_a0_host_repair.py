"""Causal attachment and finite startup controls. Native interfaces are fake;
actual host/store/runtime/boundary code and original clocks/cleanup are exercised.
Nothing here grants production or worker-web/admin acceptance.
"""
import copy,json,time,base64,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_a0_host import configure_a0,launch_row,scoped_start
from test_host_native import setup,isolated,native,offline_boundary,ingress,invoke,pin


def attached(setup,row,p):
    try:return setup.host.attach_a0_capability(row['existing_task_id'],row['owner'],p)
    except RuntimeError as e:
        assert str(e)=='gateway_offline'
        return None


def advance(setup,row,monkeypatch,step=1):
    a=row['host']['a0']['acceptance'];ticks=[a['accepted_monotonic_ns']]
    setup.host.store.clock=lambda:a['accepted_unix']+(ticks[0]-a['accepted_monotonic_ns'])/1e9
    monkeypatch.setattr(time,'monotonic_ns',lambda:ticks[0])
    monkeypatch.setattr(time,'monotonic',lambda:ticks[0]/1e9)
    def sleep(seconds):ticks[0]+=int(max(seconds,step)*1e9)
    monkeypatch.setattr(time,'sleep',sleep)
    return ticks


@pytest.mark.asyncio
async def test_real_advancing_clock_reservation_then_exact_attachment(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch)
    early=time.monotonic_ns();row=launch_row(setup,s,proof,attach=False)
    assert row['host']['a0']['acceptance']['accepted_monotonic_ns']>early
    assert row['host']['a0']['capability'] is None and not s.schedules and not s.calls
    config=copy.deepcopy(s.runtime);p=s.produce(row);attached(setup,row,p)
    current=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert current['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    assert current['host']['a0']['capability']==p and current['host']['binding']['runtime']==config
    assert setup.ctx.get_config('runtime')==config and len(s.schedules)==1
    result=scoped_start(setup,current)
    assert result['host']['terminal']['state']=='completed' and len(s.posts)==2
    assert result['host']['a0']['acceptance']==row['host']['a0']['acceptance']


@pytest.mark.asyncio
async def test_concurrent_duplicate_attachment_and_lost_schedule_never_redispatch(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof,attach=False)
    p=s.produce(row)
    # Run in current copied scopes; the metadata one-shot decides scheduling.
    from contextvars import copy_context
    contexts=[copy_context(),copy_context()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=[pool.submit(contexts[i].run,attached,setup,row,p) for i in range(2)]
        [v.result(timeout=4) for v in values]
    assert len(s.schedules)==1 and not s.calls and not s.posts
    attached(setup,row,p);assert len(s.schedules)==1
    duplicate=invoke(setup,proof,args=s.args)
    assert duplicate['reference']==row['existing_task_id'] and len(s.schedules)==1
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    changed=tmp_path/'foreign-capability';changed.write_text(s.capability.read_text()+'\n')
    with pytest.raises(Exception):attached(setup,row,pin(changed))
    assert len(s.schedules)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['stop','wall_expired','mono_expired','restart','restart_status','foreign','disabled'])
async def test_attachment_fails_closed_on_current_ownership_or_original_budget(setup,tmp_path,monkeypatch,mode):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof,attach=False);p=s.produce(row)
    host=setup.host;owner=row['owner']
    if mode=='stop':host.store.request_stop(row['existing_task_id'],owner,'cancel')
    elif mode=='wall_expired':host.store.clock=lambda:row['deadline_unix']
    elif mode=='mono_expired':monkeypatch.setattr(time,'monotonic_ns',lambda:row['host']['a0']['acceptance']['accepted_monotonic_ns']+60_000_000_000)
    elif mode.startswith('restart'):
        host=setup.module.WorkerHost(setup.ctx,setup.host.admission)
        if mode=='restart_status':host._remember(host.store.get(row['existing_task_id'],owner))
    elif mode=='foreign':owner={**owner,'user_id':'foreign'}
    else:host._closed=True
    with pytest.raises(Exception):host.attach_a0_capability(row['existing_task_id'],owner,p)
    retained=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert retained['host']['a0']['capability'] is None
    assert retained['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    assert not s.schedules and not s.calls and not s.posts


@pytest.mark.asyncio
async def test_attachment_persisted_then_write_ack_loss_is_not_retried(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof,attach=False);p=s.produce(row)
    original=setup.host.store._save
    def save(data):
        original(data)
        if data['jobs'][row['existing_task_id']]['host']['a0']['capability'] is not None:raise OSError('INJECTED_ACK_LOSS')
    monkeypatch.setattr(setup.host.store,'_save',save)
    with pytest.raises(OSError,match='ACK_LOSS'):attached(setup,row,p)
    attached(setup,row,p)
    assert not s.schedules and not s.calls and not s.posts
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['a0']['capability']==p


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['config_pin','old_receipt','old_row'])
async def test_old_preclaim_schema_is_explicitly_invalid_without_migration(setup,tmp_path,monkeypatch,mode):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch)
    if mode=='config_pin':
        bad=copy.deepcopy(s.runtime);bad['a0']['capability']=pin(s.evidence)
        with pytest.raises(Exception):s.hr.validate_a0_runtime(bad)
    elif mode=='old_receipt':
        receipt=Path(s.runtime['runtime_receipt']['path']);v=json.loads(receipt.read_text());v['schema']='friday-rework.a0-runtime.v1';v['capability_sha256']='0'*64
        receipt.write_text(json.dumps(v));bad=copy.deepcopy(s.runtime);bad['runtime_receipt']=pin(receipt)
        with pytest.raises(Exception):s.hr.check_a0_runtime(bad,setup.host.store)
    else:
        row=launch_row(setup,s,proof,attach=False);bad=copy.deepcopy(row);bad['host']['a0']['schema']='friday.a0.host.v1';bad['host']['a0'].pop('capability')
        with pytest.raises(Exception):setup.record.validate_host_record(bad)
    assert not s.calls and not s.posts


@pytest.mark.asyncio
async def test_delayed_container_and_api_ready_before_one_bootstrap(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    ticks=advance(setup,row,monkeypatch);init=s.module.Runtime.__init__;seen=[];health=[]
    def wrapped(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs);original=runtime.runner
        def command(argv,timeout):
            reply=original(argv,timeout)
            if argv[0]=='/usr/bin/systemd-run':s.obj['State'].update(Running=False,Pid=0)
            if 'inspect' in argv and s.unit_started:
                seen.append(ticks[0])
                if len(seen)<3:s.obj['State'].update(Running=False,Pid=0)
                else:s.obj['State'].update(Running=True,Pid=777777)
                reply=json.dumps([s.obj])
            return reply
        runtime.runner=command
    monkeypatch.setattr(s.module.Runtime,'__init__',wrapped)
    def ready(boundary,current,timeout):
        boundary._keys();boundary.admit(current);health.append(ticks[0]);return len(health)>=3
    monkeypatch.setattr(s.native.A0NativeBoundary,'readiness',ready)
    result=scoped_start(setup,row)
    assert len(seen)>=3 and len(health)==3 and health[-1]>health[0]
    assert len(s.posts)==2 and sum('create' in v for v in s.calls)==1 and sum(v[0]=='/usr/bin/systemd-run' for v in s.calls)==1
    assert result['host']['terminal']['state']=='completed' and result['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    assert result['host']['quiescence']['kind']=='a0'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['never_ready','cancel','keys','route','parent','stop_error'])
async def test_api_startup_uncertainty_stops_without_bootstrap_or_replay(setup,tmp_path,monkeypatch,mode):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    ticks=advance(setup,row,monkeypatch,step=5);seen=[]
    def ready(boundary,current,timeout):
        boundary._keys();boundary.admit(current);seen.append(ticks[0])
        if mode=='cancel':setup.host.store.request_stop(row['existing_task_id'],row['owner'],'cancel')
        elif mode=='keys':
            with boundary.key_material.path.open('a') as f:f.write('API_KEY_OPENAI=changed-fixture\n')
        elif mode=='route':
            def reject(*args,**kwargs):raise RuntimeError('FAKE_ROUTE_DRIFT')
            monkeypatch.setattr(s.module.Runtime,'check_network',reject)
        elif mode=='parent':raise KeyboardInterrupt('FAKE_PARENT_ERROR')
        elif mode=='stop_error':s.cleanup_uncertain=True;raise RuntimeError('FAKE_PARENT_ERROR')
        return False
    monkeypatch.setattr(s.native.A0NativeBoundary,'readiness',ready)
    with pytest.raises(BaseException):scoped_start(setup,row)
    assert seen and not s.posts and sum('create' in v for v in s.calls)==1
    assert any(v[0]=='FAKE_UNIT_STOP' for v in s.calls)
    retained=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert retained['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    if mode=='stop_error':
        assert not s.session.native_cessation and retained['host']['quiescence'] is None
    else:assert not s.running and s.session.native_cessation
    # Duplicate tool/status never restarts the one-shot association.
    before=list(s.calls);invoke(setup,proof,args=s.args);assert s.calls==before


@pytest.mark.asyncio
async def test_retained_descendant_check_cannot_be_erased_by_empty_stop_receipt(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    init=s.module.Runtime.__init__
    monkeypatch.setattr(s.module,'cessation',lambda sample:{'confirmed':False,'classification':'FAKE_PRIOR_DESCENDANT_ALIVE'})
    def wrapped(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs);original=runtime.runner
        def command(argv,timeout):
            if argv[-1]=='--property=ActiveState,InvocationID':
                s.running=False;s.obj['State'].update(Running=False,Pid=0);raise RuntimeError('AFTER_SAMPLE')
            return original(argv,timeout)
        runtime.runner=command
    monkeypatch.setattr(s.module.Runtime,'__init__',wrapped)
    with pytest.raises(Exception):scoped_start(setup,row)
    assert s.session.retained_samples
    monkeypatch.setattr(s.module.Runtime,'stop',lambda self:{'status':'STOP_CONFIRMED','container_id':s.session.created['container_id'],
        'current_sampling':'OBSERVED_OR_ALREADY_EXITED','descendant_checks':[]})
    with pytest.raises(Exception,match='STOP_UNCONFIRMED'):setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['quiescence'] is None
    assert s.session.key_cleanup=='PREPARED'


@pytest.mark.parametrize('body',[{'ok':True,'ready':False}, {'ok':True,'body':base64.b64encode(b'{"gitinfo":{"branch":"fixture"},"error":null}').decode()}])
def test_actual_readiness_parser_only_accepts_checked_get_body(body):
    # Real method, fake _exec only; no native call or key prepared.
    import importlib.util,sys
    import test_a0_adapter as source
    an=__import__('importlib').import_module('friday_a0_test.adapters.a0_native')
    from types import SimpleNamespace
    calls=[]
    class Boundary:
        def _keys(self):return SimpleNamespace(admitted=lambda:{'API_KEY_OPENAI':'fixture','API_KEY_OTHER':'fixture'})
        def _exec(self,row,script,payload,timeout):calls.append((script,payload));return json.dumps(body).encode()
    assert an.A0NativeBoundary.readiness(Boundary(),{},3) is ('body' in body)
    assert calls[0][1]['method']=='GET' and calls[0][1]['path']=='/api/health'
    compile(an.READINESS_SCRIPT,'fixed-readiness','exec')


@pytest.mark.asyncio
async def test_initial_sample_survives_into_grant_stop_pid_start_checks(setup,tmp_path,monkeypatch):
    """Fake container sample uses this disposable TEST PROCESS as a live start
    identity. Source only observes it; no signal or native kill is performed."""
    import os
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    start=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
    def sample(runtime,obj):return {'group':'/user.slice/offline/docker-'+obj['Id']+'.scope','populated':True,
                                   'processes':[{'pid':os.getpid(),'start_ticks':start}]}
    monkeypatch.setattr(s.module.Runtime,'snapshot_container',sample)
    with pytest.raises(Exception):scoped_start(setup,row)
    assert s.session.boundary.samples and s.session.retained_samples
    assert any((os.getpid(),start) in values for root,values in s.session.boundary.samples)
    assert not s.session.native_cessation and s.session.key_cleanup=='PREPARED'
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['quiescence'] is None


@pytest.mark.parametrize('body',[{}, {'ok':1,'ready':0}, {'ok':True}, {'ok':True,'ready':True}, {'ok':False},
    {'ok':True,'body':base64.b64encode(b'{"gitinfo":null,"error":null}').decode()},
    {'ok':True,'body':base64.b64encode(b'{"gitinfo":{},"error":"error"}').decode()},
    {'ok':True,'body':base64.b64encode(b'{"gitinfo":{},"gitinfo":{},"error":null}').decode()}])
def test_actual_readiness_parser_refuses_unknown_or_invalid_health(body):
    import importlib,test_a0_adapter
    from types import SimpleNamespace
    an=importlib.import_module('friday_a0_test.adapters.a0_native')
    class Boundary:
        def _keys(self):return SimpleNamespace(admitted=lambda:{'API_KEY_OPENAI':'fixture','API_KEY_OTHER':'fixture'})
        def _exec(self,*args):return json.dumps(body).encode()
    with pytest.raises(Exception):an.A0NativeBoundary.readiness(Boundary(),{},3)


@pytest.mark.asyncio
async def test_pending_container_is_finite_and_stop_remains_available_after_startup_budget(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    ticks=advance(setup,row,monkeypatch,step=5);init=s.module.Runtime.__init__
    def wrapped(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs);original=runtime.runner
        def command(argv,timeout):
            result=original(argv,timeout)
            if argv[0]=='/usr/bin/systemd-run':s.obj['State'].update(Running=False,Pid=0)
            return json.dumps([s.obj]) if 'inspect' in argv else result
        runtime.runner=command
    monkeypatch.setattr(s.module.Runtime,'__init__',wrapped)
    with pytest.raises(Exception,match='original_budget_exhausted'):scoped_start(setup,row)
    assert not s.posts and sum('create' in v for v in s.calls)==1
    assert any(v[0]=='FAKE_UNIT_STOP' for v in s.calls)
    # The fake CLI unit is deliberately still active: don't invent cessation.
    assert not s.session.native_cessation and s.session.key_cleanup=='PREPARED'
    retained=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert retained['host']['quiescence'] is None and retained['host']['a0']['acceptance']==row['host']['a0']['acceptance']


@pytest.mark.asyncio
async def test_readiness_native_api_and_unit_timeouts_use_original_stop_reserve(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    ticks=advance(setup,row,monkeypatch,step=1);seen=[];init=s.module.Runtime.__init__
    def wrapped(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs)
        runtime.supervisor._command=lambda args,timeout:seen.append(('unit',timeout))
    monkeypatch.setattr(s.module.Runtime,'__init__',wrapped)
    original_run=s.native.A0NativeBoundary._run
    def run(argv,data,timeout):
        if argv==['EXPLICIT_FAKE_NO_NATIVE_COMMAND']:return seen.append(('api',timeout))
        return original_run(argv,data,timeout)
    monkeypatch.setattr(s.native.A0NativeBoundary,'_run',staticmethod(run))
    def ready(boundary,current,timeout):
        ticks[0]+=10_000_000_000
        boundary.runner(['EXPLICIT_FAKE_NO_NATIVE_COMMAND'],None,999)
        boundary.supervisor._command(['EXPLICIT_FAKE_NO_UNIT_QUERY'],999)
        assert seen==[('api',25),('unit',25)]
        # Owned stop MUST remain usable after allowance is exhausted.
        return True
    monkeypatch.setattr(s.native.A0NativeBoundary,'readiness',ready)
    result=scoped_start(setup,row)
    assert result['host']['terminal']['state']=='completed' and len(s.posts)==2
    assert result['host']['a0']['acceptance']==row['host']['a0']['acceptance']
