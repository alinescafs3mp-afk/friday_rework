"""Source-only candidate through native dispatch; no model, network, or children."""
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools import web_process as web
from agent.web_call_context import WebTurn,WebCall,bind_web_call
from tools.process_registry import process_registry
from tools.registry import registry
from tools.web_result_cache import search_memo
import hermes_cli.friday_user_scope as user_scope

SENSITIVE='/private/profile/token-SECRET-123'

@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(user_scope,'current',lambda *a,**k:None)
    monkeypatch.setattr(user_scope,'ordinary_presentation',lambda *a,**k:True)
    monkeypatch.setattr(web,'_scope_payload',lambda home:{})
    # True native registry; async extraction bridged locally to avoid importing unrelated model tools.
    import sys
    monkeypatch.setitem(sys.modules,'model_tools',SimpleNamespace(_run_async=asyncio.run))
    registry.register('web_search','web',{'name':'web_search','parameters':{'type':'object'}},web.search_handler)
    registry.register('web_extract','web',{'name':'web_extract','parameters':{'type':'object'}},web.extract_handler,is_async=True)
    h=SimpleNamespace(ordinary=True,spawns=0,exchanges=0,stops=0,value='{"success": true}',exchange_error=None,settlement='QUIESCENT',stop_status='QUIESCENT',stop_error=None,exit_zero=True)
    h.turn=WebTurn();h.call=WebCall(h.turn,time.monotonic()+60,'test-task','test-session','test-call')
    h.session=SimpleNamespace(id='private-process-1',web_deadline=h.call.deadline(),owned=True)
    def spawn(call):
        h.spawns+=1;call.session=h.session;call.registry=process_registry;return h.session
    def exchange(session,payload,call):
        h.exchanges+=1
        if h.exchange_error:raise h.exchange_error
        return json.dumps({'value':h.value,'search_memo':None})
    def settle(session,stop=False):
        if stop:
            h.stops+=1
            if h.stop_error:raise h.stop_error
            status=h.stop_status
        else:status=h.settlement
        if status=='QUIESCENT':session.owned=False
        return {'status':status,'session_id':session.id,'native_child_exit_zero':h.exit_zero,'private_diagnostic':SENSITIVE}
    monkeypatch.setattr(process_registry,'spawn_web',spawn)
    monkeypatch.setattr(process_registry,'web_exchange',exchange)
    monkeypatch.setattr(process_registry,'settle_web',settle)
    # Real native lock, independent per private interpreter; memo payload irrelevant to adapter tests.
    monkeypatch.setattr(search_memo,'export_query',lambda *a:None)
    monkeypatch.setattr(search_memo,'import_query',lambda *a:None)
    def dispatch(name='web_search'):
        with bind_web_call(h.call):
            return registry.dispatch(name,{'query':'test query','urls':['https://invalid.invalid/test'],'limit':5},task_id='test-task',session_id='test-session')
    h.dispatch=dispatch
    return h

def assert_safe(value,cleanup):
    body=json.loads(value)
    assert body['success'] is False and body['retry_allowed'] is False
    assert body['information_verified'] is False and body['cleanup']==cleanup
    assert any('\u0400'<=c<='\u04ff' for c in body['error'])
    assert 'Не повторяй' in body['guidance'] and 'из памяти' in body['guidance']
    assert 'источника' in body['guidance']
    for hidden in ('SECRET','/private/','private-process-1','STOP_UNCONFIRMED','web_native_boundary_refused','web_provider_failed','web_call_stopped','RuntimeError','TimeoutError'):
        assert hidden not in value
    return body

@pytest.mark.parametrize('name',['web_search','web_extract'])
@pytest.mark.parametrize('value',[
    ' { "results" : [ { "title": "error handling", "content": "HTTP error is discussed" } ] }\n',
    '{"results":[{"error":"failed","url":"x"},{"content":"verified part","url":"y"}]}',
    '{"content":"An error occurred in the historical example.","success":true}',
    'Plain text mentioning error and timeout',
    '{\n  "results": [], "count": 0\n}',
    '{"partial":true,"read_file":{"path":"private-data-recovery"},"error":"capacity warning"}',
    '{"partial":true,"success":false,"error":"capacity warning","results":[{"content":"usable partial page"},{"error":"unavailable"}]}',
    '{"success":false,"error":"capacity warning","data":{"web":[{"url":"https://example.org","title":"usable source"}]}}',
    '{"error":"capacity warning","results":[{"error":"provider warning","raw_content":"usable page"}]}',
    '{"partial":true,"results":[{"read_file":{"path":"private-recovery"},"error":"page truncated"}]}',
])
def test_success_exact_bytes(harness,name,value):
    h=harness;h.value=value
    assert h.dispatch(name)==value
    assert h.spawns==h.exchanges==1
    assert h.call not in h.turn.calls
    assert h.call.receipt['status']=='QUIESCENT'
    assert not h.session.owned

@pytest.mark.parametrize('exc',[RuntimeError(SENSITIVE),TimeoutError(SENSITIVE)])
@pytest.mark.parametrize('name',['web_search','web_extract'])
def test_parent_failure_timeout_safe_cleanup(harness,exc,name):
    h=harness;h.exchange_error=exc
    assert_safe(h.dispatch(name),'confirmed')
    assert h.stops==1 and h.call not in h.turn.calls and not h.session.owned
    if name=='web_search':
        lock=search_memo.flight_lock('__native_web_call__','test query',5)
        assert lock.acquire(blocking=False);lock.release()

@pytest.mark.parametrize('name',['web_search','web_extract'])
def test_sticky_stopped_before_assignment_unknown_no_retry(harness,name):
    h=harness;h.turn.stopped.set()
    body=assert_safe(h.dispatch(name),'unknown')
    assert 'остановлена' in body['error']
    assert_safe(h.dispatch(name),'unknown')
    assert h.spawns==0 and h.turn.stopped.is_set()

@pytest.mark.parametrize('ordinary',[True,False])
def test_stop_unconfirmed_preserves_receipt_ownership_fence(harness,monkeypatch,ordinary):
    h=harness;h.settlement='STOP_UNCONFIRMED';h.stop_status='STOP_UNCONFIRMED'
    monkeypatch.setattr(user_scope,'ordinary_presentation',lambda *a,**k:ordinary)
    value=h.dispatch()
    if ordinary:assert_safe(value,'unconfirmed')
    else:assert json.loads(value)=={'error':'STOP_UNCONFIRMED','native_process_id':h.session.id}
    assert h.call.receipt['status']=='STOP_UNCONFIRMED'
    assert h.call.receipt['private_diagnostic']==SENSITIVE
    assert h.call in h.turn.calls and h.call.session is h.session and h.session.owned
    assert h.turn.stopped.is_set()
    h.dispatch()
    assert h.spawns==1
    lock=search_memo.flight_lock('__native_web_call__','test query',5)
    assert lock.acquire(blocking=False);lock.release()

def test_stop_observation_exception_never_claims_stopped(harness):
    h=harness;h.exchange_error=RuntimeError(SENSITIVE);h.stop_error=RuntimeError(SENSITIVE)
    body=assert_safe(h.dispatch(),'unconfirmed')
    assert 'остановка пока не подтверждена' in body['error']
    assert h.turn.stopped.is_set() and h.call in h.turn.calls and h.session.owned
    assert h.spawns==1
    h.dispatch();assert h.spawns==1

@pytest.mark.parametrize('value',[
    '{"error":"'+SENSITIVE+'"}',
    '{"success":false,"message":"'+SENSITIVE+'"}',
    '{"results":[{"error":"'+SENSITIVE+'"},{"error":"failed"}]}',
    '{"partial":true,"results":[],"error":"'+SENSITIVE+'"}',
    '{"success":false,"data":{"web":[]},"error":"'+SENSITIVE+'"}',
    '{"partial":true,"results":[{"error":"'+SENSITIVE+'","content":""}]}',
])
@pytest.mark.parametrize('name',['web_search','web_extract'])
def test_full_provider_failure_safe_guidance(harness,value,name):
    h=harness;h.value=value
    assert_safe(h.dispatch(name),'confirmed')
    assert h.spawns==1 and h.call not in h.turn.calls

@pytest.mark.parametrize('exc,expected',[(RuntimeError(SENSITIVE),'web_native_boundary_refused'),(TimeoutError(SENSITIVE),'web_timeout')])
def test_nonordinary_legacy_boundary_envelope(harness,monkeypatch,exc,expected):
    h=harness;h.exchange_error=exc
    monkeypatch.setattr(user_scope,'ordinary_presentation',lambda *a,**k:False)
    assert json.loads(h.dispatch())=={'error':expected,'detail':type(exc).__name__}

@pytest.mark.parametrize('value',['{"error":"provider original"}','{"success":false,"results":[]}'])
def test_nonordinary_provider_envelope_exact(harness,monkeypatch,value):
    h=harness;h.value=value
    monkeypatch.setattr(user_scope,'ordinary_presentation',lambda *a,**k:False)
    assert h.dispatch()==value

def test_private_home_isolation():
    sandbox = Path(os.environ['FRIDAY_TEST_SANDBOX']).resolve()
    for path in (Path.home(), Path(os.environ['HOME'])):
        assert path.resolve().is_relative_to(sandbox)
    for key in ('HERMES_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME',
                'XDG_DATA_HOME', 'XDG_STATE_HOME', 'TMPDIR'):
        assert Path(os.environ[key]).resolve().is_relative_to(sandbox)

@pytest.mark.parametrize('name',['web_search','web_extract'])
def test_provider_private_reason_vault_redacted_no_log_injection(harness,caplog,name):
    from agent.redact import register_vault_redaction_value,clear_vault_redaction_values
    secret='opaque synthetic vault value 728419-keep-private'
    register_vault_redaction_value(secret)
    try:
        h=harness
        h.value=json.dumps({'success':False,'error':'HTTP 401 '+secret+' '+SENSITIVE+'\nFORGED_WARNING\rcontrol'},indent=2)
        with caplog.at_level('WARNING',logger=web.__name__):
            public=h.dispatch(name)
        assert_safe(public,'confirmed')
        assert secret not in public and '401' not in public and 'FORGED_WARNING' not in public
        private=[r for r in caplog.records if r.name==web.__name__ and r.msg.startswith('Private web provider failure:')]
        assert len(private)==1
        message=private[0].getMessage()
        assert '401' in message and 'redacted-vault-secret' in message
        assert secret not in message
        assert '\n' not in message and '\r' not in message
        assert '\\n' in message
        assert h.spawns==1 and h.call not in h.turn.calls
    finally:
        clear_vault_redaction_values()

@pytest.mark.parametrize('name',['web_search','web_extract'])
def test_huge_provider_private_log_bounded_and_truncation_marked(harness,caplog,name):
    from agent.redact import register_vault_redaction_value,clear_vault_redaction_values
    secret='opaque synthetic bounded vault value 8192-private'
    register_vault_redaction_value(secret)
    try:
        h=harness
        h.value=json.dumps({'error':'HTTP 401 '+secret+' '+SENSITIVE+' '+'x'*20000+'\nFORGED_TAIL'})
        with caplog.at_level('WARNING',logger=web.__name__):
            public=h.dispatch(name)
        assert_safe(public,'confirmed')
        assert secret not in public
        private=[r for r in caplog.records if r.name==web.__name__ and r.msg.startswith('Private web provider failure:')]
        assert len(private)==1
        record=private[0]
        assert len(record.args[0])==2048
        assert record.args[1]==' [truncated]'
        message=record.getMessage()
        assert '401' in message and 'redacted-vault-secret' in message
        assert secret not in message and 'FORGED_TAIL' not in message
        assert message.endswith(' [truncated]') and len(message)<2200
        assert '\n' not in message and '\r' not in message
    finally:
        clear_vault_redaction_values()
