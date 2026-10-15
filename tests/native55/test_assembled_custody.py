import contextlib,json,time,types,sys
from pathlib import Path
import pytest
from test_browser_configure import env,base_env,invoke
from test_user_onboarding import prepare,secrets,grant,activate,admitted,home,row,ident,cas,raw,save
from hermes_cli import friday_user_scope as scope
from agent import web_call_context as web
from agent.secret_scope import load_env_file,set_secret_scope,reset_secret_scope
from tools import browser_scoped as browser

ACTIONS=[('browser_navigate',{'url':'https://example.com/'}),('browser_snapshot',{}),('browser_click',{'ref':'e1'}),('browser_type',{'ref':'e1','text':'ordinary form'}),('browser_scroll',{'direction':'down'}),('browser_back',{}),('browser_press',{'key':'Tab'})]

@pytest.fixture
def joined(env,monkeypatch):
 for uid in ('1','2'):
  prepare(env,uid);secrets(env,uid)
  proof=json.loads((home(env,uid)/scope.ONBOARDING).read_text())
  env.setup.configure_browser('default',session=env.operator,expected_config_sha256=cas(env),expected_target_config_sha256=proof['config_sha256'],expected_binding_sha256=proof['binding_sha256'],generation=row(env,uid)['generation'],preset='local-headless-basic',**ident(uid))
  grant(env,uid);assert activate(env,uid)['enabled']
 sources={}
 for uid in ('1','2'):
  ok,s=admitted(env,uid);assert ok;sources[uid]=s
 class Registry:
  def __init__(self):self.launches=[];self.stops=[];self.status='QUIESCENT'
  def spawn_browser(self,owner):
   self.launches.append(owner);owner.registry=self;owner.session=types.SimpleNamespace(web_deadline=owner.deadline(),web_stop_requested=False);return owner.session
  def settle_web(self,session,stop):self.stops.append((session,stop));return {'status':self.status}
 registry=Registry();payloads=[]
 monkeypatch.setitem(sys.modules,'tools.process_registry',types.SimpleNamespace(process_registry=registry))
 monkeypatch.setattr(browser,'_packages',lambda:{})
 monkeypatch.setattr(browser,'_OWNERS',{})
 def exchange(registry,session,call,payload):
  call.check();scope.current(required=True).check();payloads.append(payload)
  return {'ready':True} if payload.get('start') else {'success':True,'data':{'principal':scope.current().key}}
 monkeypatch.setattr(browser,'exchange',exchange)
 turns={uid:web.WebTurn() for uid in ('1','2')};original=time.monotonic()+120
 calls={uid:web.WebCall(turns[uid],time.monotonic()+45,'task-'+uid,'session-'+uid,'call-'+uid,run_deadline=original) for uid in ('1','2')}
 for uid,c in calls.items():c.turn_id='turn-'+uid;c.session_key='conversation-'+uid
 @contextlib.contextmanager
 def lane(uid):
  with scope.authority(home(env,uid)),scope.scoped_source(sources[uid]) as cap:
   token=set_secret_scope(load_env_file(home(env,uid)/'.env'),profile_home=str(home(env,uid)))
   try:
    with web.bind_web_call(calls[uid]):yield cap
   finally:reset_secret_scope(token)
 yield types.SimpleNamespace(env=env,sources=sources,registry=registry,payloads=payloads,calls=calls,turns=turns,original=original,lane=lane)
 # No process exists: cleanup reaches only the fake exact handles.
 registry.status='QUIESCENT';browser.cleanup()


def test_authenticated_two_principals_seven_actions_and_original_clocks(joined):
 h=joined
 for uid in ('1','2'):
  with h.lane(uid) as cap:
   for name,args in ACTIONS:
    assert json.loads(browser.execute(name,args,task_id='task-'+uid))['success']
    h.calls[uid].run_deadline+=1000
   assert set(cap.binding['tools'])==scope.SAFE|scope.BROWSER_TOOLS
 assert len(h.registry.launches)==2
 starts=[p for p in h.payloads if p.get('start')]
 assert {p['authority']['principal'][-1] for p in starts}=={'1','2'}
 assert len({tuple(p['pin']) for p in starts})==2
 assert all(o.deadline()==h.original for o in h.registry.launches)
 assert all(p['authority']['admission_generation']==row(h.env,p['authority']['principal'][-1])['generation'] for p in starts)


def test_discovery_family_and_batch_preflight_do_not_add_authority(joined):
 import toolsets
 h=joined
 assert set(toolsets.get_toolset('browser_scoped',include_registry=False)['tools'])==scope.BROWSER_TOOLS
 assert scope.SAFE.isdisjoint(scope.BROWSER_TOOLS)
 with h.lane('1'):
  scope.guard_tool('tool_search',{'query':'browser'});scope.guard_tool('tool_describe',{'names':['browser_navigate','browser_console']})
  for name,args in ACTIONS:scope.guard_tool('tool_call',{'name':name,'arguments':args})
  for name in ('browser_console','browser_eval','terminal','execute_code'):
   with pytest.raises(scope.ScopeDenied):scope.guard_tool(name,{})
  with pytest.raises(scope.ScopeDenied):scope.guard_tool('tool_call',{'calls':[{'name':'browser_back','arguments':{}},{'name':'browser_console','arguments':{}}]})
 assert not h.registry.launches


@pytest.mark.parametrize('change',['foreign_home','disabled','stale_generation','revoked_binding'])
def test_retained_authenticated_refusals_precede_child_effects(joined,change):
 h=joined;env=h.env
 if change in ('disabled','stale_generation'):
  from hermes_cli.friday_product_access import current_access,KEY,principal_id
  document=current_access(env.state);key=principal_id(**ident());document['users'][key]['enabled']=False
  env.state.set(KEY,document)
  if change=='stale_generation':
   document=current_access(env.state);document['users'][key]['enabled']=True;env.state.set(KEY,document)
 elif change=='revoked_binding':
  cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]['tools'].remove('web_extract');save(env,cfg)
 if change=='foreign_home':
  with scope.authority(home(env,'2')):
   with pytest.raises(scope.ScopeDenied):
    with scope.scoped_source(h.sources['1']):browser.execute('browser_back',{},task_id='task-1')
 else:
  with pytest.raises(scope.ScopeDenied):
   with h.lane('1'):browser.execute('browser_back',{},task_id='task-1')
 assert not h.registry.launches and not h.payloads
 with h.lane('2'):assert json.loads(browser.execute('browser_back',{},task_id='task-2'))['success']
 assert len(h.registry.launches)==1


def test_foreign_task_and_missing_session_refuse_before_effect(joined):
 h=joined
 with h.lane('1'):
  with pytest.raises(RuntimeError,match='native_task_session'):browser.execute('browser_back',{},task_id='task-2')
  h.calls['1'].session_id=''
  with pytest.raises(RuntimeError,match='native_task_session'):browser.execute('browser_back',{},task_id='task-1')
 assert not h.registry.launches


def test_stop_and_unknown_cleanup_are_exact_principal_and_sticky(joined,monkeypatch):
 h=joined
 for uid in ('1','2'):
  with h.lane(uid):browser.execute('browser_back',{},task_id='task-'+uid)
 h.registry.status='STOP_UNCONFIRMED'
 r=browser.cleanup(task_id='task-1');assert r['status']=='STOP_UNCONFIRMED'
 assert len(browser._OWNERS)==2 and len(h.registry.stops)==1
 with h.lane('1'):
  with pytest.raises(RuntimeError,match='not_replayable'):browser.execute('browser_back',{},task_id='task-1')
 with h.lane('2'):assert json.loads(browser.execute('browser_back',{},task_id='task-2'))['success']
 assert len(h.registry.launches)==2
 h.registry.status='QUIESCENT';assert browser.cleanup(task_id='task-1')['status']=='QUIESCENT'
 assert len(browser._OWNERS)==1


def test_unknown_command_effect_poisoned_without_replay(joined,monkeypatch):
 h=joined
 with h.lane('1'):
  browser.execute('browser_back',{},task_id='task-1')
  attempts=[]
  def unknown(*args):attempts.append(1);raise RuntimeError('unknown_effect')
  monkeypatch.setattr(browser,'exchange',unknown)
  with pytest.raises(RuntimeError,match='unknown_effect'):browser.execute('browser_click',{'ref':'e1'},task_id='task-1')
  with pytest.raises(RuntimeError,match='not_replayable'):browser.execute('browser_back',{},task_id='task-1')
 assert attempts==[1] and len(h.registry.launches)==1 and len(h.registry.stops)==1


def test_original_task_deadline_refuses_before_child(joined):
 h=joined;h.calls['1'].run_deadline=time.monotonic()-1
 with pytest.raises(TimeoutError,match='original_deadline'):
  with h.lane('1'):browser.execute('browser_back',{},task_id='task-1')
 assert not h.registry.launches


def test_actual_native_registry_discovery_direct_and_routed_handlers(joined,monkeypatch):
 from tools import browser_tool as facade
 from tools.registry import registry,invalidate_check_fn_cache
 h=joined
 def ambient(*a,**k):raise AssertionError('ambient backend must not be consulted')
 monkeypatch.setattr(facade,'check_browser_routed_requirements',ambient)
 for uid in ('1','2'):
  with h.lane(uid):
   invalidate_check_fn_cache()
   definitions=registry.get_definitions(set(scope.BROWSER_TOOLS),quiet=True)
   assert {r['function']['name'] for r in definitions}==scope.BROWSER_TOOLS
   for name,args in ACTIONS:
    assert json.loads(registry.dispatch(name,args,task_id='task-'+uid))['success']
    assert json.loads(getattr(facade,name)(**args,task_id='task-'+uid))['success']
 assert len(h.registry.launches)==2


def test_foreign_profile_secret_context_refuses_before_effect(joined):
 h=joined
 with h.lane('1'):
  t=set_secret_scope({'LOCAL_KEY':'fixture-secret-for-other-profile'},profile_home=str(home(h.env,'2')))
  try:
   with pytest.raises(RuntimeError,match='profile_secret_scope_required'):browser.execute('browser_back',{},task_id='task-1')
  finally:reset_secret_scope(t)
 assert not h.registry.launches
