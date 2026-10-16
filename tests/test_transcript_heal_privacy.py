"""Native request projection and diagnostic audience contracts, offline."""
import copy
import logging
from unittest.mock import patch
import pytest
from agent import agent_runtime_helpers as arh, chat_completion_helpers as ch
from hermes_cli import friday_user_scope as scope
from hermes_logging import clear_session_context, set_session_context
from tests.agent.test_sanitiser_escalation import TestProjectionStopsReheal as LoopFixture
from test_file_receipt_context import account, entered, actor, wire_agent, wire, frame, observation

@pytest.fixture(autouse=True)
def reset_healing():
    arh._empty_heal_log_state.clear();arh._empty_heal_pending_notice.clear();arh._empty_heal_user_notified.clear();clear_session_context()
    yield
    arh._empty_heal_log_state.clear();arh._empty_heal_pending_notice.clear();arh._empty_heal_user_notified.clear();clear_session_context()

@pytest.mark.parametrize('platform,ordinary,visible',[('telegram',False,False),('telegram',True,False),('cli',True,False),('cli',False,True),('discord',False,False)])
def test_repeated_repair_diagnostic_has_operator_audience_only(monkeypatch,caplog,platform,ordinary,visible):
    from tests.agent.test_run_agent import _mock_response
    monkeypatch.setattr("hermes_cli.friday_credential_admission.managed", lambda: False)
    a=LoopFixture()._loop_agent();a.platform=platform
    a.client.chat.completions.create.side_effect=[_mock_response(content='Useful response.',finish_reason='stop')]
    monkeypatch.setattr(scope,'ordinary_presentation',lambda source=None,**kwargs:ordinary if source is a else False)
    monkeypatch.setattr(arh,'_heal_escalation_threshold',lambda:1)
    set_session_context(str(a.session_id or '-'))
    with caplog.at_level(logging.ERROR,logger='run_agent'):
        canonical=[dict(role='user',content='First'),dict(role='assistant',content=''),dict(role='user',content='Next')]
        before=copy.deepcopy(canonical)
        arh.repair_empty_non_final_messages(canonical)
        assert canonical==before
    assert any('repeated-heal escalation' in r.message for r in caplog.records)
    expected=arh._empty_heal_pending_notice[str(a.session_id or '-')]
    emitted=[];a.status_callback=lambda kind,message:emitted.append((kind,message))
    a._print_fn=lambda *args,**kwargs:None
    history=[dict(role='user',content='Previous ask'),dict(role='assistant',content='Previous answer',finish_reason='stop')]
    original=copy.deepcopy(history)
    with patch.object(a,'_flush_messages_to_session_db'),patch.object(a,'_persist_session'),patch.object(a,'_save_trajectory'),patch.object(a,'_cleanup_task_resources'):
        result=a.run_conversation('Next ask',conversation_history=history)
    assert result['final_response']=='Useful response.'
    assert (("warn",expected) in emitted) is visible
    assert all(expected not in str(m) for m in a.client.chat.completions.create.call_args.kwargs['messages'])
    assert history==original and arh._empty_heal_pending_notice=={}
    assert next(iter(arh.get_sanitizer_heal_stats().values()))['heal_events']==1

@pytest.mark.parametrize('carrier',['text_blocks','reasoning'])
def test_private_projection_emptying_legacy_carrier_does_not_escalate(account,monkeypatch,carrier):
    monkeypatch.setattr(arh,'_heal_escalation_threshold',lambda:1)
    with entered(account):
        a=wire_agent(actor(None));a._cached_system_prompt=''
        legacy=(dict(role='assistant',content=[dict(type='text',text=frame())]) if carrier=='text_blocks'
                else dict(role='assistant',content=frame(),reasoning_content=frame()))
        rows=[dict(role='user',content='Keep this request'),legacy,observation(),dict(role='user',content='Continue')]
        before=copy.deepcopy(rows)
        for _ in range(5):
            for projected in (wire(a,rows),ch._iteration_summary_api_messages(a,rows)):
                assert len(projected)==3
                assert projected[1]['content']==arh._INTERRUPTED_PLACEHOLDER
                assert arh.repair_empty_non_final_messages(projected)==projected
        assert arh.get_sanitizer_heal_stats()=={}
        assert arh.consume_pending_sanitizer_heal_notice() is None
        assert rows==before


def test_projection_refusal_still_refuses_and_preserves_input(account):
    with entered(account):
        a=wire_agent(actor(None));a._cached_system_prompt=''
        rows=[dict(role='user',content='Continue'),dict(role='assistant',content='Previous')]
        before=copy.deepcopy(rows)
        a._friday_user_scope.revoked=True
        with pytest.raises(scope.ScopeDenied):wire(a,rows)
        assert rows==before


@pytest.mark.parametrize('pad',[' ', '\t', '\n', ''])
def test_provider_whitespace_pad_does_not_turn_receipt_into_speech(account,pad):
    from agent.message_sanitization import apply_reasoning_content_policy
    with entered(account):
        a=wire_agent(actor(None));a._cached_system_prompt=''
        a._copy_reasoning_content_for_api=lambda msg,out:apply_reasoning_content_policy(msg,out,True)
        rows=[dict(role='user',content='Original request')]
        rows.extend(dict(role='assistant',content=frame(),reasoning_content=pad) for _ in range(6))
        rows.extend([observation(),dict(role='assistant',content='Useful answer',reasoning_content=pad),dict(role='user',content='Next request')])
        before=copy.deepcopy(rows)
        for _ in range(5):
            for projected in (wire(a,rows),ch._iteration_summary_api_messages(a,rows)):
                assert [r['content'] for r in projected]==['Original request','Useful answer','Next request']
                assert projected[1]['reasoning_content']==(pad or ' ')
                assert arh.repair_empty_non_final_messages(projected)==projected
        assert arh.get_sanitizer_heal_stats()=={} and rows==before


@pytest.mark.parametrize('kind',['reasoning','tool_call','both'])
def test_receipt_with_real_reasoning_or_tool_call_is_retained(account,kind):
    with entered(account):
        a=wire_agent(actor(None));a._cached_system_prompt=''
        call=dict(id='c1',type='function',function=dict(name='read_file',arguments='{}'))
        rows=[dict(role='user',content='Read file'),dict(role='assistant',content=frame(),reasoning_content='Useful preserved reasoning',tool_calls=[call]),dict(role='tool',tool_call_id='c1',content='Evidence'),dict(role='user',content='Continue')]
        if kind=='reasoning':rows[1].pop('tool_calls')
        if kind=='tool_call':rows[1]['reasoning_content']=' '
        before=copy.deepcopy(rows);projected=wire(a,rows)
        assert len(projected)==4
        if kind!='reasoning':assert projected[1]['tool_calls']==[call]
        assert projected[1]['reasoning_content']==rows[1]['reasoning_content']
        assert projected[2]==rows[2] and rows==before


def test_user_quoted_diagnostics_and_code_are_not_filtered(account):
    with entered(account):
        a=wire_agent(actor(None));a._cached_system_prompt=''
        text="Explain this log: repeated repair; /debug share; hermes doctor; /new. Code: print('repair')."
        rows=[dict(role='user',content=text),dict(role='assistant',content='I can explain that log.'),dict(role='user',content='Keep the quotation')]
        before=copy.deepcopy(rows)
        assert wire(a,rows)==rows and rows==before
