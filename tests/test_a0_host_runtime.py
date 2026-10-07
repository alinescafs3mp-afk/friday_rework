"""Changed core controls; fake native fixtures, not live A0 acceptance."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from test_a0_host import configure_a0,launch_row,scoped_start
from test_host_native import setup,isolated,native,offline_boundary,ingress


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['daemon', 'receipt_before', 'receipt_after'])
async def test_pregrant_sample_survives_failure_until_descendants_cease(setup,tmp_path,monkeypatch,fault):
    """Stopped container/PID0 cannot erase an earlier sampled live descendant.

    Native process/cgroup observations are explicit fakes; launch, receipt I/O,
    emergency stop, retained capacity and original key cleanup are real source.
    """
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    init=s.module.Runtime.__init__;snapshot=s.module.Runtime.snapshot_container
    write=s.module.write_json
    samples=[];checked=[];alive=[False];injected=[False]
    def sample(runtime,obj):
        value=snapshot(runtime,obj);samples.append(copy.deepcopy(value));alive[0]=True
        return value
    def cessation(value):
        checked.append(copy.deepcopy(value))
        return {'confirmed':not alive[0],'classification':'EXPLICIT_FAKE_PID_START_AND_CGROUP'}
    def fail():
        injected[0]=True;s.running=False;s.obj['State'].update(Running=False,Pid=0)
        raise RuntimeError('INJECTED_FAILURE_AFTER_INITIAL_SAMPLE')
    def wrapped_init(runtime,*args,**kwargs):
        init(runtime,*args,**kwargs);run=runtime.runner
        def command(argv,timeout):
            if fault=='daemon' and argv[-1]=='--property=ActiveState,InvocationID':fail()
            return run(argv,timeout)
        runtime.runner=command
    def write_receipt(path,value,**kwargs):
        target=(fault!='daemon' and not injected[0] and path.name=='native.json'
                and isinstance(value,dict) and value.get('observations'))
        if target and fault=='receipt_before':fail()
        answer=write(path,value,**kwargs)
        if target:fail()
        return answer
    monkeypatch.setattr(s.module.Runtime,'__init__',wrapped_init)
    monkeypatch.setattr(s.module.Runtime,'snapshot_container',sample)
    monkeypatch.setattr(s.module,'cessation',cessation)
    monkeypatch.setattr(s.module,'write_json',write_receipt)
    with pytest.raises(Exception,match='INJECTED_FAILURE_AFTER_INITIAL_SAMPLE'):scoped_start(setup,row)
    assert injected[0] and len(samples)==1 and checked and alive[0]
    assert all(value==samples[0] for value in checked)
    assert s.session.runtime.known['observations']==samples
    with pytest.raises(Exception,match='STOP_UNCONFIRMED'):
        setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    retained=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert retained['host']['quiescence'] is None
    assert s.session.key_cleanup=='PREPARED'
    # Only changed observed cessation permits the same owned cancellation to
    # settle. No worker/task POST or launch is replayed.
    before_posts=list(s.posts);before_creates=sum('create' in argv for argv in s.calls)
    alive[0]=False
    stopped=setup.host._stop(retained,'cancel')
    assert stopped['host']['quiescence']['kind']=='a0_pre_grant'
    assert stopped['host']['quiescence']['observation']['native_cessation'] is True
    assert s.session.key_cleanup=='REMOVED'
    assert s.posts==before_posts and sum('create' in argv for argv in s.calls)==before_creates

@pytest.mark.asyncio
async def test_original_fractional_wall_monotonic_and_boot_are_not_reset(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    acceptance=row['host']['a0']['acceptance']
    duplicate,fresh=setup.host.store.claim(task_id=row['existing_task_id'],admission_key=row['existing_task_id'],owner=row['owner'],
        brief=s.a0.parse_brief(s.args),workspace_reference=row['workspace_reference'],supervisor=row['supervisor'],
        budget_seconds=1800,deadline_unix=row['created_at_unix']+1800,host_binding=row['host']['binding'],
        acceptance={**acceptance,'accepted_monotonic_ns':acceptance['accepted_monotonic_ns']+999})
    assert not fresh and duplicate==row
    assert duplicate['deadline_unix']-duplicate['created_at_unix']==60
    result=scoped_start(setup,row);p=s.session.plan
    assert s.module.remaining(p,now=row['created_at_unix']+3.125)==31
    for key,value in [('accepted_monotonic_ns',acceptance['accepted_monotonic_ns']+1),('boot_id','0'*36),('deadline_unix',p['deadline_unix']+1)]:
        bad=copy.deepcopy(p);bad[key]=value
        with pytest.raises(Exception):s.module.validate(bad,check_files=False)
    assert result['host']['a0']['acceptance']==acceptance

@pytest.mark.asyncio
async def test_unit_only_quiescence_cannot_release_a0_launch_capacity(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    result=scoped_start(setup,row);bad=copy.deepcopy(result)
    bad['host']['quiescence']={'kind':'native','at_unix':row['created_at_unix'],'observation':result['host']['quiescence']['observation']['unit']}
    with pytest.raises(Exception):setup.record.validate_host_record(bad)
    bad=copy.deepcopy(result);bad['native']=None;bad['submission_observation']='NOT_SUBMITTED';bad['elapsed_seconds']=0
    bad['stop_intent']='cancel';bad['host']['terminal']=None;bad['host']['observation']=None
    bad['host']['quiescence']={'kind':'never_submitted','at_unix':row['created_at_unix'],'observation':None}
    with pytest.raises(Exception):setup.record.validate_host_record(bad)

@pytest.mark.asyncio
async def test_only_one_cached_controller_wins_concurrent_pure_construction(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    barrier=threading.Barrier(2);original=setup.module.a0_binding
    def race(*args):
        value=original(*args);barrier.wait(timeout=3);return value
    monkeypatch.setattr(setup.module,'a0_binding',race)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(setup.host._controller,row) for _ in range(2)]
        controllers=[f.result(timeout=4) for f in futures]
    assert controllers[0] is controllers[1] and len(setup.host._a0_controllers)==1
    assert not s.calls and not s.posts

@pytest.mark.asyncio
async def test_fresh_route_refusal_after_bootstrap_stops_without_task_or_replay(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    def drift():
        def refuse(*args,**kw):raise RuntimeError('EXPLICIT_FAKE namespace drift after bootstrap')
        monkeypatch.setattr(s.module.Runtime,'check_network',refuse)
    s.bootstrap_hook=drift
    with pytest.raises(Exception):scoped_start(setup,row)
    assert len(s.posts)==1 and not s.running
    stopped=setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    assert stopped['host']['quiescence']['kind']=='a0'

@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['order','origin','bytes','response','context','coverage'])
async def test_pure_reader_rejects_provenance_coverage_and_byte_changes_without_native(setup,tmp_path,monkeypatch,mutation):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof);result=scoped_start(setup,row)
    session=s.session;controller=setup.host._controller(result);prepared=controller._load(result)
    root=__import__('pathlib').Path(result['workspace_reference']);p=root/'a0-result.json';value=json.loads(p.read_text())
    if mutation=='order':value['artifacts'].reverse()
    elif mutation=='origin':value['artifacts'][0]['origin_reference']='foreign'
    elif mutation=='coverage':value['artifacts']=value['artifacts'][:-1]
    elif mutation=='context':value['context_id']='foreign'
    elif mutation=='response':(root/'worker-response.json').write_text('{"context_id":"context-fixture","response":"changed"}')
    else:
        artifacts=session.adapter.artifacts(result,prepared)
        selected=session.adapter.config.staging_root/artifacts[0].reference
        selected.chmod(0o600);selected.write_bytes(b'changed');selected.chmod(0o400)
    p.write_text(json.dumps(value))
    before=list(s.calls)
    with pytest.raises(Exception):s.a0.read_retained_result(result,prepared,session.boundary.grant,session.adapter._outputs(result),session.adapter.config.staging_root,1024)
    assert s.calls==before and len(s.posts)==2
