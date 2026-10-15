"""Actual native SDK/tools with own synthetic homes and DB; no live effects.
Policy/access rows are finite synthetic authority inputs; native capability checks,
file descriptors, skill readers, memory store, SQLite/search and registry run real code.
"""
import contextvars,json,os,stat,time
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
import sys
import pytest
from hermes_cli import friday_user_scope as s,friday_product_access as a
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from tools.registry import registry
from tools import skills_tool,memory_tool,session_search_tool
from gateway import run_turn,run_busy
from gateway.platforms import base
from gateway.config import Platform
from gateway.stream_events import ToolCallChunk

def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.write_text(v);p.chmod(0o600)

@pytest.fixture
def scoped(tmp_path,monkeypatch):
 home=tmp_path/'user-1';home.mkdir(mode=0o700)
 for d in ['workspace','memories','skills']:(home/d).mkdir(mode=0o700)
 binding=dict(platform='telegram',transport_profile='default',account_id='bot-A',user_id='1',runtime_profile='user-1',tools=['read_file','write_file','skill_view','skills_list','memory','session_search'])
 key=s.principal_id('telegram','default','bot-A','1')
 put(home/s.MARKER,json.dumps(dict(schema='friday.user-home.v1',principal=key,profile='user-1',binding_sha256=s._fingerprint(binding))))
 put(home/'config.yaml',json.dumps({'memory':{'memory_enabled':True,'user_profile_enabled':True}}))
 monkeypatch.setattr(s,'policy',lambda root: {'enabled':True,'bindings':[binding]})
 monkeypatch.setattr(a,'current_access',lambda: {'users':{key:{'enabled':True,'generation':1}}})
 monkeypatch.setattr(a,'access_policy',lambda: {'accounts':[dict(platform='telegram',transport_profile='default',account_id='bot-A',runtime_profiles=['user-1'])]})
 monkeypatch.setattr(s,'_ENGAGED',True)
 st=home.stat();cap=s.UserScope(tmp_path,home,'user-1',('telegram','default','bot-A','1'),binding,(st.st_dev,st.st_ino),admission_generation=1)
 token=set_hermes_home_override(str(home));ct=s._CURRENT.set(cap)
 try:assert cap.check() is cap;yield NS(home=home,cap=cap,root=tmp_path)
 finally:s._CURRENT.reset(ct);reset_hermes_home_override(token)

def dispatch(name,args,**kw):return json.loads(registry.dispatch(name,args,**kw))

def test_real_own_files_relative_bounded_followup_and_untouched_content(scoped):
 h=scoped.home
 # User code/research may legitimately discuss a vendor or a physical path.
 text='Public OpenAI research /user/provided/path\nsecond line'
 result=json.loads(s.scoped_file('write_file',{'path':'report.txt','content':text}))
 assert result['path']=='report.txt'
 first=json.loads(s.scoped_file('read_file',{'path':str(h/'workspace/report.txt'),'limit':1}))
 assert first['path']=='report.txt' and first['content']=='1: '+text.splitlines()[0]
 again=json.loads(s.scoped_file('read_file',{'path':first['path'],'offset':2}))
 assert again['content']=='2: second line'
 assert (h/'workspace/report.txt').read_text()==text
 for raw in ['../foreign.txt',str(scoped.root/'foreign.txt')]:
  with pytest.raises(s.ScopeDenied):s.scoped_file('read_file',{'path':raw})


def test_real_skill_resources_dispatch_and_private_dedup_fields(scoped):
 p=scoped.home/'skills/procedure';p.mkdir(mode=0o700)
 put(p/'SKILL.md','---\nname: procedure\ndescription: Own research\n---\nPublic provider documentation remains verbatim.')
 put(p/'references/guide.md','OpenAI /user/source/path remains verbatim')
 first=dispatch('skill_view',{'name':'procedure'},task_id='own-task')
 assert first['success'],first
 assert 'Public provider documentation' in first['content']
 assert not {'skill_dir','_source_path','_skill_identity'}&first.keys()
 linked=dispatch('skill_view',{'name':'procedure','file_path':'references/guide.md'},task_id='own-task')
 assert linked['content']=='OpenAI /user/source/path remains verbatim'
 assert '_source_path' not in linked
 # Own native scoped reads intentionally re-read bytes; no stale dedup acknowledgement.
 put(p/'references/guide.md','Changed own facts')
 assert dispatch('skill_view',{'name':'procedure','file_path':'references/guide.md'},task_id='own-task')['content']=='Changed own facts'
 assert not dispatch('skill_view',{'name':'../outside'},task_id='own-task')['success']


def test_real_memory_drift_preserves_bytes_and_private_diagnostic(scoped,caplog):
 store=memory_tool.MemoryStore(memory_char_limit=32);store.load_from_disk()
 p=scoped.home/'memories/MEMORY.md';put(p,'LONG_UNDELIMITED_USER_TEXT_'*5)
 raw=p.read_bytes();out=dispatch('memory',{'action':'replace','old_text':raw.decode(),'content':'consolidated'},store=store)
 assert not out['success'] and 'конфликт' in out['error'],out
 assert 'drift_backup' not in out and str(scoped.home) not in json.dumps(out)
 assert p.read_bytes()==raw and list(p.parent.glob('MEMORY.md.bak.*'))
 assert str(scoped.home) in caplog.text


def test_real_session_db_read_discovery_scroll_and_isolation(scoped):
 from hermes_state import SessionDB
 db=SessionDB(db_path=scoped.home/'state.db');(scoped.home/'state.db').chmod(0o600)
 origin=json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1','platform':'telegram','transport_profile':'default','account_id':'bot-A'}})
 try:
  sid='synthetic-native-followup-id'
  db.create_session(sid,'internal-source',model='internal-provider-model',user_id='1',profile_name='user-1',origin_json=origin)
  mid=db.append_message(sid,'user','Public software research /user/path remains')
  db.append_message(sid,'assistant','Own earlier answer')
  own=dispatch('session_search',{'session_id':sid},db=db)
  assert own['success'] and own['session_id']==sid and own['link']=='@session:'+sid,own
  assert not {'source','model'}&own['session_meta'].keys()
  assert own['messages'][0]['content']=='Public software research /user/path remains'
  scroll=dispatch('session_search',{'session_id':sid,'around_message_id':mid},db=db)
  assert scroll['success'] and scroll['around_message_id']==mid
  browse=dispatch('session_search',{},db=db)
  assert browse['success'] and not {'source','model'}&browse['results'][0].keys()
  discover=dispatch('session_search',{'query':'research'},db=db)
  assert discover['success'] and discover['results'],discover
  assert not {'source','model'}&discover['results'][0].keys()
  assert not dispatch('session_search',{'session_id':sid,'profile':'user-2'},db=db)['success']
  foreign=NS(db_path=scoped.root/'user-2/state.db')
  assert not dispatch('session_search',{'session_id':sid},db=foreign)['success']
 finally:db.close()

@pytest.mark.parametrize('bad',['revoked','missing','claim'])
def test_no_revoked_missing_or_claimed_authority(scoped,bad):
 if bad=='revoked':scoped.cap.revoked=True
 else:s._CURRENT.set(None)
 args={'name':'procedure'}
 if bad=='claim':args['owner']='developer'
 out=dispatch('skill_view',args)
 assert not out.get('success') and 'недоступно' in out['error']
 assert s.ordinary_presentation()


def test_typed_projection_does_not_rewrite_nested_user_artifact(scoped):
 payload={'success':True,'source':'private','model':'private','results':[{'session_id':'needed-native-id','source':'private','model':'private','messages':[{'content':'model provider /user/path','tool_calls':[{'source':'user-code','model':'user-model'}]}]}]}
 out=json.loads(s.ordinary_tool_metadata('session_search',json.dumps(payload)))
 assert out['results'][0]['session_id']=='needed-native-id'
 assert out['results'][0]['messages']==payload['results'][0]['messages']
 assert s.ordinary_tool_metadata('research',json.dumps(payload))==json.dumps(payload)


def test_footer_progress_and_busy_do_not_fetch_raw_diagnostics(scoped,monkeypatch):
 assert run_turn.GatewayTurnMixin._hmwa_runtime_footer_line(NS(),{'model':'private'},NS(),1)==''
 e=ToolCallChunk(tool_name='internal-tool',args={'path':'/host/private'},preview='/host/private')
 assert base.BasePlatformAdapter.format_tool_event(NS(),e,mode='verbose')=='Выполняю задачу.'
 # Busy acknowledgements still use native queue/steer semantics; detailed tracker must not be called.
 constants=ModuleType('gateway.run');constants._AGENT_PENDING_SENTINEL=object();constants._hermes_home=lambda:scoped.home;constants._load_gateway_config=lambda:{};constants._platform_config_key=lambda p:'telegram'
 monkeypatch.setitem(sys.modules,'gateway.run',constants)
 class Agent:
  def get_activity_summary(self):raise AssertionError('raw diagnostics accessed')
 runner=NS(_agent_has_active_subagents=lambda a:False,_BUSY_DEMOTED_TAIL='queued',_BUSY_STEER_TAIL='steered')
 result=run_busy.GatewayBusySessionMixin._compose_busy_ack_message(runner,NS(source=NS(platform=Platform.TELEGRAM)),time.monotonic(),None,Agent(),is_steer_mode=False,is_queue_mode=True,is_redirect_mode=False,demoted_for_subagents=False,demoted_for_compression=False)
 assert '/host/' not in result


def test_unmanaged_native_diagnostics_preserved(monkeypatch):
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None)
 x=json.dumps({'success':True,'skill_dir':'/private/operator/path','_source_path':'native'})
 assert s.ordinary_tool_metadata('skill_view',x)==x
 assert session_search_tool._session_link('id','native-profile')=='@session:native-profile/id'

@pytest.mark.parametrize('form',['sentinel','explained'])
def test_empty_response_advisory_cannot_bypass_managed_copy(scoped,monkeypatch,form):
 import ast,asyncio,logging
 from agent import turn_finalizer,turn_failure_copy
 from agent.turn_explainers import EMPTY_RESPONSE_EXPLANATION
 # Run exact unchanged native normalizer/classifier functions; only unrelated final
 # transport sanitizer is a passthrough seam, as this case carries no provider envelope.
 native=ModuleType('gateway.run');native.is_context_overflow_failure_result=run_turn.is_context_overflow_failure_result
 native.logger=logging.getLogger('empty-native-test');native.t=run_turn.t
 source=Path(run_turn.__file__).with_name('run.py').read_text();tree=ast.parse(source)
 wanted={'_normalize_empty_agent_response','_is_gateway_hidden_reasoning_incomplete_turn','_should_clear_resume_pending_after_turn'}
 code=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[])
 exec(compile(code,'exact-native-gateway-functions','exec'),native.__dict__)
 native._sanitize_gateway_final_response=lambda platform,text:text
 monkeypatch.setitem(sys.modules,'gateway.run',native)
 private='SYNTHETIC_PRIVATE_PROVIDER_MODEL'
 final='(empty)' if form=='sentinel' else EMPTY_RESPONSE_EXPLANATION.format(model=private)
 result=dict(final_response=final,model=private,failed=False,completed=False,api_calls=2,messages=[],turn_exit_reason='empty_response_exhausted',failure_reason='empty_response')
 runner=NS(_is_intentional_silence=lambda *a:False)
 text,silence,messages=asyncio.run(run_turn.GatewayTurnMixin._hmwa_shape_agent_response(runner,result,NS(platform=Platform.TELEGRAM,chat_id='synthetic'),[],NS(session_id='s'),None,'key',1,'s','telegram',time.time()))
 assert text==s.empty_response_copy() and '/model' not in text and private not in text
 assert result['failed'] is False and turn_failure_copy.exit_reason_failure('empty_response_exhausted').fails_turn is False
 agent=NS(model=private,_turn_completion_explainer_enabled=lambda:True,_format_turn_completion_explanation=lambda *a,**kw:EMPTY_RESPONSE_EXPLANATION.format(model=private))
 assert turn_finalizer._explain_abnormal_exit(agent,final,'empty_response_exhausted',False,native.logger)==s.empty_response_copy()


def test_managed_verbose_progress_and_slack_card_flags_are_disabled(scoped,monkeypatch):
 native=ModuleType('gateway.run');native._gateway_platform_value=lambda p:p.value;native._has_platform_display_override=lambda *a:True
 native._platform_config_key=lambda p:p.value;native._load_gateway_config=lambda:{'display':{'tool_progress':'verbose','live_status':'full'}}
 monkeypatch.setitem(sys.modules,'gateway.run',native)
 runner=NS(_resolve_turn_toolsets=lambda *a:([],[]),_delivery_adapter_for=lambda source:NS(supports_status_text=True,native_task_cards_enabled=lambda:True),_RunAgentDisplay=lambda **kw:NS(**kw))
 from agent.secret_scope import set_secret_scope,reset_secret_scope
 secret_token=set_secret_scope({},profile_home=str(scoped.home))
 try:out=run_turn.GatewayTurnMixin._run_agent_display_settings(runner,NS(platform=Platform.SLACK))
 finally:reset_secret_scope(secret_token)
 assert out.progress_mode=='off' and not out.tool_progress_enabled and not out._native_slack_task_cards
 assert out._live_status_mode=='off' and out._live_status_adapter is None


def test_timeout_keeps_interruption_and_partial_outcome_without_raw_activity(scoped,monkeypatch,caplog):
 native=ModuleType('gateway.run');native._INTERRUPT_REASON_TIMEOUT='timeout';native._INTERRUPT_TOOL_REASON_TIMEOUT='timeout-tool';calls=[]
 native.request_hard_interrupt=lambda *a,**kw:calls.append((a,kw));monkeypatch.setitem(sys.modules,'gateway.run',native)
 agent=object();ctx=NS(session_key='private-session',result_holder=[{'messages':[]}],tools_holder=[[]],agent_holder=[agent],source=NS())
 runner=NS(_agent_activity_summary=lambda a:{'last_activity_desc':'/host/private provider','current_tool':'private-internal-tool','api_call_count':3,'max_iterations':8,'seconds_since_activity':60})
 out=run_turn.GatewayTurnMixin._run_agent_timeout_result(runner,NS(agent_timeout=60),ctx)
 assert out['failed'] is True and calls and 'Часть действий могла выполниться' in out['final_response']
 assert '/host/private' not in out['final_response'] and 'private-internal-tool' not in out['final_response']
 assert '/host/private' in caplog.text


def test_real_bounded_file_pagination_keeps_relative_native_followup(scoped,monkeypatch):
 from agent import bounded_context
 monkeypatch.setattr(bounded_context,'configured_policy',lambda:NS(tail_tokens=512))
 put(scoped.home/'workspace/long.txt','x'*1000)
 first=json.loads(s.scoped_file('read_file',{'path':'long.txt'}))
 assert first['partial'] and first['path']=='long.txt' and 0<first['next_char_offset']<1000
 second=json.loads(s.scoped_file('read_file',{'path':first['path'],'offset':first['next_offset'],'char_offset':first['next_char_offset']}))
 assert second['path']=='long.txt' and second['content'].startswith('1: x')
 assert second['next_char_offset']>first['next_char_offset']
