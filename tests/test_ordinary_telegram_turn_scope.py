"""Isolated native ordinary-turn boundary regression. Never model/live Telegram."""
import asyncio
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from gateway.run import GatewayRunner
from gateway.platforms.event import MessageEvent
from gateway.config import Platform, GatewayConfig
from gateway.session import SessionSource
from gateway.turn_lease import TurnLeaseTimeoutError
from hermes_cli import friday_user_scope as users
from hermes_constants import get_hermes_home

OLD = Path(__file__).with_name('test_ingress_receipt_scope.py')
spec = importlib.util.spec_from_file_location('source58_fixture', OLD)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
env = old.env


class PreparedBoundary(Exception):
    pass


def setup_runner(e, *, mode='return', assert_resolve=True):
    """Keep real ingress/agent/prepare/postturn producers; stop after prepare guard."""
    r=e.runner
    adapter=SimpleNamespace(send=AsyncMock())
    r.adapters={Platform.TELEGRAM:adapter}; r.pairing_store=MagicMock(); r.session_store=MagicMock()
    r._is_user_authorized_for_source=lambda s:e.auth._principal_authorized(s,allow_adapter_delegation=True)
    r._admit_bot_message_for_source=lambda s:True
    r._delivery_adapter_for=lambda s:adapter; r._intake_adapter_for=lambda s:adapter
    r._rescue_orphaned_overflow=lambda *a:None; r._enqueue_fifo=MagicMock()
    observations=[]
    def check(label, source):
        cap=users.current(required=True)
        assert cap is source._friday_user_scope
        assert users._SOURCE.get() is source
        assert get_hermes_home()==cap.home
        users.check_database()
        observations.append((label,cap.principal[-1]))
    async def resolve(event,source):
        if assert_resolve: check('session-resolution',source)
        return source,SimpleNamespace(session_id='offline-session',session_key='offline-key'),'offline-key'
    r._hmwa_resolve_session=resolve
    async def opened(entry,key,source):
        check('actual-prepare-after-check_database',source)
        await asyncio.to_thread(check,'thread-hop',source)
        if mode=='exception': raise RuntimeError('downstream-fixture-error')
        if mode=='cancel': raise asyncio.CancelledError()
        if mode=='timeout': raise TurnLeaseTimeoutError('offline-session',owner_key=key,generation=1,wait_seconds=0)
        raise PreparedBoundary()
    r._hmwa_open_session=opened
    real_prepare=GatewayRunner._hmwa_prepare_turn
    async def prepare(*args):
        try: return await real_prepare(r,*args)
        except PreparedBoundary: return 'offline-prepared-boundary',[]
    r._hmwa_prepare_turn=prepare
    class Store:
        _store=r.session_store
        async def get_or_create_session(self,source,**kwargs):
            check('native-postturn-session-resolution',source)
            await asyncio.to_thread(check,'postturn-thread-hop',source)
            return SimpleNamespace(session_id='offline-session')
    r._async_session_store=Store()
    async def callback(**kwargs):
        check('postturn-callback',kwargs['source'])
        if mode=='postturn-error': raise ValueError('offline-best-effort')
    r._post_turn_goal_continuation=callback; r._post_turn_loop_completion=callback
    cleanup=[]
    for name in ('_restore_pending_one_turn_model_override','_release_running_agent_state','_release_turn_lease'):
        original=getattr(r,name)
        def wrapped(*args,_name=name,_original=original,**kwargs):
            cleanup.append(_name);return _original(*args,**kwargs)
        setattr(r,name,wrapped)
    original_clear=r._clear_durable_active_turn
    async def clear(*args,**kwargs):
        cleanup.append('_clear_durable_active_turn');return await original_clear(*args,**kwargs)
    r._clear_durable_active_turn=clear
    return r,observations,cleanup


def event(source,mid='ordinary-offline'):
    return MessageEvent(text='synthetic isolated ordinary fixture',message_id=mid,source=source)


def restored(e):
    assert users._CURRENT.get() is None and users._SOURCE.get() is None
    assert get_hermes_home()==e.root


def cleaned(r,cleanup):
    assert cleanup==['_restore_pending_one_turn_model_override','_clear_durable_active_turn',
                     '_release_running_agent_state','_release_turn_lease']
    assert not any(r._is_session_running(k) for k in r._running_agents)




@pytest.mark.parametrize('index',[0,1])
@pytest.mark.parametrize('mode',['return','postturn-error'])
def test_candidate_native_prepare_async_thread_and_postturn(env,index,mode):
    e=env; r,seen,cleanup=setup_runner(e,mode=mode)
    cap=e.sources[index]._friday_user_scope
    assert asyncio.run(r._handle_message(event(e.sources[index])))=='offline-prepared-boundary'
    assert {label for label,uid in seen}=={'session-resolution','actual-prepare-after-check_database',
        'thread-hop','native-postturn-session-resolution','postturn-thread-hop','postturn-callback'}
    assert {uid for label,uid in seen}=={str(index+1)}
    assert e.sources[index]._friday_user_scope is cap and not cap.revoked
    restored(e);cleaned(r,cleanup)


@pytest.mark.parametrize('mode',['exception','cancel','timeout'])
def test_candidate_failure_and_cancel_restore_and_cleanup(env,mode):
    e=env;r,seen,cleanup=setup_runner(e,mode=mode)
    if mode=='timeout':
        reply=asyncio.run(r._handle_message(event(e.sources[0])))
        assert isinstance(reply,str) and reply!='offline-prepared-boundary'
    else:
        with pytest.raises(RuntimeError if mode=='exception' else asyncio.CancelledError):
            asyncio.run(r._handle_message(event(e.sources[0])))
    assert not any(label.startswith('postturn') for label,uid in seen)
    restored(e);cleaned(r,cleanup)


@pytest.mark.parametrize('mutation',['missing','wrong-user','revoked','disabled','cross-user'])
def test_candidate_bad_cap_refused_without_downstream(env,mutation):
    e=env;r,seen,cleanup=setup_runner(e)
    s=copy.copy(e.sources[0])
    # Admission already happened; preserve its exact capability and test the producer boundary.
    async def admitted(event):return event,event.source,False
    r._hm_admit_event=admitted
    if mutation=='missing':del s._friday_user_scope
    if mutation=='wrong-user':s.user_id='2'
    if mutation=='revoked':s._friday_user_scope.revoked=True
    if mutation=='disabled':e.access('1',enabled=False)
    if mutation=='cross-user':
        with e.enter(1) as parent:
            with pytest.raises(users.ScopeDenied):asyncio.run(r._handle_message(event(s)))
            assert users.current(required=True) is parent
    else:
        with pytest.raises(users.ScopeDenied):asyncio.run(r._handle_message(event(s)))
    assert seen==[]
    restored(e);cleaned(r,cleanup)


@pytest.mark.parametrize('multiplex',[False,True])
def test_candidate_no_policy_preserves_native_ordinary_return(tmp_path,monkeypatch,multiplex):
    # Reuse isolated setup but no product policy/principal; existing native scopes remain no-op.
    import contextvars,hermes_constants
    root=tmp_path/'ordinary';root.mkdir(mode=0o700)
    (root/'config.yaml').write_text('{}');(root/'config.yaml').chmod(0o600)
    monkeypatch.setenv('HERMES_HOME',str(root));monkeypatch.setattr(hermes_constants,'_PINNED_PROCESS_HERMES_HOME',str(root))
    monkeypatch.setattr(users,'_ENGAGED',False)
    monkeypatch.setattr(users,'_CURRENT',contextvars.ContextVar('legacy-current',default=None))
    monkeypatch.setattr(users,'_SOURCE',contextvars.ContextVar('legacy-source',default=None))
    token=old.set_hermes_home_override(str(root))
    try:
        r=object.__new__(GatewayRunner);r.config=GatewayConfig(multiplex_profiles=multiplex)
        r._resolve_profile_home_for_source=lambda s:root
        source=SessionSource(Platform.TELEGRAM,'ordinary-chat',user_id='ordinary-user',chat_type='dm')
        e=SimpleNamespace(runner=r,auth=SimpleNamespace(_principal_authorized=lambda *a,**k:True))
        r,seen,cleanup=setup_runner(e)
        async def agent(*args):
            assert users.current() is None and get_hermes_home()==root
            return 'legacy-native-return'
        async def post(**kwargs):assert users.current() is None and get_hermes_home()==root
        r._handle_message_with_agent=agent;r._run_post_turn_hooks=post
        assert asyncio.run(r._handle_message(event(source)))=='legacy-native-return'
        assert users._CURRENT.get() is None and get_hermes_home()==root
        cleaned(r,cleanup)
    finally:old.reset_hermes_home_override(token)
