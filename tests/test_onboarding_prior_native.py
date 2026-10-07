import os,json,copy,contextvars
from types import SimpleNamespace
import pytest
from test_user_isolation import users,native_history
from hermes_cli import friday_user_scope as scope

def test_native_readers_two_users_and_retained_foreign_denial(users):
    from tools.memory_tool import MemoryStore
    from tools.session_search_tool import session_search
    from tools.file_tools import write_file_tool,read_file_tool
    from agent.prompt_builder import _read_text_with_timeout
    from tools.registry import registry
    dbs=[native_history(users,i,content='INDEPENDENT-HISTORY-'+str(i)) for i in (0,1)]
    memories=[]
    try:
        for i in (0,1):
            with users.enter(i):
                m=MemoryStore();m.load_from_disk();assert m.add('memory','INDEPENDENT-MEMORY-'+str(i))['success'];m.load_from_disk();memories.append(m)
                assert 'INDEPENDENT-HISTORY-'+str(i) in session_search(session_id='history-'+str(i+1))
                assert 'product_user_scope_refused' in session_search(db=dbs[1-i],session_id='history-'+str(2-i))
                assert json.loads(write_file_tool('proof.txt','INDEPENDENT-FILE-'+str(i)))['success']
                assert 'INDEPENDENT-FILE-'+str(i) in read_file_tool('proof.txt')
                assert 'product_user_scope_refused' in read_file_tool(str(users.homes[1-i]/'workspace/proof.txt'))
                assert 'INDEPENDENT-FILE-'+str(i) in _read_text_with_timeout(users.homes[i]/'workspace/proof.txt')
                with pytest.raises(scope.ScopeDenied):_read_text_with_timeout(users.homes[1-i]/'workspace/proof.txt')
                assert 'product_user_scope_refused' in contextvars.Context().run(registry.dispatch,'read_file',{'path':'proof.txt'})
        with users.enter(1):
            with pytest.raises(scope.ScopeDenied):memories[0].format_for_system_prompt('memory')
            with pytest.raises(scope.ScopeDenied):memories[0].add('memory','FOREIGN-WRITE')
    finally:
        for db in dbs:db.close()

def test_disable_enable_without_old_action_must_not_revive_retained_objects(users):
    from tools.memory_tool import MemoryStore
    from agent.conversation_loop import run_conversation
    from tools.registry import registry
    calls=[]
    registry.register(name='web_extract',toolset='review',schema={'name':'web_extract','description':'synthetic','parameters':{'type':'object'}},handler=lambda args,**kw:calls.append(args) or '{}',override=True)
    with users.enter(0):
        memory=MemoryStore();memory.load_from_disk();memory.add('memory','RETAINED-PRIVATE');memory.load_from_disk()
        retained=scope.current();agent=SimpleNamespace();scope.capture_agent(agent)
        from test_admin_foundation import ProductAccess
        def admin_update(enabled):
            with scope.authority(users.root):
                return ProductAccess(users.state).set_user(platform='telegram',transport_profile='default',account_id='bot-A',user_id='1',enabled=enabled,role='user')
        admin_update(False)
        # No action on this retained capability during the disabled interval.
        admin_update(True)
        observed={}
        for name,action in [('frozen_memory',lambda:memory.format_for_system_prompt('memory')),
                            ('memory_mutation',lambda:memory.add('memory','OLD-TASK-RESUMED')),
                            ('agent',lambda:scope.check_agent(agent)),
                            ('registry',lambda:registry.dispatch('web_extract',{'query':'old retained task'}))]:
            try:
                value=str(action())
                observed[name]={'denied':(name=='registry' and json.loads(value).get('error')=='product_user_scope_refused'),'value':value}
            except scope.ScopeDenied:observed[name]={'denied':True}
        from pathlib import Path
        (Path(os.environ.get('FRIDAY_FIXTURE_EVIDENCE', Path(__file__).parent))/'revocation-counterexample.json').write_text(json.dumps({'observed':observed,'retained_revoked':retained.revoked,'synthetic_dispatch_calls':calls},indent=2)+'\n')
        assert all(value['denied'] for value in observed.values()),observed

def test_observed_disable_stays_latched_and_new_own_event_is_separate(users):
    from tools.memory_tool import MemoryStore
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    from gateway.config import Platform
    with users.enter(0):
        memory=MemoryStore();memory.load_from_disk();memory.add('memory','own retained note');memory.load_from_disk()
        users.access('1',enabled=False)
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')
        users.access('1',enabled=True)
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')
    new=SessionSource(Platform.TELEGRAM,'shared-chat',user_id='1',profile='user-1')
    new._identity=RoutingIdentity('default','user-1',users.root,users.homes[0])
    assert users.gateway._principal_authorized(new,allow_adapter_delegation=True)
    users.sources[0]=new
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')
        fresh=MemoryStore();fresh.load_from_disk();assert 'own retained note' in fresh.format_for_system_prompt('memory')

@pytest.mark.parametrize('mutation',['profile','user','transport','missing_cap'])
def test_forged_context_refuses_real_file_read_before_bytes(users,mutation):
    from tools.file_tools import read_file_tool,write_file_tool
    from gateway.session_identity import RoutingIdentity
    with users.enter(0):assert json.loads(write_file_tool('proof.txt','OWN-BYTES'))['success']
    source=users.sources[0]
    if mutation=='profile':source.profile='user-2'
    elif mutation=='user':source.user_id='2'
    elif mutation=='transport':source._identity=RoutingIdentity('other','user-1',users.root,users.homes[0])
    else:del source._friday_user_scope
    with pytest.raises(scope.ScopeDenied):
        with users.enter(0):read_file_tool('proof.txt')

@pytest.mark.parametrize('field',['user_id','profile_name','origin_json'])
def test_real_native_history_refuses_foreign_integrity(users,field):
    from tools.session_search_tool import session_search
    db=native_history(users,0,content='FOREIGN-MARKER')
    try:
        value={'user_id':'2','profile_name':'user-2','origin_json':json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1','platform':'telegram','transport_profile':'default','account_id':'bot-B'}})}[field]
        db._conn.execute('UPDATE sessions SET '+field+'=?',(value,));db._conn.commit()
        with pytest.raises(scope.ScopeDenied):
            with users.enter(0):session_search(session_id='history-1',db=db)
    finally:db.close()

def test_signed_native_admin_still_reads_both_users_with_isolation_engaged(users):
    import importlib.util,sys
    from pathlib import Path
    from starlette.requests import Request
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from hermes_cli.dashboard_auth import middleware,request_utils
    from test_admin_foundation import Administration
    import hermes_cli
    p=Path(hermes_cli.__path__[-1]).parent/'plugins/dashboard_auth/basic/__init__.py'
    spec=importlib.util.spec_from_file_location('independent_native_basic',p)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    provider=mod.BasicAuthProvider(username='owner',password_hash='synthetic-only',secret=b'REVIEW-synthetic-signing-material-32')
    users.monkeypatch.setattr(middleware,'list_session_providers',lambda:[provider])
    users.monkeypatch.setattr(request_utils,'list_session_providers',lambda:[provider])
    dbs=[native_history(users,i,content='ADMIN-USER-'+str(i)) for i in (0,1)]
    app=FastAPI();app.state.auth_required=True
    admin=Administration();observed=[]
    def request(token,profile):
        return Request({'type':'http','method':'GET','path':'/api/plugins/friday_rework/conversations/history-'+profile[-1],
                        'root_path':'','query_string':('profile='+profile).encode(),'headers':[(b'authorization',('Bearer '+token).encode())],
                        'app':app,'scheme':'http','server':('synthetic',80),'client':('synthetic',1)})
    def execute(token,profile):
        req=request(token,profile)
        async def read(req):
            # Same native auth middleware verifies the signature before the actual administration reader.
            observed.append(req.state.session.user_id)
            return JSONResponse(admin.conversation(profile,'history-'+profile[-1]))
        coro=middleware.gated_auth_middleware(req,read)
        try:coro.send(None)
        except StopIteration as done:return done.value
        finally:coro.close()
        raise AssertionError('unexpected asynchronous transport; no loop/socket permitted')
    try:
        token=provider._mint_session('owner').access_token
        for i in (0,1):
            response=execute(token,'user-'+str(i+1));assert response.status_code==200
            assert ('ADMIN-USER-'+str(i)).encode() in response.body
        assert execute(provider._mint_session('ordinary').access_token,'user-1').status_code==403
        assert execute('forged-signature','user-1').status_code==401
        assert observed==['owner','owner']
    finally:
        for db in dbs:db.close()

def test_actual_host_and_result_owner_ingress_guards(users):
    from test_admin_foundation import ROOT
    import importlib,sys
    # test_admin_foundation imports the exact product package without registering a host.
    host_module=importlib.import_module('friday_admin_controls.host')
    result_module=importlib.import_module('friday_admin_controls.result_tool')
    admission_module=importlib.import_module('friday_admin_controls.admission')
    with users.enter(0):
        fields=dict(PLATFORM='telegram',CHAT_ID='shared-chat',CHAT_TYPE='group',THREAD_ID='same-topic',USER_ID='1',KEY='owned-key',ID='owned-session',MESSAGE_ID='message',PROFILE='user-1')
        refs=[contextvars.ContextVar('HERMES_SESSION_'+key) for key in fields]
        tokens=[var.set(fields[key]) for var,key in zip(refs,fields)]
        ingress=dict(platform='telegram',source_profile='user-1',transport_profile='default',runtime_profile='user-1',chat_type='group',message=dict(bot_id='bot-A',user_id='1',chat_id='shared-chat',thread_id='same-topic'))
        call=dict(task_id='owned-session',session_id='owned-session',turn_id='turn',api_request_id='api',tool_call_id='tool')
        owner=dict(bot_id='bot-A',platform='telegram',session_key='owned-key',session_id='owned-session',user_id='1',chat_id='shared-chat',thread_id='same-topic',profile='user-1')
        row=dict(owner=owner,host={'binding':{'ingress':ingress,'runtime':{'runtime_home':str(users.homes[0])},'user_authority':{'principal_id':scope.current().key,'generation':scope.current().admission_generation}}})
        data_dir=users.state.data_dir
        host=host_module.WorkerHost.__new__(host_module.WorkerHost)
        host.store=SimpleNamespace(state=SimpleNamespace(data_dir=data_dir),snapshot=lambda:{'reference':row})
        host._state_directory=data_dir;host._closed=False
        host.admission=SimpleNamespace(match=lambda *a,**kw:(ingress,{'task_id':'owned-session','session_id':'owned-session'}))
        token=admission_module._call.set(tuple(call[k] for k in admission_module.CALL_FIELDS))
        try:
            assert result_module.owned_result(host,'reference',call) is row
            # A closed host gives a safe downstream own-user positive; no worker effects requested.
            host._closed=True
            args=dict(worker='dsh',brief='offline guard proof',goal_check='no effects')
            assert json.loads(host.handle(args,**call))['error']=='worker_not_available'
            for field,value in [('bot_id','bot-B'),('user_id','2')]:
                original=ingress['message'][field];ingress['message'][field]=value
                assert json.loads(host.handle(args,**call))['error']=='unproved_admission'
                host._closed=False
                with pytest.raises((scope.ScopeDenied,ValueError)):result_module.owned_result(host,'reference',call)
                host._closed=True;ingress['message'][field]=original
            for field,value in [('runtime_profile','user-2'),('transport_profile','other')]:
                original=ingress[field];ingress[field]=value
                assert json.loads(host.handle(args,**call))['error']=='unproved_admission'
                host._closed=False
                with pytest.raises((scope.ScopeDenied,ValueError)):result_module.owned_result(host,'reference',call)
                host._closed=True;ingress[field]=original
        finally:
            admission_module._call.reset(token)
            for var,token in zip(refs,tokens):var.reset(token)

def test_native_inline_sequential_parallel_and_dynamic_paths(users):
    from tools.memory_tool import MemoryStore
    from tools.file_tools import write_file_tool
    from tools.registry import registry
    from tools.thread_context import propagate_context_to_thread
    from agent.tool_executor import _parse_tool_call,_resolve_sequential_dispatch
    from agent.agent_runtime_helpers import invoke_tool
    from concurrent.futures import ThreadPoolExecutor
    from model_tools import handle_function_call
    calls=[]
    registry.register(name='terminal',toolset='review',schema={'name':'terminal','description':'must never execute','parameters':{'type':'object'}},handler=lambda *a,**k:calls.append('unsafe') or 'FOREIGN',override=True)
    with users.enter(0):
        m=MemoryStore();m.load_from_disk()
        agent=SimpleNamespace(_memory_store=m,_memory_manager=None,_context_engine_tool_names=set(),session_id='session',valid_tool_names={'memory','read_file','write_file'},quiet_mode=False)
        scope.capture_agent(agent)
        tc=SimpleNamespace(id='inline-call',function=SimpleNamespace(name='memory',arguments=json.dumps({'action':'add','content':'SEQUENTIAL-OWN'})))
        parsed=_parse_tool_call(agent,tc);assert parsed.parse_error is None
        dispatch=_resolve_sequential_dispatch(agent,parsed.ref('task'),[])
        assert json.loads(dispatch.execute(parsed.args))['success']
        def run_memory(content):return invoke_tool(agent,'memory',{'action':'add','content':content},'task',pre_tool_block_checked=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(propagate_context_to_thread(run_memory),'PARALLEL-OWN-'+str(i)) for i in range(2)]
            assert all(json.loads(f.result(timeout=3))['success'] for f in futures)
            assert 'product_user_scope_refused' in pool.submit(invoke_tool,agent,'terminal',{},'task').result(timeout=3)
        assert json.loads(write_file_tool('bridge.txt','BRIDGE-OWN'))['success']
        own=handle_function_call('read_file',{'path':'bridge.txt'},enabled_toolsets=['file'],skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
        assert 'BRIDGE-OWN' in own,own
        for name in ('terminal','delegate_task','manage_connections','hindsight_retain'):
            tc.function.name=name;tc.function.arguments='{}'
            assert _parse_tool_call(agent,tc).parse_error=='product_user_scope_refused'
            assert 'product_user_scope_refused' in invoke_tool(agent,name,{},'task')
            assert 'product_user_scope_refused' in handle_function_call('tool_call',{'name':name,'arguments':{}})
        assert calls==[]
        m.load_from_disk();assert 'PARALLEL-OWN-1' in m.format_for_system_prompt('memory')
    with users.enter(1):
        assert 'product_user_scope_refused' in invoke_tool(agent,'memory',{'action':'add','content':'FOREIGN-THREAD'},'task',pre_tool_block_checked=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
    assert 'FOREIGN-THREAD' not in (users.homes[0]/'memories/MEMORY.md').read_text()

def test_advertised_tool_call_schema_reaches_permitted_friday_work(users):
    from tools.registry import registry
    from tools import tool_search
    from model_tools import handle_function_call
    from pathlib import Path
    seen=[]
    registry.register(name='friday_work',toolset='review_work',schema={'name':'friday_work','description':'synthetic scoped worker boundary','parameters':{'type':'object','properties':{'brief':{'type':'string'}},'required':['brief']}},handler=lambda args,**kw:seen.append(scope.current().key) or json.dumps({'synthetic_admitted':True}),override=True)
    legacy={'name':'friday_work','arguments':{'brief':'synthetic no worker launch'}}
    advertised={'calls':[legacy]}
    with users.enter(0):
        assert tool_search.is_deferrable_tool_name('friday_work')
        kwargs=dict(enabled_toolsets=['review_work'],skip_pre_tool_call_hook=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
        old=handle_function_call('tool_call',legacy,**kwargs)
        public=handle_function_call('tool_call',advertised,**kwargs)
        (Path(os.environ.get('FRIDAY_FIXTURE_EVIDENCE', Path(__file__).parent))/'dynamic-counterexample.json').write_text(json.dumps({'legacy':old,'advertised_calls':public,'dispatches':seen},indent=2)+'\n')
        assert json.loads(old).get('synthetic_admitted') is True,old
        assert json.loads(public).get('synthetic_admitted') is True,public
