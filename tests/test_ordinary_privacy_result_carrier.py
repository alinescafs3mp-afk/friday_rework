from types import SimpleNamespace as NS
import pytest
from test_ordinary_dialogue_continuation import env,entered,home
from test_ordinary_private_reply_compression import actor
from hermes_cli import friday_user_scope as scope
from agent import turn_finalizer as tf
from gateway.run_turn import GatewayTurnMixin as GT
from gateway.run_turn_runner import TurnRunner
from gateway.turn_context import TurnContext
import copy,asyncio,time
from unittest.mock import patch

def through_real_run_sync(raw,source):
 agent=NS(model="synthetic-model",session_id="fixture")
 ctx=TurnContext(source=source,session_key=None,user_config={},message="synthetic task",agent_holder=[agent])
 gateway=NS(_resolve_session_agent_runtime=lambda **kw:("synthetic-model",{}),_provider_routing={},_resolve_session_reasoning_config=lambda **kw:None,_resolve_session_service_tier=lambda **kw:None,_resolve_turn_agent_config=lambda *a:{})
 tr=TurnRunner(gateway,ctx)
 tr._combined_ephemeral_prompt=lambda:""
 tr._setup_stream_consumer=lambda *a:(None,None,None,False)
 tr._resolve_turn_agent=lambda *a:(agent,False)
 tr._wire_turn_agent_callbacks=lambda *a:None
 tr._load_turn_history=lambda *a:([],None,set())
 tr._prepare_turn_message=lambda *a:(None,None)
 tr._run_conversation_with_approval=lambda *a:copy.deepcopy(raw)
 tr._finish_stream_consumer=lambda *a:None
 tr._sync_session_after_run=lambda *a:(False,"fixture",0)
 with patch("gateway.run._current_max_iterations",return_value=8):
  return tr.run_sync()


@pytest.mark.parametrize('effect',[None,'call','tool'])
@pytest.mark.parametrize('authority',['valid','revoked','missing'])
def test_native_finalizer_to_gateway_preserves_typed_failure_and_effects(env,monkeypatch,effect,authority):
 with entered(env):
  a=actor();a.max_iterations=8;a.platform='telegram';a.model='public-test';a.provider='custom';a.base_url='http://localhost';a.context_compressor=NS(last_prompt_tokens=0);a._tool_guardrail_halt_decision=None;a._skill_nudge_interval=0;a._iters_since_skill=0;a.valid_tool_names=set();a._persist_disabled=True;a.request_overrides={};a._drain_pending_steer=lambda:None;a.clear_interrupt=lambda:None;a._sync_external_memory_for_turn=lambda **kw:None
  for key in tf._SESSION_TOKEN_KEYS+tf._SESSION_COST_KEYS:setattr(a,'session_'+key,0)
  monkeypatch.setattr(tf,'_resolve_budget_fallback',lambda agent,final_response,*args,**kw:(final_response,'text_response(stop)',False,False));monkeypatch.setattr(tf,'_rollback_interrupted_preflight_display',lambda *a:None);monkeypatch.setattr(tf,'_guarded_cleanup',lambda *a:None);monkeypatch.setattr(tf,'_log_turn_exit',lambda *a:None);monkeypatch.setattr('hermes_cli.observability.shared_metrics_harness.finish_turn',lambda *args,**kw:None)
  monkeypatch.setattr(tf,'_append_file_mutation_footer',lambda agent,value,logger:value);monkeypatch.setattr(tf,'_explain_abnormal_exit',lambda agent,value,*args:value);monkeypatch.setattr(tf,'_invoke_hook_safely',lambda *args,**kw:[])
  rows=[{'role':'user','content':'Task'}]
  if effect=='call':rows.append({'role':'assistant','content':None,'tool_calls':[{'id':'fixture','function':{'name':'write_file','arguments':'{}'}}]})
  if effect=='tool':rows.append({'role':'tool','content':'synthetic effect evidence only','tool_call_id':'fixture'})
  if authority=='revoked':scope.current().revoked=True
  if authority=='missing':monkeypatch.setattr(scope,'_restricted_reply_values',lambda *args:(_ for _ in ()).throw(scope.ScopeDenied()))
  result=tf.finalize_turn(a,final_response='Моя модель — private-router.',api_call_count=1,interrupted=False,failed=False,messages=rows,conversation_history=[],effective_task_id=None,turn_id='fixture',user_message='Task',original_user_message='Task',_should_review_memory=False,_turn_exit_reason='text_response(stop)')
  raw=copy.deepcopy(result)
  result=through_real_run_sync(raw,env.sources['1'])
  assert raw['privacy_refusal'] is (authority=='valid')
  assert result['failed'] and not result['completed']
  assert result['effect_unknown'] is bool(effect) and result['partial'] is bool(effect)
  assert result['privacy_refusal'] is (authority=='valid')
  notice=GT._hmwa_failed_turn_notice(NS(),result);public=GT._hmwa_add_failed_turn_notice(NS(),result['final_response'],notice)
  if authority=='valid':assert public==scope.private_reply_copy(effect_unknown=bool(effect)) and 'Не удалось завершить' not in public
  else:assert scope.PRIVATE_REPLY_COPY not in public and ('ошибк' in public or 'Не удалось' in public)
  assert ('Часть действий могла выполниться' in public) is bool(effect)

@pytest.mark.parametrize("empty",[False,True])
@pytest.mark.parametrize("effect_unknown",[False,True])
@pytest.mark.parametrize("typed",[False,True])
def test_actual_result_carrier_preserves_type_and_uncertainty_on_both_returns(env,empty,effect_unknown,typed):
 with entered(env):
  raw=dict(final_response="" if empty else scope.PRIVATE_REPLY_COPY,failed=True,completed=False,partial=effect_unknown,privacy_refusal=typed,effect_unknown=effect_unknown,failure_reason="private_reply_withheld",messages=[dict(role="user",content="synthetic task")],api_calls=1,error="private safe diagnostic")
  result=through_real_run_sync(raw,env.sources['1'])
  assert result['privacy_refusal'] is typed
  assert result['effect_unknown'] is effect_unknown
  assert result['partial'] is effect_unknown
  assert result['failed'] is True and result['completed'] is False
  holder=NS(_is_intentional_silence=lambda *a:False)
  shaped,quiet,_=asyncio.run(GT._hmwa_shape_agent_response(holder,result,env.sources['1'],[],NS(session_id="fixture"),None,None,0,"fixture","telegram",time.time()))
  assert not quiet
  notice=GT._hmwa_failed_turn_notice(NS(),result)
  outbound=GT._hmwa_add_failed_turn_notice(NS(),shaped,notice)
  if typed:assert outbound==scope.private_reply_copy(effect_unknown=effect_unknown)
  else:assert scope.PRIVATE_REPLY_COPY not in outbound and ("ошибк" in outbound or "Не удалось" in outbound)
  assert ("Часть действий могла выполниться" in outbound) is effect_unknown
  assert result['failed'] and not result['completed']
  assert "private safe diagnostic" not in outbound

@pytest.mark.parametrize("empty",[False,True])
def test_absent_type_and_effect_fields_keep_ordinary_failure_default(env,empty):
 with entered(env):
  raw=dict(final_response="" if empty else "unreviewed diagnostic",failed=True,completed=False,partial=False,failure_reason="provider_error",messages=[dict(role="user",content="task")],api_calls=1,error="sensitive provider diagnostic")
  result=through_real_run_sync(raw,env.sources['1'])
  notice=GT._hmwa_failed_turn_notice(NS(),result)
  assert scope.PRIVATE_REPLY_COPY not in notice and "Не удалось завершить" in notice
  assert result['privacy_refusal'] is False and result['effect_unknown'] is False
  assert result['failed'] and not result['completed']

def test_real_run_sync_to_notice_reproduces_owner_generic_reply_before_fix(env):
 with entered(env):
  raw=dict(final_response=scope.PRIVATE_REPLY_COPY,failed=True,completed=False,partial=False,privacy_refusal=True,effect_unknown=False,failure_reason="private_reply_withheld",messages=[dict(role="user",content="private question")],api_calls=1)
  result=through_real_run_sync(raw,env.sources['1'])
  notice=GT._hmwa_failed_turn_notice(NS(),result)
  outbound=GT._hmwa_add_failed_turn_notice(NS(),result['final_response'],notice)
  assert result['failed'] and not result['completed']
  assert outbound==scope.PRIVATE_REPLY_COPY
