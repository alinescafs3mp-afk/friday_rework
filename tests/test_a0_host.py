"""Real PluginManager/WorkerHost/Controller/runtime argv; native OS/API are
explicit offline fixtures. No production readiness, model or Docker proof."""
import asyncio,base64,copy,hashlib,importlib.util,json,time
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from test_host_native import setup,isolated,native,offline_boundary,ingress,invoke,settle,CALL,pin

SOURCE=Path(__file__).resolve().parents[1]

def configure_a0(setup,proof,tmp_path,monkeypatch):
    package=setup.module.__package__
    import sys
    hr=sys.modules[package+'.host_runtime']
    ac=importlib.import_module(package+'.adapters.a0_config')
    an=importlib.import_module(package+'.adapters.a0_native')
    aa=importlib.import_module(package+'.adapters.a0')
    address=setup.record.association_address(CALL,proof)
    accepted=time.time();mono=time.monotonic_ns();boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    # Real advancing clocks: capability is produced only AFTER reservation.
    setup.host.store.clock=time.time
    root=tmp_path/'native-fixture';root.mkdir(mode=0o700)
    runtime_root=root/'runtime';runtime_root.mkdir(mode=0o700)
    docker=root/'docker';docker.write_bytes(b'OFFLINE EXECUTABLE PIN; NEVER EXECUTED')
    daemon=root/'.runtime/rootless-docker/supervisor/friday-rework-docker.service'
    daemon.parent.mkdir(parents=True);daemon.write_bytes(b'OFFLINE UNIT PIN; NEVER INSTALLED')
    launcher=root/'launch.py';launcher.write_bytes(b'# explicit offline native guard fixture\n')
    policy=root/'reviewed-policy.json';policy.write_text('{"scope":"offline fixture only"}')
    git=runtime_root/'git-metadata'/('a'*64)/'repo/.git';git.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('a0_bound_fixture',SOURCE/'scripts/a0_runtime.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.PROJECT=root;m.RUNTIME=runtime_root;m.DOCKER=docker;m.LAUNCHER=launcher
    # Native Git inventory, kernel route/namespace readback, PID/cgroup samples
    # are explicitly fake interfaces; produced plan/create/unit schema is real.
    m.check_git_metadata=lambda x:None
    state=NS(calls=[],running=False,unit_started=False,obj=None,posts=[],checks=0,session=None,
             before_task=None,bootstrap_hook=None,create_hook=None,cleanup_uncertain=False)
    class Supervisor:
        def observe(self,row):
            if state.unit_started and row.get('native'):
                assert row['native']['invocation_id']=='b'*32
            running=state.running and state.unit_started
            return sys.modules[package+'.supervision'].UnitObservation(row['supervisor']['unit'],
                'b'*32 if state.unit_started else '', 'active' if running else 'inactive',
                'running' if running else 'dead','success',777777 if running else 0,
                '/user.slice/offline' if running else '',running,not state.unit_started)
        def stop(self,row):
            state.calls.append(['FAKE_UNIT_STOP',row['supervisor']['unit']])
            return self.observe(row)
    sup=Supervisor()
    def command(argv,timeout):
        state.calls.append(list(argv))
        if argv[0]=='/usr/bin/systemctl':
            if argv[-1]=='--property=ActiveState,InvocationID':return 'ActiveState=active\nInvocationID='+('e'*32)+'\n'
            return 'ActiveState=active\nDelegateSubgroup=dockerd\nMemoryMax=21474836480\nTasksMax=2048\nCPUQuotaPerSecUSec=8s\nRestart=no\nKillMode=control-group\nSendSIGKILL=yes\nDropInPaths=\n'
        if argv[0]=='/usr/bin/systemd-run':
            assert '--unit='+state.session.plan['unit'] in argv
            assert '--property=Description=Friday rework '+state.session.identity['admission_hash'] in argv
            state.unit_started=True;state.running=True;state.obj['State'].update(Running=True,Pid=777777)
            return ''
        if 'info' in argv:return json.dumps({'CgroupVersion':'2','CgroupDriver':'systemd','SecurityOptions':['name=rootless'],'ServerVersion':'29.8.2',**{k:True for k in ('MemoryLimit','SwapLimit','CpuCfsPeriod','CpuCfsQuota','PidsLimit')}})
        if 'ps' in argv:return ''
        if 'create' in argv:
            p=state.session.plan
            assert '--network='+p['network']['id'] in argv
            assert '--label' in argv and 'friday.rework.plan='+state.session.identity['admission_hash'] in argv
            state.obj={'Id':'d'*64,'Name':'/'+p['container_name'],'Image':m.IMAGE,
                'Config':{'Image':m.IMAGE,'Labels':m.labels(p),'Entrypoint':['/bin/bash'],
                    'Cmd':['-ceu',m.START_SCRIPT],'WorkingDir':'/a0','Env':['HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1']},
                'HostConfig':{'NetworkMode':p['network']['id'],'Privileged':False,'PortBindings':{},'PublishAllPorts':False,
                    'Binds':None,'Devices':[],'DeviceRequests':None,'PidMode':'','IpcMode':'private',
                    'RestartPolicy':{'Name':'no','MaximumRetryCount':0},'CapDrop':['ALL'],'CapAdd':None,
                    'SecurityOpt':['no-new-privileges'],'Memory':m.MEMORY,'MemorySwap':m.MEMORY,
                    'NanoCpus':2000000000,'PidsLimit':256,'ReadonlyRootfs':False},
                'Mounts':[{'Type':'bind','Source':p['state_dir'],'Destination':'/a0/usr','RW':True,'Propagation':'rprivate'},
                    {'Type':'bind','Source':p['git_metadata']['source'],'Destination':'/a0/.git','RW':False,'Propagation':'rprivate'}],
                'State':{'Running':False,'Pid':0,'ExitCode':0},'NetworkSettings':{'Networks':{p['network']['name']:{'NetworkID':p['network']['id']}}}}
            if state.create_hook:state.create_hook()
            return 'd'*64
        if 'inspect' in argv:return json.dumps([state.obj])
        if 'stop' in argv:
            if state.cleanup_uncertain:raise RuntimeError('explicit fake container stop uncertainty')
            state.running=False;state.obj['State'].update(Running=False,Pid=0)
            return 'd'*64
        raise AssertionError(argv)
    init=m.Runtime.__init__
    def rt_init(self,p,**kw):init(self,p,runner=command,supervisor=sup,**kw)
    monkeypatch.setattr(m.Runtime,'__init__',rt_init)
    def route(self,container_id=None):
        state.checks+=1
        assert self.p['accepted_monotonic_ns']==setup.host.store.get(address,identity['owner'])['host']['a0']['acceptance']['accepted_monotonic_ns']
        assert self.p['association_binding']['existing_task_id']==address
        return {'status':'EXPLICIT_FAKE_CURRENT_LOCAL_NETWORK_CHECKED','id':self.p['network']['id']}
    monkeypatch.setattr(m.Runtime,'check_network',route)
    monkeypatch.setattr(m.Runtime,'snapshot_container',lambda self,obj:{'group':'/user.slice/offline/docker-'+obj['Id']+'.scope','populated':True,'processes':[{'pid':777777,'start_ticks':'1'}]})
    monkeypatch.setattr(m,'cessation',lambda sample:{'confirmed':not state.running,'fixture':True})
    def module(session):state.session=session;return m
    monkeypatch.setattr(hr.A0HostSession,'_module',module)
    monkeypatch.setattr(an,'NativeSupervisor',lambda:sup)
    monkeypatch.setattr(an.A0NativeBoundary,'_run',staticmethod(lambda argv,data,timeout:command(argv,timeout)))
    def native_sample(boundary,obj,*,caps):
        boundary.samples.append((Path('/sys/fs/cgroup')/boundary.grant.container_cgroup.lstrip('/'),
                                 [(777777,'1')]))
    monkeypatch.setattr(an.A0NativeBoundary,'_sample',native_sample)
    def admit(boundary,row):
        assert not boundary.stop_only
        boundary._association(row);obj=boundary.inspect(row)
        assert obj['State']['Running'] and boundary.grant.network_verified
        assert boundary.grant.accepted_monotonic==row['host']['a0']['acceptance']['accepted_monotonic_ns']/1e9
        assert boundary.grant.keys_prepared_monotonic>=boundary.grant.accepted_monotonic
        return sup.observe(boundary._association(row))
    monkeypatch.setattr(an.A0NativeBoundary,'admit',admit)
    def path(boundary,worker):return boundary.config.state_dir.parent/worker.removeprefix('/a0/')
    def request(boundary,row,method,url,payload,timeout,max_bytes):
        boundary._keys();boundary.admit(row)
        if url.endswith('api_message'):
            state.posts.append(copy.deepcopy(payload))
            if 'context_id' not in payload:
                for v in payload.get('attachments',[]):
                    q=boundary.config.state_dir/'uploads'/v['filename'];q.parent.mkdir(mode=0o700,exist_ok=True);q.write_bytes(base64.b64decode(v['base64']))
                if state.bootstrap_hook:state.bootstrap_hook()
                return {'context_id':'context-fixture','response':'READY'}
            if state.before_task:state.before_task()
            for v in state.session.adapter._outputs(row):
                q=path(boundary,v.worker_path);q.parent.mkdir(mode=0o700,parents=True,exist_ok=True);q.write_bytes(b'actual retained fixture bytes\n')
            return {'context_id':'context-fixture','response':'untrusted fixture worker report'}
        if url.endswith('api_files_get'):return {Path(p).name:base64.b64encode(path(boundary,p).read_bytes()).decode() for p in payload['paths']}
        if url.endswith('api_log_get'):return {'context_id':'context-fixture','log':{'guid':'fixture-guid','progress_active':True,'total_items':1}}
        raise AssertionError(url)
    def file(boundary,row,worker,limit,timeout):
        boundary._keys();boundary.admit(row)
        return an.native_file(str(boundary.config.state_dir.parent),worker.removeprefix('/a0/'),limit)
    monkeypatch.setattr(an.A0NativeBoundary,'request',request);monkeypatch.setattr(an.A0NativeBoundary,'file',file)
    args={'worker':'a0','brief':'Repair offline fixture.','goal_check':'Owner checks retained bytes.'}
    runtime={k:copy.deepcopy(v) for k,v in setup.runtime.items() if k not in {'dsh','runtime_receipt'}}
    runtime['a0']={'runtime':pin(SOURCE/'scripts/a0_runtime.py'),'launcher':pin(launcher),'docker':pin(docker),
        'daemon_unit':pin(daemon),'policy':pin(policy),'git_metadata':{'source':str(git),'manifest_sha256':'f'*64},
        'owner_slot':'sol','expected_files':[{'logical_name':'report.txt','media_type':'text/plain'},{'logical_name':'diagnosis.txt','media_type':'text/plain'}],'capability':None}
    identity={'existing_task_id':address,'admission_hash':hashlib.sha256(address.encode()).hexdigest(),
        'owner':setup.record.owner_from_ingress(CALL,proof),'worker_kind':'a0','brief_sha256':setup.record.digest(args),
        'workspace_reference':str(Path(runtime['workspace_root'])/address),
        'supervisor':{'scope':'user','unit':'friday-rework-worker-'+address[7:39]+'.service'},
        'created_at_unix':accepted,'budget_seconds':60,'deadline_unix':accepted+60}
    owner='sol:'+address+'#1';nonce='9'*32
    network={'schema':'friday.a0.local-network.v1','name':'frw-a0-local-'+nonce[:12],'id':'8'*64,
        'owner':owner,'nonce':nonce,'labels':{'friday.rework.owner':owner,'friday.rework.route':nonce},'bridge':'br-frwa0local',
        'endpoints':m.LOCAL_ENDPOINTS,'launcher_sha256':pin(launcher)['sha256'],'policy_sha256':'7'*64,
        'request_sha256':'6'*64,'guard_receipt_sha256':'5'*64,'invocation_id':'4'*32,
        'namespaces':{'user':[1,2],'mnt':[1,3],'net':[1,4]}}
    # This entire receipt is an explicitly fabricated OFFLINE input fixture,
    # never a production readiness artifact. Actual native interfaces above
    # are intercepted, so these booleans make NO live acceptance claim.
    evidence=root/'FAKE-offline-reviewed-deployment.json'
    evidence.write_text(json.dumps({'classification':'EXPLICIT_FAKE_DEPLOYMENT_REVIEW_NOT_LIVE',
        'checks':{k:True for k in ('packet_egress','negative_egress','native_deadline','native_stop','pre_ui_keys')}}))
    capability=root/'capability.json'
    receipt=root/'receipt.json';destination=setup.home/'plugins/friday_rework'
    source_pins={k:pin(destination/p)['sha256'] for k,p in {'host':'host.py','host_runtime':'host_runtime.py','host_record':'host_record.py',
        'associations':'associations.py','adapter':'adapters/a0.py','native':'adapters/a0_native.py','config':'adapters/a0_config.py','profile':'adapters/a0_profile.py','web':'adapters/a0_web.py'}.items()}
    receipt.write_text(json.dumps({'schema':'friday-rework.a0-runtime.v2','ready':True,'runtime_sha256':setup.record.digest(runtime),
        'source_pins':source_pins,'evidence':[pin(evidence)]}))
    runtime['runtime_receipt']=pin(receipt);setup.configure(runtime)
    state.runtime=runtime;state.args=args;state.capability=capability;state.module=m;state.native=an;state.a0=aa;state.hr=hr;state.evidence=evidence
    def produce(row):
        from importlib import import_module
        exact=import_module(package+'.adapters.dsh')._identity(row)
        observed=root/'FAKE-current-route.json'
        observed.write_text(json.dumps({'schema':'friday.a0.host-current-route.v2','accepted':True,
            'association_sha256':setup.record.digest(exact),'acceptance_sha256':setup.record.digest(row['host']['a0']['acceptance']),
            'network_sha256':setup.record.digest(network),'runtime_source_sha256':pin(SOURCE/'scripts/a0_runtime.py')['sha256'],
            'checks':{'namespace_recheck':True,'current_route':True}}))
        capability.write_text(json.dumps({'schema':'friday.a0.host-capability.v2','association':exact,
            'acceptance':row['host']['a0']['acceptance'],'network':network,'live_evidence':[pin(observed)]}))
        return pin(capability)
    state.produce=produce
    state.schedules=[]
    original_schedule=setup.ctx.schedule_gateway_work
    def schedule(coro,**kwargs):
        state.schedules.append(dict(kwargs))
        return original_schedule(coro,**kwargs)
    monkeypatch.setattr(setup.ctx,'schedule_gateway_work',schedule)
    def readiness(boundary,row,timeout):
        boundary._keys();boundary.admit(row)
        return True
    monkeypatch.setattr(an.A0NativeBoundary,'readiness',readiness)
    def capture():
        if state.session is not None:
            (root/'FAKE-native-observations.json').write_text(json.dumps({
                'classification':'EXPLICIT_FAKE_NATIVE_BOUNDARIES_SOURCE_OFFLINE_ONLY',
                'plan':state.session.plan,'grant':state.session.grant,
                'commands':state.calls,'fake_container_observation':state.obj,
                'api_post_count':len(state.posts),'key_cleanup':state.session.key_cleanup,
                'pending':state.session.launching or state.session.preparing,
                'fake_route_checks':state.checks},sort_keys=True,indent=2)+'\n')
    state.capture=capture;setup.offline_a0_state=state
    return state


def launch_row(setup,state,proof,*,attach=True):
    setup.native.runner._draining=True
    value=invoke(setup,proof,args=state.args)
    assert value.get('reference'),value
    row=setup.host.store.get(value['reference'],setup.record.owner_from_ingress(CALL,proof))
    assert row['host']['inputs'] is not None
    if attach:
        try:setup.host.attach_a0_capability(row['existing_task_id'],row['owner'],state.produce(row))
        except RuntimeError as e:
            # Actual Hermes offline scheduler refuses/ closes the coroutine;
            # the persisted one-shot attachment still cannot be replayed.
            assert str(e)=='gateway_offline'
        row=setup.host.store.get(row['existing_task_id'],row['owner'])
    return row


def scoped_start(setup,row):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    token=set_secret_scope({'FRIDAY_LLM_API_KEY':'offline-fixture-key-one','FRIDAY_EMBEDDINGS_API_KEY':'offline-fixture-key-two'},profile_home=str(setup.home))
    try:return setup.host._start(row)
    finally:
        reset_secret_scope(token)
        setup.offline_a0_state.capture()

@pytest.mark.asyncio
@pytest.mark.parametrize('file',[False,True])
async def test_bound_core_real_plan_argv_controller_and_retained_bytes(setup,tmp_path,monkeypatch,file):
    proof=await ingress(setup,file=file);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    result=scoped_start(setup,row)
    assert result['host']['terminal']['state']=='completed'
    assert result['host']['quiescence']['kind']=='a0'
    assert len(s.posts)==2 and not s.running
    assert result['created_at_unix']==row['created_at_unix'] and result['deadline_unix']==row['deadline_unix']
    controller=setup.host._controller(result);session=controller.bindings['a0'].adapter
    assert setup.host._controller(result) is controller
    p=session.plan;g=session.grant
    assert p['association_binding']['admission_hash']==g['labels']['friday.rework.plan']==row['admission_hash']
    assert s.module.digest(p)!=row['admission_hash']
    assert g['accepted_monotonic']==row['host']['a0']['acceptance']['accepted_monotonic_ns']/1e9
    assert session.key_cleanup=='REMOVED'
    prepared=controller._load(result)
    artifacts=s.a0.read_retained_result(result,prepared,session.boundary.grant,session.adapter._outputs(result),session.adapter.config.staging_root,1024)
    assert len(artifacts)==2
    assert all(v.complete for v in artifacts)
    before=copy.deepcopy(s.posts)
    # Pure restart reading after original keys removed; no adapter or API.
    setup.host._a0_controllers.clear()
    again=s.a0.read_retained_result(result,prepared,session.boundary.grant,session.adapter._outputs(result),session.adapter.config.staging_root,1024)
    assert artifacts==again and s.posts==before
    assert setup.host._reconcile(result)==result
    duplicate=invoke(setup,proof,args=s.args)
    assert duplicate['accepted'] and s.posts==before
    if file:
        assert result['host']['inputs'][0]['worker_path'].startswith('/a0/usr/uploads/')

@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['owner','clock','unit','network_id','capability_pin'])
async def test_stale_capability_refuses_before_create(setup,tmp_path,monkeypatch,mutation):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch)
    row=launch_row(setup,s,proof,attach=False);s.produce(row)
    value=json.loads(s.capability.read_text())
    if mutation=='owner':value['association']['owner']['user_id']='foreign'
    elif mutation=='clock':value['acceptance']['accepted_monotonic_ns']+=1
    elif mutation=='unit':value['association']['supervisor']['unit']='foreign.service'
    elif mutation=='network_id':value['network']['id']='bridge'
    else:value['extra']=True
    s.capability.write_text(json.dumps(value))
    # Self-consistent operator pin still must reject exact owner/clock/schema.
    with pytest.raises(Exception):setup.host.attach_a0_capability(row['existing_task_id'],row['owner'],pin(s.capability))
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['a0']['capability'] is None
    assert not s.posts and not any('create' in v for v in s.calls)
    assert setup.host.store.get(row['existing_task_id'],row['owner'])['host']['quiescence'] is None

@pytest.mark.asyncio
async def test_cancel_during_bootstrap_stops_before_task_and_reuses_cached_binding(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    s.bootstrap_hook=lambda:setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    with pytest.raises(Exception):scoped_start(setup,row)
    assert len(s.posts)==1 and not s.running
    current=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert current['stop_intent']=='cancel' and current['host']['quiescence']['kind']=='a0'

@pytest.mark.asyncio
async def test_status_during_submit_reuses_same_inflight_adapter_no_second_task(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    def during():
        current=setup.host.store.get(row['existing_task_id'],row['owner'])
        controller=setup.host._controller(current)
        assert controller.bindings['a0'].adapter.adapter.inflight
        assert setup.host._reconcile(current)['host']['observation']['state']=='running'
        assert setup.host._controller(current) is controller
    s.before_task=during
    result=scoped_start(setup,row)
    assert result['host']['terminal']['state']=='completed' and len(s.posts)==2

@pytest.mark.asyncio
async def test_default_and_dsh_receipt_do_not_admit_a0(setup):
    proof=await ingress(setup)
    value=invoke(setup,proof,args={'worker':'a0','brief':'fixture','goal_check':'check'})
    assert not value['accepted'] and not setup.host.store.snapshot() and not setup.boundary.launches

@pytest.mark.asyncio
async def test_restart_during_bootstrap_stops_only_and_reports_lost_keys_separately(setup,tmp_path,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    token=set_secret_scope({'FRIDAY_LLM_API_KEY':'offline-fixture-key-one','FRIDAY_EMBEDDINGS_API_KEY':'offline-fixture-key-two'},profile_home=str(setup.home))
    try:
        c=setup.host._controller(row)
        c.prepare(row['existing_task_id'],row['owner'],s.a0.parse_brief(s.args),())
    finally:reset_secret_scope(token)
    current=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert s.running and len(s.posts)==1 and current['native'] is None
    keys=s.session.keys;env_before=keys.path.read_bytes()
    setup.host._a0_controllers.clear()
    result=setup.host._reconcile(current)
    assert not s.running and len(s.posts)==1
    assert result['host']['quiescence']['kind']=='a0'
    assert result['host']['quiescence']['observation']['key_cleanup']=='RECONCILIATION_REQUIRED'
    assert keys.path.read_bytes()==env_before
    recovered=setup.host._controller(result).bindings['a0'].adapter
    assert recovered.keys is None and recovered.boundary.stop_only
    with pytest.raises(Exception):recovered.boundary.admit(result)
    with pytest.raises(Exception):recovered.boundary.request(result,'POST','/api/api_message',{},1,1024)

@pytest.mark.asyncio
async def test_missing_scoped_keys_blocks_ui_and_proves_no_create_without_never_submitted(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    with pytest.raises(Exception):setup.host._start(row)
    assert not any('create' in v for v in s.calls) and not s.posts
    stopped=setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    assert stopped['host']['quiescence']['kind']=='a0_no_create'
    assert stopped['host']['a0']['launch'] is not None

@pytest.mark.asyncio
async def test_cancel_after_create_before_ui_uses_exact_cached_container_stop(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    s.create_hook=lambda:setup.host.store.request_stop(row['existing_task_id'],row['owner'],'cancel')
    with pytest.raises(Exception):scoped_start(setup,row)
    assert not s.unit_started and not s.posts and not s.running
    stopped=setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    assert stopped['host']['quiescence']['kind']=='a0_pre_grant'
    assert stopped['host']['quiescence']['observation']['container_id']=='d'*64
    assert stopped['host']['a0']['key_cleanup']=='REMOVED'

@pytest.mark.asyncio
async def test_container_stop_uncertainty_retains_capacity_and_original_keys(setup,tmp_path,monkeypatch):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    token=set_secret_scope({'FRIDAY_LLM_API_KEY':'offline-fixture-key-one','FRIDAY_EMBEDDINGS_API_KEY':'offline-fixture-key-two'},profile_home=str(setup.home))
    try:setup.host._controller(row).prepare(row['existing_task_id'],row['owner'],s.a0.parse_brief(s.args),())
    finally:reset_secret_scope(token)
    s.cleanup_uncertain=True
    with pytest.raises(Exception):setup.host._stop(setup.host.store.get(row['existing_task_id'],row['owner']),'cancel')
    current=setup.host.store.get(row['existing_task_id'],row['owner'])
    assert current['host']['quiescence'] is None and current['host']['a0']['key_cleanup']=='PREPARED'
    assert s.running and s.session.keys.path.exists()
    # Restore only the fake OS fixture for teardown; no product retry.
    s.cleanup_uncertain=False;s.running=False;s.obj['State'].update(Running=False,Pid=0)

@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['policy','receipt'])
async def test_cached_and_restarted_stop_do_not_reread_drifted_launch_inputs(setup,tmp_path,monkeypatch,mutation):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    token=set_secret_scope({'FRIDAY_LLM_API_KEY':'offline-fixture-key-one','FRIDAY_EMBEDDINGS_API_KEY':'offline-fixture-key-two'},profile_home=str(setup.home))
    try:setup.host._controller(row).prepare(row['existing_task_id'],row['owner'],s.a0.parse_brief(s.args),())
    finally:reset_secret_scope(token)
    selected=s.runtime['a0']['policy'] if mutation=='policy' else s.runtime['runtime_receipt']
    Path(selected['path']).write_bytes(b'changed launch-only input')
    setup.host._a0_controllers.clear()
    stopped=setup.host._reconcile(setup.host.store.get(row['existing_task_id'],row['owner']))
    assert not s.running and stopped['host']['quiescence']['kind']=='a0' and len(s.posts)==1

@pytest.mark.asyncio
async def test_damaged_store_after_actual_grant_still_reaches_cached_whole_stop(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    def corrupt():
        setup.ctx.state.path.write_text('{"damaged":')
    s.before_task=corrupt
    with pytest.raises(Exception):scoped_start(setup,row)
    assert not s.running
    assert any(v[0]=='FAKE_UNIT_STOP' for v in s.calls)
    # Both native stops still happen. A broken authoritative store prevents
    # durable observation, so cessation/capacity and key cleanup stay unknown.
    assert not s.session.native_cessation
    assert s.session.quiescence(row) is None and s.session.observation_pending
    assert s.session.keys.path.exists() and s.session.key_cleanup=='PREPARED'

@pytest.mark.asyncio
async def test_foreign_row_cannot_get_cached_stop_capability(setup,tmp_path,monkeypatch):
    proof=await ingress(setup);s=configure_a0(setup,proof,tmp_path,monkeypatch);row=launch_row(setup,s,proof)
    c=setup.host._controller(row);bad=copy.deepcopy(row);bad['owner']['user_id']='foreign'
    before=list(s.calls)
    with pytest.raises(Exception):setup.host._controller(bad)
    with pytest.raises(Exception):c.bindings['a0'].emergency_stop(bad)
    assert s.calls==before
