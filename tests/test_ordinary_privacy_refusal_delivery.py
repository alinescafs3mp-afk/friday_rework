import copy,json
from types import SimpleNamespace as NS
import pytest
from test_ordinary_dialogue_continuation import env,entered,home,native_agent
from hermes_cli import friday_user_scope as scope
from gateway.run_turn import GatewayTurnMixin as GT

@pytest.mark.parametrize('evidence',[None,'call','tool','unknown'])
def test_typed_refusal_survives_gateway_failure_notice_without_claiming_task_success(env,evidence):
 with entered(env):
  messages=[{'role':'tool','content':'old result'},{'role':'user','content':'current private question'}]
  if evidence=='call':messages.append({'role':'assistant','tool_calls':[{'id':'call','function':{'name':'write_file','arguments':'{}'}}]})
  if evidence=='tool':messages.append({'role':'tool','tool_call_id':'call','content':'result'})
  result={'failed':True,'completed':False,'failure_reason':'private_reply_withheld','privacy_refusal':True,'messages':messages,'history_offset':1,'effect_unknown':evidence=='unknown'}
  before=copy.deepcopy(result)
  notice=GT._hmwa_failed_turn_notice(NS(),result)
  reply=GT._hmwa_add_failed_turn_notice(NS(),'suppressed response',notice)
  assert reply.startswith(scope.PRIVATE_REPLY_COPY) and 'Не удалось завершить' not in reply
  assert ('Часть действий могла выполниться' in reply)==(evidence is not None)
  assert result==before and result['failed'] and not result['completed']

@pytest.mark.parametrize('failure',['provider_error','private_reply_withheld'])
def test_untyped_failure_remains_honest_operational_failure(env,failure):
 with entered(env):
  notice=GT._hmwa_failed_turn_notice(NS(),{'failed':True,'completed':False,'failure_reason':failure,'messages':[{'role':'user','content':'task'}]})
  assert 'Не удалось завершить' in notice and scope.PRIVATE_REPLY_COPY not in notice

def test_scope_failure_is_not_misrepresented_as_confidentiality_policy(env):
 with entered(env):
  a=native_agent();scope.current().revoked=True
  public,blocked=scope.guard_generated_reply(a,'Harmless requested task')
  assert blocked and public==scope.PRIVATE_REPLY_FAILURE_COPY and not scope.is_privacy_refusal(a)

def test_confidential_candidate_typed_but_no_harmless_task_routing(env):
 with entered(env):
  a=native_agent();public,blocked=scope.guard_generated_reply(a,'Моя модель — private-router.')
  assert blocked and public==scope.PRIVATE_REPLY_COPY and scope.is_privacy_refusal(a)
  good='Для вашего проекта Hermes работает на Linux. [Отчёт](./report.txt)'
  assert scope.guard_generated_reply(native_agent(),good)==(good,False)

def test_reason_reset_is_part_of_native_turn_preparation():
 import inspect
 from agent import turn_context
 s=inspect.getsource(turn_context)
 assert 'agent._friday_reply_withheld = False\n    agent._friday_reply_withheld_reason = None' in s

@pytest.mark.parametrize('tool',[False,True])
def test_non_gateway_generated_rows_keep_effect_honesty_and_private_record(env,tool):
 with entered(env):
  a=native_agent()
  rows=([{'role':'tool','content':'a tool result','tool_call_id':'prior'}] if tool else []) + [{'role':'assistant','content':'Моя модель — private-router.'}]
  messages=copy.deepcopy(rows)
  scope.guard_generated_rows(a,rows,messages)
  assert rows[-1]['content']==scope.private_reply_copy(effect_unknown=tool)
  assert ('Часть действий могла выполниться' in rows[-1]['content']) is tool
  from hermes_state_registry import acquire
  db=acquire(home(env)/'state.db')
  try:record=json.loads(db.get_meta('friday.private_reply.latest'))
  finally:db.close()
  assert record['tool_effects_may_have_occurred'] is tool

