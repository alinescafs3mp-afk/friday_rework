"""Real native inline consumers, own synthetic policy/SQLite/memory, no live effects."""
import json,sys
from types import SimpleNamespace as NS,ModuleType
import pytest
from test_ordinary_tool_metadata_progress_privacy import scoped,put
from hermes_cli import friday_user_scope as s
from tools import memory_tool
from agent import inline_tool_executors as it,tool_executor as te,agent_runtime_helpers as ar
from gateway import run_turn
from gateway.config import Platform

@pytest.mark.parametrize('consumer',['inline','sequential','invoke','concurrent'])
@pytest.mark.parametrize('tool',['memory','session_search'])
def test_actual_inline_metadata_consumers(scoped,monkeypatch,consumer,tool):
 import model_tools
 observed=[];transformed=[];notified=[]
 monkeypatch.setattr(model_tools,'_emit_post_tool_call_hook',lambda **kw:observed.append(kw))
 monkeypatch.setattr(model_tools,'_apply_transform_tool_result_hook',lambda *args:(transformed.append(args),args[2])[1])
 store=memory_tool.MemoryStore(memory_char_limit=32);store.load_from_disk()
 p=scoped.home/'memories/MEMORY.md';put(p,'LONG_UNDELIMITED_USER_TEXT_'*5);raw=p.read_bytes()
 from hermes_state import SessionDB
 db=SessionDB(db_path=scoped.home/'state.db');(scoped.home/'state.db').chmod(0o600)
 origin=json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1','platform':'telegram','transport_profile':'default','account_id':'bot-A'}})
 db.create_session('native-followup','private-source',model='private-model',user_id='1',profile_name='user-1',origin_json=origin)
 mid=db.append_message('native-followup','user','Public OpenAI /user/path verbatim')
 manager=NS(notify_memory_tool_write=lambda result,*a,**k:notified.append(json.loads(result)))
 agent=NS(_friday_user_scope=scoped.cap,_memory_store=store,_memory_manager=manager,session_id='current',_get_session_db_for_recall=lambda:db,_build_memory_write_metadata=lambda **kw:kw)
 args={'action':'replace','old_text':raw.decode(),'content':'consolidated'} if tool=='memory' else {'session_id':'native-followup','around_message_id':mid}
 def call(args):
  if consumer=='concurrent':
   agent._invoke_tool=lambda *a,**kw: ar.invoke_tool(agent,*a,**kw)
   def middleware(agent,**kw):
    result=kw['execute'](args)
    return NS(result=result,args=args,middleware_trace=[],blocked=False,dispatched=True)
   monkeypatch.setattr(te,'_run_agent_tool_execution_middleware',middleware)
   batch=te._ConcurrentBatch(agent,[],'task',[],5)
   ref=te._ToolCallRef(tool,args,'task','call',[])
   return batch._dispatch_worker(0,ref,None,te._WorkerStartOnce(batch.gate,0,tool)).result
  if consumer=='invoke':return ar.invoke_tool(agent,tool,args,'task','call',pre_tool_block_checked=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
  if consumer=='inline':return it.INLINE_TOOL_EXECUTORS[tool](agent,args,it.InlineToolContext('task','call'))
  ref=NS(name=tool,args=args,task_id='task',call_id='call',trace=[])
  result=te._resolve_sequential_dispatch(agent,ref,[]).execute(args)
  return it.apply_transform_tool_result(agent,function_name=tool,function_args=args,result=result,effective_task_id='task',tool_call_id='call')
 try:
  out=json.loads(call(args))
  if tool=='memory':
   assert not out['success'] and 'конфликт' in out['error']
   assert 'drift_backup' not in out and 'remediation' not in out and str(scoped.home) not in json.dumps(out)
   assert notified and 'drift_backup' in notified[0] # native provider sees original diagnostic
   assert p.read_bytes()==raw and list(p.parent.glob('MEMORY.md.bak.*'))
  else:
   assert out['success'] and out['session_id']=='native-followup' and out['around_message_id']==mid
   assert not {'source','model'}&out['session_meta'].keys()
   assert out['messages'][0]['content']=='Public OpenAI /user/path verbatim'
   browse=json.loads(call({}));assert browse['success'] and not {'source','model'}&browse['results'][0].keys()
  if consumer!='inline':assert transformed and isinstance(transformed[0][2],str)
  if consumer in {'invoke','concurrent'}:assert len(observed)==(1 if tool=='memory' else 2)
  scoped.cap.revoked=True
  if consumer!='inline':assert json.loads(call(args)).get('error')=='product_user_scope_refused'
 finally:db.close()

def test_post_transform_projection_and_native_failure_contract(scoped,monkeypatch):
 import model_tools
 raw={'success':True,'session_meta':{'source':'private','model':'private'},'session_id':'keep','messages':[{'content':'source /user/path remains'}]}
 monkeypatch.setattr(model_tools,'_apply_transform_tool_result_hook',lambda *a:json.dumps(raw))
 kwargs=dict(function_name='session_search',function_args={},result='original',effective_task_id='task',tool_call_id='call')
 out=json.loads(it.apply_transform_tool_result(NS(),**kwargs));assert out['session_meta']=={} and out['session_id']=='keep' and out['messages']==raw['messages']
 monkeypatch.setattr(model_tools,'_apply_transform_tool_result_hook',lambda *a:'custom hook free text /user/path')
 assert it.apply_transform_tool_result(NS(),**kwargs)=='custom hook free text /user/path'
 def fail(*a):raise RuntimeError('native hook fails open')
 monkeypatch.setattr(model_tools,'_apply_transform_tool_result_hook',fail)
 kwargs['result']=json.dumps(raw);assert json.loads(it.apply_transform_tool_result(NS(),**kwargs))['session_meta']=={}
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None)
 assert it.apply_transform_tool_result(NS(),**kwargs)==kwargs['result']

@pytest.mark.parametrize('mode',['log','off','verbose'])
@pytest.mark.parametrize('managed',[True,False])
def test_slack_task_cards_all_modes_preserve_native(scoped,monkeypatch,mode,managed):
 native=ModuleType('gateway.run');native._gateway_platform_value=lambda p:p.value;native._has_platform_display_override=lambda *a:True
 native._platform_config_key=lambda p:p.value;native._load_gateway_config=lambda:{'display':{'tool_progress':mode,'live_status':'full','long_running_notifications':True}}
 monkeypatch.setitem(sys.modules,'gateway.run',native)
 if not managed:
  monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None)
 calls=[];runner=NS(_resolve_turn_toolsets=lambda *a:([],[]),_delivery_adapter_for=lambda source:NS(supports_status_text=True,native_task_cards_enabled=lambda:(calls.append(1),True)[1]),_RunAgentDisplay=lambda **kw:NS(**kw))
 from agent.secret_scope import set_secret_scope,reset_secret_scope
 token=set_secret_scope({},profile_home=str(scoped.home))
 try:out=run_turn.GatewayTurnMixin._run_agent_display_settings(runner,NS(platform=Platform.SLACK))
 finally:reset_secret_scope(token)
 if managed:
  assert not out._native_slack_task_cards and not calls and not out.tool_progress_enabled
  assert out.log_mode_enabled is (mode=='log')
  assert out._display_surface_mode('long_running_notifications',default=True,allow_generic=True)=='generic'
  assert out._generic_status_phrase('status') # friendly bounded native status remains available
 else:assert out._native_slack_task_cards is (mode!='off')

def test_managed_long_running_heartbeat_generic_bounded_and_stops(scoped,monkeypatch):
 import asyncio
 native=ModuleType('gateway.run');native._float_env=lambda *a:1
 native._interim_metadata=lambda x:x;native._non_conversational_metadata=lambda x,**kw:x
 monkeypatch.setitem(sys.modules,'gateway.run',native)
 ticks=[];sent=[];edited=[];decisions=iter([True,True,True,False])
 async def instant_tick(interval):ticks.append(interval)
 async def send(chat,text,**kw):sent.append((chat,text,kw));return NS(success=True,message_id='native-message')
 async def edit(chat,mid,text):edited.append((chat,mid,text));return NS(success=True,message_id=mid)
 monkeypatch.setattr(run_turn.asyncio,'sleep',instant_tick)
 def no_raw(*a):raise AssertionError('generic heartbeat accessed raw tool diagnostics')
 runner=NS(_delivery_adapter_for=lambda source:NS(send=send,edit_message=edit),_should_emit_long_running_notification=lambda *a:next(decisions),_agent_activity_summary=no_raw)
 disp=NS(_display_surface_mode=lambda *a,**kw:'generic',resolve_display_setting=lambda *a:True,user_config={},platform_key='telegram',_generic_status_phrase=lambda kind:'Продолжаю задачу. Остановить: /stop. Проверить: /status.')
 ctx=NS(source=NS(platform=Platform.TELEGRAM,chat_id='own-chat'),session_key='own-session',agent_holder=[object()],_status_thread_metadata=None,_cleanup_progress=True,_cleanup_msg_ids=[])
 asyncio.run(run_turn.GatewayTurnMixin._run_agent_notify_long_running(runner,disp,ctx,[object()]))
 assert ticks==[1,1,1] and len(sent)==1 and len(edited)==1 and sent[0][1].startswith('Продолжаю задачу.')
 assert edited[0][1]=='native-message' and edited[0][2]==sent[0][1]
 assert ctx._cleanup_msg_ids==['native-message']

@pytest.mark.parametrize('consumer',['sequential','invoke'])
def test_missing_managed_scope_cannot_fall_back_to_donor(scoped,consumer):
 s._CURRENT.set(None)
 agent=NS(_friday_user_scope=scoped.cap)
 if consumer=='invoke':out=ar.invoke_tool(agent,'memory',{'action':'add','content':'denied'},'task')
 else:out=te._resolve_sequential_dispatch(agent,NS(name='memory',args={'action':'add'},task_id='task',call_id='call',trace=[]),[]).execute({})
 assert json.loads(out)['error']=='product_user_scope_refused'
 assert not (scoped.home/'memories/MEMORY.md').exists()

def test_unmanaged_inline_memory_keeps_native_diagnostic(scoped,monkeypatch):
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None)
 store=memory_tool.MemoryStore(memory_char_limit=32);store.load_from_disk()
 p=scoped.home/'memories/MEMORY.md';put(p,'NATIVE_UNDELIMITED_CONTENT_'*5);raw=p.read_bytes()
 out=json.loads(it.INLINE_TOOL_EXECUTORS['memory'](NS(_memory_store=store,_memory_manager=None),{'action':'replace','old_text':raw.decode(),'content':'new'},it.InlineToolContext('task')))
 assert 'drift_backup' in out and str(scoped.home) in out['drift_backup'] and p.read_bytes()==raw
