"""Actual native onboarding, scopes, routing, credential writer and Dashboard APIs.

Two synthetic principals and local-only setup; no socket, provider or worker run.
"""
import asyncio
import contextvars
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_product_access import principal_id, current_access
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from test_admin_foundation import Administration, ProductAccess, mounted_app
from tools.configure_local_test import build_config
from tools.web_profile import research_policy
from friday_admin_controls.onboarding import Onboarding, validate_template


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / 'home'; home.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(home))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(home))
    for name in ('GATEWAY_ALLOWED_USERS', 'GATEWAY_ALLOW_ALL_USERS', 'TELEGRAM_ALLOWED_USERS',
                 'TELEGRAM_ALLOW_ALL_USERS', 'EXA_API_KEY', 'LOCAL_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(scope, '_ENGAGED', False)
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('onboarding_scope', default=None))
    config = build_config(base_url='http://127.0.0.1:9000/v1', model='observed-local',
        key_env='LOCAL_KEY', context=32768, max_input=24576, main_output=4096,
        summary_output=2048, margin=1024, template_overhead=512, web_profile='exa-paid')
    config['memory'].update(memory_enabled=True, user_profile_enabled=True)
    config['plugins']['enabled'].append('friday_rework')
    config['plugins']['entries'] = {'friday_rework': {'allow_gateway_work': True, 'allow_gateway_control': True,
        'settings': {'runtime': {'enabled': False}, 'results': {'enabled': True}}}}
    config['toolsets'] = ['web', 'memory', 'file', 'session_search', 'friday_rework']
    config['platform_toolsets'] = {'cli': config['toolsets'], 'telegram': config['toolsets']}
    config.pop('mcp_servers');config.pop('mcp')
    template = {'config': config, 'tools': sorted(scope.SAFE), 'required_secrets': ['LOCAL_KEY', 'EXA_API_KEY']}
    settings = {'product_access': {'enabled': True, 'accounts': [dict(platform='telegram',
        transport_profile='default', account_id='bot-A', runtime_profiles=['default'])]},
        'admin': {'enabled': True, 'operators': [dict(provider='basic', user_id='owner', org_id='')],
                  'profiles': ['default']}, 'onboarding': {'templates': {'approved-local': template}}}
    cfg = {'plugins': {'enabled': ['friday_rework'], 'entries': {'friday_rework': {'settings': settings}}},
           'gateway': {'multiplex_profiles': True, 'profile_routes': []}, 'owner_unrelated': 'PRESERVE_ME'}
    (home / 'config.yaml').write_text(json.dumps(cfg));(home / 'config.yaml').chmod(0o600)
    token = set_hermes_home_override(str(home))
    try:
        yield SimpleNamespace(home=home, cfg=cfg, template=template, monkeypatch=monkeypatch,
            state=PluginState('friday_rework'), admin=Administration(), setup=Onboarding(Administration()))
    finally: reset_hermes_home_override(token)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ident(uid='1'): return dict(platform='telegram', transport_profile='default', account_id='bot-A', user_id=uid)
def cas(env): return sha(env.home / 'config.yaml')
def prepare(env, uid='1', **changes):
    return env.setup.prepare('default', expected_config_sha256=cas(env), template='approved-local',
        runtime_profile='user-' + uid, **(ident(uid) | changes))
def row(env, uid='1'): return current_access(env.state)['users'][principal_id(**ident(uid))]
def home(env, uid='1'): return env.home / 'profiles' / ('user-' + uid)
def secrets(env, uid='1'):
    for name in env.template['required_secrets']:
        env.setup.credentials('default', expected_config_sha256=cas(env), generation=row(env, uid)['generation'],
                              **ident(uid), name=name, value='synthetic-' + uid + '-' + name)
def grant(env, uid='1'):
    from gateway.pairing import PairingStore
    store=PairingStore();store.generate_code('telegram',uid,'same display name')
    ref=next(r['request_id'] for r in store.list_pending() if r['user_id']==uid)
    return store.approve_request('telegram',ref)
def activate(env, uid='1', generation=None):
    return env.setup.activate('default', expected_config_sha256=cas(env),
        generation=row(env,uid)['generation'] if generation is None else generation, **ident(uid))
def source(env, uid='1', chat='shared-chat', thread='topic'):
    from gateway.session import SessionSource
    from gateway.config import Platform
    from gateway.session_identity import RoutingIdentity
    from gateway.profile_routing import parse_profile_routes, match_profile_route
    from hermes_cli.config import load_config_readonly
    cfg=load_config_readonly()
    route=match_profile_route(parse_profile_routes(cfg['gateway']['profile_routes']), 'telegram',
        user_id=uid,chat_id=chat,thread_id=thread,adapter_profile='default')
    value=SessionSource(Platform.TELEGRAM, chat, user_id=uid,thread_id=thread,profile=route.profile if route else None)
    value._identity=RoutingIdentity('default',route.profile if route else 'default',env.home,
        home(env,uid) if route else env.home,multiplexed=True,transport_inferred=False)
    return value

def admitted(env, uid='1'):
    from gateway.authz_mixin import GatewayAuthorizationMixin
    from gateway.pairing import PairingStore
    gateway=GatewayAuthorizationMixin();gateway.pairing_store=PairingStore()
    s=source(env,uid)
    return gateway._principal_authorized(s, allow_adapter_delegation=True),s

def complete(env, uid='1'):
    result=prepare(env,uid);secrets(env,uid);grant(env,uid);assert activate(env,uid)['enabled']
    return result

def raw(env):
    from hermes_cli.config import require_readable_config_before_write
    return require_readable_config_before_write(env.home/'config.yaml')
def save(env, value):
    from hermes_cli.config import atomic_config_write
    atomic_config_write(env.home/'config.yaml', value)


def test_two_principals_actual_setup_native_route_credentials_persona_and_admission(env):
    results=[complete(env,uid) for uid in ('1','2')]
    assert results[0]['principal_id'] != results[1]['principal_id']
    from agent.secret_scope import load_env_file, set_secret_scope, reset_secret_scope, get_secret
    from hermes_cli.config import load_config_readonly
    for uid in ('1','2'):
        accepted,s=admitted(env,uid);assert accepted
        token=set_hermes_home_override(str(home(env,uid)))
        try:
            with scope.scoped_source(s) as cap:
                assert cap.principal==('telegram','default','bot-A',uid)
                assert cap.profile=='user-'+uid
                local=load_env_file(home(env,uid)/'.env');t=set_secret_scope(local,profile_home=str(home(env,uid)))
                try:assert get_secret('LOCAL_KEY')=='synthetic-'+uid+'-LOCAL_KEY'
                finally:reset_secret_scope(t)
                cfg=load_config_readonly();assert cfg['model']['base_url']=='http://127.0.0.1:9000/v1'
                assert cfg['memory']['memory_enabled'] and cfg['memory']['user_profile_enabled']
                assert cfg['agent']['environment_hint']==research_policy()
                assert {'web/exa','friday_rework'}<=set(cfg['plugins']['enabled'])
                assert set(cap.binding['tools'])==scope.SAFE
                assert sha(home(env,uid)/'SOUL.md')==sha(Path(__file__).parents[1]/'config/SOUL.md')
        finally:reset_hermes_home_override(token)
    cfg=raw(env);assert cfg['owner_unrelated']=='PRESERVE_ME'
    assert len(cfg['gateway']['profile_routes'])==2
    assert not any((home(env,uid)/name).exists() for uid in ('1','2') for name in ('state.db','USER.md','MEMORY.md'))
    assert all(not list((home(env,uid)/'skills').iterdir()) for uid in ('1','2'))


def test_prepared_disabled_and_no_ambient_secret_or_context_copy(env):
    env.monkeypatch.setenv('LOCAL_KEY','ambient-canary');env.monkeypatch.setenv('EXA_API_KEY','owner-web-canary')
    (env.home/'USER.md').write_text('OWNER_CONTEXT_CANARY')
    (env.home/'SOUL.md').write_text('OWNER_PERSONA_CANARY')
    result=prepare(env);assert not result['enabled'] and row(env)['enabled'] is False
    assert not (home(env)/scope.MARKER).exists() and not (home(env)/'.env').exists()
    assert not admitted(env)[0]
    assert all(canary not in p.read_text() for p in home(env).rglob('*') if p.is_file()
               for canary in ('ambient-canary','owner-web-canary','OWNER_CONTEXT_CANARY','OWNER_PERSONA_CANARY'))


def test_native_grant_missing_stays_disabled(env):
    prepare(env);secrets(env)
    result=activate(env);assert result['state']=='DISABLED_NATIVE_GRANT_MISSING' and not result['enabled']
    assert not (home(env)/scope.MARKER).exists() and not admitted(env)[0]


@pytest.mark.parametrize('missing',['all','LOCAL_KEY','EXA_API_KEY'])
def test_missing_scoped_credentials_never_admit(env,missing):
    prepare(env);grant(env)
    for name in env.template['required_secrets']:
        if missing not in ('all',name):
            env.setup.credentials('default', expected_config_sha256=cas(env),generation=row(env)['generation'],
                                  **ident(),name=name,value='synthetic-only')
    assert activate(env)['state']=='DISABLED_SCOPED_KEYS_MISSING'
    assert not row(env)['enabled'] and not admitted(env)[0]


@pytest.mark.parametrize('mutation',['foreign_account','foreign_transport','traversal_profile','default_profile'])
def test_foreign_or_invalid_identity_refused_before_state(env,mutation):
    before=cas(env);kwargs=ident()
    target='user-1'
    if mutation=='foreign_account':kwargs['account_id']='bot-B'
    if mutation=='foreign_transport':kwargs['transport_profile']='foreign'
    if mutation=='traversal_profile':target='../owner'
    if mutation=='default_profile':target='default'
    with pytest.raises((PermissionError,ValueError)):
        env.setup.prepare('default', expected_config_sha256=before, template='approved-local',runtime_profile=target,**kwargs)
    assert cas(env)==before and current_access(env.state)['users']=={}


@pytest.mark.parametrize('mutation',['stale','corrupt','symlink','hardlink','public'])
def test_source_config_cas_and_private_boundaries(env,mutation):
    expected=cas(env);p=env.home/'config.yaml'
    if mutation=='stale':p.write_text(p.read_text()+'\n')
    elif mutation=='corrupt':p.write_text('malformed: [')
    elif mutation=='symlink':p.rename(env.home/'saved');p.symlink_to(env.home/'saved')
    elif mutation=='hardlink':os.link(p,env.home/'alias')
    elif mutation=='public':p.chmod(0o644)
    with pytest.raises((PermissionError,ValueError,RuntimeError)):
        env.setup.prepare('default',expected_config_sha256=expected,template='approved-local',runtime_profile='user-1',**ident())
    assert not home(env).exists()


@pytest.mark.parametrize('kind',['directory','symlink','hardlink_marker'])
def test_preexisting_home_is_never_adopted(env,kind):
    h=home(env);h.parent.mkdir(mode=0o700)
    if kind=='symlink':h.symlink_to(env.home,target_is_directory=True)
    else:
        h.mkdir(mode=0o700);(h/'keep').write_text('existing-user-data')
        if kind=='hardlink_marker':os.link(h/'keep',h/'config.yaml')
    before=cas(env)
    with pytest.raises(ValueError,match='not_adopted'): prepare(env)
    assert cas(env)==before and current_access(env.state)['users']=={}


def test_duplicate_original_cas_and_fresh_cas_cannot_reprepare(env):
    old=cas(env);prepare(env);after=cas(env)
    for expected in (old,after):
        with pytest.raises(ValueError):env.setup.prepare('default',expected_config_sha256=expected,
            template='approved-local',runtime_profile='user-1',**ident())
    assert cas(env)==after and len(current_access(env.state)['users'])==1


def test_actual_admission_lock_contention_refuses_no_effect(env):
    import fcntl
    from friday_admin_controls.associations import Associations, AssociationError
    state=env.state;store=Associations(state)
    with store._locked():
        before=cas(env)
        with pytest.raises(AssociationError,match='admission_busy'):prepare(env)
        assert cas(env)==before and current_access(env.state)['users']=={}


@pytest.mark.parametrize('stage',['config','home','soul','receipt','secret'])
def test_partial_failure_stays_disabled_and_cannot_adopt_on_retry(env,stage):
    from hermes_cli import config as native
    import friday_admin_controls.onboarding as module
    if stage=='config':env.monkeypatch.setattr(native,'atomic_config_write',lambda *a,**k:(_ for _ in ()).throw(OSError('injected')))
    elif stage=='home':env.monkeypatch.setattr(scope,'provision_new_home',lambda *a,**k:(_ for _ in ()).throw(OSError('injected')))
    elif stage in ('soul','receipt'):
        original=module._new_file
        def fail(path,value):
            if path.name==('SOUL.md' if stage=='soul' else scope.ONBOARDING):raise OSError('injected')
            original(path,value)
        env.monkeypatch.setattr(module,'_new_file',fail)
    if stage=='secret':
        prepare(env);env.monkeypatch.setattr(native,'save_env_value_secure',lambda *a,**k:(_ for _ in ()).throw(OSError('injected')))
        with pytest.raises(OSError):secrets(env)
    else:
        with pytest.raises(OSError):prepare(env)
    assert not row(env)['enabled']
    assert not (home(env)/scope.MARKER).exists()
    with pytest.raises(ValueError):prepare(env)


@pytest.mark.parametrize('mutation',['config','soul','env_symlink','env_hardlink','route','binding','directory','proof_deleted','proof_changed'])
def test_committed_setup_tamper_refuses_actual_channel(env,mutation):
    complete(env)
    h=home(env)
    if mutation=='config':(h/'config.yaml').write_text((h/'config.yaml').read_text()+'\n')
    elif mutation=='soul':(h/'SOUL.md').write_text('foreign-persona')
    elif mutation=='env_symlink':(h/'.env').rename(h/'saved');(h/'.env').symlink_to(h/'saved')
    elif mutation=='env_hardlink':os.link(h/'.env',h/'alias')
    elif mutation=='route':cfg=raw(env);cfg['gateway']['profile_routes'][0]['profile']='default';save(env,cfg)
    elif mutation=='binding':cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]['tools']=['memory'];save(env,cfg)
    elif mutation=='proof_deleted':(h/scope.ONBOARDING).unlink()
    elif mutation=='proof_changed':(h/scope.ONBOARDING).write_text((h/scope.ONBOARDING).read_text()+'\n')
    elif mutation=='directory':h.rename(h.with_name('old'));h.mkdir(mode=0o700)
    assert not admitted(env)[0]


def test_revocation_generation_and_retained_source_no_revival(env):
    complete(env);ok,retained=admitted(env);assert ok
    generation=row(env)['generation']
    env.admin.set_user('default',**ident(),enabled=False,role='user')
    assert row(env)['generation']>generation
    with pytest.raises(ValueError,match='generation'):activate(env,generation=generation)
    assert not admitted(env)[0]
    assert activate(env)['enabled']
    token=set_hermes_home_override(str(home(env)))
    try:
        with pytest.raises(scope.ScopeDenied):retained._friday_user_scope.check()
    finally:reset_hermes_home_override(token)
    assert admitted(env)[0]


def test_admin_enable_cannot_bypass_pending_setup(env):
    prepare(env);grant(env)
    with pytest.raises((PermissionError,FileNotFoundError)):env.admin.set_user('default',**ident(),enabled=True,role='user')
    assert not row(env)['enabled']


def test_actual_pairing_approval_keeps_new_profile_pending(env):
    prepare(env)
    from gateway.pairing import PairingStore
    p=PairingStore();p.generate_code('telegram','1','same name');ref=p.list_pending()[0]['request_id']
    result=env.admin.approve('default',platform='telegram',transport_profile='default',account_id='bot-A',request_id=ref)
    assert result['native_grant']=='PAIRING_APPROVED' and result['enabled'] is False
    assert not row(env)['enabled'] and not admitted(env)[0]
    secrets(env);assert activate(env)['enabled']


@pytest.mark.parametrize('mutation',['cloud','inline_secret','fallback','web_disabled','plugins','memory','persona','ambient_source'])
def test_explicit_template_rejects_incomplete_or_unscoped_setup(env,mutation):
    t=copy.deepcopy(env.template)
    if mutation=='cloud':t['config']['model']['base_url']='https://api.example.com/v1'
    elif mutation=='inline_secret':t['config']['model']['api_key']='secret-canary'
    elif mutation=='fallback':t['config']['fallback_providers']=['openai']
    elif mutation=='web_disabled':t['config']['web']['backend']='disabled'
    elif mutation=='plugins':t['config']['plugins']['enabled']=[]
    elif mutation=='memory':t['config']['memory']['memory_enabled']=False
    elif mutation=='persona':t['config']['agent']['system_prompt']='foreign-persona'
    elif mutation=='ambient_source':t['config']['secrets']={'sources':[{'profile':'owner'}]}
    with pytest.raises(ValueError):validate_template(t)


def test_scoped_capture_refuses_unknown_names_foreign_identity_and_no_secret_response(env):
    prepare(env)
    for changes in ({'name':'PATH'},{'name':'UNAPPROVED_KEY'},{'user_id':'2'},{'account_id':'bot-B'},{'generation':2}):
        kwargs=dict(expected_config_sha256=cas(env),generation=row(env)['generation'],**ident(),name='LOCAL_KEY',value='synthetic-secret-canary')|changes
        with pytest.raises((PermissionError,ValueError)):env.setup.credentials('default',**kwargs)
    result=env.setup.credentials('default',expected_config_sha256=cas(env),generation=row(env)['generation'],
        **ident(),name='LOCAL_KEY',value='synthetic-secret-canary')
    assert 'synthetic-secret-canary' not in json.dumps(result)


def test_native_signed_dashboard_middleware_ordinary_foreign_and_prepare_flow(env):
    import importlib.util,sys
    from hermes_cli.dashboard_auth import middleware,request_utils
    path=Path(__import__('hermes_cli').__path__[-1]).parent/'plugins/dashboard_auth/basic/__init__.py'
    spec=importlib.util.spec_from_file_location('onboard_basic',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    provider=m.BasicAuthProvider(username='owner',password_hash='synthetic-unused',secret=b'synthetic-signing-secret-32bytes')
    env.monkeypatch.setattr(middleware,'list_session_providers',lambda:[provider])
    env.monkeypatch.setattr(request_utils,'list_session_providers',lambda:[provider])
    owner=provider._mint_session('owner').access_token;ordinary=provider._mint_session('ordinary').access_token
    app=mounted_app(env)
    @app.middleware('http')
    async def gate(req,next_call):return await middleware.gated_auth_middleware(req,next_call)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as c:
            headers=lambda t:{'Authorization':'Bearer '+t}
            body=dict(expected_config_sha256=cas(env),template='approved-local',runtime_profile='user-1',**ident())
            for token,code in ((ordinary,403),('bad-signature',401)):
                r=await c.post('/api/plugins/friday_rework/onboarding/prepare?profile=default',json=body,headers=headers(token));assert r.status_code==code
            r=await c.post('/api/plugins/friday_rework/onboarding/prepare?profile=foreign',json=body,headers=headers(owner));assert r.status_code==403
            assert not home(env).exists()
            r=await c.get('/api/plugins/friday_rework/onboarding?profile=default',headers=headers(owner));assert r.status_code==200 and r.json()['templates']==['approved-local']
            r=await c.post('/api/plugins/friday_rework/onboarding/prepare?profile=default',json=body,headers=headers(owner));assert r.status_code==200,r.text
            prepared=r.json();assert prepared['enabled'] is False and prepared['required_names']==['LOCAL_KEY','EXA_API_KEY']
            args=dict(expected_config_sha256=prepared['config_sha256'],generation=prepared['generation'],**ident())
            for name in ('LOCAL_KEY','EXA_API_KEY'):
                r=await c.put('/api/plugins/friday_rework/onboarding/credentials?profile=default',json=args|{'name':name,'value':'synthetic-secret-canary-'+name},headers=headers(owner));assert r.status_code==200,r.text
                assert 'synthetic-secret-canary' not in r.text
            grant(env)
            r=await c.post('/api/plugins/friday_rework/onboarding/activate?profile=default',json=args,headers=headers(owner));assert r.status_code==200 and r.json()['enabled'],r.text
            for change in ({'generation':True},{'generation':0},{'extra':True}):
                r=await c.post('/api/plugins/friday_rework/onboarding/activate?profile=default',json=args|change,headers=headers(owner));assert r.status_code==422
    asyncio.run(scenario());assert admitted(env)[0]


def test_actual_gateway_refreshes_stale_routes_and_served_set_after_setup(env):
    from gateway.run import GatewayRunner
    from gateway.config import GatewayConfig, Platform
    from gateway.session import SessionSource
    from gateway.session_identity import resolve_identity
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig.from_dict({'multiplex_profiles': True, 'profile_routes': []})
    complete(env)
    for chat, thread in [('same-chat','topic'),('other-chat','other-topic')]:
        s = SessionSource(Platform.TELEGRAM, chat, user_id='1', thread_id=thread)
        assert runner._profile_name_for_source(s, adapter_profile='default') == 'user-1'
    s = SessionSource(Platform.TELEGRAM, 'same-chat', user_id='2', thread_id='topic')
    assert runner._profile_name_for_source(s, adapter_profile='default') is None
    assert runner._profile_name_for_source(s, adapter_profile='foreign') is None
    cfg = raw(env); cfg['gateway']['profile_routes'][0]['enabled'] = False; save(env,cfg)
    s = SessionSource(Platform.TELEGRAM, 'same-chat', user_id='1', thread_id='topic')
    assert runner._profile_name_for_source(s, adapter_profile='default') is None


def test_unchanged_profile_routes_keep_native_semantics_when_onboarding_absent(env):
    cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings'].pop('onboarding')
    from hermes_cli.config import atomic_config_replace
    atomic_config_replace(env.home/'config.yaml',cfg)
    sentinel=object();assert scope.onboarding_profile_routes(sentinel) is sentinel


def test_read_only_recovery_uses_same_home_original_generation_and_no_adoption(env):
    initial=prepare(env);secrets(env)
    before=cas(env);st=home(env).stat();pending=env.setup.templates('default')['pending']
    assert len(pending)==1 and pending[0]['recoverable'] and pending[0]['generation']==initial['generation']
    assert pending[0]['config_sha256']==before and pending[0]['principal_id']==initial['principal_id']
    assert home(env).stat().st_ino==st.st_ino and cas(env)==before
    grant(env);assert Onboarding(Administration()).activate('default',expected_config_sha256=before,
        generation=pending[0]['generation'],**ident())['enabled']
    assert env.setup.templates('default')['pending']==[]


def test_pending_tampered_receipt_is_inspected_without_recovery_or_adoption(env):
    prepare(env);(home(env)/'SOUL.md').write_text('changed')
    rows=env.setup.templates('default')['pending']
    assert not rows[0]['recoverable'] and rows[0]['state']=='SETUP_CHANGED_RECONCILIATION_REQUIRED'
    assert not row(env)['enabled']


def test_native_credential_capture_never_unions_user_keys_into_ambient_process(env):
    env.monkeypatch.setenv('LOCAL_KEY','owner-local-canary');env.monkeypatch.setenv('EXA_API_KEY','owner-web-canary')
    prepare(env);secrets(env)
    assert os.environ['LOCAL_KEY']=='owner-local-canary' and os.environ['EXA_API_KEY']=='owner-web-canary'


def test_same_user_id_different_receiving_platform_is_distinct_principal(env):
    cfg=raw(env);settings=cfg['plugins']['entries']['friday_rework']['settings']
    settings['product_access']['accounts'].append(dict(platform='discord',transport_profile='default',account_id='bot-B',runtime_profiles=['default']))
    settings['onboarding']['templates']['approved-local']['config']['platform_toolsets']['discord']=env.template['config']['toolsets']
    save(env,cfg);complete(env,'1')
    other=dict(platform='discord',transport_profile='default',account_id='bot-B',user_id='1')
    result=env.setup.prepare('default',expected_config_sha256=cas(env),template='approved-local',runtime_profile='discord-user-1',**other)
    assert result['principal_id'] != principal_id(**ident()) and result['generation']==1
    assert not result['enabled'] and row(env)['enabled']
    cfg=raw(env);routes=cfg['gateway']['profile_routes'];assert len(routes)==2
    from gateway.profile_routing import parse_profile_routes,match_profile_route
    parsed=parse_profile_routes(routes)
    assert match_profile_route(parsed,'discord',adapter_profile='default',user_id='1').profile=='discord-user-1'
    assert match_profile_route(parsed,'telegram',adapter_profile='default',user_id='1').profile=='user-1'


def test_new_profiles_use_actual_native_memory_history_files_and_cross_user_refusal(env):
    from test_user_isolation import native_history
    from tools.memory_tool import MemoryStore, memory_tool
    from tools.session_search_tool import session_search
    from tools.file_tools import read_file_tool,write_file_tool
    complete(env,'1');complete(env,'2')
    bindings=scope.policy(env.home)['bindings']
    users=SimpleNamespace(root=env.home,bindings=bindings,homes=[home(env,'1'),home(env,'2')])
    dbs=[native_history(users,i,content='new-user-'+str(i+1)) for i in (0,1)]
    try:
        for i in (0,1):
            uid=str(i+1);accepted,s=admitted(env,uid);assert accepted
            token=set_hermes_home_override(str(home(env,uid)))
            try:
                with scope.scoped_source(s):
                    memory=MemoryStore();memory.load_from_disk()
                    assert json.loads(memory_tool(action='add',content='private-onboard-'+uid,store=memory))['success']
                    assert json.loads(write_file_tool('own.txt','onboard-file-'+uid))['success']
                    assert 'onboard-file-'+uid in read_file_tool('own.txt')
                    assert 'new-user-'+uid in session_search(session_id='history-'+uid,db=dbs[i])
                    assert 'product_user_scope_refused' in session_search(profile='user-'+str(2-i),session_id='history-'+str(2-i))
            finally:reset_hermes_home_override(token)
    finally:
        for db in dbs:db.close()


def test_actual_trusted_native_plugin_registers_managed_profile_worker_and_result_hooks(env):
    import shutil,sys,importlib
    from hermes_cli import plugins
    from tools.registry import registry
    from agent.secret_scope import load_env_file,set_secret_scope,reset_secret_scope
    from test_admin_foundation import ROOT
    complete(env);accepted,s=admitted(env);assert accepted
    token=set_hermes_home_override(str(home(env)));secret=set_secret_scope(load_env_file(home(env)/'.env'),profile_home=str(home(env)))
    try:
        with scope.scoped_source(s):
            destination=home(env)/'plugins/friday_rework';shutil.copytree(ROOT,destination,ignore=shutil.ignore_patterns('__pycache__'))
            for f in ROOT.rglob('*'):
                if f.is_file():assert sha(f)==sha(destination/f.relative_to(ROOT))
            env.monkeypatch.setattr(plugins,'get_bundled_plugins_dir',lambda:home(env)/'empty')
            env.monkeypatch.setattr(plugins.PluginManager,'_scan_entry_points',lambda self:[])
            manager=plugins.PluginManager(scope_key=str(home(env)));manager.discover_and_load()
            try:
                entry=manager._plugins['friday_rework'];assert entry.enabled,entry.error
                host=registry.get_entry('friday_work',scope=manager.scope_key).handler.__self__
                assert registry.get_entry('friday_result',scope=manager.scope_key)
                assert manager._hooks['post_gateway_admission'] and manager._middleware['tool_execution']
                assert host.ctx.get_config('results')=={'enabled':True}
                assert host.ctx.get_config('runtime')=={'enabled':False}
                assert not host._a0_controllers
            finally:manager.unload()
    finally:reset_secret_scope(secret);reset_hermes_home_override(token)


def test_missing_template_and_multiplex_readiness_are_explicit_and_have_no_state_effect(env):
    cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']={}
    from hermes_cli.config import atomic_config_replace
    atomic_config_replace(env.home/'config.yaml',cfg)
    assert env.setup.templates('default')['state']=='INSTALLATION_INPUT_MISSING'
    with pytest.raises(KeyError):prepare(env)
    assert current_access(env.state)['users']=={}
    cfg=copy.deepcopy(env.cfg);cfg['gateway']['multiplex_profiles']=False;atomic_config_replace(env.home/'config.yaml',cfg)
    with pytest.raises(ValueError,match='multiplex'):prepare(env)
    assert current_access(env.state)['users']=={} and not home(env).exists()
