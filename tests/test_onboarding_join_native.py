"""Prior independently reviewed actual PluginManager -> advertised bridge -> middleware -> native host/result.
Only the final scheduler boundary closes coroutines; it never runs a worker.
"""
import os, asyncio, contextvars, copy, hashlib, importlib, json, shutil, sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_user_isolation import users
from test_user_retained_repair import update, fresh
from test_admin_foundation import ROOT
from hermes_cli import friday_user_scope as scope
from hermes_cli.plugins_state import PluginState
from hermes_cli.friday_product_access import KEY, current_access

@pytest.fixture
def wired(users, monkeypatch, request):
    source_profile=getattr(request,"param","user-1")
    if source_profile != 'user-1':
        from gateway.session import SessionSource
        from gateway.config import Platform
        from gateway.session_identity import RoutingIdentity
        source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id='1',chat_type='group',thread_id='same-topic',profile=source_profile)
        source._identity=RoutingIdentity('default','user-1',users.root,users.homes[0])
        assert users.gateway._principal_authorized(source,allow_adapter_delegation=True)
        users.sources[0]=source
    source_profile=source_profile or ''
    from hermes_cli import plugins
    from tools.registry import registry
    with users.enter(0):
        home=users.homes[0]
        destination=home/'plugins/friday_rework'
        shutil.copytree(ROOT,destination,ignore=shutil.ignore_patterns('__pycache__'))
        monkeypatch.setattr(plugins,'get_bundled_plugins_dir',lambda:home/'empty')
        monkeypatch.setattr(plugins.PluginManager,'_scan_entry_points',lambda self:[])
        paths=[home/n for n in ('jobs','staging','cache','payload','toolchain')]
        for p in paths:p.mkdir(mode=0o700)
        jobs,staging,cache,payload,toolchain=paths
        def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        node,cli,patch,nativefile=toolchain/'node',payload/'apps/cli/lib/bin.js',home/'local.yml',payload/'native.js'
        cli.parent.mkdir(mode=0o700,parents=True)
        for p in (node,cli,patch,nativefile):p.write_bytes(b'INDEPENDENT SYNTHETIC PIN; NEVER EXECUTED');p.chmod(0o600)
        runtime=dict(enabled=True,runtime_profile='user-1',runtime_home=str(home),workspace_root=str(jobs),staging_root=str(staging),
            cache_roots=[str(cache)],budget_seconds=60,max_file_bytes=1024,max_total_bytes=4096,
            dsh=dict(payload_root=str(payload),toolchain_root=str(toolchain),node=pin(node),cli=pin(cli),patch=pin(patch),native_files=[pin(nativefile)],
                key_name='UNUSED_SYNTHETIC_KEY',profile='headless',memory_bytes=2*1024**3,cpu_percent=200,tasks=64,shutdown_seconds=2,tmp_bytes=64*1024**2))
        from friday_admin_controls.host_record import digest
        evidence=home/'proof.json';evidence.write_text('{"synthetic_offline_admission":true}')
        receipt=home/'receipt.json';receipt.write_text(json.dumps(dict(schema='friday-rework.dsh-runtime.v1',ready=True,
            runtime_sha256=digest(runtime),adapter_sha256=pin(destination/'adapters/dsh.py')['sha256'],evidence=[pin(evidence)])))
        runtime['runtime_receipt']=pin(receipt)
        configuration={'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'allow_gateway_work':True,
            'allow_gateway_control':True,'settings':{'runtime':runtime,'results':{'enabled':True}}}}}}
        (home/'config.yaml').write_text(json.dumps(configuration));(home/'config.yaml').chmod(0o600)
        manager=plugins.PluginManager(scope_key=str(home));manager.discover_and_load()
        assert manager._plugins['friday_rework'].enabled,manager._plugins['friday_rework'].error
        monkeypatch.setattr(plugins,'get_plugin_manager',lambda:manager)
        entry=registry.get_entry('friday_work',scope=manager.scope_key);host=entry.handler.__self__
        scheduled=[]
        def schedule(coro,**kwargs):scheduled.append(kwargs);coro.close()
        monkeypatch.setattr(host.ctx,'schedule_gateway_work',schedule)
        package=manager._plugins['friday_rework'].module.__name__
        admission=importlib.import_module(package+'.admission')
        result=importlib.import_module(package+'.result_tool')
        supervision=importlib.import_module(package+'.supervision')
        def absent_fixture_unit(arguments, timeout):
            # This fixture closes scheduled coroutines before execution. Its
            # metadata-only UNKNOWN row must not query the real user manager
            # when the native host reconciles during PluginManager unload.
            units={r['supervisor']['unit'] for r in host.store.snapshot().values()}
            assert arguments[0]=='show' and arguments[1] in units and timeout==3
            fields=dict(LoadState='not-found',Transient='no',Description=arguments[1],
                InvocationID='',ActiveState='inactive',SubState='dead',Result='success',
                MainPID='0',ControlGroup='',KillMode='control-group',SendSIGKILL='yes')
            return SimpleNamespace(returncode=0,stdout='\n'.join(k+'='+v for k,v in fields.items()))
        monkeypatch.setattr(supervision.NativeSupervisor,'_command',staticmethod(absent_fixture_unit))
        assert admission.native_call_scope in manager._middleware['tool_execution']
        fields=dict(PLATFORM='telegram',CHAT_ID='shared-chat',CHAT_TYPE='group',THREAD_ID='same-topic',USER_ID='1',
            KEY='independent-key',ID='independent-session',MESSAGE_ID='independent-message',PROFILE=source_profile)
        variables=[contextvars.ContextVar('HERMES_SESSION_'+k) for k in fields]
        tokens=[v.set(fields[k]) for v,k in zip(variables,fields)]
        ingress=dict(platform='telegram',session_key=fields['KEY'],source_profile=source_profile,transport_profile='default',runtime_profile='user-1',chat_type='group',
            message=dict(bot_id='bot-A',user_id='1',chat_id='shared-chat',thread_id='same-topic',message_id=fields['MESSAGE_ID'],
            platform_update_id='independent-update',reply_to_message_id='',media=[]))
        # Use the real post-admission callback registration and receipt writer.
        source=dict(user_id='1',chat_id='shared-chat',thread_id='same-topic',message_id=fields['MESSAGE_ID'],profile=source_profile,chat_type='group')
        for callback in manager._hooks['post_gateway_admission']:
            callback(admitted_ingress=ingress,session_key=fields['KEY'],message_id=fields['MESSAGE_ID'],platform='telegram',source=source)
        call=dict(task_id=fields['ID'],session_id=fields['ID'],turn_id='independent-turn',api_request_id='independent-api',tool_call_id='work-call')
        args=dict(worker='dsh',brief='Prior independently reviewed native admission',goal_check='Check owned original admission without worker execution')
        from model_tools import handle_function_call
        def invoke(name,args,**options):
            identity=options.pop('call',call)
            return json.loads(handle_function_call('tool_call',{'calls':[{'name':name,'arguments':args}]},
                **identity,enabled_toolsets=['friday_rework'],**options))
        value=SimpleNamespace(users=users,host=host,manager=manager,admission=admission,result=result,scheduled=scheduled,
            package=package,call=call,args=args,invoke=invoke,ingress=ingress,fields=fields,variables=variables)
        try:yield value
        finally:
            for variable,token in zip(variables,tokens):variable.reset(token)
            # Real manager unload closes the host; the same scheduler boundary
            # closes any cleanup coroutine. No actual worker ever existed.
            manager.unload()
            assert not host._a0_controllers

@pytest.mark.parametrize('bad',['none','no_middleware','payload_ids','missing_turn','wrong_task','foreign_session','mixed','nested'])
def test_actual_registered_advertised_join(wired,bad):
    w=wired
    args=copy.deepcopy(w.args);call=copy.deepcopy(w.call);options={}
    if bad=='no_middleware':options['skip_tool_execution_middleware']=True
    if bad=='payload_ids':
        args.update(w.call);call={k:None for k in call}
    if bad=='missing_turn':call['turn_id']=None
    if bad=='wrong_task':call['task_id']='foreign-task'
    if bad=='foreign_session':call['session_id']='foreign-session'
    if bad in ('mixed','nested'):
        from model_tools import handle_function_call
        entry={'name':'friday_work','arguments':args}
        denied={'name':'terminal','arguments':{}} if bad=='mixed' else {'name':'tool_call','arguments':{'calls':[entry]}}
        result=json.loads(handle_function_call('tool_call',{'calls':[entry,denied]},**call,enabled_toolsets=['friday_rework']))
    else:result=w.invoke('friday_work',args,call=call,**options)
    if bad!='none':
        assert not result.get('accepted'),result
        assert w.scheduled==[] and w.host.store.snapshot()=={}
        return
    assert result['accepted'] and len(w.scheduled)==1,result
    row=w.host.store.snapshot()[result['reference']]
    assert row['host']['binding']['correlation']==w.call
    assert row['host']['binding']['user_authority']=={'principal_id':scope.current().key,'generation':scope.current().admission_generation}
    assert row['budget_seconds']==60 and row['stop_intent'] is None
    result_args={'action':'status','reference':result['reference']}
    assert w.invoke('friday_result',result_args,call={**call,'tool_call_id':'result-call'})['accepted']
    assert w.admission._call.get() is None  # middleware restored its lease
    assert not w.invoke('friday_result',result_args,skip_tool_execution_middleware=True)['accepted']
    assert w.invoke('friday_work',args)==result and len(w.scheduled)==1
    assert w.host.store.snapshot()[result['reference']]==row

@pytest.mark.parametrize('mutation',['idle_disable','remove_recreate','role_cycle'])
def test_old_job_no_revival_original_deadline_and_owned_stop(wired,mutation):
    w=wired;u=w.users
    result=w.invoke('friday_work',w.args);assert result['accepted']
    before=w.host.store.snapshot()[result['reference']]
    retained=scope.current();generation=retained.admission_generation
    if mutation=='idle_disable':update(u,enabled=False);update(u)
    elif mutation=='role_cycle':update(u,role='admin');update(u)
    else:
        with scope.authority(u.root):
            state=PluginState('friday_rework');doc=current_access(state);doc['users'].pop(retained.key);state.set(KEY,doc)
            doc=current_access(PluginState('friday_rework'));assert not doc['users'][retained.key]['enabled']
        update(u)
    # Discard only the active invocation context, never relabel the retained job.
    token=scope._CURRENT.set(None)
    try:
        new=fresh(u)
        with scope.scoped_source(u.sources[0]):
            assert new.admission_generation>generation
            assert not w.invoke('friday_work',w.args)['accepted']
            assert not w.invoke('friday_result',{'action':'status','reference':result['reference']})['accepted']
            with pytest.raises(scope.ScopeDenied):w.host._start(before)
            coroutine=w.result.notify_finished(w.host,before)
            try:
                with pytest.raises(scope.ScopeDenied):coroutine.send(None)
            finally:coroutine.close()
            assert w.host.store.snapshot()[result['reference']]==before and len(w.scheduled)==1
            from hermes_cli.plugin_command_context import _command_context
            receipt=dict(command='friday-stop',session_key=w.ingress['session_key'],admitted_ingress=w.ingress,
                source=dict(platform='telegram',profile='user-1',user_id='1',chat_id='shared-chat',thread_id='same-topic'))
            with _command_context(w.host.ctx,receipt):
                stopped=json.loads(w.host.control('friday-stop',result['reference']))
            assert stopped['accepted'] and stopped['stop_intent']=='cancel' and stopped['quiescent']
            after=w.host.store.snapshot()[result['reference']]
            assert after['deadline_unix']==before['deadline_unix'] and after['budget_seconds']==before['budget_seconds']
            assert after['host']['binding']==before['host']['binding']
            assert after['host']['quiescence']['kind']=='never_submitted'
    finally:scope._CURRENT.reset(token)

@pytest.mark.parametrize('requested_generation',[None,1,999999999])
def test_generation_is_authoritative_not_requested_and_tombstones_persist(users,requested_generation):
    u=users
    with u.enter(0) as cap:
        original=cap.admission_generation
        with scope.authority(u.root):
            doc=current_access();doc['users'].pop(cap.key);PluginState('friday_rework').set(KEY,doc)
            tomb=current_access()['users'][cap.key]
            assert tomb['enabled'] is False and tomb['generation']==original+1
            again=current_access();again['users'].pop(cap.key);PluginState('friday_rework').set(KEY,again)
            assert current_access()['users'][cap.key]==tomb
            tomb['enabled']=True
            if requested_generation is None:tomb.pop('generation')
            else:tomb['generation']=requested_generation
            doc=current_access();doc['users'][cap.key]=tomb;PluginState('friday_rework').set(KEY,doc)
            assert current_access()['users'][cap.key]['generation']==original+1
        with pytest.raises(scope.ScopeDenied):cap.check()
    assert fresh(u).admission_generation==original+1


@pytest.mark.parametrize('wired',['',None],indirect=True)
def test_own_native_route_without_explicit_source_profile(wired,monkeypatch):
    from test_user_implicit_profile import offline_execution
    w=wired
    observed=offline_execution(w,monkeypatch)
    assert w.users.sources[0].profile in ('',None)
    result=w.invoke('friday_work',w.args)
    assert result['accepted'],result
    row=w.host.store.snapshot()[result['reference']]
    duplicate=w.invoke('friday_work',w.args)
    result_reply=w.invoke('friday_result',{'action':'status','reference':result['reference']},call={**w.call,'tool_call_id':'result-call'})
    start_error=None
    from agent.secret_scope import load_env_file,set_secret_scope,reset_secret_scope
    secret=set_secret_scope(load_env_file(w.users.homes[0]/'.env'),profile_home=str(w.users.homes[0]))
    try:
        try:w.host._start(row)
        except scope.ScopeDenied as error:start_error=str(error)
    finally:reset_secret_scope(secret)
    proof={'source_event_profile':w.users.sources[0].profile,'actual_workerhost_start_refusal':start_error,'source_profile':row['host']['binding']['ingress']['source_profile'],'owner_profile':row['owner']['profile'],
        'runtime_profile':row['host']['binding']['ingress']['runtime_profile'],'admission':result,'duplicate':duplicate,'result':result_reply,
        'scope_generation':scope.current().admission_generation,'bound_authority':row['host']['binding']['user_authority']}
    (Path(os.environ.get("FRIDAY_FIXTURE_EVIDENCE", Path(__file__).parent))/('implicit-profile-'+('none' if w.users.sources[0].profile is None else 'empty')+'-observation.json')).write_text(json.dumps(proof,indent=2)+'\n')
    assert duplicate['accepted'] and result_reply['accepted'] and start_error is None,proof
    assert len(observed.launches)==1  # Synthetic final-effect carrier; no process launched.

@pytest.mark.parametrize('execution',['sequential','parallel'])
def test_real_native_batch_expansion_with_registered_middleware(wired,execution):
    from agent.tool_call_batches import expand_local_tool_batches
    from agent.tool_executor import _parse_tool_call,_resolve_sequential_dispatch
    from agent.agent_runtime_helpers import invoke_tool
    from agent.transports.types import ToolCall
    from hermes_cli.middleware import run_tool_execution_middleware
    from concurrent.futures import ThreadPoolExecutor
    from tools.thread_context import propagate_context_to_thread
    w=wired
    agent=SimpleNamespace(valid_tool_names={'tool_call','friday_work','friday_result'},enabled_toolsets=['friday_rework'],disabled_toolsets=[],
        _context_engine_tool_names=set(),_memory_manager=None,session_id=w.call['session_id'],quiet_mode=False,
        _current_turn_id=w.call['turn_id'],_current_api_request_id=w.call['api_request_id'])
    scope.capture_agent(agent)
    initial=w.invoke('friday_work',w.args);assert initial['accepted']
    status_args={'action':'status','reference':initial['reference']}
    envelope={'calls':[{'name':'friday_result','arguments':status_args},{'name':'friday_result','arguments':status_args}]}
    expanded=expand_local_tool_batches([ToolCall(id='independent-batch',name='tool_call',arguments=json.dumps(envelope))])
    parsed=[_parse_tool_call(agent,call) for call in expanded]
    assert len(parsed)==2 and all(p.parse_error is None and p.name=='friday_result' for p in parsed)
    if execution=='sequential':
        answers=[]
        for p in parsed:
            dispatch=_resolve_sequential_dispatch(agent,p.ref(w.call['task_id']),[])
            call={**w.call,'tool_call_id':p.tool_call.id}
            answers.append(json.loads(run_tool_execution_middleware('friday_result',p.args,dispatch.execute,**call)))
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(propagate_context_to_thread(invoke_tool),agent,'friday_result',p.args,w.call['task_id'],tool_call_id=p.tool_call.id) for p in parsed]
            answers=[json.loads(f.result(timeout=4)) for f in futures]
    assert all(x['accepted'] for x in answers),answers
    assert {x['reference'] for x in answers}=={initial['reference']} and len(w.scheduled)==1
    rows=w.host.store.snapshot()
    assert all(r['host']['binding']['user_authority']['generation']==scope.current().admission_generation for r in rows.values())
    for result in answers:
        assert w.invoke('friday_result',{'action':'status','reference':result['reference']},call={**w.call,'tool_call_id':'independent-result'})['accepted']

@pytest.mark.parametrize('name',['tool_search','tool_describe'])
def test_retained_search_dispatch_cannot_use_replacement_capability(users,name):
    from agent.tool_executor import _parse_tool_call,_resolve_sequential_dispatch
    from agent.agent_runtime_helpers import invoke_tool
    from agent.transports.types import ToolCall
    args={'queries':['friday_work']} if name=='tool_search' else {'names':['friday_work']}
    agent=SimpleNamespace(valid_tool_names={name},enabled_toolsets=[],disabled_toolsets=[],_context_engine_tool_names=set(),
        _memory_manager=None,session_id='search-session',quiet_mode=False)
    with users.enter(0):
        scope.capture_agent(agent)
        parsed=_parse_tool_call(agent,ToolCall(id='search',name=name,arguments=json.dumps(args)))
        assert parsed.parse_error is None
        prepared=_resolve_sequential_dispatch(agent,parsed.ref('search-session'),[])
    update(users,enabled=False);update(users);fresh(users)
    with users.enter(0):
        assert json.loads(prepared.execute(args))['error']=='product_user_scope_refused'
        assert json.loads(invoke_tool(agent,name,args,'search-session'))['error']=='product_user_scope_refused'
        assert _parse_tool_call(agent,ToolCall(id='search-again',name=name,arguments=json.dumps(args))).parse_error=='product_user_scope_refused'

@pytest.mark.parametrize('boundary',['active_reconcile','result_delivery'])
def test_retained_generation_refuses_before_active_or_delivery_effect(wired,boundary,monkeypatch):
    w=wired;u=w.users
    response=w.invoke('friday_work',w.args);assert response['accepted']
    row=w.host.store.snapshot()[response['reference']]
    # The UNKNOWN metadata below is deliberately synthetic. Retained authority
    # must fail before observation in the test body; real manager unload still
    # owes exact-owned cleanup. Keep the actual supervisor parser/stop path but
    # supply its native command boundary with an explicit missing-unit record.
    observations=[]
    supervisor=importlib.import_module(w.package+'.supervision')
    def missing_owned_unit(arguments, timeout):
        assert w.host._closed, 'native observation reached before unload'
        unit=row['supervisor']['unit']
        assert arguments==['show',unit,'--property='+','.join(supervisor.NativeSupervisor.properties)]
        observations.append(arguments)
        fields=dict(LoadState='not-found',Transient='no',Description=unit,InvocationID='',
            ActiveState='inactive',SubState='dead',Result='success',MainPID='0',ControlGroup='',
            KillMode='control-group',SendSIGKILL='yes')
        return SimpleNamespace(returncode=0,stdout='\n'.join(k+'='+v for k,v in fields.items()))
    monkeypatch.setattr(supervisor.NativeSupervisor,'_command',staticmethod(missing_owned_unit))
    if boundary=='active_reconcile':
        # Existing native state transition records uncertainty only; no external
        # submission is performed in this isolated metadata fixture.
        row=w.host.store.begin_submission(row['existing_task_id'],row['owner'])
        assert row['submission_observation']=='UNKNOWN'
    update(u,enabled=False);update(u)
    token=scope._CURRENT.set(None)
    try:
        fresh(u)
        with scope.scoped_source(u.sources[0]):
            before=w.host.store.snapshot()[row['existing_task_id']]
            if boundary=='active_reconcile':
                with pytest.raises(scope.ScopeDenied):w.host._reconcile_checked(row)
            else:
                retained=copy.deepcopy(row)
                retained['result']={'artifacts':[{'reference':'synthetic-output'}]}
                delivery=w.result.ResultTool(w.host).deliver(retained)
                try:
                    with pytest.raises(scope.ScopeDenied):delivery.send(None)
                finally:delivery.close()
            assert w.host.store.snapshot()[row['existing_task_id']]==before
            assert len(w.scheduled)==1 and not observations
    finally:scope._CURRENT.reset(token)
