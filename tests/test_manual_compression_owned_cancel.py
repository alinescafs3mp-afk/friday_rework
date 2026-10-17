import asyncio,threading,sys
from types import SimpleNamespace as NS,ModuleType
import pytest
from test_ordinary_first_contact_copy import source
from test_ordinary_tool_metadata_progress_privacy import scoped
from test_manual_ordinary_compress import native_offload
from manual_owned_fixture import own_runner
from gateway import run_busy,slash_commands_session as session
from gateway.platforms.base import BasePlatformAdapter
from gateway.platforms.event import MessageEvent,MessageType
from hermes_cli.commands import resolve_command
from agent.conversation_compression import CompressionCommitFence
from agent.conversation_compression_manual import CompressRequest,CompressResult
from agent.interrupt_compat import request_hard_interrupt

@pytest.mark.parametrize('cause',['platform_cancel','native_stop','owner_shutdown','stale_successor','commit_won','global_cancel'])
def test_actual_live_worker_ownership_stop_and_publication(scoped,source,monkeypatch,cause):
 import agent.conversation_compression_manual as core
 calls=[];independent_stops=[];release=threading.Event();finished=threading.Event();fence=CompressionCommitFence()
 class Agent:
  session_id='parent'
  context_compressor=NS(_last_compress_aborted=False)
  _hard_interrupt_requested=threading.Event()
  _active_compression_commit_fence=fence
  def hard_interrupt(self,message=None,**kw):
   # Exact native fence primitive and explicit Event used by the real compressor.
   fence.cancel_before_commit(self._hard_interrupt_requested)
   calls.append('hard_interrupt')
 agent=Agent()
 mod=ModuleType('gateway.run');mod._platform_config_key=lambda p:p.value;mod._AGENT_PENDING_SENTINEL=object();mod._INTERRUPT_REASON_STOP='stop';mod._INTERRUPT_REASON_EVICTED='evicted';mod._INTERRUPT_TOOL_REASON_EVICTED='evicted';mod._reap_gateway_turn_processes=lambda *a,**kw:None;mod.request_hard_interrupt=request_hard_interrupt
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 delegation=ModuleType('tools.async_delegation')
 def stop_delegation(**kw):
  assert kw==dict(session_key='key',reason='test_stop',parent_session_id='parent')
  independent_stops.append('delegation')
 delegation.interrupt_for_session=stop_delegation
 monkeypatch.setitem(sys.modules,'tools.async_delegation',delegation)
 request=CompressRequest();history=[{'role':'user','content':'original'}]*4
 async def go():
  loop=asyncio.get_running_loop();started=asyncio.Event();persisting=asyncio.Event();publish_release=asyncio.Event()
  def compress(a,msgs,req,**kw):
   calls.append('worker')
   committed=False
   if cause=='commit_won':
    assert fence.begin_commit(a._hard_interrupt_requested);committed=True
   loop.call_soon_threadsafe(started.set)
   try:
    assert release.wait(3),'worker bounded wait'
    if not committed:committed=fence.begin_commit(a._hard_interrupt_requested)
    if committed:calls.append('durable_commit');fence.finish_commit()
    else:calls.append('commit_refused')
    return CompressResult('compressed',msgs,msgs,10,10,req,summary={'noop':True})
   finally:finished.set()
  monkeypatch.setattr(core,'compress_now',compress)
  async def build(*a):return agent
  async def execute(fn):return await native_offload(NS(_get_executor=lambda:None),fn)
  async def persist(*a):
   calls.append('persist');assert finished.is_set();persisting.set()
   if cause=='commit_won':await publish_release.wait()
  async def cleanup(*a,**kw):
   assert finished.is_set(),'resources closed while executor alive';calls.append('cleanup')
  async def settle(key):
   assert key=='key';independent_stops.append('custody')
   return {'status':'QUIESCENT','sessions':[],'newly_settled':0}
  runner=own_runner(NS(_session_key_for_source=lambda s:'key',_resolve_session_agent_runtime=lambda **kw:('fixture-model',{'api_key':'fixture-only'}),_resolve_session_reasoning_config=lambda **kw:{},_build_manual_compression_agent=build,_run_in_executor_with_context=execute,_persist_manual_compression=persist,_evict_cached_agent=lambda key:calls.append('evict'),_cleanup_agent_resources_off_loop=cleanup),source)
  runner._settle_session_web_custody=settle
  task=asyncio.create_task(session.GatewaySessionCommandsMixin._run_manual_compression(runner,source,NS(session_id='parent'),history,request))
  await asyncio.wait_for(started.wait(),1)
  work=agent._gateway_manual_compression_task
  from gateway.run_shutdown import GatewayShutdownMixin
  # Shutdown must not flush, finalize or close a manual worker still holding its input.
  await GatewayShutdownMixin._finalize_shutdown_agents(runner,{'key':agent})
  await GatewayShutdownMixin._cleanup_agent_resources_off_loop(runner,agent,context='shutdown finalize')
  assert len(runner._deferred_agent_workers)==1
  assert all(not isinstance(f,asyncio.Task) and not f.done() for f in runner._deferred_agent_workers)
  assert runner._is_session_running('key') and runner._state.turn.agent is agent
  # /status uses the same native turn.agent, and no replacement compression can start.
  denied=await session.GatewaySessionCommandsMixin._run_manual_compression(runner,source,NS(session_id='parent'),history,request)
  assert 'Дождитесь' in denied and calls==['worker']
  for mode in ('steer','interrupt'):
   runner._BusySteerOutcome=lambda **kw:NS(**kw)
   runner._agent_has_active_subagents=lambda a:False
   runner._demote_interrupt=lambda *a:'queue'
   event=MessageEvent(source=source,text='followup',message_type=MessageType.TEXT)
   route=await run_busy.GatewayBusySessionMixin._resolve_busy_steer_or_redirect(runner,event,'key',mode,agent)
   assert route.effective_mode=='queue' and not route.steered and not route.redirected
  denied=await run_busy.GatewayBusySessionMixin._dispatch_busy_slash_command(runner,MessageEvent(source=source,text='/compact'),resolve_command('compact'),'key',source)
  assert 'Дождитесь' in denied
  try:
   if cause=='stale_successor':
    successor=object();runner._state.turn.agent=successor;runner._begin_session_run_generation('key')
   elif cause=='global_cancel':
    for pending in asyncio.all_tasks():
     if pending is not asyncio.current_task():pending.cancel()
    await asyncio.sleep(0);await asyncio.sleep(0)
    assert all(not f.done() for f in runner._deferred_agent_workers)
   elif cause=='owner_shutdown':
    work.cancel();await asyncio.sleep(0)
   elif cause in {'native_stop','commit_won'}:
    if cause=='commit_won':
     timer=threading.Timer(.05,release.set);timer.start()
    receipt=await runner._interrupt_and_clear_session('key',source,interrupt_reason='stop',invalidation_reason='test_stop')
    assert receipt['status']=='STOP_UNCONFIRMED'
    assert independent_stops==['delegation','custody']
    assert runner._is_session_running('key')
    # Native release/evict cannot clear this unfinished owner, even after invalidation.
    runner._drop_turn_slot('key',run_generation=runner._current_session_run_generation('key'))
    assert runner._state.turn.agent is agent and 'cleanup' not in calls and 'evict' not in calls
    from gateway.run_inbound import GatewayInboundMixin
    GatewayInboundMixin._hm_evict_running_agent(runner,'key','stale_reaped_fixture')
    assert runner._state.turn.agent is agent and 'evict' not in calls
   if cause in {'platform_cancel','native_stop','commit_won'}:
    adapter=NS(name='fixture',_session_tasks={'key':task},_expected_cancelled_tasks=set(),_requeue_counts={},_pending_messages={},_discard_text_debounce=lambda key:None,_release_session_guard=lambda key:None)
    await BasePlatformAdapter.cancel_session_processing(adapter,'key')
    assert task.cancelled() and agent._hard_interrupt_requested.is_set()
   if cause!='stale_successor':assert runner._state.turn.agent is agent and 'cleanup' not in calls
  finally:
   release.set();publish_release.set()
  if cause in {'owner_shutdown','global_cancel','stale_successor'}:
   with pytest.raises(asyncio.CancelledError if cause in {'owner_shutdown','global_cancel'} else RuntimeError):await task
  else:await work
  if cause=='global_cancel':
   with pytest.raises(asyncio.CancelledError):await work
  assert finished.is_set() and 'cleanup' in calls
  if cause=='stale_successor':
   assert runner._state.turn.agent is successor and 'evict' not in calls and 'persist' not in calls
  else:
   assert runner._state.turn.agent is None
   assert calls.index('cleanup')<calls.index('evict')
  if cause in {'platform_cancel','native_stop','owner_shutdown','global_cancel'}:
   assert 'commit_refused' in calls and 'durable_commit' not in calls
  if cause=='commit_won':
   assert 'durable_commit' in calls and 'persist' in calls and calls.index('persist')<calls.index('cleanup')
 asyncio.run(go())


def test_native_stop_guard_retains_and_drains_followup_once_even_after_second_stop():
 from types import MethodType
 async def go():
  gate=asyncio.Event();replies=[];drained=[]
  manual=asyncio.create_task(gate.wait())
  owner=NS(_gateway_manual_compression_task=manual)
  state=NS(turn=NS(agent=owner))
  async def noop(*a,**kw):pass
  async def inline(*a,**kw):replies.append('stop')
  adapter=NS(name='fixture',gateway_runner=NS(_peek_session_state=lambda key:state),_active_sessions={'key':asyncio.Event()},_session_tasks={},_expected_cancelled_tasks=set(),_requeue_counts={},_pending_messages={},_dispatch_inline_reply=inline,_flush_text_debounce_now=noop,_discard_text_debounce=lambda key:None,_start_session_processing=lambda event,key:drained.append(event))
  def release(key,guard=None):
   if guard is None or adapter._active_sessions.get(key) is guard:adapter._active_sessions.pop(key,None)
  adapter._release_session_guard=release
  adapter.cancel_session_processing=MethodType(BasePlatformAdapter.cancel_session_processing,adapter)
  adapter._drain_pending_after_session_command=MethodType(BasePlatformAdapter._drain_pending_after_session_command,adapter)
  stop1=asyncio.create_task(BasePlatformAdapter._dispatch_active_session_command(adapter,NS(),'key','stop'))
  await asyncio.sleep(0);await asyncio.sleep(0)
  event=object();adapter._pending_messages['key']=event
  stop2=asyncio.create_task(BasePlatformAdapter._dispatch_active_session_command(adapter,NS(),'key','stop'))
  await asyncio.sleep(0);await asyncio.sleep(0)
  assert replies==['stop','stop'] and not drained and not stop1.done() and not stop2.done()
  gate.set();await asyncio.gather(stop1,stop2)
  assert drained==[event] and not adapter._pending_messages and 'key' not in adapter._active_sessions
 asyncio.run(go())
