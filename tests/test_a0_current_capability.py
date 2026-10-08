"""Ordinary host producer with real validators and explicit fake native I/O.

No native service, namespace, Docker, key or model effect is run. The fixtures
publish synthetic post-reservation route inputs; production preparation remains
an unmet dependency and is deliberately not implemented by these controls.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest
from test_a0_host import configure_a0, launch_row, scoped_start
from test_host_native import setup, isolated, native, offline_boundary, ingress, invoke, CALL


def route_fixture(setup, s, row, monkeypatch):
    m = s.module
    # Exercise the exact pinned loader first, then substitute OS observations in
    # that loaded namespace. The production loader itself is never bypassed by
    # input configuration or a runtime hook.
    loader = m.checked_launcher
    l = loader(s.runtime['a0']['launcher']['sha256'])
    root = Path(s.runtime['a0']['launcher']['path']).parent
    req = root/'local-route.json'; guard = root/'route-guard.json'
    tools = {}
    for name in ('dockerd', 'rootlesskit', 'slirp4netns', 'nft', 'nsenter'):
        p = root/(name+'.FAKE');p.write_text('NEVER EXECUTED\n'+name);p.chmod(0o700);tools[name] = p
    l.update(ROOT=root, REQUEST=req, GUARD=guard)
    l['tool_paths'] = lambda: tools
    actual_path = l['Path']
    proc = root/'fake-proc';proc.mkdir()
    daemon = {'pid':77777, 'start':'123', 'ppid':77776, 'cgroup':l['SERVICE_GROUP'], 'boot':row['host']['a0']['acceptance']['boot_id']}
    parent = {**daemon, 'pid':77776, 'start':'122', 'ppid':11111}
    (proc/str(daemon['pid'])).mkdir()
    (proc/str(daemon['pid'])/'exe').symlink_to(tools['dockerd'])
    def fake_path(*parts):
        return proc.joinpath(*parts[1:]) if parts[:1] == ('/proc',) else actual_path(*parts)
    l['Path'] = fake_path
    l['proc_identity'] = lambda pid: copy.deepcopy(daemon if pid == daemon['pid'] else parent)
    namespaces = {'user':[1,21], 'mnt':[1,22], 'net':[1,23]}
    state = NS(calls=[], opens=0, drift=False, bad_policy=False, members={}, after_inspect=None,
               row=copy.deepcopy(row), request=req, guard=guard, launcher=l, network_id='8'*64)
    @contextmanager
    def held(pid):
        assert pid == daemon['pid']
        state.opens += 1
        current = copy.deepcopy(namespaces)
        if state.drift and state.opens % 2 == 0:current['net'] = [1,999]
        yield current, {'user':101, 'mnt':102, 'net':103}
    l['namespaces'] = held
    a = row['host']['a0']['acceptance']
    request = {'schema':'friday.a0.local-route-request.v1', 'owner':'sol:'+row['existing_task_id']+'#1',
               'nonce':'9'*32, 'accepted_unix':a['accepted_unix'], 'deadline_unix':row['deadline_unix'],
               'original_budget_seconds':row['budget_seconds'], 'accepted_monotonic_ns':a['accepted_monotonic_ns'],
               'launcher_sha256':s.runtime['a0']['launcher']['sha256'], 'policy_sha256':l['policy_hash'](),
               'tools':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in tools.items()}, 'endpoints':m.LOCAL_ENDPOINTS}
    req.write_text(json.dumps(request));req.chmod(0o600)
    ctx = {'request_sha256':hashlib.sha256(req.read_bytes()).hexdigest(), 'invocation_id':'4'*32,
           'parent_pid':parent['pid'], 'parent':parent,
           'host_namespaces':{'user':[2,21],'mnt':[2,22],'net':[2,23]}}
    state.context = ctx
    g = {'schema':'friday.a0.local-route-guard.v1','status':'GUARDED_BEFORE_DOCKERD',
         'request':request,'policy_sha256':request['policy_sha256'],'context':ctx,'daemon':daemon,'namespaces':namespaces}
    guard.write_text(json.dumps(g));guard.chmod(0o600)
    def readback():
        entries = [{'table':{'family':'inet','name':'frw_a0_local'}}]
        for chain, rules in l['expected_rules']().items():
            entries.append({'chain':{'family':'inet','table':'frw_a0_local','name':chain,'type':'filter',
                                    'hook':chain,'prio':-10,'policy':'accept' if state.bad_policy else 'drop'}})
            for expressions in rules:
                expressions = copy.deepcopy(expressions)
                for expr in expressions:
                    if 'counter' in expr:expr['counter']={'packets':0,'bytes':0}
                entries.append({'rule':{'family':'inet','table':'frw_a0_local','chain':chain,'expr':expressions}})
        return json.dumps({'nftables':entries})
    def native_call(argv, *, data=None, fds=(), timeout=5):
        assert data is None and 0 < timeout <= 5
        state.calls.append((list(argv),timeout))
        if argv[0] == '/usr/bin/systemctl':
            assert argv == ['/usr/bin/systemctl','--user','show','friday-rework-docker.service',
                            '--property=InvocationID,MainPID,ControlGroup,DropInPaths,Restart']
            return 'InvocationID='+ctx['invocation_id']+'\nMainPID='+str(parent['pid'])+'\nControlGroup='+l['SERVICE_GROUP']+'\nDropInPaths=\nRestart=no\n'
        assert argv[0] == str(l['NSENTER']) and fds == (101,102,103)
        assert argv[-7:] == [str(l['NFT']),'--json','--numeric-priority','list','table','inet','frw_a0_local']
        return readback()
    l['native_call'] = native_call
    def checked(sha):
        # Still verify exact bytes on every production loader call.
        loader(sha)
        return l
    monkeypatch.setattr(m, 'checked_launcher', checked)
    def network_command(argv, timeout):
        state.calls.append((list(argv),timeout))
        assert argv[:5] == [str(m.DOCKER),'--host',m.SOCKET,'network','inspect']
        assert argv[5] in ('frw-a0-local-'+'9'*12, state.network_id) and 0 < timeout <= 10
        obj = {'Id':state.network_id,'Name':'frw-a0-local-'+'9'*12,'Driver':'bridge','Scope':'local',
               'EnableIPv6':False,'Internal':False,'Attachable':False,'Ingress':False,'ConfigOnly':False,
               'Labels':{'friday.rework.owner':request['owner'],'friday.rework.route':request['nonce']},
               'Options':{'com.docker.network.bridge.name':'br-frwa0local','com.docker.network.bridge.enable_icc':'false'},
               'Containers':copy.deepcopy(state.members)}
        if state.after_inspect:state.after_inspect()
        return json.dumps([obj])
    monkeypatch.setattr(m.Runtime, '_command', staticmethod(network_command))
    init = m.Runtime.__init__
    def checked_init(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs)
        prior = runtime.runner
        runtime.runner = lambda argv,timeout: network_command(argv,timeout) if argv[3:5] == ['network','inspect'] else prior(argv,timeout)
    monkeypatch.setattr(m.Runtime,'__init__',checked_init)
    monkeypatch.setattr(m.Runtime,'check_network',s.real_check_network)
    return state


def automatic(setup, s, monkeypatch, *, fault=None):
    """Synthetic native preparation only after the actual reservation exists."""
    original = s.hr.A0HostSession.produce_capability
    # This module isolates the unchanged observation/attachment consumer.
    # The actual preparation/ownership native I/O is exercised separately by
    # test_a0_route_lifecycle, not fabricated as production readiness here.
    monkeypatch.setattr(s.module,'prepare_route',lambda *args,**kwargs:None)
    states = []
    def produce(session,row):
        if not states:
            state = route_fixture(setup,s,row,monkeypatch);states.append(state)
            if fault:fault(state)
        try:
            return original(session,row)
        except Exception as error:
            if states:states[0].error = repr(error)
            raise
    monkeypatch.setattr(s.hr.A0HostSession,'produce_capability',produce)
    monkeypatch.setattr(setup.host,'produce_a0_capability',s.host_producer)
    # Actual scheduling API's behavior is a fixture: retain the same coroutine,
    # close it instead of executing native work. Other tests run the real _start.
    def schedule(coro,**kwargs):
        assert coro.cr_code == setup.host._run.__code__
        s.schedules.append(kwargs);coro.close()
    monkeypatch.setattr(setup.ctx,'schedule_gateway_work',schedule)
    return states


@pytest.mark.asyncio
async def test_ordinary_host_current_producer_attaches_and_schedules_once(setup,tmp_path,monkeypatch):
    proof = await ingress(setup,file=True)
    s = configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    states = automatic(setup,s,monkeypatch)
    answer = invoke(setup,proof,args=s.args)
    assert answer['accepted'] and len(states)==1 and len(s.schedules)==1, [getattr(st,'error',None) for st in states]
    row = setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['a0']['acceptance']==states[0].row['host']['a0']['acceptance']
    assert row['host']['inputs'] and not s.posts and not s.calls
    capability=json.loads(Path(row['host']['a0']['capability']['path']).read_text())
    assert capability['association']==s.hr.A0HostSession(s.runtime,setup.host.store,row).identity
    assert capability['network']['id']==states[0].network_id
    assert states[0].opens >= 6
    assert all(0 < timeout <= 5 for _,timeout in states[0].calls)
    assert s.schedules[0]['name']=='friday:'+row['existing_task_id']
    assert invoke(setup,proof,args=s.args)['reference']==answer['reference']
    assert len(states)==len(s.schedules)==1
    # Direct operator entry cannot rerun the producer; same attachment is also
    # incapable of redispatching even if the original scheduler ACK was lost.
    with pytest.raises(Exception):s.host_producer(row['existing_task_id'],row['owner'])
    setup.host.attach_a0_capability(row['existing_task_id'],row['owner'],row['host']['a0']['capability'])
    assert len(s.schedules)==1
    finished=scoped_start(setup,row)
    assert finished['host']['terminal']['state']=='completed'
    assert finished['host']['quiescence']['kind']=='a0' and len(s.posts)==2 and not s.running
    assert finished['host']['a0']['acceptance']==row['host']['a0']['acceptance']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['namespace','policy','member','clock','missing','late_namespace','daemon_drift','launcher_drift','stop'])
async def test_current_native_unknown_never_attaches_or_dispatches(setup,tmp_path,monkeypatch,fault):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    def damage(st):
        if fault=='namespace':st.drift=True
        elif fault=='policy':st.bad_policy=True
        elif fault=='member':st.members={'f'*64:{'EndpointID':'1'*64}}
        elif fault=='missing':st.request.unlink()
        elif fault=='late_namespace':st.after_inspect=lambda:setattr(st,'drift',True)
        elif fault=='daemon_drift':st.after_inspect=lambda:st.context.update(invocation_id='f'*32)
        elif fault=='launcher_drift':
            def change_launcher():
                p=Path(s.runtime['a0']['launcher']['path']);p.write_bytes(p.read_bytes()+b'\n# changed\n')
            st.after_inspect=change_launcher
        elif fault=='stop':st.after_inspect=lambda:setup.host.store.request_stop(st.row['existing_task_id'],st.row['owner'],'cancel')
        else:
            v=json.loads(st.request.read_text());v['accepted_monotonic_ns']-=1;st.request.write_text(json.dumps(v))
    states=automatic(setup,s,monkeypatch,fault=damage)
    answer=invoke(setup,proof,args=s.args)
    assert answer['accepted'] is False and len(states)==1
    errors={'namespace':'guard_namespace_changed_during_readback','policy':'policy_chain_changed',
            'member':'foreign_local_network_member','clock':'foreign_host_route_clock','missing':'FileNotFoundError',
            'late_namespace':'guard_namespace_changed_during_readback','daemon_drift':'guard_binding_changed',
            'launcher_drift':'route_launcher_changed','stop':'a0_stopped_or_original_budget_expired'}
    assert errors[fault] in states[0].error
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['a0']['capability'] is None and row['host']['a0']['launch'] is None
    assert row['host']['a0']['acceptance']==states[0].row['host']['a0']['acceptance']
    assert not s.schedules and not s.posts and not s.calls
    assert not (Path(row['workspace_reference'])/'a0-capability.json').exists()
    invoke(setup,proof,args=s.args)
    assert len(states)==1 and not s.schedules


@pytest.mark.asyncio
async def test_real_missing_production_route_is_a_reserved_failure_not_queue_success(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    # A pinned real launcher plus reusable readiness is insufficient: no
    # per-row request or live OS observation exists in this isolated fixture.
    monkeypatch.setattr(setup.host,'produce_a0_capability',s.host_producer)
    loader=s.module.checked_launcher
    def absent(sha):
        l=loader(sha);l['REQUEST']=tmp_path/'ABSENT-original-route';return l
    monkeypatch.setattr(s.module,'checked_launcher',absent)
    monkeypatch.setattr(s.module,'prepare_route',lambda *args,**kwargs:None)
    answer=invoke(setup,proof,args=s.args)
    assert answer['accepted'] is False and answer['reference']
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['a0']['capability'] is None and not s.schedules and not s.calls and not s.posts


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['stop','wall_expired','mono_expired','restart','foreign','config','closed'])
async def test_producer_revalidates_owner_config_original_clocks_before_native(setup,tmp_path,monkeypatch,mode):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    row=launch_row(setup,s,proof,attach=False)
    calls=[]
    monkeypatch.setattr(s.module,'current_network',lambda *args,**kwargs:calls.append((args,kwargs)))
    host=setup.host;owner=row['owner'];producer=s.host_producer
    if mode=='stop':host.store.request_stop(row['existing_task_id'],owner,'cancel')
    elif mode=='wall_expired':host.store.clock=lambda:row['deadline_unix']
    elif mode=='mono_expired':monkeypatch.setattr(time,'monotonic_ns',lambda:row['host']['a0']['acceptance']['accepted_monotonic_ns']+60_000_000_000)
    elif mode=='restart':
        host=setup.module.WorkerHost(setup.ctx,setup.host.admission);producer=host.produce_a0_capability
    elif mode=='foreign':owner={**owner,'user_id':'foreign'}
    elif mode=='config':setup.configure({'enabled':False})
    else:host._closed=True
    with pytest.raises(Exception):producer(row['existing_task_id'],owner)
    retained=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert retained['host']['a0']['capability'] is None
    assert retained['host']['a0']['acceptance']==row['host']['a0']['acceptance']
    assert not calls and not s.schedules and not s.calls and not s.posts


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['schedule_ack','attach_ack','proof_write'])
async def test_partial_production_and_lost_ack_are_not_replayed(setup,tmp_path,monkeypatch,fault):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch,native_launcher=True)
    states=automatic(setup,s,monkeypatch)
    if fault=='schedule_ack':
        schedule=setup.ctx.schedule_gateway_work
        def uncertain(coro,**kwargs):
            schedule(coro,**kwargs)
            raise RuntimeError('EXPLICIT_FAKE_SCHEDULE_ACK_LOST')
        monkeypatch.setattr(setup.ctx,'schedule_gateway_work',uncertain)
    elif fault=='attach_ack':
        save=setup.host.store._save
        def uncertain(data):
            save(data)
            if any(r['host']['a0']['capability'] is not None for r in data['jobs'].values()):
                raise OSError('EXPLICIT_FAKE_ATTACH_ACK_LOST')
        monkeypatch.setattr(setup.host.store,'_save',uncertain)
    else:
        write=s.module.write_json
        def uncertain(path,value,**kwargs):
            write(path,value,**kwargs)
            if path.name=='a0-current-route.json':raise OSError('EXPLICIT_FAKE_PROOF_ACK_LOST')
        monkeypatch.setattr(s.module,'write_json',uncertain)
    answer=invoke(setup,proof,args=s.args)
    assert answer['accepted'] is False
    row=setup.host.store.get(answer['reference'],setup.record.owner_from_ingress(CALL,proof))
    calls=list(states[0].calls)
    assert row['host']['a0']['launch'] is None
    assert (row['host']['a0']['capability'] is None)==(fault=='proof_write')
    assert len(s.schedules)==(1 if fault=='schedule_ack' else 0)
    invoke(setup,proof,args=s.args)
    with pytest.raises(Exception):s.host_producer(row['existing_task_id'],row['owner'])
    assert states[0].calls==calls and not s.calls and not s.posts


@pytest.mark.parametrize('kind',['timeout','os_error','zero','infinite','boolean'])
def test_launcher_probe_is_finite_categorical_and_never_retried(monkeypatch,kind):
    import subprocess
    namespace={'__name__':'frw_offline_launcher_control'}
    source=Path(__file__).resolve().parents[1]/'scripts/rootless_docker_launch.py'
    exec(compile(source.read_bytes(),str(source),'exec'),namespace)
    calls=[]
    def fail(*args,**kwargs):
        calls.append((args,kwargs))
        if kind=='timeout':raise subprocess.TimeoutExpired(['secret-free-fixture'],kwargs['timeout'])
        raise OSError('EXPLICIT_OFFLINE_NATIVE_ERROR')
    monkeypatch.setattr(subprocess,'run',fail)
    limits={'timeout':1.25,'os_error':1.25,'zero':0,'infinite':float('inf'),'boolean':True}
    expected='route_native_check_failed' if kind in {'timeout','os_error'} else 'route_probe_budget_invalid'
    with pytest.raises(RuntimeError,match=expected):namespace['native_call'](['NEVER_EXECUTED'],timeout=limits[kind])
    assert len(calls)==(1 if kind in {'timeout','os_error'} else 0)
