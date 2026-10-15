"""Real native memory preference/approval under own synthetic signed scopes; offline."""
import asyncio,json,hashlib,sys
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
import pytest
from test_ordinary_tool_metadata_progress_privacy import scoped,put
from test_ordinary_first_contact_copy import source
from hermes_cli import friday_user_scope as s,friday_product_access as access
from gateway import slash_commands
from tools import memory_tool,write_approval as wa
from hermes_cli import write_approval_commands as commands

@pytest.fixture
def signed(scoped,source,monkeypatch):
 put(scoped.home/'SOUL.md','Own synthetic soul');put(scoped.home/'.env','SYNTHETIC_MEMORY_TEST=not-a-secret\n')
 receipt={'schema':'friday.onboarding.v1','binding_sha256':s._fingerprint(scoped.cap.binding),'config_sha256':hashlib.sha256((scoped.home/'config.yaml').read_bytes()).hexdigest(),'soul_sha256':hashlib.sha256((scoped.home/'SOUL.md').read_bytes()).hexdigest(),'required_secrets':['SYNTHETIC_MEMORY_TEST'],'directory_identity':list(scoped.cap.directory_identity),'template':'synthetic','authorization_home':str(scoped.root)}
 put(scoped.home/s.ONBOARDING,json.dumps(receipt));m=json.loads((scoped.home/s.MARKER).read_text());m['onboarding_sha256']=hashlib.sha256((scoped.home/s.ONBOARDING).read_bytes()).hexdigest();put(scoped.home/s.MARKER,json.dumps(m))
 route={'name':'friday-'+scoped.cap.key,'platform':'telegram','bot_profile':'default','user_id':'1','profile':'user-1','enabled':True}
 put(scoped.root/'config.yaml',json.dumps({'gateway':{'multiplex_profiles':True,'profile_routes':[route]}}))
 native=ModuleType('gateway.run');native._gateway_config_home=lambda:scoped.home;monkeypatch.setitem(sys.modules,'gateway.run',native)
 runner=NS(_session_key_for_source=lambda source:'own',_evict_cached_agent=lambda key:None)
 runner._write_approval_setter=lambda section,event:slash_commands.GatewaySlashCommandsMixin._write_approval_setter(runner,section,event)
 def call(args):return asyncio.run(slash_commands.GatewaySlashCommandsMixin._handle_memory_command(runner,NS(source=source,get_command_args=lambda:args)))
 assert s.slash_allowed(source,'memory') and scoped.cap.check() is scoped.cap
 return NS(**vars(scoped),source=source,call=call,config=(scoped.home/'config.yaml').read_bytes())

@pytest.mark.parametrize('sub',['approval','mode'])
@pytest.mark.parametrize('enabled',[True,False])
def test_real_command_set_read_gate_approve_keeps_signed_config(signed,monkeypatch,sub,enabled):
 x=signed;out=x.call(sub+(' on' if enabled else ' off'));assert ('включено' if enabled else 'выключено') in out
 assert wa.write_approval_enabled(wa.MEMORY) is enabled
 assert ('включено' if enabled else 'выключено') in x.call('approval')
 assert (x.home/'config.yaml').read_bytes()==x.config and x.cap.check() is x.cap
 monkeypatch.setattr(wa,'_prompt_inline_memory_approval',lambda *a:None)
 store=memory_tool.load_on_disk_store()
 result=json.loads(memory_tool.memory_tool(action='add',content='Public OpenAI /user/path fact',store=store))
 assert result['success']
 if enabled:
  assert result['staged'] and not (x.home/'memories/MEMORY.md').exists()
  pid=result['pending_id'];assert wa.get_pending(wa.MEMORY,pid)
  approved=x.call('approve '+pid);assert 'Approved 1 memory write(s).' in approved and wa.get_pending(wa.MEMORY,pid) is None
 assert 'Public OpenAI /user/path fact' in (x.home/'memories/MEMORY.md').read_text()
 assert (x.home/'memories/MEMORY.md').stat().st_mode & 0o777 == 0o600
 assert (x.home/'config.yaml').read_bytes()==x.config and x.cap.check() is x.cap


def test_existing_signed_default_and_closed_registry_reopen_persistence(signed):
 from hermes_state_registry import acquire,_generations
 x=signed;assert wa.write_approval_enabled(wa.MEMORY) is False
 x.call('approval on');assert not _generations
 assert wa.write_approval_enabled(wa.MEMORY) is True and not _generations
 db=acquire(x.home/'state.db')
 try:assert db.get_meta('memory.write_approval')=='1'
 finally:db.close()
 # Export finite synthetic authority inputs for a separate fresh interpreter control.
 D=Path(__file__).resolve().parents[2]
 (D/'RESTART-INPUT.json').write_text(json.dumps({'home':str(x.home),'root':str(x.root),'binding':x.cap.binding,'principal':list(x.cap.principal),'directory_identity':list(x.cap.directory_identity),'config_sha256':hashlib.sha256(x.config).hexdigest()}))


def test_own_user_isolation_and_no_foreign_scope(signed,monkeypatch):
 from hermes_constants import set_hermes_home_override,reset_hermes_home_override
 x=signed;x.call('approval on')
 home=x.root/'user-2';home.mkdir(mode=0o700)
 for name in ['memories','workspace','skills']:(home/name).mkdir(mode=0o700)
 b=dict(x.cap.binding,user_id='2',runtime_profile='user-2');key=s.principal_id('telegram','default','bot-A','2')
 put(home/s.MARKER,json.dumps({'schema':'friday.user-home.v1','principal':key,'profile':'user-2','binding_sha256':s._fingerprint(b)}));put(home/'config.yaml','{}')
 monkeypatch.setattr(s,'policy',lambda root:{'enabled':True,'bindings':[x.cap.binding,b]});monkeypatch.setattr(access,'current_access',lambda:{'users':{x.cap.key:{'enabled':True,'generation':1},key:{'enabled':True,'generation':1}}});monkeypatch.setattr(access,'access_policy',lambda:{'accounts':[{'platform':'telegram','transport_profile':'default','account_id':'bot-A','runtime_profiles':['user-1','user-2']}]})
 st=home.stat();cap=s.UserScope(x.root,home,'user-2',('telegram','default','bot-A','2'),b,(st.st_dev,st.st_ino),admission_generation=1)
 tok=set_hermes_home_override(str(home));ct=s._CURRENT.set(cap)
 try:
  assert wa.write_approval_enabled(wa.MEMORY) is False
  assert wa.set_scoped_memory_approval(False) is False
 finally:s._CURRENT.reset(ct);reset_hermes_home_override(tok)
 assert wa.write_approval_enabled(wa.MEMORY) is True and x.cap.check() is x.cap

@pytest.mark.parametrize('bad',['revoked','missing','cold_missing','foreign_home'])
def test_no_scope_fallback_or_claimed_owner(signed,monkeypatch,bad):
 x=signed;x.source.user_name='owner developer admin'
 if bad=='revoked':x.cap.revoked=True
 elif bad in {'missing','cold_missing'}:
  s._CURRENT.set(None)
  if bad=='cold_missing':monkeypatch.setattr(s,'_ENGAGED',False)
 else:monkeypatch.setattr(wa,'get_hermes_home',lambda:x.root/'foreign')
 if bad=='foreign_home':
  # Native effective-home validation occurs inside cap.check, not an arbitrary string claim.
  from hermes_constants import set_hermes_home_override
  set_hermes_home_override(str(x.root/'foreign'))
 with pytest.raises(s.ScopeDenied):wa.set_scoped_memory_approval(True)
 assert (x.home/'config.yaml').read_bytes()==x.config

@pytest.mark.parametrize('kind',['drift','backup_failed'])
def test_actual_approval_drift_projection_truthful_original_backup(signed,monkeypatch,caplog,kind):
 x=signed;store=memory_tool.MemoryStore(memory_char_limit=32);store.load_from_disk();p=x.home/'memories/MEMORY.md';put(p,'LONG_UNDELIMITED_PRIVATE_NATIVE_'*5);raw=p.read_bytes()
 rec=wa.stage_write(wa.MEMORY,{'action':'replace','target':'memory','content':'new','old_text':raw.decode(),'matched_entry':raw.decode()},summary='Own /user/path content',origin='foreground')
 if kind=='backup_failed':
  original=Path.write_text
  def fail(path,*a,**kw):
   if '.bak.' in path.name:raise OSError('private backup failure '+str(path))
   return original(path,*a,**kw)
  monkeypatch.setattr(Path,'write_text',fail)
 out=commands.handle_pending_subcommand(wa.MEMORY,['approve',rec['id']],memory_store=store)
 assert 'Approved 0' in out and 'конфликт' in out and str(x.home) not in out and 'issue #' not in out and '§' not in out
 assert p.read_bytes()==raw and wa.get_pending(wa.MEMORY,rec['id'])
 backups=list(p.parent.glob('MEMORY.md.bak.*'))
 assert (len(backups)>0) is (kind=='drift')
 if backups:assert backups[0].read_bytes()==raw
 assert str(x.home) in caplog.text

@pytest.mark.parametrize('where',['tool','approve'])
def test_failed_memory_save_is_unconfirmed_private_and_pending_kept(signed,monkeypatch,caplog,where):
 from tools import memory_tool_store
 x=signed;x.call('approval off');store=memory_tool.load_on_disk_store()
 def fail(*a,**kw):raise OSError('PRIVATE native path '+str(x.home/'memories/MEMORY.md'))
 monkeypatch.setattr(memory_tool_store,'atomic_write_text',fail)
 if where=='tool':
  out=json.loads(memory_tool.memory_tool(action='add',content='Own fact',store=store));assert not out['success'] and out['effect_unknown'];text=out['error']
 else:
  rec=wa.stage_write(wa.MEMORY,{'action':'add','target':'memory','content':'Own fact'},summary='Own fact',origin='foreground')
  text=commands.handle_pending_subcommand(wa.MEMORY,['approve',rec['id']],memory_store=store);assert 'Approved 0' in text and wa.get_pending(wa.MEMORY,rec['id'])
 assert 'не подтверждено' in text and str(x.home) not in text and 'PRIVATE' not in text
 assert str(x.home) in caplog.text and not (x.home/'memories/MEMORY.md').exists()

@pytest.mark.parametrize('phase',['before_commit','after_commit'])
def test_preference_save_failure_never_fakes_success(signed,monkeypatch,caplog,phase):
 import hermes_state_registry as registry
 x=signed;x.call('approval off');real=registry.acquire
 class Wrap:
  def __init__(self,db):self.db=db
  def get_meta(self,*a):return self.db.get_meta(*a)
  def set_meta(self,*a):
   if phase=='after_commit':self.db.set_meta(*a)
   raise OSError('PRIVATE preference failure '+str(x.home))
  def close(self):self.db.close()
 monkeypatch.setattr(registry,'acquire',lambda p:Wrap(real(p)))
 text=x.call('approval on');assert 'не подтверждено' in text and 'PRIVATE' not in text and str(x.home) not in text
 monkeypatch.setattr(registry,'acquire',real)
 assert wa.write_approval_enabled(wa.MEMORY) is (phase=='after_commit')
 assert (x.home/'config.yaml').read_bytes()==x.config and x.cap.check() is x.cap


def test_corrupt_preference_does_not_allow_tool_writes(signed):
 from hermes_state_registry import acquire
 x=signed;db=acquire(x.home/'state.db')
 try:db.set_meta('memory.write_approval','untrusted-unknown')
 finally:db.close()
 state=x.call('approval');assert 'не установлено' in state and 'выключено' not in state
 result=json.loads(memory_tool.memory_tool(action='add',content='Must not save',store=memory_tool.load_on_disk_store()))
 assert not result['success'] and result['effect_unknown'] and not (x.home/'memories/MEMORY.md').exists()


def test_genuine_unmanaged_native_config_and_error_contract_unchanged(tmp_path,monkeypatch):
 from hermes_constants import set_hermes_home_override,reset_hermes_home_override
 home=tmp_path/'standalone';home.mkdir(mode=0o700);put(home/'config.yaml','{"memory":{"write_approval":true}}')
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda root:None);ct=s._CURRENT.set(None);tok=set_hermes_home_override(str(home))
 try:
  assert wa.scoped_memory_approval() is None and wa.write_approval_enabled(wa.MEMORY) is True
  saved=[];text=commands.handle_pending_subcommand(wa.MEMORY,['approval','off'],set_mode_fn=lambda enabled:saved.append(enabled))
  assert saved==[False] and text=="memory.write_approval set to 'off'."
  store=memory_tool.MemoryStore();store.load_from_disk()
  from tools import memory_tool_store
  monkeypatch.setattr(memory_tool_store,'atomic_write_text',lambda *a,**kw:(_ for _ in ()).throw(OSError('native private donor detail')))
  monkeypatch.setattr(wa,'_prompt_inline_memory_approval',lambda *a:True)
  with pytest.raises(RuntimeError,match='native private donor detail'):memory_tool.memory_tool(action='add',content='Own fact',store=store)
 finally:s._CURRENT.reset(ct);reset_hermes_home_override(tok)

def test_approved_replacement_preserves_user_content_and_native_anchor(signed):
 x=signed;x.call('approval off');store=memory_tool.load_on_disk_store()
 content='Public OpenAI /user/path issue #26045 stays user-authored'
 assert json.loads(memory_tool.memory_tool(action='add',content=content,store=store))['success']
 rec=wa.stage_write(wa.MEMORY,{'action':'replace','target':'memory','old_text':content,'matched_entry':content,'content':'Updated own fact'},summary='own replacement',origin='foreground')
 out=commands.handle_pending_subcommand(wa.MEMORY,['approve',rec['id']],memory_store=store)
 assert 'Approved 1' in out and rec['id'] in out and content in out
 assert 'Updated own fact' in (x.home/'memories/MEMORY.md').read_text() and wa.get_pending(wa.MEMORY,rec['id']) is None

@pytest.mark.parametrize('consumer',['sequential','invoke'])
def test_actual_agent_tool_consumers_honor_preference_in_propagated_thread(signed,consumer):
 import contextvars
 from concurrent.futures import ThreadPoolExecutor
 from agent import tool_executor,agent_runtime_helpers,inline_tool_executors
 x=signed;x.call('approval on');agent=NS(_friday_user_scope=x.cap,_memory_store=memory_tool.load_on_disk_store(),_memory_manager=None,session_id='own-current')
 args={'action':'add','content':'Own threaded fact'}
 def run():
  if consumer=='invoke':return agent_runtime_helpers.invoke_tool(agent,'memory',args,'own-task','own-call',pre_tool_block_checked=True,skip_tool_request_middleware=True,skip_tool_execution_middleware=True)
  ref=NS(name='memory',args=args,task_id='own-task',call_id='own-call',trace=[])
  result=tool_executor._resolve_sequential_dispatch(agent,ref,[]).execute(args)
  return inline_tool_executors.apply_transform_tool_result(agent,function_name='memory',function_args=args,result=result,effective_task_id='own-task',tool_call_id='own-call')
 ctx=contextvars.copy_context()
 with ThreadPoolExecutor(max_workers=1) as pool:result=json.loads(pool.submit(ctx.run,run).result(timeout=5))
 assert result['success'] and result['staged'] and wa.get_pending(wa.MEMORY,result['pending_id'])
 assert not (x.home/'memories/MEMORY.md').exists() and x.cap.check() is x.cap and (x.home/'config.yaml').read_bytes()==x.config
