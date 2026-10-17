"""Offline native onboarding + Telegram SDK observation + actual inbound gate.
No Telegram/model/network call. Synthetic numeric bot/account identities only.
"""
import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import test_user_onboarding as upstream
from test_user_onboarding import env as native_env
from gateway.config import Platform, GatewayConfig
from gateway.run import GatewayRunner
from gateway.pairing import PairingStore
from gateway.platforms.event import MessageEvent
from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_bot_pairing import request_prepared_pairing
from hermes_cli.friday_product_access import current_access
from telegram import Bot, Message


@pytest.fixture
def env(native_env,monkeypatch):
    e=native_env
    e.cfg['plugins']['entries']['friday_rework']['settings']['product_access']['accounts'][0]['account_id']='1001'
    upstream.save(e,e.cfg)
    monkeypatch.setattr(upstream,'ident',lambda uid='1':dict(platform='telegram',transport_profile='default',account_id='1001',user_id=uid))
    for name in ('TELEGRAM_ALLOW_BOTS','TELEGRAM_ALLOW_ALL_USERS','GATEWAY_ALLOW_ALL_USERS','GATEWAY_ALLOWED_USERS'):
        monkeypatch.delenv(name,raising=False)
    return e


def prepared(e,uid='2001'):
    return upstream.prepare(e,uid)


def event_runner(e,uid='2001',*,bot=True):
    sdk=Bot('1001:synthetic-offline-token')
    sdk._bot_user=__import__('telegram').User(1001,'Receiver',True)
    # Telegram JSON key is "from", not the Python attribute name.
    raw=dict(message_id=11,date=int(datetime.now(timezone.utc).timestamp()),
        chat=dict(id=3001,type='private',first_name='Synthetic'),text='offline')
    raw['from']=dict(id=int(uid),first_name='Synthetic',is_bot=bot)
    message=Message.de_json(raw,sdk)
    adapter=SimpleNamespace(_bot=sdk,_effective_message_thread_id=lambda m:None,send=AsyncMock())
    source=upstream.source(e,uid,chat='3001',thread=None)
    source.chat_type='dm';source.is_bot=bot;source.message_id='11'
    source._identity=replace(source._identity,transport=lambda:adapter)
    event=MessageEvent(text='offline',source=source,raw_message=message,message_id='11',platform_update_id=21)
    event._ingress_update_id=21
    r=object.__new__(GatewayRunner);r.config=GatewayConfig(multiplex_profiles=False)
    r.pairing_store=PairingStore();r._intake_adapter_for=lambda s:adapter;r._delivery_adapter_for=lambda s:adapter
    r._hm_pre_gateway_dispatch_hook=AsyncMock(side_effect=lambda event,source:event)
    r._scale_to_zero_note_real_inbound=MagicMock()
    r._is_user_authorized_for_source=lambda s:r._principal_authorized(s,allow_adapter_delegation=True)
    r._admit_bot_message_for_source=MagicMock(return_value=True)
    return r,event,adapter


def denied(r,event,adapter):
    assert asyncio.run(r._hm_admit_event(event)) is None
    adapter.send.assert_not_awaited()
    r._admit_bot_message_for_source.assert_not_called()
    assert not hasattr(event.source,'_friday_user_scope')


def test_actual_pending_operator_approval_and_separate_activation(env):
    result=prepared(env);r,event,adapter=event_runner(env)
    before=upstream.cas(env)
    denied(r,event,adapter)
    pending=r.pairing_store.list_pending('telegram');assert len(pending)==1
    assert pending[0]['user_id']=='2001'
    assert not r.pairing_store.is_approved('telegram','2001')
    assert upstream.row(env,'2001')['enabled'] is False and upstream.cas(env)==before
    assert not (upstream.home(env,'2001')/scope.MARKER).exists()
    approval=env.admin.approve('default',platform='telegram',transport_profile='default',account_id='1001',request_id=pending[0]['request_id'])
    assert approval['enabled'] is False and approval['native_grant']=='PAIRING_APPROVED'
    denied(r,event,adapter)
    upstream.secrets(env,'2001')
    assert upstream.activate(env,'2001')['enabled'] is True
    admitted=asyncio.run(r._hm_admit_event(event))
    assert admitted==(event,event.source,False)
    cap=event.source._friday_user_scope
    assert cap.principal==('telegram','default','1001','2001') and cap.profile=='user-2001'
    assert upstream.row(env,'2001')['role']=='user'
    adapter.send.assert_not_awaited()
    assert not (upstream.home(env,'2001')/'state.db').exists()


@pytest.mark.parametrize('bad',['unknown','wrong-receiver','raw-human','wrong-user','no-transport','foreign-adapter',
 'inferred','nonmultiplex','wrong-profile','wrong-home','missing-receipt','bad-receipt','bad-config','bad-soul',
 'marker','marker-symlink','wrong-account','route','generation','admin','enabled','approved','group','thread',
 'merged','internal','wrong-update','wrong-message','wrong-chat','foreign-store'])
def test_negative_preparation_and_observation_controls(env,bad):
    prepared(env);r,event,adapter=event_runner(env)
    h=upstream.home(env,'2001');s=event.source
    if bad=='unknown':r,event,adapter=event_runner(env,'2002')
    elif bad=='wrong-receiver':adapter._bot._bot_user=__import__('telegram').User(9999,'Foreign',True)
    elif bad=='raw-human':
        with event.raw_message.from_user._unfrozen():event.raw_message.from_user.is_bot=False
    elif bad=='wrong-user':s.user_id='2002'
    elif bad=='no-transport':s._identity=replace(s._identity,transport=None)
    elif bad=='foreign-adapter':r._intake_adapter_for=lambda s:object()
    elif bad=='inferred':s._identity=replace(s._identity,transport_inferred=True)
    elif bad=='nonmultiplex':s._identity=replace(s._identity,multiplexed=False)
    elif bad=='wrong-profile':s.profile='default'
    elif bad=='wrong-home':s._identity=replace(s._identity,runtime_home=env.home)
    elif bad=='missing-receipt':(h/scope.ONBOARDING).unlink()
    elif bad=='bad-receipt':(h/scope.ONBOARDING).write_text('{}')
    elif bad=='bad-config':(h/'config.yaml').write_text('{}')
    elif bad=='bad-soul':(h/'SOUL.md').write_text('changed')
    elif bad=='marker':(h/scope.MARKER).write_text('{}')
    elif bad=='marker-symlink':(h/scope.MARKER).symlink_to(h/'missing')
    elif bad in {'wrong-account','route'}:
        cfg=upstream.raw(env)
        if bad=='wrong-account':cfg['plugins']['entries']['friday_rework']['settings']['product_access']['accounts'][0]['account_id']='9999'
        else:cfg['gateway']['profile_routes'][0]['user_id']='2002'
        upstream.save(env,cfg)
    elif bad in {'generation','admin','enabled'}:
        delta={'role':'admin'} if bad=='admin' else {'enabled':True}
        # Inject invalid lower-level state through the real native generation writer.
        upstream.ProductAccess(env.state).set_user(**(upstream.ident('2001')|dict(enabled=False,role='user')|delta))
        if bad=='generation':upstream.ProductAccess(env.state).set_user(**upstream.ident('2001'),enabled=False,role='user')
    elif bad=='approved':upstream.grant(env,'2001')
    elif bad=='group':s.chat_type='group'
    elif bad=='thread':s.thread_id='42'
    elif bad=='merged':event._ingress_merged=True
    elif bad=='internal':event.internal=True
    elif bad=='wrong-update':event.platform_update_id=22
    elif bad=='wrong-message':event.message_id='12'
    elif bad=='wrong-chat':s.chat_id='3002'
    elif bad=='foreign-store':r._pairing_store_for=lambda s:SimpleNamespace(_dir=env.home/'foreign')
    assert request_prepared_pairing(r,event) is False
    assert r.pairing_store.list_pending('telegram')==[]
    adapter.send.assert_not_awaited()


def test_duplicate_expired_and_revoked_request_is_not_recreated(env,monkeypatch):
    prepared(env);r,event,adapter=event_runner(env)
    denied(r,event,adapter)
    first=r.pairing_store.list_pending('telegram')
    for _ in range(3):denied(r,event,adapter)
    assert r.pairing_store.list_pending('telegram')==first
    approved=env.admin.approve('default',**{k:v for k,v in upstream.ident('2001').items() if k!='user_id'},request_id=first[0]['request_id'])
    assert r.pairing_store.revoke('telegram','2001')
    import gateway.pairing as pairing
    now=pairing.time.time();monkeypatch.setattr(pairing.time,'time',lambda:now+7200)
    denied(r,event,adapter)
    assert r.pairing_store.list_pending('telegram')==[]


def test_human_pending_and_reply_unchanged(env):
    r,event,adapter=event_runner(env,'2002',bot=False)
    r._get_unauthorized_dm_behavior=lambda *a,**k:'pair'
    assert asyncio.run(r._hm_admit_event(event)) is None
    assert r.pairing_store.list_pending('telegram')[0]['user_id']=='2002'
    adapter.send.assert_awaited_once()


def test_unknown_bot_does_not_trigger_native_or_denial_responses(env):
    r,event,adapter=event_runner(env,'2002')
    r._get_unauthorized_dm_behavior=MagicMock(return_value='decline')
    denied(r,event,adapter)
    assert r.pairing_store.list_pending('telegram')==[]
    r._get_unauthorized_dm_behavior.assert_not_called()


def test_native_limit_and_lockout_preserved(env):
    prepared(env);r,event,adapter=event_runner(env)
    for uid in ('4001','4002','4003'):r.pairing_store.generate_code('telegram',uid)
    denied(r,event,adapter)
    assert len(r.pairing_store.list_pending('telegram'))==3
    r.pairing_store.clear_pending('telegram')
    import time
    r.pairing_store._save_limits({'_lockout:telegram':time.time()+3600})
    denied(r,event,adapter)
    assert r.pairing_store.list_pending('telegram')==[]


def test_concurrent_distinct_store_instances_mint_only_one_request(env):
    from concurrent.futures import ThreadPoolExecutor
    prepared(env);r,event,adapter=event_runner(env)
    def invoke(_):
        # Native config/state locks serialize even distinct PairingStore instances.
        with scope.authority(env.home):
            own=copy.copy(r);own.pairing_store=PairingStore()
            return request_prepared_pairing(own,event)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(invoke,range(12)))
    assert results.count(True)==1
    assert len(r.pairing_store.list_pending('telegram'))==1
    adapter.send.assert_not_awaited()


def test_revoked_completed_principal_never_reenters_pairing(env):
    prepared(env);r,event,adapter=event_runner(env)
    assert request_prepared_pairing(r,event)
    p=r.pairing_store.list_pending('telegram')[0]
    env.admin.approve('default',platform='telegram',transport_profile='default',account_id='1001',request_id=p['request_id'])
    upstream.secrets(env,'2001');assert upstream.activate(env,'2001')['enabled']
    env.admin.set_user('default',**upstream.ident('2001'),enabled=False,role='user')
    assert upstream.row(env,'2001')['generation']==2
    assert r.pairing_store.revoke('telegram','2001')
    denied(r,event,adapter)
    assert r.pairing_store.list_pending('telegram')==[]


@pytest.mark.parametrize('kind',['limits-malformed','limits-list','limits-symlink','pending-malformed','approved-malformed'])
def test_corrupt_native_pairing_metadata_never_becomes_fresh(env,kind):
    prepared(env);r,event,adapter=event_runner(env)
    p=(r.pairing_store._pending_path('telegram') if kind=='pending-malformed' else
       r.pairing_store._approved_path('telegram') if kind=='approved-malformed' else r.pairing_store._rate_limit_path())
    if kind=='limits-symlink':p.symlink_to(env.home/'missing')
    else:p.write_text('[]' if kind=='limits-list' else '{broken');p.chmod(0o600)
    before=p.read_bytes() if not p.is_symlink() else None
    assert request_prepared_pairing(r,event) is False
    if before is not None:assert p.read_bytes()==before
    adapter.send.assert_not_awaited()


@pytest.mark.parametrize('where',['stamp','directory-sync','pending'])
def test_partial_native_commit_cannot_recreate_request(env,monkeypatch,where):
    import utils
    prepared(env);r,event,adapter=event_runner(env)
    original=r.pairing_store._save_json
    def fail(path,data):
        if path == (r.pairing_store._rate_limit_path() if where=='stamp' else r.pairing_store._pending_path('telegram')):
            raise OSError('synthetic-write-failure')
        return original(path,data)
    if where=='directory-sync':
        with monkeypatch.context() as m:
            m.setattr(utils,'fsync_directory',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic-fsync-failure')))
            assert request_prepared_pairing(r,event) is False
    else:
        with monkeypatch.context() as m:
            m.setattr(r.pairing_store,'_save_json',fail)
            assert request_prepared_pairing(r,event) is False
    assert not r.pairing_store.list_pending('telegram')
    if where=='stamp':
        # No pending effect and no stamp committed: a new event may try once.
        assert request_prepared_pairing(r,event) is True
    else:
        # Reservation persisted but pending effect uncertain: do not replay.
        assert request_prepared_pairing(r,event) is False
    adapter.send.assert_not_awaited()


def test_bad_routed_home_does_not_create_profile(env):
    prepared(env);r,event,adapter=event_runner(env)
    foreign=env.home/'profiles'/'unknown'
    event.source.profile='unknown'
    event.source._identity=replace(event.source._identity,runtime_profile='unknown',runtime_home=foreign)
    assert request_prepared_pairing(r,event) is False
    assert not foreign.exists()


def test_native_rate_transactions_preserve_stamps_across_processes(env):
    import os,subprocess,sys
    script="""from gateway.pairing import PairingStore
import sys
store=PairingStore()
for i in range(8):
    store._record_rate_limit('telegram',sys.argv[1]+str(i))
"""
    child_env=dict(os.environ,HERMES_HOME=str(env.home))
    children=[subprocess.Popen([sys.executable,'-c',script,str(n)],env=child_env,
               stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True) for n in range(4)]
    for child in children:
        _,error=child.communicate(timeout=20)
        assert child.returncode==0,error
    store=PairingStore()
    assert all('telegram:'+str(n)+str(i) in store._limits() for n in range(4) for i in range(8))


def test_native_telegram_builder_and_canonical_route_reach_pending(env):
    from gateway.config import PlatformConfig
    from gateway.session_identity import identity_of
    from gateway.platforms.event import MessageType
    from plugins.platforms.telegram.adapter import TelegramAdapter
    from plugins.platforms.telegram.telegram_message_event import build_message_event
    prepared(env)
    runner,old,_=event_runner(env)
    runner.config=GatewayConfig(multiplex_profiles=True)
    adapter=object.__new__(TelegramAdapter)
    adapter.platform=Platform.TELEGRAM;adapter.gateway_runner=runner
    adapter._bot=old.raw_message.get_bot();adapter.config=PlatformConfig()
    adapter._resolve_topic_binding=lambda *a:(None,None)
    adapter._reply_context=lambda *a:(None,None)
    adapter.send=AsyncMock()
    runner.adapters={Platform.TELEGRAM:adapter}
    # Use actual builder, route refresh, served-profile discovery, identity
    # resolver and intake/receiving-pairing selection. No source identity patch.
    del runner._intake_adapter_for
    event=build_message_event(adapter,old.raw_message,MessageType.TEXT,21)
    assert event.source.profile=='user-2001' and identity_of(event.source) is None
    assert asyncio.run(runner._hm_admit_event(event)) is None
    identity=identity_of(event.source)
    assert identity is not None and identity.adapter() is adapter
    assert identity.authorization_home==env.home
    assert identity.runtime_home==upstream.home(env,'2001')
    assert runner.pairing_store.list_pending('telegram')[0]['user_id']=='2001'
    adapter.send.assert_not_awaited()
