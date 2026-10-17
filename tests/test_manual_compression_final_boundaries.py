"""Portable r3 independent-stop controls and native committed-child recovery.

Synthetic cancellation targets and bounded workers; temporary SQLite only.
Run with run_manual_ordinary_compress.py against the explicit composed source.
"""
import asyncio,ast,threading,sys,json
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType,MethodType
import pytest
from test_ordinary_first_contact_copy import source
from test_ordinary_tool_metadata_progress_privacy import scoped
from manual_owned_fixture import own_runner
from gateway import slash_commands_session as session,run_agent_cache
from gateway.run_shutdown import GatewayShutdownMixin
from gateway.session_transcript import SessionTranscriptMixin
from gateway.session_state import SessionFieldView,LEGACY_FIELD_SPECS
from agent.conversation_compression import CompressionCommitFence
from agent.conversation_compression_manual import CompressRequest,CompressResult
from agent.interrupt_compat import request_hard_interrupt
from hermes_state import SessionDB



@pytest.mark.parametrize('reason',['owner_stop','owner_new'])
@pytest.mark.parametrize('custody_status',['QUIESCENT','STOP_UNCONFIRMED'])
def test_exact_stop_delivers_independent_targets_while_manual_active(monkeypatch,reason,custody_status):
 calls=[]
 class Agent:
  session_id='parent'
  def hard_interrupt(self,*a,**kw):calls.append('manual')
 async def go():
  task=asyncio.create_task(asyncio.Event().wait())
  try:
   agent=Agent();agent._gateway_manual_compression_task=task
   runner=own_runner(NS(),None);runner._state.turn.agent=agent
   cache={'key':(agent,'signature',4)};runner._agent_cache=cache
   runner.session_store=NS(_entries={'key':NS(session_id='fallback-parent')})
   mod=ModuleType('gateway.run');mod._AGENT_PENDING_SENTINEL=object();mod.request_hard_interrupt=request_hard_interrupt;mod._reap_gateway_turn_processes=lambda *a,**kw:None
   monkeypatch.setitem(sys.modules,'gateway.run',mod)
   delegation=ModuleType('tools.async_delegation')
   def stop_delegation(**kw):
    assert kw==dict(session_key='key',reason=reason,parent_session_id='parent')
    calls.append('delegation');return 1
   delegation.interrupt_for_session=stop_delegation
   monkeypatch.setitem(sys.modules,'tools.async_delegation',delegation)
   resources=[{'session_id':'web-fixture','newly_settled':True},{'session_id':'terminal-fixture','newly_settled':True}]
   async def settle(key):
    assert key=='key';calls.append('custody')
    return {'status':custody_status,'sessions':resources,'newly_settled':2}
   runner._settle_session_web_custody=settle
   receipt=await runner._interrupt_and_clear_session('key',None,interrupt_reason='stop',invalidation_reason=reason)
   assert calls==['manual','delegation','custody']
   assert receipt=={'status':'STOP_UNCONFIRMED','sessions':resources,'newly_settled':2}
   assert runner._state.turn.agent is agent and cache['key'][0] is agent and not task.done()
   runner._drop_turn_slot('key',run_generation=runner._current_session_run_generation('key'))
   assert runner._state.turn.agent is agent and cache['key'][0] is agent
  finally:
   task.cancel();await asyncio.gather(task,return_exceptions=True)
 asyncio.run(go())


@pytest.mark.parametrize('boundary',['owner_cancel_after_begin_commit','native_shutdown_release'])
def test_committed_child_boundary_and_native_recovery(scoped,source,monkeypatch,tmp_path,boundary):
 import agent.conversation_compression_manual as core
 db=SessionDB(tmp_path/'fixture.db');db.create_session('parent',source='test')
 for i in range(4):db.append_message('parent',role='user' if i%2==0 else 'assistant',content=f'original {i}')
 fence=CompressionCommitFence();release=threading.Event();finished=threading.Event();calls=[];observations={'boundary':boundary}
 class Agent:
  session_id='parent'
  context_compressor=NS(_last_compress_aborted=False)
  _hard_interrupt_requested=threading.Event()
  _active_compression_commit_fence=fence
  def hard_interrupt(self,*a,**kw):
   fence.cancel_before_commit(self._hard_interrupt_requested);calls.append('hard_interrupt')
 agent=Agent();entry=NS(session_id='parent',session_key='key')
 history=db.get_messages_as_conversation('parent');summary=[{'role':'user','content':'summary'},{'role':'assistant','content':'continue'}]
 store=NS(_db_for_session_id=lambda sid:db)
 for name in ['is_published_compression_child','persist_rotated_compression_child','_compression_tip_for_session_id','_heal_compression_tip_locked','load_transcript']:
  setattr(store,name,MethodType(getattr(SessionTranscriptMixin,name),store))
 store._follow_reroutes=lambda sid:sid
 async def pub(*args):calls.append('persist');return store.persist_rotated_compression_child(*args)
 async def save():calls.append('save')
 async def update(*a,**kw):calls.append('update')
 async def cleanup(*a,**kw):assert finished.is_set();calls.append('cleanup')
 async def noop(*a,**kw):pass
 runner=own_runner(NS(_cleanup_agent_resources_off_loop=cleanup,_evict_cached_agent=lambda key:calls.append('evict'),async_session_store=NS(persist_rotated_compression_child=pub,_save=save,update_session=update),_sync_telegram_topic_binding=lambda *a,**kw:calls.append('binding')),source)
 runner._persist_manual_compression=MethodType(session.GatewaySessionCommandsMixin._persist_manual_compression,runner)
 mod=ModuleType('gateway.run');mod._AGENT_PENDING_SENTINEL=object();mod.GatewayRunner=NS(_stop_kill_tool_subprocesses_off_loop=noop)
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 monkeypatch.setattr(GatewayShutdownMixin,'_quiet_step',staticmethod(lambda *a:None))
 async def go():
  loop=asyncio.get_running_loop();started=asyncio.Event()
  def compress(a,msgs,req,**kw):
   assert db.try_acquire_compression_lock('parent','fixture-holder')
   assert fence.begin_commit(a._hard_interrupt_requested)
   loop.call_soon_threadsafe(started.set)
   try:
    assert release.wait(3)
    db.publish_compression_child(parent_session_id='parent',child_session_id='child',source='test',messages=summary,compression_lock_holder='fixture-holder',require_compression_lease=True,watermark=db.get_active_message_watermark('parent'))
    a.session_id='child';calls.append('durable_commit')
    return CompressResult('compressed',history,summary,20,10,req,summary={'noop':False})
   finally:
    fence.finish_commit();finished.set()
  monkeypatch.setattr(core,'compress_now',compress)
  runner._state.turn.agent=agent
  owner=asyncio.create_task(runner._complete_manual_compression(agent,source,entry,'key',history,CompressRequest()))
  agent._gateway_manual_compression_task=owner
  await asyncio.wait_for(started.wait(),1)
  if boundary=='owner_cancel_after_begin_commit':
   timer=threading.Timer(.05,release.set);timer.start();owner.cancel()
   with pytest.raises(asyncio.CancelledError):await owner
   timer.join(1)
  else:
   runner._sessions={'key':runner._state}
   for name in ['_running_agents','_running_agents_ts','_pending_messages','_pending_approvals','_active_session_leases']:
    setattr(runner,name,SessionFieldView(runner,LEGACY_FIELD_SPECS[name]))
   runner._background_tasks=set();runner._stop_task=None;runner._restart_task=None;runner._active_api_run_count=lambda:0;runner.adapters={};runner._shutdown_event=asyncio.Event()
   await GatewayShutdownMixin._stop_release_runtime_state(runner,NS(elapsed=lambda:0))
   observations['owner_slot_present_before_worker_terminal']=runner._state.turn.agent is agent
   observations['worker_finished_at_release']=finished.is_set()
   release.set()
   with pytest.raises(RuntimeError,match='ownership changed'):await owner
  observations['entry_before_recovery']=entry.session_id
  observations['native_tip']=store._compression_tip_for_session_id('parent')
  observations['native_recovered_transcript']=[m['content'] for m in store.load_transcript('parent')]
  observations['route_healed']=store._heal_compression_tip_locked(entry,'parent',observations['native_tip'])
  observations['entry_after_recovery']=entry.session_id
  observations['calls']=calls
  assert entry.session_id=='child' and observations['route_healed']
  assert observations['native_recovered_transcript']==['summary','continue']
  assert 'persist' not in calls and 'cleanup' in calls
 try:asyncio.run(go())
 finally:release.set();db.close()
 (tmp_path/(boundary+'-observation.json')).write_text(json.dumps(observations,indent=2)+'\n')
