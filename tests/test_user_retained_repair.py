"""Real native retained grants and advertised tool dispatch; synthetic transport only."""
import contextvars, copy, json
from dataclasses import replace
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_user_isolation import users, native_history
from test_admin_foundation import ProductAccess
from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_product_access import KEY, current_access
from hermes_cli.plugins_state import PluginState


def update(users, uid='1', enabled=True, role='user'):
    with scope.authority(users.root):
        return ProductAccess(PluginState('friday_rework')).set_user(platform='telegram',
            transport_profile='default', account_id='bot-A', user_id=uid, enabled=enabled, role=role)


def fresh(users, i=0):
    from gateway.session import SessionSource
    from gateway.config import Platform
    from gateway.session_identity import RoutingIdentity
    source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id=str(i+1),profile='user-'+str(i+1))
    source._identity=RoutingIdentity('default','user-'+str(i+1),users.root,users.homes[i])
    assert users.gateway._principal_authorized(source,allow_adapter_delegation=True)
    users.sources[i]=source
    return source._friday_user_scope


@pytest.mark.parametrize('route',['product','native','omit','role'])
def test_durable_revocation_survives_idle_capability_and_new_reader(users,route):
    from tools.memory_tool import MemoryStore
    with users.enter(0) as cap:
        memory=MemoryStore();memory.load_from_disk();memory.add('memory','retained useful memory');memory.load_from_disk()
        inherited=contextvars.copy_context(); generation=cap.admission_generation
        if route=='product':update(users,enabled=False);update(users)
        elif route=='role':update(users,role='admin');update(users)
        else:
            with scope.authority(users.root):
                state=PluginState('friday_rework'); doc=current_access(state)
                if route=='omit':doc['users'].pop(cap.key)
                else:doc['users'][cap.key]['enabled']=False
                state.set(KEY,doc)
                # Construct a new disk reader/writer, including stale requested generation.
                doc=current_access(PluginState('friday_rework'));doc['users'][cap.key]['enabled']=True
                doc['users'][cap.key]['generation']=generation
                PluginState('friday_rework').set(KEY,doc)
        reconstructed=replace(cap,revoked=False)  # persisted original admission, not a new grant
        with pytest.raises(scope.ScopeDenied):reconstructed.check()
        with pytest.raises(scope.ScopeDenied):inherited.run(scope.current)
        with pytest.raises(scope.ScopeDenied):memory.add('memory','old task must not continue')
    new=fresh(users)
    assert new.admission_generation>generation
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')
        own=MemoryStore();own.load_from_disk();assert 'retained useful memory' in own.format_for_system_prompt('memory')
        assert own.add('memory','fresh task useful')['success']


@pytest.mark.parametrize('other',['noop','unrelated','repeat-disable-other'])
def test_noop_and_other_principal_do_not_revoke_current_capability(users,other):
    with users.enter(0) as cap:
        generation=cap.admission_generation
        if other=='noop':update(users);update(users)
        elif other=='unrelated':update(users,'2',False);update(users,'2',True)
        else:update(users,'2',False);update(users,'2',False)
        assert cap.check() is cap
        assert fresh(users).admission_generation==generation


def test_concurrent_native_writers_cannot_overwrite_revocation_generation(users):
    with users.enter(0) as cap:
        original=cap.admission_generation
        with scope.authority(users.root):
            original_doc=current_access(users.state)
        disabled=copy.deepcopy(original_doc);disabled['users'][cap.key]['enabled']=False
        enabled=copy.deepcopy(original_doc)
        # Competing whole-document writers have the same stale version. Native
        # locking derives the version from the committed state, not these inputs.
        def write(doc):
            with scope.authority(users.root):PluginState('friday_rework').set(KEY,doc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(contextvars.copy_context().run,write,doc) for doc in (disabled,enabled)]
            for f in futures:f.result(timeout=8)
        update(users)
        with scope.authority(users.root):
            assert current_access(PluginState('friday_rework'))['users'][cap.key]['generation']==original+1
        with pytest.raises(scope.ScopeDenied):cap.check()
    assert fresh(users).admission_generation==original+1


def test_legacy_rows_require_explicit_native_migration_and_missing_retained_generation_denies(users):
    with scope.authority(users.root):
        doc=current_access(users.state)
        for row in doc['users'].values():row.pop('generation')
        # Simulate persisted old native bytes; authority migration happens through actual PluginState.
        data=users.state._read_unlocked();data[KEY]=doc
        users.state.path.write_text(json.dumps(data));users.state.path.chmod(0o600)
    from gateway.session import SessionSource
    from gateway.config import Platform
    from gateway.session_identity import RoutingIdentity
    source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id='1',profile='user-1')
    source._identity=RoutingIdentity('default','user-1',users.root,users.homes[0])
    assert not users.gateway._principal_authorized(source,allow_adapter_delegation=True)
    update(users)
    cap=fresh(users)
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):replace(cap,admission_generation=None).check()
        assert cap.check() is cap


@pytest.mark.parametrize('shape',['single','batch','json-batch','dict-batch','legacy-json-args'])
def test_advertised_bridge_real_expansion_parser_sequential_parallel_own_positives(users,shape):
    from tools.registry import registry
    from model_tools import handle_function_call
    from agent.tool_call_batches import expand_local_tool_batches
    from agent.tool_executor import _parse_tool_call, _resolve_sequential_dispatch
    from agent.transports.types import ToolCall
    from tools.thread_context import propagate_context_to_thread
    seen=[]
    def handle(args,**kw):
        cap=scope.current(required=True);seen.append((cap.key,args['brief']));return json.dumps({'own':True})
    registry.register(name='friday_work',toolset='retained_fixture',schema={'name':'friday_work','description':'synthetic coding admission',
        'parameters':{'type':'object','properties':{'brief':{'type':'string'}},'required':['brief']}},handler=handle,override=True)
    entry={'name':'friday_work','arguments':{'brief':'actual deferred own coding entry'}}
    args={'calls':[entry]}
    if shape=='batch':args={'calls':[entry,copy.deepcopy(entry)]}
    elif shape=='json-batch':args={'calls':json.dumps([entry])}
    elif shape=='dict-batch':args={'calls':entry}
    elif shape=='legacy-json-args':args={'name':'friday_work','arguments':json.dumps(entry['arguments'])}
    agent=SimpleNamespace(valid_tool_names={'tool_call','friday_work'},enabled_toolsets=['retained_fixture'],disabled_toolsets=[],
        _context_engine_tool_names=set(),_memory_manager=None,session_id='session',quiet_mode=False)
    with users.enter(0) as cap:
        scope.capture_agent(agent)
        calls=expand_local_tool_batches([ToolCall(id='batch',name='tool_call',arguments=json.dumps(args))])
        assert len(calls)==(2 if shape=='batch' else 1)
        for call in calls:
            parsed=_parse_tool_call(agent,call);assert parsed.parse_error is None and parsed.name=='friday_work'
            dispatch=_resolve_sequential_dispatch(agent,parsed.ref('original-task'),[])
            assert json.loads(dispatch.execute(parsed.args))['own']
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs=[pool.submit(propagate_context_to_thread(handle_function_call),'tool_call',{'calls':[entry]},
                enabled_toolsets=['retained_fixture'],skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,
                skip_tool_execution_middleware=True) for _ in range(2)]
            assert all(json.loads(f.result(timeout=5))['own'] for f in fs)
        assert all(key==cap.key for key,brief in seen)


@pytest.mark.parametrize('bad',['mixed','nested','missing','forged-scope','revoked','foreign-agent','missing-context','oversized','malformed'])
def test_batch_negative_controls_refuse_before_any_prefix_effect(users,bad):
    from tools.registry import registry
    from model_tools import handle_function_call
    from agent.tool_call_batches import expand_local_tool_batches
    from agent.tool_executor import _parse_tool_call
    from agent.transports.types import ToolCall
    from agent.agent_runtime_helpers import invoke_tool
    from tools.connectors.gateway.config import MAX_CALLS_PER_DISPATCH
    seen=[]
    registry.register(name='friday_work',toolset='retained_fixture',schema={'name':'friday_work','description':'positive scoped handler',
        'parameters':{'type':'object'}},handler=lambda *a,**k:seen.append('effect') or '{}',override=True)
    good={'name':'friday_work','arguments':{}}
    args={'calls':[good,{'name':'terminal','arguments':{}}]}
    if bad=='nested':args={'calls':[good,{'name':'tool_call','arguments':{'calls':[good]}}]}
    elif bad=='missing':args={'calls':[good,{'arguments':{}}]}
    elif bad=='malformed':args={'calls':[good,{'name':'friday_work','arguments':'['}]}
    elif bad=='oversized':args={'calls':[good]*(MAX_CALLS_PER_DISPATCH+1)}
    elif bad not in ('mixed','nested','missing'):args={'calls':[good]}
    if bad=='foreign-agent':
        with users.enter(0):
            agent=SimpleNamespace();scope.capture_agent(agent)
        with users.enter(1):
            assert 'product_user_scope_refused' in invoke_tool(agent,'tool_call',args,'old-task')
        assert seen==[]
        return
    with users.enter(0) as cap:
        agent=SimpleNamespace();scope.capture_agent(agent)
        if bad=='revoked':update(users,enabled=False);update(users)
        if bad=='missing-context':assert 'product_user_scope_refused' in contextvars.Context().run(handle_function_call,'tool_call',args)
        elif bad=='forged-scope':assert 'product_user_scope_refused' in registry.dispatch('tool_call',args,scope=str(users.homes[1]))
        else:
            calls=expand_local_tool_batches([ToolCall(id='bad',name='tool_call',arguments=json.dumps(args))]);assert len(calls)==1
            assert _parse_tool_call(agent,calls[0]).parse_error=='product_user_scope_refused'
            assert 'product_user_scope_refused' in handle_function_call('tool_call',args)
        assert seen==[]


def test_cached_real_sequential_dispatch_does_not_acquire_new_user_or_generation(users):
    from tools.registry import registry
    from agent.tool_executor import _parse_tool_call, _resolve_sequential_dispatch
    from agent.agent_runtime_helpers import invoke_tool
    from agent.transports.types import ToolCall
    seen=[]
    registry.register(name='friday_work',toolset='retained_fixture',schema={'name':'friday_work','description':'scoped synthetic',
        'parameters':{'type':'object'}},handler=lambda *a,**k:seen.append('effect') or '{}',override=True)
    agent=SimpleNamespace(valid_tool_names={'friday_work','tool_call'},_context_engine_tool_names=set(),_memory_manager=None,
                          enabled_toolsets=['retained_fixture'],session_id='session',quiet_mode=False)
    args={'calls':[{'name':'friday_work','arguments':{}}]}
    with users.enter(0):
        scope.capture_agent(agent)
        parsed=_parse_tool_call(agent,ToolCall(id='own',name='tool_call',arguments=json.dumps(args)))
        prepared=_resolve_sequential_dispatch(agent,parsed.ref('original-task'),[])
    with users.enter(1):
        assert 'product_user_scope_refused' in prepared.execute({})
        assert _parse_tool_call(agent,ToolCall(id='foreign',name='tool_call',arguments=json.dumps(args))).parse_error=='product_user_scope_refused'
    update(users,enabled=False);update(users);fresh(users)
    with users.enter(0):
        assert 'product_user_scope_refused' in prepared.execute({})
        assert 'product_user_scope_refused' in invoke_tool(agent,'tool_call',args,'original-task')
    assert seen==[]


@pytest.mark.parametrize('tamper',['none','foreign-user','foreign-account','missing-correlation','revoked','forged-payload'])
def test_advertised_coding_entry_reaches_actual_workerhost_owned_admission(users,tamper):
    """Actual Product WorkerHost/IngressAdmissions/Associations; scheduler closes
    queued coroutine before execution. No alternate or actual worker is run."""
    import hashlib, importlib
    from pathlib import Path
    from tools.registry import registry
    from model_tools import handle_function_call
    from test_admin_foundation import ROOT
    admission=importlib.import_module('friday_admin_controls.admission')
    hostmod=importlib.import_module('friday_admin_controls.host')
    record=importlib.import_module('friday_admin_controls.host_record')
    with users.enter(0):
        state=PluginState('friday_rework'); admitted=admission.IngressAdmissions(state)
        home=users.homes[0]
        jobs,staging,cache,payload,toolchain=[home/name for name in ('jobs','staging','cache','payload','toolchain')]
        for p in (jobs,staging,cache,payload,toolchain):p.mkdir(mode=0o700)
        def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        node=toolchain/'node';cli=payload/'cli.js';patch=home/'local.yml';nativefile=payload/'native.js'
        for p in (node,cli,patch,nativefile):p.write_bytes(b'SYNTHETIC-PINNED-TRANSPORT-NOT-EXECUTABLE');p.chmod(0o600)
        runtime=dict(enabled=True,runtime_profile='user-1',runtime_home=str(home),workspace_root=str(jobs),staging_root=str(staging),
            cache_roots=[str(cache)],budget_seconds=60,max_file_bytes=1024,max_total_bytes=4096,
            dsh=dict(payload_root=str(payload),toolchain_root=str(toolchain),node=pin(node),cli=pin(cli),patch=pin(patch),native_files=[pin(nativefile)],
                key_name='SYNTHETIC_UNUSED_KEY',profile='headless',memory_bytes=2*1024**3,cpu_percent=200,tasks=64,shutdown_seconds=2,tmp_bytes=64*1024**2))
        evidence=home/'synthetic-proof.json';evidence.write_text('{"offline_admission_only":true}')
        receipt=home/'synthetic-receipt.json';receipt.write_text(json.dumps(dict(schema='friday-rework.dsh-runtime.v1',ready=True,
            runtime_sha256=record.digest(runtime),adapter_sha256=pin(ROOT/'adapters/dsh.py')['sha256'],evidence=[pin(evidence)])))
        runtime['runtime_receipt']=pin(receipt)
        scheduled=[]
        def schedule(coro,**kw):scheduled.append(kw);coro.close()  # no scheduler/worker execution
        ctx=SimpleNamespace(get_config=lambda k:runtime if k=='runtime' else {'enabled':True},get_command_context=lambda:None,schedule_gateway_work=schedule,
            register_tool=lambda **kw:registry.register(name=kw['name'],toolset='retained_fixture',schema=kw['schema'],handler=kw['handler'],override=True))
        host=hostmod.WorkerHost(ctx,admitted)
        fields=dict(PLATFORM='telegram',CHAT_ID='shared-chat',CHAT_TYPE='group',THREAD_ID='same-topic',USER_ID='1',
            KEY='owned-key',ID='owned-session',MESSAGE_ID='message',PROFILE='user-1')
        variables=[contextvars.ContextVar('HERMES_SESSION_'+k) for k in fields]
        tokens=[var.set(fields[k]) for var,k in zip(variables,fields)]
        ingress=dict(platform='telegram',session_key='owned-key',source_profile='user-1',transport_profile='default',runtime_profile='user-1',chat_type='group',
            message=dict(bot_id='bot-A',user_id='1',chat_id='shared-chat',thread_id='same-topic',message_id='message',
                platform_update_id='synthetic-update',reply_to_message_id='',media=[]))
        if tamper=='foreign-account':ingress['message']['bot_id']='bot-B'
        if tamper=='foreign-user':ingress['message']['user_id']='2'
        admitted.record(admitted_ingress=ingress,session_key='owned-key',message_id='message',platform='telegram',
            source=dict(user_id=ingress['message']['user_id'],chat_id='shared-chat',thread_id='same-topic',message_id='message',profile='user-1',chat_type='group'))
        registry.register(name='friday_work',toolset='retained_fixture',schema={'name':'friday_work','description':'actual product coding boundary',
            'parameters':{'type':'object','properties':{'worker':{'type':'string'},'brief':{'type':'string'},'goal_check':{'type':'string'}},
                'required':['worker','brief','goal_check']}},handler=host.handle,override=True)
        call=dict(task_id='owned-session',session_id='owned-session',turn_id='turn',api_request_id='api',tool_call_id='tool')
        args=dict(worker='dsh',brief='Scoped coding admission fixture',goal_check='Admission and owned bytes only; no execution')
        if tamper=='forged-payload':args['user_id']='2'
        try:
            if tamper=='revoked':update(users,enabled=False);update(users)
            def bridge(_):return handle_function_call('tool_call',{'calls':[{'name':'friday_work','arguments':args}]},
                **call,enabled_toolsets=['retained_fixture'],skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
            answer=bridge(None) if tamper=='missing-correlation' else admission.native_call_scope(tool_name='friday_work',args=args,next_call=bridge,**call)
            parsed=json.loads(answer)
            if tamper=='none':
                assert parsed['accepted'] and parsed['worker']=='dsh' and parsed['submission']=='NOT_SUBMITTED'
                row=host.store.snapshot()[parsed['reference']]
                assert row['owner']['user_id']=='1' and row['owner']['profile']=='user-1'
                assert row['budget_seconds']==60 and row['stop_intent'] is None and len(scheduled)==1
                resultmod=importlib.import_module('friday_admin_controls.result_tool')
                resulttool=resultmod.register_result_tool(ctx,host)
                result_seen=[]
                def observed_result(args,**kwargs):
                    result_seen.append((args,kwargs))
                    return resulttool.handle(args,**kwargs)
                registry.get_entry('friday_result').handler=observed_result
                with pytest.raises((ValueError, RuntimeError)):
                    admission.native_call_scope(tool_name='friday_result',args={},next_call=lambda _:resultmod.owned_result(host,parsed['reference'],{**call,'tool_call_id':'forged'}),**call)
                direct_row=admission.native_call_scope(tool_name='friday_result',args={},next_call=lambda _:resultmod.owned_result(host,parsed['reference'],call),**call)
                assert direct_row==row
                result_args={'action':'status','reference':parsed['reference']}
                def result_bridge(_):
                    return handle_function_call('tool_call',{'calls':[{'name':'friday_result','arguments':result_args}]},
                        **call,enabled_toolsets=['retained_fixture'],skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
                own_result=json.loads(admission.native_call_scope(tool_name='friday_result',args=result_args,next_call=result_bridge,**call))
                assert own_result['accepted'] and own_result['reference']==parsed['reference'], json.dumps({'result':own_result,'seen':result_seen})
                # Exact duplicate cannot reset original budget or reschedule.
                again=json.loads(admission.native_call_scope(tool_name='friday_work',args=args,next_call=bridge,**call))
                assert again['reference']==parsed['reference'] and again['deadline_unix']==parsed['deadline_unix'] and len(scheduled)==1
            else:
                assert not parsed.get('accepted') and not scheduled and not host.store.snapshot()
                assert parsed['error'] in ('unproved_admission','product_user_scope_refused')
        finally:
            for var,token in zip(variables,tokens):var.reset(token)
            assert not host._a0_controllers
        # The same durable job cannot acquire a fresh capability after enable.
    if tamper=='none':
        before=copy.deepcopy(row)
        update(users,enabled=False);update(users);fresh(users)
        with users.enter(0):
            tokens=[var.set(fields[k]) for var,k in zip(variables,fields)]
            try:
                denied=json.loads(admission.native_call_scope(tool_name='friday_work',args=args,next_call=bridge,**call))
                assert not denied['accepted'] and len(scheduled)==1
                refused_result=json.loads(admission.native_call_scope(tool_name='friday_result',args=result_args,next_call=result_bridge,**call))
                assert not refused_result['accepted'] and refused_result['error']=='result_unavailable'
                with pytest.raises(scope.ScopeDenied):host._start(before)
                resultmod=importlib.import_module('friday_admin_controls.result_tool')
                with pytest.raises(scope.ScopeDenied):
                    admission.native_call_scope(tool_name='friday_result',args={},
                        next_call=lambda _:resultmod.owned_result(host,before['existing_task_id'],call),**call)
                legacy=copy.deepcopy(before);legacy['host']['binding'].pop('user_authority')
                with pytest.raises(scope.ScopeDenied):scope.check_retained_job(legacy)
                assert host.store.snapshot()[before['existing_task_id']]==before
                # At a fresh host startup, even a legacy job without marker or
                # retained metadata cannot bypass the protected root policy.
                marker=users.homes[0]/scope.MARKER; saved=marker.read_bytes();marker.unlink()
                users.monkeypatch.setattr(scope,'_ENGAGED',False)
                try:
                    with pytest.raises(scope.ScopeDenied):contextvars.Context().run(scope.check_retained_job,legacy)
                finally:marker.write_bytes(saved);marker.chmod(0o600)
            finally:
                for var,token in zip(variables,tokens):var.reset(token)
