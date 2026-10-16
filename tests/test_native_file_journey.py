import json,time,hashlib
from pathlib import Path
import pytest
from file_native_fixture import env,entered,home,own_db,scope
from test_tool_result_context import actor
from agent import tool_executor as te,web_call_context as wc
from tools import file_tools as ft
from tools.budget_config import DEFAULT_BUDGET

O=Path(__file__).resolve().parents[1]
OBS=[]
TEXT='1. Keep the first point.\n2. Original second point.\n3. Keep the third point.\n'
REVISED='1. Keep the first point.\n2. Revised second point.\n3. Keep the third point.\n'

def call(a,name,args,ident,messages=None):
 r=te._ToolCallRef(name,args,'native-file-task',ident,[])
 if messages is not None:
  messages.append({'role':'assistant','content':None,'tool_calls':[{'id':ident,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]})
  assert a._flush_messages_to_session_db(messages)
 def execute(arguments):
  scope.guard_tool(name,arguments)
  ctx=wc.current_web_call();assert ctx.call_id==ident and ctx.task_id=='native-file-task'
  if name=='write_file':return ft.write_file_tool(task_id='native-file-task',**arguments)
  return ft.read_file_tool(task_id='native-file-task',**arguments)
 out=te._run_sequential_tool_execution_middleware(a,**r.middleware_kwargs(),execute=execute)
 assert out.dispatched and not out.blocked
 if messages is not None:
  assert te._commit_tool_result(a,messages,r,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None) is not None
  te._finalize_tool_batch(a,messages,'native-file-task',1,DEFAULT_BUDGET)
 return r,out

def test_actual_native_file_durable_journey_and_followup_revision_gap(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);m=[]
   _,w=call(a,'write_file',{'path':'notes.txt','content':TEXT},'file-create',m)
   result=json.loads(w.result);assert result['success'] and result['create_only']
   path=home(env)/'workspace/notes.txt';assert path.read_text()==TEXT
   first=next(r for r in db.get_messages(a.session_id) if r.get('tool_call_id')=='file-create')
   _,read=call(a,'read_file',{'path':'notes.txt'},'file-read',m)
   assert '2: 2. Original second point.' in json.loads(read.result)['content']
   m.append({'role':'assistant','content':'Created notes.txt with three points.'})
   m.append({'role':'user','content':'Change the second point in the previous file; preserve the first and third.'})
   assert a._flush_messages_to_session_db(m)
   a._current_turn_id='native-file-followup-turn';a._web_run_deadline=time.monotonic()+60
   _,revision=call(a,'write_file',{'path':'notes.txt','content':REVISED},'file-followup-revision',m)
   denied=json.loads(revision.result)
   assert denied=={'success':False,'error':'product_user_scope_refused'}
   assert path.read_text()==TEXT
   _,after=call(a,'read_file',{'path':'notes.txt'},'file-read-after-revision',m)
   assert 'Original second point.' in json.loads(after.result)['content']
   rows=db.get_messages(a.session_id)
   retained=next(r for r in rows if r.get('tool_call_id')=='file-create')
   assert retained==first
   from hermes_state import SessionDB
   reopened=SessionDB(home(env)/'state.db')
   try:assert reopened.get_messages(a.session_id)==rows
   finally:reopened.close()
   assert json.loads(retained['content'])['path']=='notes.txt'
   assert [r['tool_call_id'] for r in rows if r['role']=='tool']==['file-create','file-read','file-followup-revision','file-read-after-revision']
   assert scope.current().profile not in json.dumps(rows)
   (env.root.parent/'journey-observations.json').write_text(json.dumps({'create':result,'read':json.loads(read.result),'revision':denied,'after':json.loads(after.result),'retained_first_result_exact':retained==first,'tool_call_ids':[r['tool_call_id'] for r in rows if r['role']=='tool'],'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'second_point_revised':False,'db_message_count':len(rows),'new_followup_turn':True,'reopened_native_database_exact':True},indent=2)+'\n')
 finally:db.close()

@pytest.mark.parametrize('bad',['foreign-path','traversal','private-path'])
def test_path_controls_have_no_file_effect(env,bad):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db)
   path={'foreign-path':str(home(env,'2')/'workspace/forbidden.txt'),'traversal':'../forbidden.txt','private-path':str(home(env)/'config.yaml')}[bad]
   _,denied=call(a,'write_file',{'path':path,'content':'FORBIDDEN'},'file-path-negative')
   assert json.loads(denied.result)=={'success':False,'error':'product_user_scope_refused'}
   _,read=call(a,'read_file',{'path':path},'file-read-negative')
   assert json.loads(read.result)=={'success':False,'error':'product_user_scope_refused'}
   assert not (home(env,'2')/'workspace/forbidden.txt').exists()
   assert not (home(env)/'forbidden.txt').exists()
 finally:db.close()

@pytest.mark.parametrize('kind',['foreign-user','revoked'])
def test_actual_result_authority_cannot_be_reassigned(env,kind):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);r,out=call(a,'write_file',{'path':'safe.txt','content':'OWN'},'file-authority')
   if kind=='revoked':
    scope.current().revoked=True
    with pytest.raises(scope.ScopeDenied):te._commit_tool_result(a,[],r,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None)
  if kind=='foreign-user':
   with entered(env,'2'):
    with pytest.raises(scope.ScopeDenied):te._commit_tool_result(a,[],r,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None)
 finally:db.close()

def test_completed_file_effect_then_stop_retains_original_unknown_evidence(env):
 db=own_db(env)
 try:
  with entered(env):
   a=actor(db);m=[]
   r,out=call(a,'write_file',{'path':'stopped.txt','content':'OWN'},'file-stop')
   original=a._tool_result_calls[('native-file-task','file-stop')]
   original.turn.stop();a._interrupt_requested=True
   m.append({'role':'assistant','content':None,'tool_calls':[{'id':'file-stop','type':'function','function':{'name':'write_file','arguments':json.dumps(r.args)}}]})
   assert a._flush_messages_to_session_db(m)
   assert te._commit_tool_result(a,m,r,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition='unknown') is not None
   row=db.get_messages(a.session_id)[-1]
   assert row['role']=='tool' and row['effect_disposition']=='unknown'
   assert a._friday_reply_effect_unknown
   assert (home(env)/'workspace/stopped.txt').read_text()=='OWN'
 finally:db.close()
