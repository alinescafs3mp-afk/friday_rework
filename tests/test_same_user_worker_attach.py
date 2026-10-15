"""Ordinary-first same identity, actual native scopes; external IO is OFFLINE fixture."""
import asyncio,copy,importlib.util,json,sys
from pathlib import Path
import httpx,pytest
from fastapi import FastAPI
from test_user_onboarding import env,home,row,cas,ident,secrets,grant,activate,admitted as native_admitted,save,raw
from test_normal_user_worker_join import normal_env,fixture_native,action
from hermes_cli import friday_user_scope as scope
from hermes_cli.config import require_readable_config_before_write
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from friday_admin_controls import onboarding
OWN=Path(__file__).resolve().parents[1]

def admitted(e,*args):
    # Gateway and dashboard have distinct process-global engagement boundaries.
    # Restore only this fixture boundary; native admission/capability checks run.
    engaged=scope._ENGAGED
    try:return native_admitted(e,*args)
    finally:scope._ENGAGED=engaged

def ordinary(e,worker_keys=False):
    full=copy.deepcopy(e.template)
    ordinary=copy.deepcopy(full);ordinary.pop('worker_inputs')
    if not worker_keys:ordinary['required_secrets']=[n for n in ordinary['required_secrets'] if n!='SEARXNG_SECRET']
    cfg=raw(e);cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['ordinary']=ordinary
    save(e,cfg)
    e.setup.prepare('default',session=e.operator,expected_config_sha256=cas(e),template='ordinary',runtime_profile='user-1',**ident())
    for name in ordinary['required_secrets']:capture(e,name)
    grant(e);assert activate(e)['enabled']
    assert admitted(e)[0]
    return {n:(home(e)/n).read_bytes() for n in ('config.yaml',scope.ONBOARDING,scope.MARKER)}

def capture(e,name='SEARXNG_SECRET'):
    return e.setup.credentials('default',session=e.operator,expected_config_sha256=cas(e),generation=row(e)['generation'],
        **ident(),name=name,value='synthetic-worker-value-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')

def same(e,before):
    assert admitted(e)[0]
    assert all((home(e)/n).read_bytes()==v for n,v in before.items())
    assert require_readable_config_before_write(home(e)/'config.yaml')['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}

def test_pending_keeps_ordinary_admission_receipt_and_existing_conversation(normal_env):
    e=normal_env;before=ordinary(e);generation=row(e)['generation'];ok,source=admitted(e)
    h=home(e);(h/'workspace/continued.txt').write_text('same conversation retained');(h/'workspace/continued.txt').chmod(0o600)
    p=e.admin.onboarding_templates('default')['pending'][0]
    assert p['enabled'] and p['can_attach_workers'] and p['required_workers']==[]
    r=action(e,'prepare',template='friday-local');assert r['enabled'] and r['required_workers']==['dsh','a0']
    assert r['capture_names']==['SEARXNG_SECRET'] and not r['can_qualify_workers']
    same(e,before)
    assert capture(e)['recorded'];same(e,before)
    assert action(e,'state')['can_qualify_workers']
    r=action(e,'qualify');assert r['state']=='ADMITTED_OWN_A0_NATIVE_PREREQUISITES_PENDING'
    same(e,before);assert not (h/'workers/qualification').exists()
    token=set_hermes_home_override(str(h))
    try:
        with scope.scoped_source(source) as cap:cap.check();assert cap.admission_generation==generation
    finally:reset_hermes_home_override(token);scope._ENGAGED=False
    assert (h/'workspace/continued.txt').read_text()=='same conversation retained' and row(e)['generation']==generation

def test_both_original_consumers_commit_same_profile_generation_and_old_source(normal_env,monkeypatch):
    e=normal_env;before=ordinary(e);generation=row(e)['generation'];ok,source=admitted(e)
    root_before=(e.home/'config.yaml').read_bytes();action(e,'prepare',template='friday-local');capture(e)
    calls,_=fixture_native(e,monkeypatch)
    r=action(e,'qualify');assert r['state']=='ADMITTED_BOTH_WORKERS_ATTACHED' and r['enabled']
    assert calls==['a0','dsh'] and all(v['qualified'] for v in r['workers'].values())
    cfg=require_readable_config_before_write(home(e)/'config.yaml')['plugins']['entries']['friday_rework']['settings']
    assert cfg['worker_requirements']==['dsh','a0'] and set(cfg['runtime']['workers'])=={'dsh','a0'}
    assert row(e)['generation']==generation and (e.home/'config.yaml').read_bytes()==root_before
    assert admitted(e)[0]
    token=set_hermes_home_override(str(home(e)))
    try:
        with scope.scoped_source(source) as cap:cap.check();assert cap.admission_generation==generation
    finally:reset_hermes_home_override(token);scope._ENGAGED=False
    assert action(e,'state')['enabled']
    with pytest.raises(PermissionError):action(e,'qualify')
    assert calls==['a0','dsh']

def test_existing_scoped_worker_names_need_no_additional_capture(normal_env):
    e=normal_env;before=ordinary(e,worker_keys=True)
    r=action(e,'prepare',template='friday-local')
    assert r['capture_names']==[] and r['can_qualify_workers'];same(e,before)

@pytest.mark.parametrize('bad',['session','cas','generation','account','template-missing','wrong-template','revoked','worker-state'])
def test_prepare_negative_boundaries_leave_ordinary_home_unchanged(normal_env,bad,monkeypatch):
    e=normal_env;before=ordinary(e);changes={'template':'friday-local'}
    if bad=='session':changes['session']=None
    elif bad=='cas':changes['expected_config_sha256']='f'*64
    elif bad=='generation':changes['generation']=row(e)['generation']+1
    elif bad=='account':changes['account_id']='other'
    elif bad=='template-missing':changes.pop('template')
    elif bad=='wrong-template':changes['template']='ordinary'
    elif bad=='revoked':e.admin.set_user('default',**ident(),enabled=False,role='user')
    elif bad=='worker-state':monkeypatch.setattr(onboarding.Associations,'snapshot',lambda self:{'uncertain-owned':{}})
    try:r=action(e,'prepare',**changes);assert r['state']=='INSTALLATION_WORKER_INPUTS_MISSING'
    except (PermissionError,ValueError,KeyError):pass
    assert all((home(e)/n).read_bytes()==v for n,v in before.items())
    assert not (home(e)/'workers').exists()
    if bad!='revoked':assert admitted(e)[0]

@pytest.mark.parametrize('damage',['template','generation','input','attachment','runtime','partial','existing-key'])
def test_staged_drift_no_replay_no_ordinary_reseal(normal_env,monkeypatch,damage):
    e=normal_env;before=ordinary(e)
    if damage=='partial':
        original=onboarding.Onboarding.prepare_worker
        def interrupted(self,*a,**kw):
            if kw['worker']=='a0':raise OSError('offline interruption')
            return original(self,*a,**kw)
        with monkeypatch.context() as m:
            m.setattr(onboarding.Onboarding,'prepare_worker',interrupted)
            with pytest.raises(OSError):action(e,'prepare',template='friday-local')
        r=action(e,'prepare',template='friday-local');assert not r['can_prepare_workers'] and not r['can_qualify_workers']
        same(e,before);return
    action(e,'prepare',template='friday-local');capture(e)
    if damage=='template':
        c=raw(e);c['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']['worker_inputs']['workers']['dsh']['budget_seconds']-=1;save(e,c)
    elif damage=='generation':
        e.admin.set_user('default',**ident(),enabled=False,role='user')
    elif damage=='input':(home(e)/'workers/dsh/inputs/dsh-local.json').write_text('{}')
    elif damage=='attachment':
        p=home(e)/onboarding.WORKER_ATTACHMENT;v=json.loads(p.read_text());v['required_names']=v['required_names'][:-1];p.write_text(json.dumps(v))
    elif damage=='runtime':
        p=home(e)/'workers/dsh/runtime-input.json';v=json.loads(p.read_text());v['runtime']['budget_seconds']-=1;p.write_text(json.dumps(v))
    elif damage=='existing-key':
        with pytest.raises(PermissionError):capture(e,e.template['required_secrets'][0])
        same(e,before);return
    from scripts import worker_qualification as q
    monkeypatch.setattr(q,'dsh_observe',lambda *a,**k:pytest.fail('effect after staged drift'))
    monkeypatch.setattr(q,'a0_observe',lambda *a,**k:pytest.fail('effect after staged drift'))
    with pytest.raises(Exception):action(e,'qualify')
    assert not (home(e)/'workers/qualification').exists()
    assert all((home(e)/n).read_bytes()==v for n,v in before.items())
    if damage!='generation':assert admitted(e)[0]

def own_app(e):
    import test_admin_repair
    def mount(env):
        spec=importlib.util.spec_from_file_location('attach_test_api',OWN/'plugins/friday_rework/dashboard/api.py')
        api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)
        app=FastAPI();app.state.auth_required=True;app.include_router(api.router,prefix='/api/plugins/friday_rework');return app
    e.monkeypatch.setattr(test_admin_repair,'mounted_app',mount)
    return test_admin_repair.basic_app(e)

def test_actual_signed_router_requires_explicit_template_and_refuses_opaque_runtime(normal_env):
    e=normal_env;before=ordinary(e);app,token=own_app(e)
    body={'expected_config_sha256':cas(e),'generation':row(e)['generation'],**ident()}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline') as c:
            url='/api/plugins/friday_rework/onboarding/workers/prepare?profile=default'
            assert (await c.post(url,json=body|{'template':'friday-local'},headers={'Authorization':'Bearer forged'})).status_code==401
            headers={'Authorization':'Bearer '+token}
            assert (await c.post(url,json=body|{'template':'friday-local','runtime':{}},headers=headers)).status_code==422
            denied=await c.post(url,json=body,headers=headers);assert denied.status_code==403,denied.text
            r=await c.post(url,json=body|{'template':'friday-local'},headers=headers);assert r.status_code==200,r.text
            assert r.json()['enabled'] and r.json()['required_workers']==['dsh','a0']
    asyncio.run(run());same(e,before)

@pytest.mark.parametrize('mode',['normal','uncertain'])
def test_shipped_active_ui_explicit_selector_same_identity_and_uncertainty_controls(mode):
    import subprocess,resource
    if resource.getrlimit(resource.RLIMIT_AS)[0]==536870912:
        pytest.skip('Node V8 cannot initialize under original 512MiB AS; UI fixture NOT_RUN')
    result=subprocess.run(['/usr/bin/node',str(OWN/'tests/same_user_worker_attach_ui.cjs'),
        str(OWN/'plugins/friday_rework/dashboard/index.js'),mode],text=True,capture_output=True,timeout=5,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','NODE_OPTIONS':'--max-old-space-size=32'})
    assert result.returncode==0,result.stderr
    v=json.loads(result.stdout);assert v['browser_live']=='NOT_RUN'
    writes=[r for r in v['requests'] if r.get('method')=='POST']
    assert len(writes)==(3 if mode=='normal' else 2)

def test_failed_native_observation_preserves_ordinary_and_consumed_attempt(normal_env,monkeypatch):
    e=normal_env;before=ordinary(e);action(e,'prepare',template='friday-local');capture(e)
    calls,_=fixture_native(e,monkeypatch,bad='dsh-network')
    with pytest.raises(Exception):action(e,'qualify')
    same(e,before);assert calls==['a0','dsh'] and (home(e)/'workers/qualification/original.json').exists()
    with pytest.raises(Exception):action(e,'qualify')
    assert calls==['a0','dsh'];same(e,before)

@pytest.mark.parametrize('damage',['names','preparation'])
def test_active_capture_rejects_staged_drift_before_secret_write(normal_env,damage):
    e=normal_env;before=ordinary(e);action(e,'prepare',template='friday-local')
    secret_before=(home(e)/'.env').read_bytes()
    if damage=='names':
        p=home(e)/onboarding.WORKER_ATTACHMENT;v=json.loads(p.read_text());v['required_names'].append('UNREVIEWED_CAPTURE_KEY');p.write_text(json.dumps(v))
        name='UNREVIEWED_CAPTURE_KEY'
    else:
        p=home(e)/'workers/a0/runtime-input.json';v=json.loads(p.read_text());v['generation']+=1;p.write_text(json.dumps(v));name='SEARXNG_SECRET'
    with pytest.raises(Exception):capture(e,name)
    assert (home(e)/'.env').read_bytes()==secret_before;same(e,before)
