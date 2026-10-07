"""Actual native authorization, profiles, memory, history and file entrypoints.

Synthetic identities/private state only. No sockets/models/workers/live journey.
"""
import asyncio
from contextlib import nullcontext
import contextvars
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_cli import friday_user_scope as scope
from hermes_cli.plugins_state import PluginState
from hermes_cli.friday_product_access import KEY, principal_id
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway.authz_mixin import GatewayAuthorizationMixin
from gateway.config import Platform
from gateway.session import SessionSource
from gateway.session_identity import RoutingIdentity
from hermes_state import SessionDB


@pytest.fixture
def users(tmp_path, monkeypatch):
    # Native startup discovers builtins before an admission fixture snapshots
    # the registry. Otherwise teardown erases late first-import registrations
    # while Python keeps their modules cached, corrupting later package cases.
    import model_tools
    from tools.registry import registry
    with registry._lock:
        saved_tools = dict(registry._tools); saved_checks = dict(registry._toolset_checks)
    root = tmp_path / 'home'; root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(root))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(root))
    monkeypatch.setenv('GATEWAY_ALLOWED_USERS', '*')
    monkeypatch.setattr(scope, '_ENGAGED', False)
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('fixture_scope', default=None))
    for key in ('TELEGRAM_ALLOWED_USERS', 'GATEWAY_ALLOW_ALL_USERS', 'TELEGRAM_ALLOW_ALL_USERS'):
        monkeypatch.delenv(key, raising=False)
    bindings = [dict(platform='telegram', transport_profile='default', account_id='bot-A',
                     user_id=uid, runtime_profile='user-' + uid,
                     tools=['memory', 'session_search', 'read_file', 'write_file', 'web_search',
                            'web_extract', 'friday_work', 'friday_result']) for uid in ('1', '2')]
    settings = {'product_access': {'enabled': True, 'accounts': [dict(platform='telegram',
        transport_profile='default', account_id='bot-A', runtime_profiles=['user-1', 'user-2'])]},
        'user_isolation': {'enabled': True, 'bindings': bindings},
        'admin': {'enabled': True, 'operators': [dict(provider='basic', user_id='owner', org_id='')],
                  'profiles': ['default', 'user-1', 'user-2']}}
    cfg = {'plugins': {'enabled': ['friday_rework'], 'entries': {'friday_rework': {'settings': settings}}}}
    def save():
        (root / 'config.yaml').write_text(json.dumps(cfg)); (root / 'config.yaml').chmod(0o600)
    save()
    home_token = set_hermes_home_override(str(root))
    state = PluginState('friday_rework')
    rows = {principal_id(*(b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))):
            {k: b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')} |
            {'enabled': True, 'role': 'user'} for b in bindings}
    def access(uid, enabled=True, role='user'):
        row = next(v for v in rows.values() if v['user_id'] == uid)
        row.update(enabled=enabled, role=role)
        with scope.authority(root):
            state.set(KEY, {'schema': KEY, 'users': rows})
    access('1'); access('2')
    homes = [scope.provision_new_home(root, b, {'model': {'default': 'local-test',
        'provider': 'custom', 'base_url': 'http://127.0.0.1:9000/v1'}, 'max_iterations': 8}) for b in bindings]
    sources = []
    gateway = GatewayAuthorizationMixin()
    for b, home in zip(bindings, homes):
        source = SessionSource(Platform.TELEGRAM, 'shared-chat', user_id=b['user_id'],
                               chat_type='group', thread_id='same-topic', profile=b['runtime_profile'])
        source._identity = RoutingIdentity('default', b['runtime_profile'], root, home,
                                           multiplexed=True, transport_inferred=False)
        assert gateway._principal_authorized(source, allow_adapter_delegation=True)
        sources.append(source)
    @scope.contextmanager
    def enter(index):
        token = set_hermes_home_override(str(homes[index]))
        try:
            with scope.scoped_source(sources[index]) as cap:
                yield cap
        finally:
            reset_hermes_home_override(token)
    try:
        yield SimpleNamespace(root=root, cfg=cfg, settings=settings, bindings=bindings, homes=homes,
            sources=sources, gateway=gateway, state=state, access=access, enter=enter, save=save,
            monkeypatch=monkeypatch)
    finally:
        reset_hermes_home_override(home_token)
        with registry._lock:
            registry._tools = saved_tools; registry._toolset_checks = saved_checks
            registry._generation += 1


def native_history(users, index, sid=None, content=None, **change):
    b = users.bindings[index]; home = users.homes[index]
    sid = sid or 'history-' + b['user_id']; content = content or 'own-history-' + b['user_id']
    token = set_hermes_home_override(str(home))
    try:
        db = SessionDB(home / 'state.db')
        account = {'schema': 'friday.account_origin.v1', **{k:b[k] for k in
                   ('platform', 'transport_profile', 'account_id')}}
        db.create_session(sid, 'telegram', user_id=b['user_id'], profile_name=b['runtime_profile'],
            origin_json=json.dumps({'friday_account_origin': account}), **change)
        db.append_message(sid, 'user', content)
        return db
    finally:
        reset_hermes_home_override(token)


def test_two_native_users_own_memory_history_and_files(users):
    from tools.memory_tool import MemoryStore, memory_tool
    from tools.session_search_tool import session_search
    from tools.file_tools import read_file_tool, write_file_tool
    dbs = [native_history(users, i) for i in range(2)]
    try:
        for i in range(2):
            with users.enter(i):
                memory = MemoryStore(); memory.load_from_disk()
                result = json.loads(memory_tool(action='add', content='own-memory-' + str(i), store=memory))
                assert result['success']
                memory.load_from_disk()
                assert 'own-memory-' + str(i) in memory.format_for_system_prompt('memory')
                assert 'own-memory-' + str(1-i) not in memory.format_for_system_prompt('memory')
                history = session_search(session_id='history-' + str(i+1), db=dbs[i])
                assert 'own-history-' + str(i+1) in history
                assert 'own-history-' + str(2-i) not in history
                assert json.loads(write_file_tool('own.txt', 'own-file-' + str(i)))['success']
                read = read_file_tool('own.txt')
                assert 'own-file-' + str(i) in read and 'own-file-' + str(1-i) not in read
    finally:
        for db in dbs: db.close()


@pytest.mark.parametrize('foreign', ['user-2', 'default', '../user-2', '/tmp/foreign'])
def test_cross_profile_history_refused_before_profile_reader(users, foreign):
    from tools import session_search_tool as tool
    calls = []
    users.monkeypatch.setattr(tool, '_resolve_profile_db', lambda *a: calls.append(a))
    with users.enter(0):
        result = tool.session_search(profile=foreign, session_id='secret')
    assert 'product_user_scope_refused' in result and calls == []


def test_embedded_profile_and_caller_database_refused(users):
    from tools.session_search_tool import session_search
    foreign = native_history(users, 1)
    try:
        with users.enter(0):
            for args in [dict(session_id='user-2/history-2'), dict(db=foreign, session_id='history-2')]:
                assert 'product_user_scope_refused' in session_search(**args)
    finally:
        foreign.close()


@pytest.mark.parametrize('alteration', ['user', 'account', 'profile', 'missing_origin'])
def test_mixed_or_unproved_store_refuses_before_transcript_bytes(users, alteration):
    db = native_history(users, 0)
    calls = []
    try:
        with db._lock:
            if alteration == 'user': db._conn.execute("UPDATE sessions SET user_id='2'")
            elif alteration == 'profile': db._conn.execute("UPDATE sessions SET profile_name='user-2'")
            elif alteration == 'missing_origin': db._conn.execute('UPDATE sessions SET origin_json=NULL')
            else:
                db._conn.execute('UPDATE sessions SET origin_json=?', (json.dumps({'friday_account_origin':
                    {'schema': 'friday.account_origin.v1', 'platform':'telegram', 'transport_profile':'default',
                     'account_id':'another-bot'}}),))
        users.monkeypatch.setattr(db, 'get_messages', lambda *a: calls.append(a))
        with pytest.raises(scope.ScopeDenied):
            with users.enter(0): pass
        assert calls == []
    finally:
        db.close()


@pytest.mark.parametrize('kind', ['disable', 'binding', 'account', 'remove_policy', 'corrupt'])
def test_retained_memory_prompt_and_next_action_recheck_revocation(users, kind):
    from tools.memory_tool import MemoryStore
    from tools.registry import registry
    called = []
    registry.register(name='web_search', toolset='isolation-test', schema={'name':'web_search',
        'description':'synthetic bounded transport', 'parameters':{'type':'object'}},
        handler=lambda args, **kw: called.append(args) or json.dumps({'own':True}),override=True)
    with users.enter(0):
        memory = MemoryStore(); memory.load_from_disk(); memory.add('memory', 'own retained note')
        if kind == 'disable': users.access('1', enabled=False)
        elif kind == 'binding': users.bindings[0]['tools'].remove('web_search'); users.save()
        elif kind == 'account': users.settings['product_access']['accounts'][0]['account_id']='bot-B'; users.save()
        elif kind == 'remove_policy': users.settings.pop('user_isolation'); users.save()
        else: (users.root/'config.yaml').write_text('invalid: [')
        with pytest.raises(scope.ScopeDenied): memory.format_for_system_prompt('memory')
        assert 'product_user_scope_refused' in registry.dispatch('web_search', {'query':'research'})
        assert not called
        users.access('1', enabled=True)
        with pytest.raises(scope.ScopeDenied): memory.format_for_system_prompt('memory')


def test_retained_memory_cannot_cross_current_user(users):
    from tools.memory_tool import MemoryStore, memory_tool
    with users.enter(0):
        memory = MemoryStore(); memory.load_from_disk(); assert memory.add('memory','user-one')['success']
    with users.enter(1):
        with pytest.raises(scope.ScopeDenied): memory.format_for_system_prompt('memory')
        assert 'product_user_scope_refused' in memory_tool(action='add', content='foreign', store=memory)
    assert 'foreign' not in (users.homes[0]/'memories/MEMORY.md').read_text()


@pytest.mark.parametrize('path', ['../user-2/private.txt', '/etc/passwd', '~/.env', '.env',
    'nested/../../secret', str(Path('/tmp')/'another-user')])
def test_file_paths_do_not_enlarge_scope(users, path):
    from tools.file_tools import read_file_tool, write_file_tool
    with users.enter(0):
        assert 'product_user_scope_refused' in read_file_tool(path)
        assert 'product_user_scope_refused' in write_file_tool(path, 'unauthorized')


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'parent_symlink', 'fifo', 'loose'])
def test_file_inode_paths_refused_without_bytes_or_write(users, kind):
    from tools.file_tools import read_file_tool, write_file_tool
    foreign = users.homes[1]/'workspace/secret.txt'; foreign.write_text('SECRET-USER-2'); foreign.chmod(0o600)
    root = users.homes[0]/'workspace'; path=root/'foreign.txt'
    if kind=='symlink': path.symlink_to(foreign)
    elif kind=='hardlink': os.link(foreign,path)
    elif kind=='parent_symlink': (root/'nested').symlink_to(foreign.parent);path=root/'nested/secret.txt'
    elif kind=='fifo':os.mkfifo(path,0o600)
    else:path.write_text('SECRET');path.chmod(0o644)
    with users.enter(0):
        result=read_file_tool(str(path));assert 'product_user_scope_refused' in result and 'SECRET' not in result
        assert 'product_user_scope_refused' in write_file_tool(str(path),'clobber')
    assert foreign.read_text()=='SECRET-USER-2'


@pytest.mark.parametrize('name', ['terminal', 'execute_code', 'delegate_task', 'cronjob_manage',
    'browser_console', 'manage_connections', 'connectors__other__read', 'search_files', 'patch'])
def test_registry_dynamic_direct_and_nested_dispatch_cannot_bypass(users,name):
    from tools.registry import registry
    called=[]
    registry.register(name=name,toolset='isolation-test',schema={'name':name,'description':'unsafe fixture',
        'parameters':{'type':'object'}},handler=lambda args,**kw:called.append(args) or 'SECRET',override=True)
    from model_tools import handle_function_call
    with users.enter(0):
        assert 'product_user_scope_refused' in registry.dispatch(name,{})
        assert 'product_user_scope_refused' in handle_function_call(name,{})
        assert 'product_user_scope_refused' in handle_function_call('tool_call',{'name':name,'arguments':{}})
    assert not called


def test_forged_registry_scope_and_lost_thread_context_refuse(users):
    from tools.registry import registry
    with users.enter(0):
        assert 'product_user_scope_refused' in registry.dispatch('memory',{},scope=str(users.homes[1]))
        empty=contextvars.Context()
        assert 'product_user_scope_refused' in empty.run(registry.dispatch,'web_search',{})
        inherited=contextvars.copy_context()
        assert inherited.run(scope.current).key==scope.current().key


@pytest.mark.parametrize('forgery',['user','runtime','missing_cap','role','inferred','same_id_account'])
def test_actual_native_admission_and_scope_reject_context_forgery(users,forgery):
    source=users.sources[0]
    if forgery=='user':source.user_id='2'
    elif forgery=='runtime':source._identity=RoutingIdentity('default','user-2',users.root,users.homes[1])
    elif forgery=='missing_cap':del source._friday_user_scope
    elif forgery=='role':source.role_authorized=True;users.access('1',enabled=False,role='admin')
    elif forgery=='inferred':source._identity=RoutingIdentity('default','user-1',users.root,users.homes[0],transport_inferred=True)
    else:
        source._identity=RoutingIdentity('other','user-1',users.root,users.homes[0]);source.user_id='1'
    if forgery not in ('missing_cap','user'):
        assert not users.gateway._principal_authorized(source,allow_adapter_delegation=True)
    with pytest.raises(scope.ScopeDenied):
        with users.enter(0):pass


def test_no_existing_home_or_secret_context_bootstrap(users):
    with pytest.raises(FileExistsError):scope.provision_new_home(users.root,users.bindings[0],{})
    with pytest.raises(scope.ScopeDenied):scope.provision_new_home(users.root,users.bindings[0],{'env':{'KEY':'other'}})
    with pytest.raises(scope.ScopeDenied):scope.provision_new_home(users.root,users.bindings[0],{'model':{'api_key':'owner'}})
    for home in users.homes:
        assert set(p.name for p in home.iterdir())=={'config.yaml','config.yaml.lock',scope.MARKER,'memories','workspace'}
        lock=home/'config.yaml.lock';assert lock.read_bytes()==b'' and lock.stat().st_nlink==1
        assert lock.stat().st_uid==__import__('os').getuid() and not lock.stat().st_mode & 0o077


def test_shared_runtime_binding_refused(users):
    users.bindings[1]['runtime_profile']='user-1';users.save()
    assert not users.gateway._principal_authorized(users.sources[0],allow_adapter_delegation=True)


def test_worker_owner_intersection_preserves_original_context(users):
    with users.enter(0) as cap:
        owner=dict(platform='telegram',user_id='1',profile='user-1',chat_id='shared-chat',thread_id='same-topic')
        ingress=dict(platform='telegram',transport_profile='default',runtime_profile='user-1',source_profile='user-1',
                     message=dict(bot_id='bot-A',user_id='1',chat_id='shared-chat',thread_id='same-topic'))
        cap.require_owner(owner,ingress)
        for change in ({'user_id':'2'},{'profile':'user-2'},{'platform':'discord'}):
            with pytest.raises(scope.ScopeDenied):cap.require_owner(owner|change,ingress)
        forged=copy.deepcopy(ingress);forged['message']['bot_id']='bot-B'
        with pytest.raises(scope.ScopeDenied):cap.require_owner(owner,forged)
        assert 'friday_work' in cap.binding['tools']
        assert owner==dict(platform='telegram',user_id='1',profile='user-1',chat_id='shared-chat',thread_id='same-topic')


def test_web_transport_dispatch_keeps_auth_scope_and_both_users_progress(users):
    # Synthetic transport, not a retrieved source/live web journey. The actual
    # native registry executes it under each authenticated user and rechecks.
    from tools.registry import registry
    seen=[]
    def transport(args,**kw):
        cap=scope.current(required=True);seen.append(cap.principal)
        return json.dumps({'scope':cap.key,'query':args['query']})
    registry.register(name='web_extract',toolset='isolation-test',schema={'name':'web_extract',
        'description':'bounded synthetic transport', 'parameters':{'type':'object'}},handler=transport,override=True)
    for i in range(2):
        with users.enter(i) as cap:
            result=json.loads(registry.dispatch('web_extract',{'query':'documentation gap'}))
            assert result['scope']==cap.key
    assert seen==[('telegram','default','bot-A','1'),('telegram','default','bot-A','2')]


def test_actual_native_gateway_profile_wrapper_binds_before_memory_and_tools(users):
    from gateway.run_turn import GatewayTurnMixin
    from tools.memory_tool import MemoryStore
    class Runner(GatewayTurnMixin):
        config=SimpleNamespace(multiplex_profiles=True)
        def _resolve_profile_home_for_source(self,source):return source._identity.runtime_home
    runner=Runner()
    from hermes_constants import get_hermes_home
    for i in range(2):
        with runner._profile_scope_for_source(users.sources[i]):
            assert get_hermes_home()==users.homes[i]
            assert scope.current().principal[3]==str(i+1)
            memory=MemoryStore();memory.load_from_disk()
            assert memory.add('memory','native-profile-own-'+str(i))['success']
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')


def test_actual_native_async_profile_wrapper_keeps_same_principal(users):
    from gateway.run_turn import GatewayTurnMixin
    class Runner(GatewayTurnMixin):
        config=SimpleNamespace(multiplex_profiles=True)
        def _resolve_profile_home_for_source(self,source):return source._identity.runtime_home
    async def check():
        for i in range(2):
            async with Runner()._async_profile_scope_for_source(users.sources[i]):
                assert scope.current().principal[3]==str(i+1)
                await asyncio.sleep(0)  # scheduler boundary, no waiting or polling
                assert scope.current().profile=='user-'+str(i+1)
    asyncio.run(check())


def test_product_channel_role_cannot_acquire_admin_read_all(users):
    import time
    from hermes_cli.dashboard_auth.base import Session
    from hermes_cli.friday_product_access import session_allowed
    users.access('1',role='admin')
    # A changed product role revokes the old admission, without granting signed
    # Dashboard authority. Check the independently authorized new event.
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    from gateway.config import Platform
    fresh = SessionSource(Platform.TELEGRAM, 'shared-chat', user_id='1', profile='user-1')
    fresh._identity = RoutingIdentity('default', 'user-1', users.root, users.homes[0])
    assert users.gateway._principal_authorized(fresh, allow_adapter_delegation=True)
    users.sources[0] = fresh
    token=Session(user_id='owner',provider='basic',org_id='',expires_at=int(time.time())+300,
                  email='',display_name='',access_token='synthetic',refresh_token='')
    assert session_allowed(token)
    ordinary=Session(user_id='1',provider='basic',org_id='',expires_at=int(time.time())+300,
                     email='',display_name='owner',access_token='synthetic',refresh_token='')
    assert not session_allowed(ordinary)
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):scope.guard_tool('terminal',{'command':'read-all'})


@pytest.mark.parametrize('kind',['memory_link','marker_link','home_swap','config_link'])
def test_retained_private_home_cannot_be_replaced_or_linked(users,kind):
    from tools.memory_tool import MemoryStore
    home=users.homes[0]
    with users.enter(0):
        memory=MemoryStore();memory.load_from_disk()
        if kind=='memory_link':
            foreign=users.homes[1]/'memories/MEMORY.md';foreign.write_text('FOREIGN-MEMORY');foreign.chmod(0o600)
            (home/'memories/MEMORY.md').symlink_to(foreign)
        elif kind=='marker_link':
            (home/scope.MARKER).unlink();(home/scope.MARKER).symlink_to(users.homes[1]/scope.MARKER)
        elif kind=='config_link':
            (home/'config.yaml').unlink();(home/'config.yaml').symlink_to(users.root/'config.yaml')
        else:
            home.rename(home.with_name('retired'));home.mkdir(mode=0o700)
        with pytest.raises(scope.ScopeDenied):memory.load_from_disk()
        with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')


@pytest.mark.parametrize('name',['delegate_task','cronjob_manage','manage_connections','hindsight_retain','terminal'])
def test_native_agent_inline_parallel_and_sequential_boundaries_refuse(users,name):
    from agent.agent_runtime_helpers import invoke_tool
    from agent.tool_executor import _parse_tool_call, _resolve_sequential_dispatch
    called=[]
    agent=SimpleNamespace(_dispatch_delegate_task=lambda *a:called.append(a),
                          _memory_manager=SimpleNamespace(has_tool=lambda *a:True,
                              handle_tool_call=lambda *a:called.append(a)))
    tc=SimpleNamespace(id='call',function=SimpleNamespace(name=name,arguments='{}'))
    with users.enter(0):
        parsed=_parse_tool_call(agent,tc)
        assert parsed.parse_error=='product_user_scope_refused'
        assert 'product_user_scope_refused' in invoke_tool(agent,name,{},'own-task')
        dispatch=_resolve_sequential_dispatch(agent,parsed.ref('own-task'),[])
        assert 'product_user_scope_refused' in dispatch.execute({})
    assert not called


def test_native_runtime_prompt_context_uses_only_own_workspace(users):
    from agent.runtime_cwd import resolve_agent_cwd,resolve_context_cwd,set_session_cwd,reset_session_cwd
    from agent.prompt_builder import _read_text_with_timeout
    foreign=users.root/'SOUL.md';foreign.write_text('OWNER-PRIVATE-CONTEXT');foreign.chmod(0o600)
    for i in range(2):
        own=users.homes[i]/'workspace/AGENTS.md';own.write_text('Own useful instructions '+str(i));own.chmod(0o600)
        with users.enter(i):
            token=set_session_cwd(str(users.root))
            try:
                assert resolve_agent_cwd()==users.homes[i]/'workspace'
                assert resolve_context_cwd()==users.homes[i]/'workspace'
                assert 'Own useful instructions '+str(i) in _read_text_with_timeout(own)
                with pytest.raises(scope.ScopeDenied):_read_text_with_timeout(foreign)
                with pytest.raises(scope.ScopeDenied):_read_text_with_timeout(users.homes[1-i]/'workspace/AGENTS.md')
            finally:reset_session_cwd(token)


@pytest.mark.parametrize('command',['login','exec','model','sethome','skills','config','custom-quick-shell','tools'])
def test_native_slash_sink_refuses_unsafe_config_shell_and_unknown_plugin(users,command):
    from gateway.run_busy import GatewayBusySessionMixin
    assert GatewayBusySessionMixin()._check_slash_access(users.sources[0],command).startswith('product_user_scope_refused')
    assert scope.slash_allowed(users.sources[0],'memory')
    assert scope.slash_allowed(users.sources[0],'stop')


@pytest.mark.parametrize('endpoint',['https://cloud.example/v1','http://0.0.0.0/v1',
    'http://127.0.0.1/v1?key=secret','http://name.local/v1','http://127.0.0.1/other'])
def test_home_bootstrap_cannot_introduce_cloud_inference_or_arbitrary_endpoint(users,endpoint):
    with pytest.raises(scope.ScopeDenied):scope.provision_new_home(users.root,users.bindings[0],
        {'model':{'default':'test','provider':'custom','base_url':endpoint}})


def test_cached_native_memory_remains_useful_on_next_authenticated_own_event(users):
    from tools.memory_tool import MemoryStore
    with users.enter(0):
        memory=MemoryStore();memory.load_from_disk();assert memory.add('memory','own persistent memory')['success']
        memory.load_from_disk()
    source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id='1',chat_type='group',
                         thread_id='same-topic',profile='user-1')
    source._identity=RoutingIdentity('default','user-1',users.root,users.homes[0])
    assert users.gateway._principal_authorized(source,allow_adapter_delegation=True)
    assert source._friday_user_scope is not users.sources[0]._friday_user_scope
    users.sources[0]=source
    with users.enter(0):
        assert 'own persistent memory' in memory.format_for_system_prompt('memory')
        assert memory.add('user','own user profile')['success']


def test_actual_cached_agent_turn_and_api_boundaries_reject_foreign_or_revoked_context(users):
    from agent.conversation_loop import run_conversation
    from agent.turn_api_call import perform_api_call
    agent=SimpleNamespace()
    with users.enter(0):scope.capture_agent(agent);scope.check_agent(agent)
    with users.enter(1):
        with pytest.raises(scope.ScopeDenied):run_conversation(agent,'foreign task',conversation_history=[{'content':'owned-user-one'}])
    with users.enter(0):
        users.access('1',enabled=False)
        with pytest.raises(scope.ScopeDenied):perform_api_call(agent,api_kwargs={},_original_api_kwargs={},
            _llm_middleware_trace=[],_moa_prepared_request=None,_retry=None,thinking_spinner=None,
            retry_count=0,api_call_count=0,api_request_id='call',effective_task_id='task',turn_id='turn',interrupted=False)


def test_same_user_id_in_second_configured_native_account_is_a_distinct_principal(users):
    from tools.memory_tool import MemoryStore
    other=users.root/'profiles/other';other.mkdir(mode=0o700)
    binding=dict(platform='telegram',transport_profile='other',account_id='bot-B',user_id='1',
                 runtime_profile='account-B-user-1',tools=['memory','session_search','read_file','write_file'])
    cfg={'plugins':{'entries':{'friday_rework':{'settings':{
        'product_access':{'enabled':True,'accounts':[dict(platform='telegram',transport_profile='other',
            account_id='bot-B',runtime_profiles=['account-B-user-1'])]},
        'user_isolation':{'enabled':True,'bindings':[binding]}}}}}}
    (other/'config.yaml').write_text(json.dumps(cfg));(other/'config.yaml').chmod(0o600)
    with scope.authority(other):
        state=PluginState('friday_rework')
        row={k:binding[k] for k in ('platform','transport_profile','account_id','user_id')}|{'enabled':True,'role':'user'}
        state.set(KEY,{'schema':KEY,'users':{principal_id(*(row[k] for k in
            ('platform','transport_profile','account_id','user_id'))):row}})
    home=scope.provision_new_home(other,binding,{})
    source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id='1',profile='account-B-user-1')
    source._identity=RoutingIdentity('other','account-B-user-1',other,home)
    assert users.gateway._principal_authorized(source,allow_adapter_delegation=True)
    with users.enter(0):
        memory=MemoryStore();memory.load_from_disk();memory.add('memory','ACCOUNT-A-PRIVATE')
        memory.load_from_disk()
    with scope.authority(home):
        with scope.scoped_source(source) as cap:
            assert cap.principal==('telegram','other','bot-B','1')
            with pytest.raises(scope.ScopeDenied):memory.format_for_system_prompt('memory')
            own=MemoryStore();own.load_from_disk()
            assert own.add('memory','ACCOUNT-B-OWN')['success']
            own.load_from_disk()
            assert 'ACCOUNT-B-OWN' in own.format_for_system_prompt('memory')
            assert 'ACCOUNT-A-PRIVATE' not in own.format_for_system_prompt('memory')
