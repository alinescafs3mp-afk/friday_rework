"""Offline manual-compression behavior on a composed native source checkout.

Run via run_manual_ordinary_compress.py with explicit --source/--repository/--workdir.
Authority, adapters, compression/model effects and publication stores are synthetic.
Native admission, command dispatch, context propagation, preview and cleanup run real
code. This suite does not prove persistence durability or installed/live acceptance.
"""
import asyncio,contextlib,contextvars,json,sys
from types import SimpleNamespace as NS,ModuleType
import ast
from pathlib import Path
from contextvars import copy_context
import pytest
from test_ordinary_first_contact_copy import source
from test_ordinary_tool_metadata_progress_privacy import scoped
from hermes_cli import friday_user_scope as scope
from hermes_cli.commands import resolve_command
from gateway import run_inbound,run_busy,run_turn,slash_commands_session as session
from gateway.platforms.event import MessageEvent
from agent.conversation_compression_manual import CompressRequest,CompressResult
# Execute exact unchanged native offload method, without importing the runtime gateway entrypoint.
_native_path=Path(run_turn.__file__).with_name('run.py')
_tree=ast.parse(_native_path.read_text())
_method=next(n for n in ast.walk(_tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_run_in_executor_with_context')
_ns={'asyncio':asyncio,'copy_context':copy_context}
exec(compile(ast.Module(body=[_method],type_ignores=[]),str(_native_path),'exec'),_ns)
native_offload=_ns['_run_in_executor_with_context']

@pytest.mark.parametrize('alias',['compact','compress'])
def test_actual_alias_resolution_and_idle_dispatch_retains_native_user_scope(scoped,source,monkeypatch,alias):
 seen=[]
 @contextlib.asynccontextmanager
 async def native(home):
  assert home==scoped.home
  yield
 mod=ModuleType('gateway.run');mod._async_profile_runtime_scope=native
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 class Runner(run_inbound.GatewayInboundMixin,run_busy.GatewayBusySessionMixin,run_turn.GatewayTurnMixin):
  def _resolve_profile_home_for_source(self,src):return scoped.home
  def _gateway_plain_command_handlers(self):return {}
  def _gateway_idle_command_handlers(self):return {'compress':self._handle_compress_command}
  async def _hm_command_hooks(self,*args):return False,None,None
  async def _handle_compress_command(self,event):
   seen.append((scope.current(required=True),event.source))
   await native_offload(NS(_get_executor=lambda:None),lambda:seen.append(scope.current(required=True)))
   return 'scoped-existing-handler'
 runner=Runner();runner.config=NS(multiplex_profiles=True)
 event=MessageEvent(text='/'+alias,source=source,message_id='fixture')
 async def go():
  handled,reply,command,canonical=await runner._hm_resolve_command(event,source,'synthetic-key')
  assert not handled and reply is None and canonical=='compress'
  return await runner._hm_dispatch_canonical_command(event,source,'synthetic-key',canonical)
 assert asyncio.run(go())==(True,'scoped-existing-handler')
 assert seen==[(scoped.cap,source),scoped.cap]

@pytest.mark.parametrize('bad',['revoked','missing','account','user','profile','transport','inferred'])
def test_manual_denies_foreign_missing_revoked_before_dispatch(scoped,source,bad):
 from dataclasses import replace
 if bad=='revoked':scoped.cap.revoked=True
 elif bad=='missing':del source._friday_user_scope
 elif bad=='user':source.user_id='foreign'
 elif bad=='profile':source.profile='foreign'
 elif bad=='account':scoped.cap.principal=('telegram','default','foreign-bot','1')
 elif bad=='transport':source._identity=replace(source._identity,transport_profile='foreign')
 elif bad=='inferred':source._identity=replace(source._identity,transport_inferred=True)
 assert scope.slash_allowed(source,'compress') is False
 assert 'недоступна' in run_busy.GatewayBusySessionMixin._check_slash_access(NS(),source,'compress')

@pytest.mark.parametrize('alias',['compact','compress'])
def test_busy_remains_rejected_without_handler_or_state_access(scoped,source,alias):
 class Runner(run_busy.GatewayBusySessionMixin):
  def _gateway_plain_command_handlers(self):raise AssertionError('must not dispatch')
 out=asyncio.run(Runner()._dispatch_busy_slash_command(MessageEvent(text='/'+alias,source=source),resolve_command(alias),'key',source))
 assert out=='Дождитесь завершения текущей задачи, затем повторите /compact.'

@pytest.mark.parametrize('aborted',[True,False])
def test_result_does_not_leak_backend_summary_focus_or_lock(scoped,aborted):
 private='http://private-host /home/private model-X lease-123 secret'
 out=session._manual_compression_reply_lines(dict(headline=private,token_line=private,note=private),NS(_last_compress_aborted=aborted,_last_summary_error=private,_last_aux_model_failure_model=private,_last_aux_model_failure_error=private),private)
 assert private not in '\n'.join(out)
 assert 'сохранены.' in out[0]

@pytest.mark.parametrize('mode',['error','preview','aggressive','short'])
def test_inner_expected_and_exception_replies_are_private(scoped,source,mode):
 hist=[{'role':'user','content':'x'}]* (2 if mode=='short' else 4)
 async def get(src):return NS(session_id='fixture')
 async def load(sid):return hist
 async def fail(*a):raise RuntimeError('http://private /home/private model-X lease-123')
 runner=NS(async_session_store=NS(get_or_create_session=get,load_transcript=load),_run_manual_compression=fail)
 arg={'preview':' --preview','aggressive':' --aggressive'}.get(mode,'')
 out=asyncio.run(session.GatewaySessionCommandsMixin._handle_compress_command_inner(runner,MessageEvent(text='/compact'+arg,source=source)))
 assert all(v not in out for v in ['http://','/home/','model-X','lease-123','/undo'])
 assert out

@pytest.mark.parametrize('mode',['lock','cancel','success','nothing','unavailable'])
def test_native_manual_work_cleanup_lock_privacy_and_context(scoped,source,monkeypatch,mode):
 import agent.conversation_compression_manual as core
 calls=[];agent=NS(session_id='parent',context_compressor=NS(_last_compress_aborted=False))
 mod=ModuleType('gateway.run');mod._platform_config_key=lambda p:p.value;mod._AGENT_PENDING_SENTINEL=object()
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 request=CompressRequest();history=[{'role':'user','content':'unchanged original'}]*4
 before=json.dumps(history)
 def compress(a,msgs,req,**kw):
  assert scope.current(required=True) is scoped.cap
  assert kw['skip_without_window'] is True and kw['task_id']=='parent'
  calls.append('compress')
  if mode=='cancel':raise asyncio.CancelledError()
  if mode=='lock':return CompressResult('lock_skipped',msgs,msgs,10,10,req,lock_holder='private-holder-path')
  if mode=='nothing':return CompressResult('nothing_to_do',msgs,msgs,10,10,req)
  if mode=='unavailable':return CompressResult('lock_skipped',msgs,msgs,10,10,req)
  return CompressResult('compressed',msgs,[{'role':'user','content':'fixture summary'}],10,5,req,summary=dict(headline='private model',token_line='private',note='private'))
 monkeypatch.setattr(core,'compress_now',compress)
 async def build(*a):return agent
 async def execute(fn):return await native_offload(NS(_get_executor=lambda:None),fn)
 async def persist(*a):calls.append('persist')
 async def clean(*a,**kw):calls.append('cleanup')
 runner=NS(_session_key_for_source=lambda s:'key',_resolve_session_agent_runtime=lambda **kw:('fixture-model',{'api_key':'fixture-only'}),_resolve_session_reasoning_config=lambda **kw:{},_build_manual_compression_agent=build,_run_in_executor_with_context=execute,_persist_manual_compression=persist,_evict_cached_agent=lambda key:calls.append('evict'),_cleanup_agent_resources_off_loop=clean)
 from manual_owned_fixture import own_runner
 own_runner(runner,source)
 if mode=='cancel':
  with pytest.raises(asyncio.CancelledError):asyncio.run(session.GatewaySessionCommandsMixin._run_manual_compression(runner,source,NS(session_id='parent'),history,request))
 else:
  out=asyncio.run(session.GatewaySessionCommandsMixin._run_manual_compression(runner,source,NS(session_id='parent'),history,request))
  assert 'private' not in out
 assert calls==['compress']+(['persist'] if mode=='success' else [])+['cleanup','evict']
 assert json.dumps(history)==before

@pytest.mark.parametrize('publish_ok',[True,False])
def test_native_manual_persist_child_before_repoint_and_preserve_old_on_failure(scoped,source,publish_ok):
 calls=[];entry=NS(session_id='parent',session_key='key');child=[{'content':'summary'}]
 async def publish(parent,new,msgs):
  calls.append('publish');assert entry.session_id=='parent';return publish_ok
 async def save():calls.append('repoint')
 async def update(*a,**kw):calls.append('tokens')
 store=NS(persist_rotated_compression_child=publish,_save=save,update_session=update)
 runner=NS(async_session_store=store,_sync_telegram_topic_binding=lambda *a,**kw:calls.append('binding'))
 go=lambda:session.GatewaySessionCommandsMixin._persist_manual_compression(runner,NS(session_id='child'),entry,source,child)
 if publish_ok:
  asyncio.run(go());assert entry.session_id=='child' and calls==['publish','repoint','binding','tokens']
 else:
  with pytest.raises(RuntimeError):asyncio.run(go())
  assert entry.session_id=='parent' and calls==['publish']

@pytest.mark.parametrize('status',['noop','aborted','refused_would_grow','fallback_used'])
def test_result_reports_real_non_success_outcomes_without_diagnostics(scoped,status):
 summary={status:True,'headline':'PRIVATE_DIAGNOSTIC','token_line':'PRIVATE_DIAGNOSTIC','note':'PRIVATE_DIAGNOSTIC'}
 out='\n'.join(session._manual_compression_reply_lines(summary,NS(_last_compress_aborted=False),'PRIVATE_FOCUS'))
 assert 'PRIVATE' not in out and 'Контекст разговора сжат.' not in out
 if status=='noop':assert 'не изменился' in out
 if status in {'aborted','refused_would_grow'}:assert 'не выполнено' in out
 if status=='fallback_used':assert 'ограниченная сводка' in out

def test_ordinary_preview_uses_existing_partial_boundary_without_focus_echo(scoped):
 history=[{'role':'user' if i%2==0 else 'assistant','content':str(i)} for i in range(12)]
 before=json.dumps(history)
 out=session._compress_preview_reply(history,True,2,'PRIVATE_FOCUS', '')
 assert 'сообщений: 4' in out and 'PRIVATE' not in out
 assert json.dumps(history)==before

@pytest.mark.parametrize('fault',['unreadable','unknown','cancel'])
def test_public_compress_wrapper_keeps_unknown_errors_private_and_cancellation(scoped,source,fault):
 async def inner(event):
  if fault=='cancel':raise asyncio.CancelledError()
  raise RuntimeError('PRIVATE_MODEL http://private /home/private')
 runner=NS(config=NS(multiplex_profiles=False),_handle_compress_command_inner=inner)
 event=MessageEvent(text='/compact',source=source)
 if fault=='cancel':
  with pytest.raises(asyncio.CancelledError):asyncio.run(session.GatewaySessionCommandsMixin._handle_compress_command(runner,event))
 else:
  out=asyncio.run(session.GatewaySessionCommandsMixin._handle_compress_command(runner,event))
  assert 'PRIVATE' not in out and 'http' not in out and '/home' not in out
  assert 'не подтверждено' in out

def test_unreadable_history_has_no_host_repair_instructions(scoped,source):
 from gateway.session_transcript import TranscriptReadError
 async def get(src):return NS(session_id='fixture')
 async def load(sid):raise TranscriptReadError('PRIVATE')
 runner=NS(async_session_store=NS(get_or_create_session=get,load_transcript=load))
 out=asyncio.run(session.GatewaySessionCommandsMixin._handle_compress_command_inner(runner,MessageEvent(text='/compact',source=source)))
 assert 'историю' in out and all(x not in out for x in ['PRIVATE','doctor','hermes','/new'])


@pytest.mark.parametrize('mode',['missing','pending','sessionless','success','incomplete','failure','cancel'])
def test_codex_manual_copy_is_private_preserves_count_and_cancellation(scoped,monkeypatch,mode):
 mod=ModuleType('gateway.run');mod._AGENT_PENDING_SENTINEL=object()
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 compressor=NS(compression_count=4);seen=[]
 def compress(messages,system,**kw):
  seen.append((messages,system,kw))
  if mode=='failure':raise RuntimeError('PRIVATE_PROVIDER /private/path')
  if mode=='cancel':raise asyncio.CancelledError()
  if mode=='success':compressor.compression_count+=1
 agent=NS(_codex_session=object(),context_compressor=compressor,_compress_context=compress)
 if mode=='missing':agent=None
 elif mode=='pending':agent=mod._AGENT_PENDING_SENTINEL
 elif mode=='sessionless':agent=NS()
 async def execute(fn):return fn()
 runner=NS(_cached_agent_for=lambda *a,**kw:agent,_run_in_executor_with_context=execute)
 go=lambda:session.GatewaySessionCommandsMixin._compress_codex_app_server_session(runner,'fixture-key','fixture-session')
 if mode=='cancel':
  with pytest.raises(asyncio.CancelledError):asyncio.run(go())
 else:
  out=asyncio.run(go())
  assert 'PRIVATE' not in out and '/private' not in out
  if mode=='success':assert out=='Разговор сжат.'
  elif mode=='incomplete':assert 'не завершено' in out
  elif mode=='failure':assert 'не подтверждено' in out
  else:assert out=='Пока нечего сжимать.'
 assert bool(seen)==(mode not in {'missing','pending','sessionless'})
 if seen:assert seen==[([], '', {'force':True,'task_id':'fixture-session'})]
 assert compressor.compression_count==(5 if mode=='success' else 4)


def test_no_provider_does_not_build_agent_or_start_compression(scoped,source,monkeypatch):
 mod=ModuleType('gateway.run');mod._platform_config_key=lambda p:p.value;mod._AGENT_PENDING_SENTINEL=object()
 monkeypatch.setitem(sys.modules,'gateway.run',mod)
 def forbidden(*a,**kw):raise AssertionError('missing provider must not start work')
 runner=NS(_session_key_for_source=lambda s:'fixture-key',_resolve_session_agent_runtime=lambda **kw:('fixture-model',{}),_build_manual_compression_agent=forbidden)
 from manual_owned_fixture import own_runner
 own_runner(runner,source)
 out=asyncio.run(session.GatewaySessionCommandsMixin._run_manual_compression(runner,source,NS(session_id='fixture'),[{'role':'user','content':'own'}]*4,CompressRequest()))
 assert out=='Сжатие сейчас недоступно. Попробуйте позже.'


def test_unmanaged_result_retains_native_summary_and_focus(scoped,monkeypatch):
 from hermes_constants import set_hermes_home_override,reset_hermes_home_override
 monkeypatch.setattr(scope,'_ENGAGED',False);monkeypatch.setattr(scope,'policy',lambda home:None)
 scope._CURRENT.set(None);token=set_hermes_home_override(str(scoped.root))
 try:
  assert not scope.ordinary_presentation()
  out='\n'.join(session._manual_compression_reply_lines({'headline':'native-headline','token_line':'native-token-count','note':'native-note'},NS(_last_compress_aborted=False),'native-focus'))
  assert all(v in out for v in ['native-headline','native-token-count','native-note','native-focus'])
 finally:reset_hermes_home_override(token)
