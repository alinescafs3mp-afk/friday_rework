import json,time,threading,copy,importlib.util,sys,hashlib
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from file_native_fixture import env,entered,home,native_agent,scope
from agent import tool_executor as te,web_call_context as wc,turn_api_call as api
from tools import file_tools as ft,file_tools_read_tracking as tracking
from tools.budget_config import DEFAULT_BUDGET
from agent.tool_guardrails import ToolCallGuardrailController
O=Path(__file__).resolve().parents[1]
import importlib
mod=importlib.import_module('run_agent')
TASK='delivery-task'
OBS={}

def actor():
 a=native_agent();a._current_turn_id='delivery-turn';a._web_run_deadline=time.monotonic()+60
 a._interrupt_requested=False;a._tool_worker_threads=set();a._tool_worker_threads_lock=threading.Lock()
 a._context_engine_tool_names=set();a._checkpoint_mgr=NS(enabled=False);a._tool_guardrails=ToolCallGuardrailController()
 a.quiet_mode=True;a.verbose_logging=False;a.tool_progress_callback=None;a.tool_start_callback=None;a.tool_complete_callback=None;a.tool_result_metadata_callback=None
 a._touch_activity=lambda *args:None;a._subdirectory_hints=NS(check_tool_call=lambda *args:None)
 a._flush_messages_to_session_db=lambda *args,**kw:True
 a._tool_result_content_for_active_model=lambda name,result:result
 a._apply_pending_steer_to_tool_results=lambda *args:None
 a.model='custom:friday-local';a.provider='custom';a.context_compressor.context_length=40960
 a._disable_streaming=True;a.base_url='http://192.168.1.78:8001/v1';a.api_mode='chat_completions';a.thinking_callback=None
 a._has_pending_redirect=lambda:False
 return a

def dispatch(a,name,args,ident):
 ref=te._ToolCallRef(name,args,TASK,ident,[])
 def execute(arguments):
  scope.guard_tool(name,arguments)
  assert wc.current_web_call().call_id==ident
  if name=='write_file': return ft.write_file_tool(task_id=TASK,**arguments)
  return ft.read_file_tool(task_id=TASK,**arguments)
 out=te._run_sequential_tool_execution_middleware(a,**ref.middleware_kwargs(),execute=execute)
 assert out.dispatched and not out.blocked
 return ref,out

def value(out):return json.loads(out.result)
def create(a,path,text):
 _,out=dispatch(a,'write_file',dict(path=path,content=text),'create-'+path);assert value(out)['success']
def read(a,path,ident='read',**kw):return dispatch(a,'read_file',dict(path=path,**kw),ident)
def write(a,path,text='REVISED'):
 _,out=dispatch(a,'write_file',dict(path=path,content=text),'write-'+path);return value(out)
def commit(a,m,r,out,budget=DEFAULT_BUDGET):
 assert te._commit_tool_result(a,m,r,out.result,budget=budget,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None) is not None

def transport(a,m,monkeypatch,*,shape='chat',fail=False,stream=False,mutate=None):
 rows=copy.deepcopy(m)
 if shape=='responses':payload={'input':[{'type':'function_call_output','call_id':r['tool_call_id'],'output':r['content']} for r in rows]}
 elif shape=='anthropic':payload={'messages':[{'role':'user','content':[{'type':'tool_result','tool_use_id':r['tool_call_id'],'content':r['content']} for r in rows]}]}
 else:payload={'messages':rows}
 if mutate:mutate(payload)
 from agent import relay_llm
 def actual(request,*args,**kwargs):
  if fail:raise RuntimeError('synthetic-transport-failed')
  if fail is None:return None
  return NS(choices=[])
 monkeypatch.setattr(relay_llm,'execute',lambda request,callback,**kw:callback(request))
 a._interruptible_api_call=actual
 a._interruptible_streaming_api_call=lambda request,**kw:actual(request)
 a._disable_streaming=not stream;a._has_stream_consumers=lambda:True
 a._is_copilot_url=lambda:False;a._is_codex_backend=lambda:False
 a._get_transport=lambda:NS(preflight_kwargs=lambda p,**kw:p)
 return api.perform_api_call(a,api_kwargs=payload,_original_api_kwargs=payload,_llm_middleware_trace=[],_moa_prepared_request=None,_retry=NS(),thinking_spinner=None,retry_count=0,api_call_count=1,api_request_id='fixture',effective_task_id=TASK,turn_id=a._current_turn_id,interrupted=False)

def finalized(a,path,ident='read',budget=DEFAULT_BUDGET,**kw):
 r,out=read(a,path,ident,**kw);m=[];commit(a,m,r,out,budget);te._finalize_tool_batch(a,m,TASK,1,budget);return m

@pytest.mark.parametrize('stage',['raw','committed','finalized'])
def test_same_batch_cannot_write_before_model_delivery(env,monkeypatch,stage):
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');r,out=read(a,'x.txt');m=[]
  if stage!='raw':commit(a,m,r,out)
  if stage=='finalized':te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET)
  result=write(a,'x.txt');assert result['error']=='file_revision_requires_current_full_read'
  assert (home(env)/'workspace/x.txt').read_text()=='ORIGINAL'

@pytest.mark.parametrize('shape',['chat','responses','anthropic'])
@pytest.mark.parametrize('stream',[False,True])
def test_exact_final_transport_delivery_enables_revision(env,monkeypatch,shape,stream):
 with entered(env):
  a=actor();create(a,'x.txt','one\ntwo\nthree\n');m=finalized(a,'x.txt');assert getattr(a._tool_result_calls[(TASK,'read')], '_workspace_read_ready',False), vars(a._tool_result_calls[(TASK,'read')]);transport(a,m,monkeypatch,shape=shape,stream=stream)
  result=write(a,'x.txt','one\nTWO\nthree\n');assert result['success']
  assert (home(env)/'workspace'/('.friday-before-'+result['revision_ref'])/'before').read_text()=='one\ntwo\nthree\n'

@pytest.mark.parametrize('kind',['omit','trim','stub','duplicate','foreign-id','failed','none','unfinalized','extra-body'])
def test_missing_or_uncertain_final_delivery_grants_nothing(env,monkeypatch,kind):
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');r,out=read(a,'x.txt');m=[];commit(a,m,r,out)
  if kind!='unfinalized':te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET)
  def mutate(p):
   if kind=='omit':p['messages']=[]
   elif kind=='trim':p['messages'][0]['content']=p['messages'][0]['content'][:20]
   elif kind=='stub':p['messages'][0]['content']='See persisted tool result'
   elif kind=='duplicate':p['messages']*=2
   elif kind=='foreign-id':p['messages'][0]['tool_call_id']='other'
   elif kind=='extra-body':p['extra_body']={'messages':[]}
  if kind=='failed':
   with pytest.raises(RuntimeError,match='synthetic-transport-failed'):transport(a,m,monkeypatch,fail=True)
  elif kind=='none':transport(a,m,monkeypatch,fail=None)
  else:transport(a,m,monkeypatch,mutate=mutate)
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_aggregate_native_spill_denies_hidden_middle_but_visible_read_works(env,monkeypatch):
 with entered(env):
  a=actor();m=[];text='A'*40000+'UNSEEN_MIDDLE_SENTINEL'+'B'*49000
  for i in range(3):
   path=f'bulk{i}.txt';create(a,path,text);r,out=read(a,path,'bulk-read-'+str(i));commit(a,m,r,out)
  total=sum(len(r['content']) for r in m);te._finalize_tool_batch(a,m,TASK,3,DEFAULT_BUDGET)
  hidden=[i for i,r in enumerate(m) if 'UNSEEN_MIDDLE_SENTINEL' not in r['content']];assert hidden
  transport(a,m,monkeypatch)
  for i in hidden:assert write(a,f'bulk{i}.txt')['error']=='file_revision_requires_current_full_read'
  visible=[i for i in range(3) if i not in hidden];assert visible
  assert write(a,f'bulk{visible[0]}.txt')['success']
  OBS['aggregate']={'raw_characters':total,'turn_budget':DEFAULT_BUDGET.turn_budget,'hidden':hidden,'visible':visible}


def test_dropped_page_then_genuine_continuation_joins_only_delivered_pages(env,monkeypatch):
 with entered(env):
  a=actor();create(a,'page.txt','one\ntwo\nthree\n')
  m=finalized(a,'page.txt','page1',offset=1,limit=1);transport(a,m,monkeypatch)
  m=finalized(a,'page.txt','page2-drop',offset=2,limit=2);transport(a,[],monkeypatch)
  assert write(a,'page.txt')['error']=='file_revision_requires_current_full_read'
  m=finalized(a,'page.txt','page2-real',offset=2,limit=2);transport(a,m,monkeypatch)
  assert write(a,'page.txt')['success']

@pytest.mark.parametrize('kind',['stop','expire','session','turn','deadline','missing'])
def test_original_read_authority_revalidated_even_when_other_last_call_valid(env,monkeypatch,kind):
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt');original=a._tool_result_calls[(TASK,'read')]
  if kind=='stop':original.stopped.set()
  elif kind=='expire':original.base_deadline=time.monotonic()-1
  elif kind=='session':original.session_id='FOREIGN'
  elif kind=='turn':original.turn_id='FOREIGN'
  elif kind=='deadline':original.run_deadline+=1
  elif kind=='missing':del a._tool_result_calls[(TASK,'read')]
  try:transport(a,m,monkeypatch)
  except (RuntimeError,scope.ScopeDenied,TimeoutError):pass
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_direct_scope_read_never_mints_native_delivery(env):
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');assert json.loads(ft.read_file_tool('x.txt',task_id=TASK))['success']
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_real_source74_parent_sequential_read_write_same_batch(env,monkeypatch):
 with entered(env):
  a=mod.AIAgent.__new__(mod.AIAgent);a.__dict__.update(actor().__dict__);a._base_url='offline://fixture';a._should_emit_quiet_tool_messages=lambda:False
  a._append_guardrail_observation=lambda n,args,result,**kw:result
  a._record_file_mutation_result=lambda *args,**kw:None
  a._flush_messages_to_session_db=lambda *args,**kw:True
  def invoke(name,args,task,call,**kw):
   scope.guard_tool(name,args)
   return (ft.read_file_tool(task_id=task,**args) if name=='read_file' else ft.write_file_tool(task_id=task,**args))
  a._invoke_tool=invoke
  import model_tools
  monkeypatch.setattr(model_tools,'handle_function_call',lambda name,args,*rest,**kw:invoke(name,args,kw.get('task_id',rest[0] if rest else TASK),kw.get('tool_call_id','')))
  create(a,'x.txt','ORIGINAL')
  calls=[NS(id='parent-read',function=NS(name='read_file',arguments=json.dumps({'path':'x.txt'}))),NS(id='parent-write',function=NS(name='write_file',arguments=json.dumps({'path':'x.txt','content':'BLIND'})))]
  m=[{'role':'assistant','content':None,'tool_calls':[{'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}} for c in calls]}]
  a._execute_tool_calls(NS(tool_calls=calls),m,TASK)
  rows=[r for r in m if r.get('role')=='tool'];assert len(rows)==2
  assert json.loads(rows[1]['content'])['error']=='file_revision_requires_current_full_read'
  assert (home(env)/'workspace/x.txt').read_text()=='ORIGINAL'
  transport(a,rows,monkeypatch);assert write(a,'x.txt')['success']




@pytest.mark.parametrize('kind',['bytes','inode','task'])
def test_delivery_does_not_weaken_version_or_task_fence(env,monkeypatch,kind):
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt');transport(a,m,monkeypatch)
  p=home(env)/'workspace/x.txt'
  if kind=='bytes':p.write_text('OTHER')
  if kind=='inode':p.unlink();p.write_text('ORIGINAL');p.chmod(0o600)
  task=TASK if kind!='task' else 'foreign-task'
  r=te._ToolCallRef('write_file',{'path':'x.txt','content':'BLIND'},task,'negative',[])
  out=te._run_sequential_tool_execution_middleware(a,**r.middleware_kwargs(),execute=lambda args:ft.write_file_tool(task_id=task,**args))
  assert not json.loads(out.result)['success']


def test_native_per_tool_spill_and_failed_flush_never_grant(env,monkeypatch):
 from dataclasses import replace
 with entered(env):
  a=actor();create(a,'x.txt','A'*9000);budget=replace(DEFAULT_BUDGET,default_result_size=1500)
  from tools.tool_result_storage import maybe_persist_tool_result
  r,out=read(a,'x.txt');m=[];commit(a,m,r,out)
  m[0]['content']=maybe_persist_tool_result(m[0]['content'],'read_file','read',env=None,config=budget,threshold=1500)
  te._finalize_tool_batch(a,m,TASK,1,budget);assert len(m[0]['content'])<9000
  transport(a,m,monkeypatch);assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'
  r,out=read(a,'x.txt','failed-flush');a._flush_messages_to_session_db=lambda *args,**kw:False;m=[]
  assert te._commit_tool_result(a,m,r,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None) is None
  te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET);transport(a,m,monkeypatch)
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_native_multibyte_pages_remain_usable(env,monkeypatch):
 from agent import bounded_context as bc
 with entered(env):
  a=actor();text='é漢字🙂'*500+'\nlast line\n';create(a,'utf.txt',text)
  policy=bc.BoundedContextPolicy('custom:fixture','fixture','http://127.0.0.1:1/v1',16000,16000,1000,1000,100,100)
  token=bc._SUMMARY_POLICY.set(policy)
  try:
   offset=1;char=0;pages=0
   while True:
    r,out=read(a,'utf.txt','utf-'+str(pages),offset=offset,char_offset=char);page=value(out);m=[];commit(a,m,r,out);te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET);transport(a,m,monkeypatch)
    pages+=1;assert pages<100
    if not page['partial']:break
    assert write(a,'utf.txt')['error']=='file_revision_requires_current_full_read'
    offset=page['next_offset'];char=page['next_char_offset']
   assert write(a,'utf.txt',text.replace('last','LAST'))['success'];OBS['multibyte_pages']=pages
  finally:bc._SUMMARY_POLICY.reset(token)


def test_managed_stream_rewrite_uncertainty_fails_closed(env,monkeypatch):
 from agent import relay_runtime
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt')
  monkeypatch.setattr(relay_runtime,'resolve_execution_context',lambda *args:(NS(managed_execution_enabled=lambda:True),object(),None))
  transport(a,m,monkeypatch,stream=True)
  monkeypatch.setattr(relay_runtime,'resolve_execution_context',lambda *args:(None,None,None))
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'

@pytest.mark.parametrize('stream',[False,True])
def test_unqualified_codex_route_never_grants_new_coverage(env,monkeypatch,stream):
 with entered(env):
  a=actor();a.api_mode='codex_responses';create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt')
  transport(a,m,monkeypatch,stream=stream,shape='responses')
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_native_request_execution_middleware_rewrite_is_observed(env,monkeypatch):
 from hermes_cli import middleware
 from agent import relay_llm
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt')
  # Run native execution middleware's terminal callback with rewritten request;
  # no provider/model is invoked by this fixture.
  monkeypatch.setattr(middleware,'run_llm_execution_middleware',lambda payload,next_call,**kw:next_call({'messages':[]}))
  transport(a,m,monkeypatch)
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'


def test_f1_f2_write_body_preserved_exactly():
 from hermes_cli import friday_workspace_revision as revision
 current=Path(revision.__file__).read_text()
 # Exact sealed F1/F2 write/durability body; read-delivery code precedes it.
 assert hashlib.sha256(current[current.index('def _baseline'):].encode()).hexdigest()=='3445d6450fe11f01673398dcf84804d1cd479548fdbeeb6d8398d9158e9132b7'


def test_actual_native_context_selection_can_hide_read_without_grant(env,monkeypatch):
 import logging
 from agent import conversation_loop as loop
 with entered(env):
  a=actor();create(a,'x.txt','ORIGINAL');m=finalized(a,'x.txt')
  class Engine:
   context_length=40960
   def select_context(self,*args,**kwargs):return [{'role':'user','content':'current request without omitted read'}]
  a.context_compressor=Engine()
  selected=loop._apply_context_engine_selection(a,copy.deepcopy(m),m,None,logger=logging.getLogger('native-fixture'))
  assert selected!=m
  transport(a,selected,monkeypatch)
  assert write(a,'x.txt')['error']=='file_revision_requires_current_full_read'
