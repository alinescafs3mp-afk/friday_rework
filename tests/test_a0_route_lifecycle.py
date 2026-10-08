"""Actual ordinary host/store/preparation/stop joins with explicit fake OS I/O.

No daemon, unit, Docker, namespace, network, model or real key is executed. File
publication, pinned code copies, locks, row identity and clocks are real. Native
systemd/guard/PID/cgroup observations are source controls, not live acceptance.
"""
import copy
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest
from test_a0_current_capability import route_fixture
from test_a0_host import configure_a0, launch_row
from test_host_native import setup, isolated, native, offline_boundary, ingress, invoke, CALL


def current(setup, row):
    return setup.host.store.get(row['existing_task_id'], row['owner'])


def preparation_fixture(setup, s, row, monkeypatch):
    st=route_fixture(setup,s,row,monkeypatch)
    m=s.module;l=st.launcher
    # The previous fixture deliberately models an externally prepared route.
    # Here only native I/O is fake; actual prepare_route publishes the request.
    st.request.unlink();st.guard.unlink()
    l['STATE']=st.request.parent/'state';l['STATE'].mkdir(mode=0o700)
    l['checked_unit_registration']=lambda:st.calls.append(['FAKE_REGISTERED_PINNED_UNIT_CHECK'])
    daemon_group=l['SERVICE_GROUP']
    native_pid=l['proc_identity'](77777)
    native_parent=l['proc_identity'](77776)
    native_pid['cgroup']=native_parent['cgroup']='0::'+daemon_group+'/dockerd'
    l['proc_identity']=lambda pid:copy.deepcopy(native_pid if pid==77777 else native_parent)
    st.active=False;st.network_exists=False;st.network_members={};st.started_at=0
    st.foreign=False;st.infinite=False;st.no_guard=False;st.unit_swapped=False
    st.after_start=None;st.after_create=None;st.before_probe=None;st.live_sample=False
    st.producer_error=None;st.native_deadline='5s';st.start_count=0;st.create_count=0
    st.inspect_count=0;st.daemon_stops=0;st.network_removals=0;st.owned_invocation='4'*32
    st.boundary_events=[]
    worker_type=__import__(s.hr.__package__+'.supervision',fromlist=['UnitObservation']).UnitObservation
    class WorkerSupervisor:
        def observe(self,binding):
            return worker_type(binding['supervisor']['unit'],'','inactive','dead','success',0,'',False,True)
    monkeypatch.setattr(m,'native_supervisor',lambda:WorkerSupervisor())
    monkeypatch.setattr(s.hr,'NativeSupervisor',lambda:WorkerSupervisor())

    def fields():
        return {'ActiveState':'active' if st.active or st.foreign else 'inactive',
                'InvocationID':('f'*32 if st.unit_swapped else st.owned_invocation) if st.start_count else '',
                'MainPID':'77776' if st.active or st.foreign else '0',
                'ControlGroup':daemon_group if st.active or st.foreign else '',
                'FragmentPath':str(l['ROOT']/'supervisor'/m.DAEMON), 'DropInPaths':'',
                'Restart':'no', 'KillMode':'control-group','SendSIGKILL':'yes', 'DelegateSubgroup':'dockerd',
                'MemoryMax':str(20*1024**3),'TasksMax':'2048','CPUQuotaPerSecUSec':'8s',
                'RuntimeMaxUSec':'infinity' if st.infinite else st.native_deadline,
                'TimeoutStartUSec':'1s','TimeoutStopUSec':'1s',
                'ActiveEnterTimestampMonotonic':str(st.started_at)}
    st.fields=fields
    original_native_call=l['native_call']
    def route_native_call(argv,*,data=None,fds=(),timeout=5):
        if argv[0]=='/usr/bin/systemctl':
            values=fields()
            return ''.join(k+'='+values[k]+'\n' for k in
                           ('InvocationID','MainPID','ControlGroup','DropInPaths','Restart'))
        return original_native_call(argv,data=data,fds=fds,timeout=timeout)
    l['native_call']=route_native_call
    def network():
        r=json.loads(st.request.read_text())
        return {'Id':st.network_id,'Name':'frw-a0-local-'+r['nonce'][:12], 'Driver':'bridge','Scope':'local',
                'EnableIPv6':False,'Internal':False,'Attachable':False,'Ingress':False,'ConfigOnly':False,
                'Labels':{'friday.rework.owner':r['owner'],'friday.rework.route':r['nonce']},
                'Options':{'com.docker.network.bridge.name':l['BRIDGE'],
                           'com.docker.network.bridge.enable_icc':'false'},'Containers':copy.deepcopy(st.network_members)}
    st.network=network
    def command(argv,timeout=10):
        assert 0<timeout<=20
        st.calls.append((list(argv),timeout))
        if argv[0]=='/usr/bin/systemctl':
            if argv[2]=='show':return ''.join(k+'='+v+'\n' for k,v in fields().items())
            if argv[2]=='start':
                r=current(setup,row)['host']['a0']['route']
                assert r['pending']=='daemon' and r['daemon_attempted'] and r['request_published']
                assert r['request_sha256']==hashlib.sha256(st.request.read_bytes()).hexdigest()
                assert r['daemon_limits']['runtime_seconds']==5
                st.active=True;st.start_count+=1;st.started_at=int(time.monotonic()*1e6)
                req=json.loads(st.request.read_text())
                st.context.update(request_sha256=hashlib.sha256(st.request.read_bytes()).hexdigest(),parent=native_parent)
                if not st.no_guard:
                    guard={'schema':'friday.a0.local-route-guard.v1','status':'GUARDED_BEFORE_DOCKERD',
                           'request':req,'context':st.context,'daemon':native_pid,
                           'namespaces':{'user':[1,21],'mnt':[1,22],'net':[1,23]},
                           'mappings':{'uid':[[0,1000,1],[1,100000,65536]],'gid':[[0,1000,1],[1,100000,65536]]},
                           'policy_sha256':req['policy_sha256']}
                    st.guard.write_text(json.dumps(guard));st.guard.chmod(0o600)
                if st.after_start:st.after_start()
                return ''
            assert argv[2]=='stop'
            st.daemon_stops+=1;st.active=False;return ''
        assert argv[:3]==[str(m.DOCKER),'--host',m.SOCKET]
        if argv[3]=='ps':return ''
        assert argv[3]=='network'
        if argv[4]=='ls':
            return '\n'.join(json.dumps({'Name':n,'Driver':d}) for n,d in [('bridge','bridge'),('host','host'),('none','null')])
        if argv[4]=='create':
            r=current(setup,row)['host']['a0']['route']
            assert r['pending']=='network' and r['network_attempted'] and r['daemon'] and r['samples']
            assert not st.network_exists
            assert argv[-1]=='frw-a0-local-'+r['request']['nonce'][:12]
            assert '--opt=com.docker.network.bridge.name='+l['BRIDGE'] in argv
            st.network_exists=True;st.create_count+=1
            if st.after_create:st.after_create()
            return st.network_id
        if argv[4]=='inspect':
            assert st.network_exists
            st.inspect_count+=1
            if st.before_probe:st.before_probe()
            return json.dumps([network()])
        if argv[4]=='rm':
            assert argv[5]==st.network_id and st.network_exists and not st.network_members
            st.network_removals+=1;st.network_exists=False;return st.network_id
        raise AssertionError(argv)
    monkeypatch.setattr(m.Runtime,'_command',staticmethod(command))
    init=m.Runtime.__init__
    def init_current(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs);runtime.runner=command
    monkeypatch.setattr(m.Runtime,'__init__',init_current)
    def sample(group):
        assert group==daemon_group
        return {'group':group,'populated':st.active,'processes':[
            {'pid':77777,'start_ticks':123,'state':'S'},{'pid':77776,'start_ticks':122,'state':'S'}] if st.active else []}
    def ceased(before):
        return {'confirmed':not st.active and not st.live_sample,'before':before,
                'survivors':before['processes'] if st.live_sample else [],'after':sample(daemon_group)}
    monkeypatch.setattr(m,'cgroup_snapshot',sample);monkeypatch.setattr(m,'cessation',ceased)
    # The copied stop source is actually read/compiled/checked before substituting
    # these same fake native OS boundaries in its otherwise real stop function.
    loader=s.hr.A0HostSession._route_module
    def stop_module(session):
        sm=loader(session)
        for key in ('DOCKER','SOCKET','PROJECT'):setattr(sm,key,getattr(m,key))
        sm.Runtime._command=staticmethod(command);sm.cgroup_snapshot=sample;sm.cessation=ceased
        def stop_launcher(route):
            p=Path(route['stop_launcher']['path'])
            assert hashlib.sha256(p.read_bytes()).hexdigest()==route['stop_launcher']['sha256']
            return l
        sm._route_launcher=stop_launcher
        return sm
    monkeypatch.setattr(s.hr.A0HostSession,'_route_module',stop_module)
    st.command=command
    return st


def ordinary(setup,s,monkeypatch,*,fault=None):
    original=s.hr.A0HostSession.produce_capability;states=[]
    def produce(session,row):
        if not states:
            st=preparation_fixture(setup,s,row,monkeypatch);states.append(st)
            if fault:fault(st,session,row)
        try:return original(session,row)
        except BaseException as error:
            states[0].producer_error=str(error);raise
    monkeypatch.setattr(s.hr.A0HostSession,'produce_capability',produce)
    monkeypatch.setattr(setup.host,'produce_a0_capability',s.host_producer)
    def schedule(coro,**kwargs):
        s.schedules.append(kwargs);coro.close()
    monkeypatch.setattr(setup.ctx,'schedule_gateway_work',schedule)
    return states


@pytest.mark.asyncio
async def test_actual_ordinary_preparation_precedes_current_probe_and_single_dispatch(setup,tmp_path,monkeypatch):
    proof=await ingress(setup,file=True);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    states=ordinary(setup,s,monkeypatch)
    answer=invoke(setup,proof,args=s.args)
    st=states[0]
    assert answer['accepted'],st.producer_error
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof));r=row['host']['a0']['route']
    assert r['network']['id']==st.network_id and r['pending'] is None
    assert r['association']==s.session.identity and r['acceptance']==row['host']['a0']['acceptance']
    assert r['request']['host']['boot_id']==r['acceptance']['boot_id']
    assert len(s.schedules)==st.start_count==st.create_count==1 and not s.posts
    assert row['host']['a0']['launch'] is None and row['host']['a0']['key_cleanup']=='NOT_PREPARED'
    invoke(setup,proof,args=s.args)
    with pytest.raises(Exception):s.host_producer(row['existing_task_id'],row['owner'])
    assert len(s.schedules)==st.start_count==st.create_count==1
    assert current(setup,row)['stop_intent'] is None
    assert current(setup,row)['host']['a0']['route']['settlement'] is None
    assert st.daemon_stops==st.network_removals==0 and st.active and st.network_exists
    stopped=setup.host._stop(row,'pause')
    assert stopped['stop_intent']=='pause' and stopped['host']['quiescence']['kind']=='a0_route'
    assert stopped['host']['terminal']['state']=='stopped'
    assert st.daemon_stops==st.network_removals==1 and not st.active and not st.network_exists
    assert not st.request.exists() and not st.guard.exists()
    assert current(setup,row)['host']['a0']['acceptance']==r['acceptance']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['infinite','active','old_request','old_guard','old_namespace','wrong_deadline'])
async def test_native_precontainer_admission_refuses_before_any_effect(setup,tmp_path,monkeypatch,fault):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    def damage(st,session,row):
        if fault=='infinite':st.infinite=True
        elif fault=='active':st.foreign=True
        elif fault=='wrong_deadline':st.native_deadline='120s'
        elif fault=='old_namespace':
            p=st.launcher['STATE']/'rootlesskit/child_pid';p.parent.mkdir();p.write_text('OLD DO NOT ADOPT')
        else:(st.request if fault=='old_request' else st.guard).write_text('OLD DO NOT ADOPT')
    states=ordinary(setup,s,monkeypatch,fault=damage)
    answer=invoke(setup,proof,args=s.args);st=states[0]
    assert not answer['accepted'] and not st.start_count and not st.create_count and not s.schedules and not s.posts
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['a0']['route'] is None and row['host']['a0']['capability'] is None
    if fault in ('infinite','wrong_deadline'):assert st.producer_error=='a0_route_native_deadline_unavailable'
    invoke(setup,proof,args=s.args)
    assert not st.start_count and not st.create_count


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['daemon_ack','bridge_ack','proof_write','schedule_ack'])
async def test_partial_route_failure_cleans_owned_resources_without_replay(setup,tmp_path,monkeypatch,phase):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    def damage(st,session,row):
        def lost():raise s.module.RuntimeErrorBoundary('EXPLICIT_NATIVE_ACK_LOST')
        if phase=='daemon_ack':st.after_start=lost
        elif phase=='bridge_ack':st.after_create=lost
        elif phase=='proof_write':
            write=s.module.write_json
            def fail(path,*args,**kwargs):
                if path.name=='a0-current-route.json':raise OSError('EXPLICIT_PROOF_WRITE_FAILED')
                return write(path,*args,**kwargs)
            monkeypatch.setattr(s.module,'write_json',fail)
        else:
            def fail(coro,**kwargs):coro.close();s.schedules.append(kwargs);raise RuntimeError('EXPLICIT_SCHEDULE_ACK_LOST')
            monkeypatch.setattr(setup.ctx,'schedule_gateway_work',fail)
    states=ordinary(setup,s,monkeypatch,fault=damage)
    answer=invoke(setup,proof,args=s.args);st=states[0]
    assert not answer['accepted'],st.producer_error
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['stop_intent']=='cancel' and row['host']['quiescence']['kind']=='a0_route',row
    assert row['host']['a0']['route']['settlement']['status']=='STOP_CONFIRMED'
    assert not st.active and not st.network_exists and not s.posts
    starts,creates=st.start_count,st.create_count
    invoke(setup,proof,args=s.args)
    assert (st.start_count,st.create_count)==(starts,creates)
    assert current(setup,row)['host']['a0']['acceptance']==row['host']['a0']['acceptance']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['no_guard','foreign_invocation','foreign_member','incomplete_sample','survivor'])
async def test_unknown_custody_cannot_be_never_submitted_or_release_capacity(setup,tmp_path,monkeypatch,fault):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    def damage(st,session,row):
        if fault=='no_guard':st.no_guard=True
        elif fault=='foreign_invocation':
            st.after_create=lambda:setattr(st,'unit_swapped',True)
        elif fault=='foreign_member':st.network_members={'f'*64:{'EndpointID':'1'*64}}
        elif fault=='incomplete_sample':
            sample=s.module.cgroup_snapshot;calls=[0]
            def interrupted(group):
                calls[0]+=1
                if calls[0]==3:raise OSError('EXPLICIT_INTERRUPTED_SAMPLE')
                return sample(group)
            monkeypatch.setattr(s.module,'cgroup_snapshot',interrupted)
        else:
            st.live_sample=True
            st.after_create=lambda:(_ for _ in ()).throw(RuntimeError('EXPLICIT_POST_CREATE_FAILURE'))
    states=ordinary(setup,s,monkeypatch,fault=damage)
    answer=invoke(setup,proof,args=s.args);st=states[0]
    assert not answer['accepted']
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['a0']['route'] is not None and row['stop_intent']=='cancel'
    assert row['host']['quiescence'] is None and row['host']['terminal'] is None
    assert row['host']['a0']['route']['settlement'] is None
    if fault in ('foreign_member','foreign_invocation','no_guard'):assert st.daemon_stops==0
    before=st.start_count,st.create_count
    invoke(setup,proof,args=s.args)
    assert (st.start_count,st.create_count)==before
    from test_a0_host_recovery import second_claim
    with pytest.raises(Exception,match='worker_capacity_reserved'):second_claim(setup,s,row)


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['start','create','probe'])
async def test_original_stop_during_precontainer_io_settles_without_dispatch(setup,tmp_path,monkeypatch,boundary):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    def damage(st,session,row):
        def stop():setup.host.store.request_stop(row['existing_task_id'],row['owner'],'pause')
        setattr(st,{'start':'after_start','create':'after_create','probe':'before_probe'}[boundary],stop)
    states=ordinary(setup,s,monkeypatch,fault=damage)
    answer=invoke(setup,proof,args=s.args);st=states[0]
    assert not answer['accepted'] and not s.schedules and not s.posts
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['stop_intent']=='pause' and row['host']['quiescence']['kind']=='a0_route',row
    assert not st.active and not st.network_exists


@pytest.mark.asyncio
@pytest.mark.parametrize('expired',['wall','mono','source'])
async def test_restart_stop_uses_recorded_ownership_after_work_expiry_or_launch_drift(setup,tmp_path,monkeypatch,expired):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    states=ordinary(setup,s,monkeypatch);answer=invoke(setup,proof,args=s.args)
    assert answer['accepted'],states[0].producer_error
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof));r=copy.deepcopy(row['host']['a0']['route'])
    setup.host._a0_controllers.clear();setup.host._a0_admissions.clear()
    if expired=='wall':setup.host.store.clock=lambda:row['deadline_unix']+1
    elif expired=='mono':monkeypatch.setattr(time,'monotonic_ns',lambda:r['acceptance']['accepted_monotonic_ns']+61_000_000_000)
    else:
        for key in ('runtime','launcher','policy'):
            p=Path(s.runtime['a0'][key]['path'])
            if key=='runtime':continue # source checkout must stay immutable during gate
            p.write_bytes(p.read_bytes()+b'\nLAUNCH-ONLY-DRIFT\n')
        monkeypatch.setattr(s.hr.A0HostSession,'_module',lambda *args:(_ for _ in ()).throw(AssertionError('launch module reopened')))
    result=setup.host._reconcile(row)
    assert result['host']['quiescence']['kind']=='a0_route' and result['stop_intent']=='cancel'
    assert result['host']['a0']['acceptance']==r['acceptance']
    assert not states[0].active and states[0].start_count==states[0].create_count==1 and not s.posts
    with pytest.raises(Exception):setup.host.produce_a0_capability(row['existing_task_id'],row['owner'])


@pytest.mark.asyncio
async def test_retained_route_immutables_and_cessation_validator_refuse_fabrication(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    states=ordinary(setup,s,monkeypatch);answer=invoke(setup,proof,args=s.args)
    assert answer['accepted'],states[0].producer_error
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof));r=row['host']['a0']['route']
    for field in ('nonce','accepted_monotonic_ns','owner'):
        bad=copy.deepcopy(r);bad['request'][field]='f'*32
        with pytest.raises(Exception):setup.host.store.retain_a0_route(row['existing_task_id'],row['owner'],bad)
    bad=copy.deepcopy(row);bad['stop_intent']='cancel'
    bad['host']['quiescence']={'kind':'never_submitted','observation':None,'at_unix':time.time()}
    with pytest.raises(Exception):setup.record.validate_host_record(bad)
    bad=copy.deepcopy(row);del bad['host']['a0']['route']
    with pytest.raises(Exception):setup.record.validate_host_record(bad)
    result=setup.host._stop(row,'cancel')
    bad=copy.deepcopy(result);bad['host']['a0']['route']['settlement']=None
    with pytest.raises(Exception):setup.record.validate_host_record(bad)
