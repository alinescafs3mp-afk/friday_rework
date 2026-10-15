"""Synthetic ingress through native authorization, source scope, discovery and receipts.
No worker, model, network, Telegram send or live acceptance.
"""
import asyncio, contextvars, copy, importlib, json, weakref
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from hermes_cli import friday_user_scope as users, plugins
from hermes_cli.friday_product_access import KEY, principal_id
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override, get_hermes_home
from gateway.authz_mixin import GatewayAuthorizationMixin
from gateway.config import Platform, GatewayConfig
from gateway.session import SessionSource
from gateway.session_identity import RoutingIdentity
from gateway.run import GatewayRunner
from gateway.run_inbound_consumer import run_post_admission_hook

@pytest.fixture
def env(tmp_path, monkeypatch):
    root=tmp_path/'home';root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME',str(root)); monkeypatch.setenv('GATEWAY_ALLOWED_USERS','*')
    import hermes_constants
    monkeypatch.setattr(hermes_constants,'_PINNED_PROCESS_HERMES_HOME',str(root))
    monkeypatch.setattr(users,'_ENGAGED',False)
    monkeypatch.setattr(users,'_CURRENT',contextvars.ContextVar('test_current',default=None))
    monkeypatch.setattr(users,'_SOURCE',contextvars.ContextVar('test_source',default=None))
    for key in ('TELEGRAM_ALLOWED_USERS','TELEGRAM_ALLOW_ALL_USERS','GATEWAY_ALLOW_ALL_USERS'):
        monkeypatch.delenv(key,raising=False)
    bindings=[dict(platform='telegram',transport_profile='default',account_id='bot-A',user_id=uid,
        runtime_profile='user-'+uid,tools=['memory','read_file','friday_work','friday_result']) for uid in ('1','2')]
    settings=dict(product_access=dict(enabled=True,accounts=[dict(platform='telegram',transport_profile='default',account_id='bot-A',runtime_profiles=['user-1','user-2'])]),user_isolation=dict(enabled=True,bindings=bindings))
    cfg={'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'settings':settings}}}}
    (root/'config.yaml').write_text(json.dumps(cfg));(root/'config.yaml').chmod(0o600)
    token=set_hermes_home_override(str(root))
    state=PluginState('friday_rework'); rows={principal_id(*(b[k] for k in ('platform','transport_profile','account_id','user_id'))):{k:b[k] for k in ('platform','transport_profile','account_id','user_id')}|dict(enabled=True,role='user') for b in bindings}
    state.set(KEY,dict(schema=KEY,users=rows))
    homes=[users.provision_new_home(root,b,{'max_iterations':8}) for b in bindings]
    product=Path(__file__).resolve().parents[1]/'plugins'/'friday_rework'
    import shutil
    for home in homes:
        shutil.copytree(product,home/'plugins/friday_rework')
        (home/'config.yaml').write_text(json.dumps({'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'settings':{}}}}}));(home/'config.yaml').chmod(0o600)
    monkeypatch.setattr(plugins,'get_bundled_plugins_dir',lambda:root/'no-bundled')
    monkeypatch.setattr(plugins.PluginManager,'_scan_entry_points',lambda self:[])
    plugins._reset_plugin_managers_for_tests()
    runner=object.__new__(GatewayRunner);runner.config=GatewayConfig(multiplex_profiles=True)
    runner._resolve_profile_home_for_source=lambda source:source._identity.runtime_home
    auth=GatewayAuthorizationMixin()
    sources=[];adapters=[]
    class Adapter:
        def message_provenance(self,event):
            s=event.source
            return dict(bot_id='bot-A',user_id=s.user_id,chat_id=s.chat_id,thread_id=s.thread_id or '',message_id=event.message_id,platform_update_id='update-'+event.message_id,reply_to_message_id='',media=[])
    for b,home in zip(bindings,homes):
        adapter=Adapter();adapters.append(adapter)
        source=SessionSource(Platform.TELEGRAM,'shared-chat',user_id=b['user_id'],chat_type='group',thread_id='topic',profile=b['runtime_profile'])
        source._identity=RoutingIdentity('default',b['runtime_profile'],root,home,multiplexed=True,transport_inferred=False,transport=weakref.ref(adapter))
        assert auth._principal_authorized(source,allow_adapter_delegation=True)
        sources.append(source)
    def access(uid,**delta):
        row=next(r for r in rows.values() if r['user_id']==uid);row.update(delta)
        with users.authority(root):state.set(KEY,dict(schema=KEY,users=rows))
    @contextmanager
    def enter(index):
        with users.authority(homes[index]):
            with users.scoped_source(sources[index]) as cap:yield cap
    def receipts(index):
        with enter(index):return PluginState('friday_rework').get('admitted_ingress.v1',dict(schema_version=1,receipts={}))['receipts']
    def event(source,mid='m1'):
        source.message_id=mid
        return SimpleNamespace(internal=False,source=source,message_id=mid,text='synthetic offline fixture')
    def invoke(source=None,mid='m1'):
        source=source or sources[0]
        return asyncio.run(run_post_admission_hook(runner,event(source,mid),source,'synthetic-session-'+source.user_id))
    try:
        yield SimpleNamespace(root=root,homes=homes,sources=sources,runner=runner,auth=auth,access=access,enter=enter,receipts=receipts,invoke=invoke,event=event,rows=rows,settings=settings,cfg=cfg,monkeypatch=monkeypatch)
    finally:
        # No runtime settings/claims: unload has no native worker to inspect.
        plugins._reset_plugin_managers_for_tests();reset_hermes_home_override(token)

@pytest.mark.parametrize('preloaded',[False,True],ids=['cold-discovery','preloaded-callback'])
def test_first_second_ingress_persists_receipts_under_native_scope(env,preloaded):
    e=env
    if preloaded:
        with e.enter(0):
            manager=plugins.get_plugin_manager();manager.discover_and_load()
            assert manager._plugins['friday_rework'].enabled
    assert users._CURRENT.get() is None and users._ENGAGED
    assert e.invoke(mid='first')==(False,None)
    assert e.invoke(mid='second')==(False,None)
    receipts=e.receipts(0)
    assert {r['message']['message_id'] for r in receipts.values()}=={'first','second'}
    assert all(r['message']['user_id']=='1' and r['runtime_profile']=='user-1' for r in receipts.values())
    assert e.receipts(1)=={}
    assert users._CURRENT.get() is None and users._SOURCE.get() is None and get_hermes_home()==e.root

@pytest.mark.parametrize('mutation',['missing-cap','foreign-user','foreign-runtime','foreign-transport','foreign-account','source-profile','nonmultiplex','inferred','disabled','revoked-reenabled','role-generation','crossuser'])
def test_invalid_source_never_discovers_or_dispatches_hook(env,mutation):
    e=env;source=e.sources[0];seen=[]
    paths=[h/'plugin-data/friday_rework/state.json' for h in e.homes]
    before={str(p):p.read_bytes() if p.exists() else None for p in paths}
    import hermes_cli.lifecycle as lifecycle
    original=lifecycle.has_hook
    e.monkeypatch.setattr(lifecycle,'has_hook',lambda name:seen.append(name) or original(name))
    if mutation=='missing-cap':del source._friday_user_scope
    elif mutation=='foreign-user':source.user_id='2'
    elif mutation=='foreign-runtime':source._identity=replace(source._identity,runtime_profile='user-2',runtime_home=e.homes[1])
    elif mutation=='foreign-transport':source._identity=replace(source._identity,transport_profile='foreign')
    elif mutation=='foreign-account':source._friday_user_scope.principal=('telegram','default','bot-B','1')
    elif mutation=='source-profile':source.profile='user-2'
    elif mutation=='nonmultiplex':source._identity=replace(source._identity,multiplexed=False)
    elif mutation=='inferred':source._identity=replace(source._identity,transport_inferred=True)
    elif mutation=='disabled':e.access('1',enabled=False)
    elif mutation=='role-generation':e.access('1',role='admin')
    elif mutation=='revoked-reenabled':
        e.access('1',enabled=False)
        assert not e.auth._principal_authorized(source,allow_adapter_delegation=True)
        e.access('1',enabled=True)
    if mutation=='crossuser':
        with e.enter(1):
            original_cap=users.current(required=True)
            assert e.invoke(source)==(False,None)
            assert users.current(required=True) is original_cap
    else:assert e.invoke(source)==(False,None)
    assert seen==[]
    assert {str(p):p.read_bytes() if p.exists() else None for p in paths}==before
    assert users._CURRENT.get() is None and get_hermes_home()==e.root


def test_native_disabled_admission_no_capability(env):
    e=env;e.access('1',enabled=False);source=copy.copy(e.sources[0]);del source._friday_user_scope
    assert not e.auth._principal_authorized(source,allow_adapter_delegation=True)
    assert not hasattr(source,'_friday_user_scope')
    assert e.invoke(source)==(False,None)


def test_handled_callback_and_cancellation_restore_user_scope(env):
    e=env
    with e.enter(0):
        manager=plugins.get_plugin_manager();manager._discovered=True
        def handled(**payload):
            cap=users.current(required=True)
            assert cap.principal[-1]=='1' and cap.home==e.homes[0]
            return dict(action='handled',reply='accepted offline fixture')
        manager._hooks['post_gateway_admission']=[handled]
    assert e.invoke()==(True,'accepted offline fixture')
    async def cancelled(**payload):raise asyncio.CancelledError()
    manager._hooks['post_gateway_admission']=[cancelled]
    with pytest.raises(asyncio.CancelledError):e.invoke(mid='cancel')
    assert users._CURRENT.get() is None and users._SOURCE.get() is None and get_hermes_home()==e.root


def test_full_inbound_first_second_receipt_without_model(env):
    from gateway.platforms.event import MessageEvent
    from unittest.mock import AsyncMock, MagicMock
    e=env;runner=e.runner
    adapter=SimpleNamespace(send=AsyncMock())
    runner.adapters={Platform.TELEGRAM:adapter};runner.pairing_store=MagicMock();runner.session_store=MagicMock()
    runner._is_user_authorized_for_source=lambda source:e.auth._principal_authorized(source,allow_adapter_delegation=True)
    runner._admit_bot_message_for_source=lambda source:True
    runner._delivery_adapter_for=lambda source:adapter
    runner._intake_adapter_for=lambda source:adapter
    runner._rescue_orphaned_overflow=lambda *args:None
    runner._enqueue_fifo=MagicMock()
    runner._handle_message_with_agent=AsyncMock(return_value='isolated-no-model-boundary')
    runner._run_post_turn_hooks=AsyncMock()
    async def exercise():
        for mid in ('full-first','full-second'):
            source=copy.copy(e.sources[0]);source.message_id=mid
            event=MessageEvent(text='synthetic offline source',message_id=mid,source=source)
            assert await runner._handle_message(event)=='isolated-no-model-boundary'
    asyncio.run(exercise())
    assert runner._handle_message_with_agent.await_count==2
    assert {r['message']['message_id'] for r in e.receipts(0).values()}=={'full-first','full-second'}
    assert users._CURRENT.get() is None and get_hermes_home()==e.root

@pytest.mark.parametrize('multiplex',[False,True],ids=['ordinary-standalone','ordinary-multiplex'])
def test_ordinary_scope_without_product_policy_preserves_hook(tmp_path,monkeypatch,multiplex):
    root=tmp_path/'ordinary';root.mkdir(mode=0o700)
    (root/'config.yaml').write_text('{}');(root/'config.yaml').chmod(0o600)
    import hermes_constants
    monkeypatch.setattr(hermes_constants,'_PINNED_PROCESS_HERMES_HOME',str(root))
    monkeypatch.setenv('HERMES_HOME',str(root));monkeypatch.setattr(users,'_ENGAGED',False)
    monkeypatch.setattr(users,'_CURRENT',contextvars.ContextVar('ordinary_scope',default=None))
    token=set_hermes_home_override(str(root));plugins._reset_plugin_managers_for_tests()
    try:
        source=SessionSource(Platform.TELEGRAM,'ordinary-chat',user_id='ordinary-user',chat_type='dm')
        runner=object.__new__(GatewayRunner);runner.config=GatewayConfig(multiplex_profiles=multiplex)
        runner._resolve_profile_home_for_source=lambda s:root
        manager=plugins.get_plugin_manager();manager._discovered=True
        seen=[]
        def hook(**payload):
            assert users.current() is None and get_hermes_home()==root
            seen.append(payload);return dict(action='handled',reply='ordinary-fixture')
        manager._hooks['post_gateway_admission']=[hook]
        event=SimpleNamespace(source=source,internal=False,message_id='ordinary',text='ordinary isolated fixture')
        assert asyncio.run(run_post_admission_hook(runner,event,source,'ordinary-key'))==(True,'ordinary-fixture')
        assert len(seen)==1 and users._CURRENT.get() is None
    finally:plugins._reset_plugin_managers_for_tests();reset_hermes_home_override(token)
