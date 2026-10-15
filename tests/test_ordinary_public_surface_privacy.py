"""Isolated actual-native interface regression: no service, network, model or user data."""
import asyncio
import contextlib
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import time
import sys
from types import ModuleType

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from hermes_cli import friday_user_scope as scope, friday_product_access as access
from hermes_cli.dashboard_auth import middleware as mw
from hermes_cli.dashboard_auth.base import Session
from gateway import run_busy, run_turn, slash_commands_status as status
from gateway.platforms import base
from gateway.session import SessionSource
from gateway.config import Platform
from tools.registry import ToolRegistry


def run(coro):return asyncio.run(coro)

@pytest.fixture
def ordinary(monkeypatch):
    cap=NS(check=lambda:cap)
    token=scope._CURRENT.set(cap)
    try:yield cap
    finally:scope._CURRENT.reset(token)

@pytest.mark.parametrize('revoked',[False,True])
def test_audience_does_not_grant_by_claim_and_denied_scope_stays_minimal(monkeypatch,revoked):
    monkeypatch.setattr(scope,'_ENGAGED',False)
    monkeypatch.setattr(scope,'policy',lambda home:None)
    source=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id='synthetic-user',user_name='owner developer admin')
    assert scope.ordinary_presentation(source) is False
    monkeypatch.setattr(scope,'policy',lambda home: {'managed':True})
    assert scope.ordinary_presentation(source) is True
    if revoked:
        monkeypatch.setattr(scope,'policy',lambda home: (_ for _ in ()).throw(scope.ScopeDenied()))
        assert scope.ordinary_presentation(source) is True
    assert 'подтверждена' in scope.pending_stop_copy(source)
    assert 'пока не начат' in scope.pending_stop_copy(source,reset=True)


def test_unscoped_native_stop_diagnostic_unchanged(monkeypatch):
    monkeypatch.setattr(scope,'_ENGAGED',False)
    monkeypatch.setattr(scope,'policy',lambda home:None)
    assert scope.pending_stop_copy()=='Stop pending: native web process cessation is unconfirmed.'


def test_ordinary_slash_denial_is_plain_russian(ordinary,monkeypatch):
    monkeypatch.setattr(scope,'slash_allowed',lambda source,name:False)
    value=run_busy.GatewayBusySessionMixin._check_slash_access(NS(),NS(),'model')
    assert 'недоступна' in value and '/status' in value and 'product_' not in value

@pytest.mark.parametrize('state',['idle','pending','running'])
def test_ordinary_status_never_loads_model_route_or_database(ordinary,state,monkeypatch):
    native_constants=ModuleType("gateway.run");native_constants._AGENT_PENDING_SENTINEL=object()
    monkeypatch.setitem(sys.modules,"gateway.run",native_constants)
    _AGENT_PENDING_SENTINEL=native_constants._AGENT_PENDING_SENTINEL
    source=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id='synthetic-user')
    async def get(source):return NS(session_key='private-key',session_id='00000000-1111-2222-3333-444444444444')
    agents={} if state=='idle' else {'private-key':_AGENT_PENDING_SENTINEL if state=='pending' else object()}
    def forbidden(*a):raise AssertionError('ordinary projection touched detailed metadata')
    runner=NS(async_session_store=NS(get_or_create_session=get),_running_agents=agents,
              adapters={Platform.TELEGRAM:object(),Platform.SLACK:object()},_queue_depth=lambda *a,**k:2,
              _status_session_db_facts=forbidden,_cached_agent_for=forbidden)
    result=run(status.GatewayStatusCommandsMixin._handle_status_command(runner,NS(source=source)))
    assert 'В очереди: 2' in result and 'подтверждение остановки' in result
    assert {'idle':'нет активного','pending':'начинаю','running':'выполняю'}[state] in result
    for secret in ['00000000','private-key','slack','telegram','provider','model','Hermes']:assert secret not in result

@pytest.mark.parametrize('managed',[False,True])
def test_outer_error_keeps_private_traceback_and_only_managed_copy_is_minimal(monkeypatch,caplog,managed):
    monkeypatch.setattr(scope,'ordinary_presentation',lambda source=None:managed)
    source=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id='synthetic-user')
    event=NS(source=source,reply_to_message_id=None,message_id='m',internal=False)
    sent=[]
    async def send(**kwargs):sent.append(kwargs['content'])
    adapter=NS(name='fixture',_media_delivery_scope=lambda source:contextlib.nullcontext(),
               warning_text=lambda detailed,*a,**k:detailed,send=send)
    err=RuntimeError('synthetic /host/private/profile model=fixture-provider UUID-ONLY-PRIVATE')
    run(base.BasePlatformAdapter._notify_turn_error(adapter,event,err))
    assert len(sent)==1
    if managed:
        assert 'Часть действий могла выполниться' in sent[0]
        assert '/host/private' not in sent[0] and 'RuntimeError' not in sent[0]
        assert '/host/private' in caplog.text
    else:assert '/host/private' in sent[0] and 'RuntimeError' in sent[0]

@pytest.mark.parametrize('partial',[False,True])
def test_native_failed_turn_copy_retains_partial_semantics_without_selfhelp(ordinary,partial):
    messages=[{'role':'user','content':'do it'}]
    if partial:messages.append({'role':'tool','content':'synthetic result','tool_call_id':'x'})
    mix=run_turn.GatewayTurnMixin
    notice=mix._hmwa_failed_turn_notice(NS(),{'messages':messages,'history_offset':0})
    result=mix._hmwa_add_failed_turn_notice(NS(),'private provider failure /host/path hermes logs /login',notice)
    assert 'ошиб' in result or 'удалось' in result
    assert ('Часть действий' in result)==partial
    for value in ['provider','/host','hermes','/login']:assert value not in result


def test_native_dispatch_error_and_scope_denial_minimize_metadata(ordinary,monkeypatch,caplog):
    def fail(args):raise RuntimeError('synthetic /host/private UUID-ONLY-PRIVATE')
    registry=ToolRegistry();registry.register('fixture','fixture',{'name':'fixture','parameters':{'type':'object'}},fail)
    monkeypatch.setattr(scope,'guard_tool',lambda *a:None)
    result=registry.dispatch('fixture',{})
    assert '/host/private' not in str(result) and 'Частич' not in str(result) and 'частичный' in str(result)
    assert '/host/private' in caplog.text
    monkeypatch.setattr(scope,'guard_tool',lambda *a:(_ for _ in ()).throw(scope.ScopeDenied()))
    result=registry.dispatch('fixture',{})
    assert 'недоступно' in str(result) and 'product_' not in str(result)


def request(path,headers=(),auth=True):
    return Request({'type':'http','method':'GET','path':path,'raw_path':path.encode(),'root_path':'',
                    'query_string':b'','scheme':'https','headers':list(headers),'server':('fixture.invalid',443),
                    'client':('192.0.2.1',1234),'app':NS(state=NS(auth_required=auth))})

@pytest.fixture
def admin_policy(monkeypatch):
    policy={'enabled':True,'operators':[{'provider':'fixture','user_id':'operator','org_id':''}],'profiles':['default']}
    monkeypatch.setattr(access,'admin_policy',lambda:policy)
    monkeypatch.setattr(mw,'_auto_sso_response',lambda req:None)
    monkeypatch.setattr(mw,'audit_log',lambda *a,**k:None)
    return policy

@pytest.mark.parametrize('path',['/api/health','/api/status'])
@pytest.mark.parametrize('auth',[False,True])
def test_public_liveness_is_minimal_without_reading_route(admin_policy,path,auth):
    async def never(req):raise AssertionError('public request invoked native deployment metadata')
    result=run(mw.gated_auth_middleware(request(path,auth=auth),never))
    assert result.status_code==200 and json.loads(result.body)=={'ok':True}

@pytest.mark.parametrize('path',['/api/model/info','/api/config/defaults','/api/config/schema','/api/dashboard/themes','/api/dashboard/plugins'])
def test_managed_public_metadata_requires_native_authentication(admin_policy,path):
    async def never(req):raise AssertionError('unauthenticated native metadata bypass')
    result=run(mw.gated_auth_middleware(request(path),never))
    assert result.status_code==401

@pytest.mark.parametrize('identity',['operator','ordinary','claimed-owner'])
def test_admin_metadata_requires_verified_allowed_identity(admin_policy,monkeypatch,identity):
    sess=Session(identity,'','', '', 'fixture', int(time.time())+60,'synthetic','')
    monkeypatch.setattr(mw,'_verify_access_token',lambda *a,**k:sess)
    called=[]
    async def next_(req):called.append(req.state.session.user_id);return JSONResponse({'private_model':'fixture'})
    result=run(mw.gated_auth_middleware(request('/api/status',[(b'authorization',b'Bearer synthetic')]),next_))
    assert result.status_code==(200 if identity=='operator' else 403)
    assert bool(called)==(identity=='operator')

@pytest.mark.parametrize('path',['/api/status','/api/model/info'])
def test_forged_headers_do_not_authorize(admin_policy,monkeypatch,path):
    monkeypatch.setattr(mw,'_verify_access_token',lambda *a,**k:None)
    async def never(req):raise AssertionError('forged caller reached privileged route')
    headers=[(b'authorization',b'Bearer forged'),(b'user-agent',b'hermes native owner'),(b'x-role',b'admin')]
    result=run(mw.gated_auth_middleware(request(path,headers),never));assert result.status_code==401


def test_unmanaged_native_public_metadata_remains_donor_behavior(monkeypatch):
    monkeypatch.setattr(access,'admin_policy',lambda:None)
    async def next_(req):return JSONResponse({'configuredModel':'fixture','version':'synthetic'})
    result=run(mw.gated_auth_middleware(request('/api/model/info'),next_))
    assert json.loads(result.body)['configuredModel']=='fixture'


def test_policy_failure_does_not_enable_metadata_bypass(monkeypatch):
    monkeypatch.setattr(access,'admin_policy',lambda:(_ for _ in ()).throw(ValueError('private broken config')))
    async def never(req):raise AssertionError('broken policy became privileged')
    assert json.loads(run(mw.gated_auth_middleware(request('/api/health'),never)).body)=={'ok':True}
    result=run(mw.gated_auth_middleware(request('/api/model/info',auth=False),never));assert result.status_code==403


def test_signed_native_identity_authorization_path_is_unchanged():
    # Exact source invariance of the IPC owner/proof and status route is separately
    # asserted by runner; this protects middleware classification, not live ownership.
    assert '/api/host/identity' not in mw.PUBLIC_API_PATHS
    assert not mw._path_is_public('/api/host/identity')

@pytest.mark.parametrize('operation',['stop','new'])
def test_busy_uncertain_stop_never_runs_reset_or_claims_clean_exit(ordinary,monkeypatch,operation):
    constants=ModuleType('gateway.run');constants._INTERRUPT_REASON_STOP='synthetic-stop';constants._INTERRUPT_REASON_RESET='synthetic-reset'
    monkeypatch.setitem(sys.modules,'gateway.run',constants)
    calls=[]
    async def interrupt(*a,**k):calls.append(k);return {'status':'STOP_UNCONFIRMED'}
    async def forbidden(*a):raise AssertionError('reset executed after unconfirmed stop')
    runner=NS(_interrupt_and_clear_session=interrupt,_handle_reset_command=forbidden)
    handler=getattr(run_busy.GatewayBusySessionMixin,'_busy_'+operation+'_command').__wrapped__
    result=run(handler(runner,NS(),'synthetic-key',NS()))
    assert len(calls)==1 and 'подтверждена' in str(result)
    assert ('пока не начат' in str(result))==(operation=='new')
    for leaked in ['native','process','STOP_UNCONFIRMED']:assert leaked not in str(result)


def test_managed_auth_outage_hides_exception_and_preserves_503(admin_policy,monkeypatch,caplog):
    from hermes_cli.dashboard_auth.base import ProviderError
    def unavailable(*a,**k):raise ProviderError('synthetic-provider /host/private')
    monkeypatch.setattr(mw,'_verify_access_token',unavailable)
    async def never(req):raise AssertionError('outage became authenticated')
    result=run(mw.gated_auth_middleware(request('/api/status',[(b'authorization',b'Bearer synthetic')]),never))
    assert result.status_code==503 and 'временно недоступен' in json.loads(result.body)['detail']
    assert '/host/private' not in result.body.decode() and '/host/private' in caplog.text


def test_real_native_nonce_owner_proof_accepts_exact_and_refuses_tampering(monkeypatch,tmp_path):
    from hermes_cli import friday_dashboard_owner as owner
    from gateway import host_rendezvous as hr
    assert hr.PROBE_TIMEOUT_S == 2.0
    token='synthetic-private-role-token';secret=b'synthetic-owner-secret';nonce='a'*32
    identity={'operator':{'user_id':'operator'},'synthetic':'owner'}
    record=NS(home=str(tmp_path),role='serve',friday_owner=identity,pid=31337,start_time=123.0,token_fingerprint=hr.token_fingerprint(token))
    monkeypatch.setattr(owner,'credentials',lambda *a:(None,{'secret':secret},None,None))
    monkeypatch.setattr(owner,'read_owned',lambda *a,**k:token.encode())
    payload={'probeNonce':nonce,'ownerProof':owner.proof_mac(identity,nonce,record.pid,record.start_time,token,secret)}
    owner.verify_probe(record,payload,nonce)
    for bad in [dict(payload,probeNonce='b'*32),dict(payload,ownerProof='0'*64)]:
        with pytest.raises(ValueError):owner.verify_probe(record,bad,nonce)
