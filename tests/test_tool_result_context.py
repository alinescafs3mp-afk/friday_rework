import json,threading,time,copy
from types import SimpleNamespace as NS
import pytest
from test_ordinary_dialogue_continuation import env,entered,home,native_agent,own_db
from hermes_cli import friday_user_scope as scope
from agent import tool_executor as te,web_call_context as wc
from agent.session_persistence import SessionPersistenceMixin
from tools.budget_config import DEFAULT_BUDGET
from agent.tool_guardrails import ToolCallGuardrailController

class Actor(SessionPersistenceMixin):pass

def actor(db):
 a=Actor();a.__dict__.update(native_agent(db).__dict__)
 a._persist_disabled=False;a._session_db_created=True;a._last_flushed_db_idx=0
 a._current_turn_id='native-turn';a._web_run_deadline=time.monotonic()+60
 a._interrupt_requested=False;a._tool_worker_threads=set();a._tool_worker_threads_lock=threading.Lock()
 a._checkpoint_mgr=NS(enabled=False);a._tool_guardrails=ToolCallGuardrailController()
 a.quiet_mode=True;a.verbose_logging=False;a.tool_progress_callback=None;a.tool_start_callback=None;a.tool_complete_callback=None;a.tool_result_metadata_callback=None
 a._touch_activity=lambda *args:None;a._subdirectory_hints=NS(check_tool_call=lambda *args:None)
 a._tool_result_content_for_active_model=lambda name,result:result
 a._apply_pending_steer_to_tool_results=lambda *args:None
 return a

def ref():return te._ToolCallRef('tool_search',{'queries':['memory']},'native-task','native-call',[])

def dispatch(a):
 r=ref()
 def execute(args):
  scope.guard_tool('tool_search',args)
  call=wc.current_web_call()
  assert call.call_id==r.call_id and call.task_id==r.task_id
  from tools.tool_search import dispatch_tool_search
  return dispatch_tool_search(args,current_tool_defs=[])
 return te._run_sequential_tool_execution_middleware(a,**r.middleware_kwargs(),execute=execute)

def commit(a,m,value):
 return te._commit_tool_result(a,m,ref(),value,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None)

def callrow(reasoning=None):
 row={'role':'assistant','content':None,'tool_calls':[{'id':'native-call','type':'function','function':{'name':'tool_search','arguments':'{"queries":["memory"]}'}}]}
 if reasoning:row['reasoning_content']=reasoning
 return row

def test_real_scoped_worker_catalog_commit_followup_and_native_history(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);messages=[callrow()]
   assert a._flush_messages_to_session_db(messages)
   out=dispatch(a);assert not out.blocked and out.dispatched and 'queries' in out.result
   with pytest.raises(RuntimeError,match='web_caller_context_required'):wc.current_web_call()
   assert commit(a,messages,out.result) is not None
   te._finalize_tool_batch(a,messages,'native-task',1,DEFAULT_BUDGET)
   messages.append({'role':'assistant','content':'I can help with your task.'})
   assert a._flush_messages_to_session_db(messages)
   rows=db.get_messages(a.session_id)
   assert [r['role'] for r in rows][-3:]==['assistant','tool','assistant']
   assert rows[-2]['tool_call_id']=='native-call' and 'queries' in rows[-2]['content']
   scope.check_search(db=db)
   assert db.get_messages(a.session_id)[-1]['content']=='I can help with your task.'
   assert te.tool_execution_cwd(a,'native-task')==home(env)/'workspace'
 finally:db.close()

@pytest.mark.parametrize('bad',['foreign','missing','revoked','session','turn','deadline'])
def test_original_result_authority_cannot_be_adopted(env,bad):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);out=dispatch(a)
   if bad=='foreign':
    a._friday_user_scope=None
   elif bad=='missing':scope._CURRENT.set(None)
   elif bad=='revoked':scope.current().revoked=True
   elif bad=='session':a.session_id='foreign-session'
   elif bad=='turn':a._current_turn_id='foreign-turn'
   else:a._web_run_deadline+=30
   with pytest.raises((scope.ScopeDenied,RuntimeError)):commit(a,[],out.result)
 finally:db.close()

@pytest.mark.parametrize('kind',['cancel','expired','unknown'])
def test_stopped_result_is_durable_evidence_without_terminal_access(env,kind):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);dispatch(a)
   call=a._tool_result_calls[('native-task','native-call')]
   if kind=='cancel':call.turn.stop();a._interrupt_requested=True
   if kind=='expired':call.base_deadline=time.monotonic()-1
   messages=[callrow()];assert a._flush_messages_to_session_db(messages)
   assert te._commit_tool_result(a,messages,ref(),'Execution uncertain',budget=DEFAULT_BUDGET,tool_duration=.01,is_error=True,blocked=False,effect_disposition='unknown') is not None
   assert db.get_messages(a.session_id)[-1]['effect_disposition']=='unknown'
   assert a._friday_reply_effect_unknown is True
   if kind!='unknown':
    with wc.bind_web_call(call):
     with pytest.raises((RuntimeError,TimeoutError)):te.get_active_env('native-task')
 finally:db.close()

def test_source73_private_reasoning_dispatch_result_then_refusal_are_durable(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);messages=[callrow('Internal profile '+scope.current().profile)]
   assert a._flush_messages_to_session_db(messages)
   assert a._friday_reply_withheld and messages[0]['reasoning_content'] is None
   out=dispatch(a)
   assert commit(a,messages,out.result) is not None
   messages.append({'role':'assistant','content':'A harmless followup answer.'})
   assert a._flush_messages_to_session_db(messages)
   rows=db.get_messages(a.session_id)
   assert [r['role'] for r in rows][-3:]==['assistant','tool','assistant']
   assert rows[-1]['content']==scope.private_reply_copy(effect_unknown=True)
   assert scope.current().profile not in json.dumps(rows)
   assert a._friday_reply_effect_unknown is True
 finally:db.close()

def test_genuine_new_private_call_is_refused_before_storage(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);row=callrow()
   row['tool_calls'][0]['function']['arguments']=json.dumps({'queries':[str(home(env)/'config.yaml')]})
   assert a._flush_messages_to_session_db([row]) is False
   assert not any(x['role']=='assistant' for x in db.get_messages(a.session_id))
 finally:db.close()

def test_native_foreign_scope_cannot_publish_original_user_result(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);out=dispatch(a)
  with entered(env,'2'):
   with pytest.raises(scope.ScopeDenied):commit(a,[],out.result)
 finally:db.close()

def test_actual_cached_terminal_binding_stays_required_during_publication(env,monkeypatch):
 from pathlib import Path
 from tools.terminal_binding import TerminalBinding,canonical,directory_identity,cache_key,TerminalScopeDenied
 from tools.environments.scoped_local import ScopedLocalEnvironment
 from tools.terminal_tool import _active_environments
 db=own_db(env)
 try:
  with entered(env) as cap:
   a=actor(db);out=dispatch(a);call=a._tool_result_calls[('native-task','native-call')]
   state=home(env)/'cache'/'native-terminal-fixture';state.mkdir(parents=True,mode=0o700);state.chmod(0o700)
   workspace=home(env)/'workspace'
   binding=TerminalBinding(canonical(scope.delegation_authority()),'native-task',a.session_id,call.session_key,a._current_turn_id,a._web_run_deadline,Path('/proc/sys/kernel/random/boot_id').read_text().strip(),str(workspace),directory_identity(workspace),str(state),directory_identity(state),canonical({}),cap,call.turn)
   cached=object.__new__(ScopedLocalEnvironment);cached.binding=binding;cached.cwd=str(workspace)
   with wc.bind_web_call(call):
    key=cache_key('native-task');binding.check(caller=True)
   monkeypatch.setitem(_active_environments,key,cached)
   messages=[callrow()];assert a._flush_messages_to_session_db(messages)
   assert commit(a,messages,out.result) is not None
   te._finalize_tool_batch(a,messages,'native-task',1,DEFAULT_BUDGET)
   with wc.bind_web_call(call):
    with pytest.raises(TerminalScopeDenied):te.get_active_env('foreign-task')
   call.turn.stop()
   with wc.bind_web_call(call):
    with pytest.raises(RuntimeError):te.get_active_env('native-task')
 finally:db.close()

@pytest.mark.parametrize('kind',['stop','expiry','foreign'])
def test_stop_racing_native_environment_validation_commits_only_original_evidence(env,monkeypatch,kind):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);dispatch(a);call=a._tool_result_calls[('native-task','native-call')]
   native=te.get_active_env
   def during_lookup(task):
    if kind=='stop':call.turn.stop()
    elif kind=='expiry':call.base_deadline=time.monotonic()-1
    else:raise RuntimeError('foreign caller failure')
    return native(task)
   monkeypatch.setattr(te,'get_active_env',during_lookup)
   messages=[callrow()];assert a._flush_messages_to_session_db(messages)
   if kind=='foreign':
    with pytest.raises(RuntimeError,match='foreign caller'):commit(a,messages,'Unsettled evidence')
   else:
    assert commit(a,messages,'Unsettled evidence') is not None
    assert db.get_messages(a.session_id)[-1]['role']=='tool'
 finally:db.close()

def test_native_parallel_segment_preserves_each_original_call_and_order(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);a._should_emit_quiet_tool_messages=lambda:False
   a._append_guardrail_observation=lambda name,args,result,**kwargs:result
   from tools.tool_search import dispatch_tool_search
   def invoke(name,args,task,call,**kwargs):
    scope.guard_tool(name,args)
    assert wc.current_web_call().call_id==call
    return dispatch_tool_search(args,current_tool_defs=[])
   a._invoke_tool=invoke
   calls=[NS(id='native-call-'+str(i),function=NS(name='tool_search',arguments=json.dumps({'queries':[q]}))) for i,q in enumerate(['memory','calendar'])]
   messages=[{'role':'assistant','content':None,'tool_calls':[{'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}} for c in calls]}]
   assert a._flush_messages_to_session_db(messages)
   te.execute_tool_calls_segmented(a,NS(tool_calls=calls),messages,'native-task')
   rows=db.get_messages(a.session_id)
   assert [r['tool_call_id'] for r in rows if r['role']=='tool']==[c.id for c in calls]
   assert not a._tool_worker_threads
 finally:db.close()

def test_inline_interaction_retains_only_original_task_deadline(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db)
   def execute(args):
    call=wc.current_web_call()
    assert call.base_deadline==a._web_run_deadline
    assert call.run_deadline==a._web_run_deadline
    return 'Native inline interaction completed'
   managed=te._run_sequential_tool_execution_middleware(a,function_name='clarify',function_args={},effective_task_id='native-task',tool_call_id='native-call',execute=execute)
   assert managed.dispatched and not managed.blocked
 finally:db.close()
