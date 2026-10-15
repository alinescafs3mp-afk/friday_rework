import copy,json,hashlib,ast,os
from dataclasses import replace
from pathlib import Path
import pytest
from test_user_onboarding import env as base_env,prepare,secrets,grant,home,row,ident,cas,sha,raw,save,complete
from hermes_cli import friday_user_scope as scope
from friday_admin_controls.onboarding import validate_template


@pytest.fixture
def env(base_env):
 import friday_admin_controls.onboarding as onboarding
 onboarding.RESOURCE=Path(os.environ['FRIDAY_PROJECT_SOURCE']).resolve()/'plugins/friday_rework'
 c=base_env.template['config'];c['model']['key_env']='LOCAL_KEY'
 c['auth']={'adopt_external_logins':False}
 c['delegation'].update(base_url=c['model']['base_url'],key_env='LOCAL_KEY')
 c['agent']['environment_hint']=(onboarding.RESOURCE/'RESEARCH.md').read_text().strip()
 cfg=raw(base_env);cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']=base_env.template
 save(base_env,cfg)
 return base_env


def body(env):
 p=json.loads((home(env)/scope.ONBOARDING).read_text())
 return dict(expected_config_sha256=cas(env),expected_target_config_sha256=p['config_sha256'],
  expected_binding_sha256=p['binding_sha256'],generation=row(env)['generation'],
  preset='local-headless-basic',**ident())

def invoke(env,**delta):
 return env.admin.onboarding_browser_configure('default',session=env.operator,**(body(env)|delta))

def payloads(env):
 return {str(p.relative_to(env.home)):p.read_bytes() for p in env.home.rglob('*')
  if p.is_file() and not p.name.endswith('.lock') and 'backups' not in p.parts
  and p.name!='dashboard-auth.log'}

def test_prepare_existing_disabled_preserves_payload_identity_generation(env):
 prepare(env);secrets(env)
 h=home(env);(h/'workspace/kept.txt').write_text('private-history-canary')
 before={n:(h/n).read_bytes() for n in ('.env','SOUL.md','workspace/kept.txt')}
 inode=h.stat().st_ino;generation=row(env)['generation'];old=body(env)
 result=invoke(env)
 assert not result['enabled'] and row(env)['generation']==generation and not row(env)['enabled']
 assert h.stat().st_ino==inode and not (h/scope.MARKER).exists()
 assert all((h/n).read_bytes()==v for n,v in before.items())
 binding=raw(env)['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]
 config=__import__('yaml').safe_load((h/'config.yaml').read_text())
 assert scope.BROWSER_TOOLS<=set(binding['tools']) and not (set(binding['tools'])-scope.BROWSER_TOOLS-scope.SAFE)
 assert config['browser']==scope.BROWSER_LOCAL_CONFIG
 assert config['platform_toolsets']['telegram'].count(scope.BROWSER_TOOLSET)==1
 proof=json.loads((h/scope.ONBOARDING).read_text())
 assert proof['binding_sha256']==scope._fingerprint(binding) and proof['config_sha256']==sha(h/'config.yaml')
 assert proof['required_secrets']==['LOCAL_KEY','EXA_API_KEY']
 assert result['browser_execution'] is None
 # An interrupted or repeated request cannot replay the migration.
 with pytest.raises((ValueError,PermissionError)):
  env.setup.configure_browser('default',session=env.operator,**old)

@pytest.mark.parametrize('field,value',[
 ('expected_config_sha256','0'*64),('expected_target_config_sha256','0'*64),
 ('expected_binding_sha256','0'*64),('generation',999),('user_id','foreign'),
 ('transport_profile','foreign'),('preset','cloud')])
def test_stale_foreign_and_arbitrary_inputs_refuse_before_payload_write(env,field,value):
 prepare(env);env.admin.users('default');args=body(env)|{field:value};before=payloads(env)
 with pytest.raises((ValueError,PermissionError)):
  env.setup.configure_browser('default',session=env.operator,**args)
 assert payloads(env)==before

@pytest.mark.parametrize('actor',('missing','expired','foreign'))
def test_native_signed_operator_required_before_write(env,actor):
 prepare(env);args=body(env);before=payloads(env)
 session={'missing':None,'expired':replace(env.operator,expires_at=1),
  'foreign':replace(env.operator,user_id='foreign')}[actor]
 with pytest.raises(PermissionError):
  env.setup.configure_browser('default',session=session,**args)
 assert payloads(env)==before

@pytest.mark.parametrize('attachment',('marker','workers'))
def test_existing_custody_is_not_adopted(env,attachment):
 prepare(env);args=body(env)
 if attachment=='marker':(home(env)/scope.MARKER).write_text('{}')
 else:(home(env)/'workers').mkdir(mode=0o700)
 before=payloads(env)
 with pytest.raises(PermissionError):
  env.setup.configure_browser('default',session=env.operator,**args)
 assert payloads(env)==before


def test_browser_custody_gap_does_not_block_ordinary_admission(env):
 from test_user_onboarding import admitted
 prepare(env);secrets(env);grant(env);invoke(env)
 result=env.setup.activate('default',session=env.operator,expected_config_sha256=cas(env),
  generation=row(env)['generation'],**ident())
 assert result['state']=='ADMITTED_NEXT_NATIVE_REQUEST'
 assert result['browser_execution'] is None
 assert row(env)['enabled'] and (home(env)/scope.MARKER).exists()
 accepted,source=admitted(env);assert accepted
 with scope.authority(home(env)),scope.scoped_source(source):
  scope.guard_tool('web_search',{'query':'ordinary chat keeps web tools'})
  scope.guard_tool('browser_navigate',{'url':'https://example.com'})
  from tools.browser_scoped import execute
  with pytest.raises(RuntimeError):execute('browser_navigate',{'url':'https://example.com'},task_id='missing-native-task')


def test_exact_family_and_provider_config_refuses_wider_authority(env):
 c=copy.deepcopy(env.template['config']);tools=sorted(scope.SAFE|scope.BROWSER_TOOLS)
 c['browser']=copy.deepcopy(scope.BROWSER_LOCAL_CONFIG);c['toolsets'].append(scope.BROWSER_TOOLSET)
 c['platform_toolsets']['telegram'].append(scope.BROWSER_TOOLSET)
 scope.validate_browser_config(c,tools,'telegram')
 for field,value in [('cloud_provider','auto'),('use_real_profile',True),('cdp_url','http://localhost:9222'),('allow_private_urls',True)]:
  broken=copy.deepcopy(c);broken['browser'][field]=value
  with pytest.raises(scope.ScopeDenied):scope.validate_browser_config(broken,tools,'telegram')
 with pytest.raises(scope.ScopeDenied):scope.validate_browser_config(c,list(scope.SAFE),'telegram')
 assert 'browser_eval' not in scope.SAFE|scope.BROWSER_TOOLS
 assert 'browser_console' not in scope.SAFE|scope.BROWSER_TOOLS


def test_no_browser_requirement_for_existing_ordinary_chat_activation(env):
 complete(env)
 assert row(env)['enabled'] and not scope.browser_admission_error(scope.SAFE)


def test_operator_expired_after_target_lock_refuses_before_any_payload_write(env,monkeypatch):
 from contextlib import contextmanager
 from hermes_cli import config as native,friday_product_access as policy
 prepare(env);args=body(env);before=payloads(env);original=native.config_write_transaction
 clock=policy.time
 @contextmanager
 def target_lock(path):
  with original(path):
   if Path(path)==home(env)/'config.yaml':
    from types import SimpleNamespace
    monkeypatch.setattr(policy,'time',SimpleNamespace(time=lambda:clock.time()+86400,monotonic=clock.monotonic))
   yield
 monkeypatch.setattr(native,'config_write_transaction',target_lock)
 with pytest.raises(PermissionError):
  env.setup.configure_browser('default',session=env.operator,**args)
 assert payloads(env)==before


def test_receipt_write_failure_keeps_disabled_and_refuses_replay(env,monkeypatch):
 import friday_admin_controls.onboarding as onboarding
 prepare(env);args=body(env)
 monkeypatch.setattr(onboarding,'finish_admin_config_edit',lambda *a: (_ for _ in ()).throw(OSError('synthetic interrupted receipt write')))
 with pytest.raises(OSError):env.setup.configure_browser('default',session=env.operator,**args)
 assert not row(env)['enabled'] and not (home(env)/scope.MARKER).exists()
 args['expected_config_sha256']=cas(env)
 with pytest.raises(PermissionError,match='prepared_home_changed'):
  env.setup.configure_browser('default',session=env.operator,**args)


def test_foreign_second_profile_payload_is_unchanged(env):
 prepare(env);prepare(env,'2');secrets(env,'2')
 foreign={str(p.relative_to(home(env,'2'))):p.read_bytes() for p in home(env,'2').rglob('*') if p.is_file()}
 invoke(env)
 assert all((home(env,'2')/n).read_bytes()==v for n,v in foreign.items())
 assert not row(env,'2')['enabled']


def test_retained_scope_revocation_precedes_browser_or_operator_effect(env):
 from test_user_onboarding import admitted
 complete(env);accepted,source=admitted(env);assert accepted
 with scope.authority(home(env)),scope.scoped_source(source) as cap:
  pass
 cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]['tools'].remove('web_extract')
 save(env,cfg)
 with scope.authority(home(env)):
  token=scope._CURRENT.set(cap)
  try:
   with pytest.raises(scope.ScopeDenied):scope.guard_tool('browser_navigate',{'url':'https://example.com'})
   assert cap.revoked
   with pytest.raises(PermissionError,match='operator_source_scope_required'):
    env.setup.configure_browser('default',session=env.operator,expected_config_sha256='0'*64,
     expected_target_config_sha256='0'*64,expected_binding_sha256='0'*64,generation=1,preset='local-headless-basic',**ident())
  finally:scope._CURRENT.reset(token)


def test_candidate_api_signed_session_and_closed_body(env):
 import asyncio,importlib.util,sys,httpx
 from fastapi import FastAPI
 prepare(env)
 for name,module in list(sys.modules.items()):
  if name=='friday_admin_controls' or name.startswith('friday_admin_controls.'):
   sys.modules[name.replace('friday_admin_controls','_friday_dashboard_projection',1)]=module
 p=Path(__file__).resolve().parents[1]/'project/plugins/friday_rework/dashboard/api.py'
 spec=importlib.util.spec_from_file_location('candidate_browser_api',p);api=importlib.util.module_from_spec(spec)
 sys.modules[spec.name]=api;spec.loader.exec_module(api)
 app=FastAPI();app.state.auth_required=True
 @app.middleware('http')
 async def native_signed_session(request,call_next):
  token=request.headers.get('Authorization','').removeprefix('Bearer ')
  request.state.session=env.provider.verify_session(access_token=token)
  return await call_next(request)
 app.include_router(api.router,prefix='/api/plugins/friday_rework')
 async def run():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as client:
   url='/api/plugins/friday_rework/onboarding/browser/configure?profile=default'
   args=body(env);before=payloads(env)
   r=await client.post(url,json=args);assert r.status_code==403
   outsider=env.provider._mint_session('ordinary').access_token
   r=await client.post(url,json=args,headers={'Authorization':'Bearer '+outsider});assert r.status_code==403
   assert payloads(env)==before
   owner=env.provider._mint_session('owner').access_token;headers={'Authorization':'Bearer '+owner}
   r=await client.post(url,json=args|{'cloud_provider':'auto'},headers=headers);assert r.status_code==422
   r=await client.post(url,json=args,headers=headers);assert r.status_code==200,r.text
   assert r.json()['state']=='DISABLED_BROWSER_PREPARED_CUSTODY_REQUIRED'
 asyncio.run(run())
