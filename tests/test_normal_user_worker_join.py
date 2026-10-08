"""Shipped normal compiler -> signed admin API -> own native-result consumer.

Files, grants, scopes, CAS, secrets and consumer validation are real. Native
DSH/A0 observations below are explicit offline fixtures, never live acceptance.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import httpx
import pytest
from test_user_onboarding import env, prepare as legacy_prepare, secrets, grant, activate, home, row, ident, cas, raw, save, admitted
from test_user_worker_provision import inputs, pin
from test_product_profile import inputs as product_input
from test_worker_web_admission import policy, spec_web, observation
from test_worker_qualification import probe
from test_admin_repair import basic_app
from hermes_cli import friday_user_scope as scope
from hermes_cli.config import require_readable_config_before_write
from friday_admin_controls import user_worker_join as join, host_runtime as hr
from tools.configure_product import compose_product
from plugins.friday_rework.adapters.a0_profile import legacy_profile

ROOT=Path(__file__).resolve().parents[1]


def prepare(e,uid='1',**changes):
    return e.setup.prepare('default',session=e.operator,expected_config_sha256=cas(e),
        template='friday-local',runtime_profile='user-'+uid,**(ident(uid)|changes))


@pytest.fixture
def normal_env(env):
    d,_=inputs(env);a,_=inputs(env,worker='a0')
    deployment=legacy_profile()
    for kind,c in (('dsh',d),('a0',a)):
        base=env.home/'workers'/kind
        c.update(runtime_home=str(env.home),runtime_profile='default',workspace_root=str(base/'jobs'),
            staging_root=str(base/'staging'),cache_roots=[str(base/'cache')],budget_seconds=215)
    d['dsh']['key_name']='FRIDAY_LLM_API_KEY'
    p=Path(d['dsh']['web']['egress_evidence']['path'])
    p.write_text(json.dumps(policy(str(env.home),'default',time.time())));p.chmod(0o600)
    d['dsh']['web']['egress_evidence']=pin(p)
    a['a0'].update(deployment=deployment,web=spec_web())
    spec=product_input();spec['inference'].update(base_url=deployment['chat']['endpoint'],model='dispatcher',
        key_env='FRIDAY_LLM_API_KEY',context=40960,max_input=32000)
    spec.update(a0_deployment=deployment,runtime={'enabled':True,'workers':{'dsh':d,'a0':a}})
    bundle=compose_product(spec)
    env.template=bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
    config=raw(env);config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']=env.template
    save(env,config);env.operator_runtime=spec['runtime'];env.bundle=bundle
    return env


def action(e,name,uid='1',**changes):
    return getattr(e.admin,'onboarding_workers_'+name)('default',**(dict(session=e.operator,
        expected_config_sha256=cas(e),generation=row(e,uid)['generation'],**ident(uid))|changes))


def pending(e,uid='1'):
    p=prepare(e,uid);r=action(e,'prepare',uid);secrets(e,uid);grant(e,uid)
    assert r['required_workers']==['dsh','a0'] and not r['can_activate']
    return p,r


def fixture_native(e,monkeypatch,uid='1',bad=None):
    """Replace only external native boundaries; exact own producer stays real."""
    from scripts import worker_qualification as q
    from scripts import a0_runtime as a0
    h=home(e,uid);native=h/join.PLAN
    for name,filename in (('PROFILE_SOURCE','a0_profile.py'),('WEB_SOURCE','a0_web.py')):
        path=h/('synthetic-'+filename)
        path.write_bytes((ROOT/'plugins/friday_rework/adapters'/filename).read_bytes());path.chmod(0o600)
        monkeypatch.setattr(a0,name,path)
    prepared={k:json.loads((h/'workers'/k/'runtime-input.json').read_text())['runtime'] for k in ('dsh','a0')}
    c=prepared['a0'];a=c['a0'];now=time.time()
    native.write_text(json.dumps({'association_binding':{'owner':{'profile':'user-'+uid,'bot_id':'bot-A','user_id':uid},
        'workspace_reference':str(h/'workers/a0/jobs/native-fixture')},'deployment':a['deployment'],'web':a['web'],
        'git_metadata':a['git_metadata'],'network':{'id':'f'*64,'launcher_sha256':a['launcher']['sha256'],
            'policy_sha256':a['policy']['sha256']},'code_sha256':a['runtime']['sha256'],
        'docker_sha256':a['docker']['sha256'],'daemon_unit_sha256':a['daemon_unit']['sha256'],
        'accepted_unix':now-1,'deadline_unix':now+300}));native.chmod(0o600)
    m=SimpleNamespace(validate=lambda p,**kw:p,remaining=lambda p: 300,
        probe_report_checked=a0.probe_report_checked,MEMORY=2*1024**3,PIDS=128)
    monkeypatch.setattr(hr,'a0_runtime_module',lambda c:m)
    calls=[]
    def dsh(c,h,folder,budget):
        calls.append('dsh');d=c['dsh'];prefix=hashlib.sha256(str(folder).encode()).hexdigest()[:24]
        def run(i): return {'returncode':0,'timeout':False,'reaped':True,'resource_envelope':{
            'unit':'friday-qualify-dsh-'+prefix+'-'+str(i)+'.scope',
            **{k:d[k] for k in ('memory_bytes','cpu_percent','tasks')},
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'deadline':budget.deadline}}
        p=json.loads(Path(d['web']['egress_evidence']['path']).read_text())
        urls=['https://api.exa.ai/',*p['document_probes']]
        v={'smoke':[{'kind':kind,'observation':run(i)} for i,kind in enumerate(
            ('version','help','headless-config','headless-help'),1)],'network':observation(urls),
            'network_execution':run(5),'policy_sha256':d['web']['egress_evidence']['sha256']}
        if bad=='dsh-unreaped':v['smoke'][0]['observation']['reaped']=False
        if bad=='dsh-network':v['network']={'ready':True}
        if bad=='dsh-envelope':v['smoke'][0]['observation']['resource_envelope']['memory_bytes']=1
        if bad=='source':Path(d['cli']['path']).write_text('changed source')
        return v
    def a0obs(c,ref,budget):
        calls.append('a0');v={'plan':ref,'container_id':'e'*64,'invocation_id':'b'*32,
            'native_probe':probe(c['a0']['deployment']),
            'web':{'status':'CURRENT_NATIVE_WEB_SERVICE_CHECKED','version':c['a0']['web']['version'],
                'processes':[{'name':n,'pid':i,'start':1,'statename':'RUNNING'} for i,n in enumerate(('run_ui','run_searxng'),1)]},
            'route':{'status':'CURRENT_LOCAL_NETWORK_CHECKED','id':'f'*64},
            'native_resources':{'running':True,'unit_quiescent':False,'caps':{'memory.max':str(m.MEMORY),
                'memory.swap.max':'0','pids.max':str(m.PIDS),'cpu.max':'200000 100000'}}}
        if bad=='a0-caps':v['native_resources']['caps']['memory.swap.max']='max'
        if bad=='a0-web':v['web']['processes'].pop()
        if bad=='a0-route':v['route']['id']='c'*64
        if bad=='a0-stopped':v['native_resources']['running']=False
        if bad=='cancel':e.admin.set_user('default',**ident(uid),enabled=False,role='user')
        if bad=='keys':(h/'.env').write_text('')
        if bad=='expiry':budget.deadline=time.monotonic()-1
        return v
    monkeypatch.setattr(q,'dsh_observe',dsh);monkeypatch.setattr(q,'a0_observe',a0obs)
    return calls,native


def test_normal_compiler_retains_declarations_without_operator_receipts(normal_env):
    e=normal_env;v=e.template['worker_inputs'];assert set(v['workers'])=={'dsh','a0'}
    for kind,c in v['workers'].items():
        assert 'runtime_receipt' not in c and 'runtime_home' not in c and 'runtime_profile' not in c
        assert c['budget_seconds']==215
    assert v['workers']['a0']['a0']['capability'] is None
    assert 'patch' not in v['workers']['dsh']['dsh']
    assert e.template['config']['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}


def test_normal_pending_cannot_activate_or_publish_blocking_marker(normal_env):
    e=normal_env;prepare(e);secrets(e);grant(e)
    assert require_readable_config_before_write(home(e)/'config.yaml')['plugins']['entries']['friday_rework']['settings']['worker_requirements']==['dsh','a0']
    r=activate(e);assert r['state']=='DISABLED_REQUIRED_WORKERS_PENDING' and not r['enabled']
    assert not (home(e)/scope.MARKER).exists() and not row(e)['enabled']
    r=action(e,'prepare');assert not r['can_activate']
    assert activate(e)['state']=='DISABLED_REQUIRED_WORKERS_PENDING'


def test_old_valid_same_template_home_keeps_its_original_contract(normal_env):
    e=normal_env;legacy_prepare(e)
    for name in json.loads((home(e)/scope.ONBOARDING).read_text())['required_secrets']:
        e.setup.credentials('default',session=e.operator,expected_config_sha256=cas(e),
            generation=row(e)['generation'],**ident(),name=name,value='synthetic-legacy-key')
    grant(e);assert activate(e)['enabled']
    h=home(e);p=h/scope.ONBOARDING;marker=h/scope.MARKER
    # Exact historical unextended receipt shape, synthetic existing home.
    old=json.loads(p.read_text());assert 'required_workers' not in old
    old['template']='friday-local';p.write_text(json.dumps(old))
    v=json.loads(marker.read_text());v['onboarding_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();marker.write_text(json.dumps(v))
    generation=row(e)['generation']
    from test_admin_onboarding_join import edit
    assert not join.required_workers(raw(e),old,h)
    assert edit(e)['recorded'] and admitted(e)[0] and row(e)['generation']==generation
    assert not (h/'workers').exists()
    assert require_readable_config_before_write(h/'config.yaml')['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}


def test_two_users_derive_distinct_original_scoped_inputs_no_keys_or_receipts(normal_env):
    e=normal_env;results=[]
    for uid in ('1','2'):
        prepare(e,uid);results.append(action(e,'prepare',uid))
        for kind in ('dsh','a0'):
            h=home(e,uid);v=json.loads((h/'workers'/kind/'runtime-input.json').read_text())
            c=v['runtime'];assert c['runtime_home']==str(h) and c['runtime_profile']=='user-'+uid
            assert c['budget_seconds']==215 and not Path(c['runtime_receipt']['path']).exists()
            assert not (h/'FRIDAY-INSTALL.json').exists() and not (h/'.env').exists()
        p=json.loads((home(e,uid)/'workers/dsh/inputs/web-policy.json').read_text())
        original=json.loads(Path(e.operator_runtime['workers']['dsh']['dsh']['web']['egress_evidence']['path']).read_text())
        assert p==dict(original,runtime_home=str(home(e,uid)),runtime_profile='user-'+uid)
    assert results[0]['workers']==results[1]['workers'] and raw(e)['owner_unrelated']=='PRESERVE_ME'


def test_no_own_a0_producer_is_explicit_pending_no_claim_or_observer(normal_env,monkeypatch):
    e=normal_env;pending(e)
    from scripts import worker_qualification as q
    monkeypatch.setattr(q,'dsh_observe',lambda *a:pytest.fail('native IO before owning A0 prerequisite'))
    r=action(e,'qualify');assert r['state']=='DISABLED_OWN_A0_NATIVE_PROBE_REQUIRED'
    assert not (home(e)/join.FOLDER).exists()
    assert action(e,'qualify')['state']==r['state']  # Inspection only, no retry/claim.
    assert not row(e)['enabled'] and not (home(e)/scope.MARKER).exists()


def test_actual_own_producer_both_consumers_and_native_admission_join(normal_env,monkeypatch):
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch)
    r=action(e,'qualify');assert calls==['dsh','a0'] and r['can_activate']
    assert not r['enabled'] and all(x['qualified'] for x in r['workers'].values())
    config=require_readable_config_before_write(home(e)/'config.yaml')
    assert set(hr.configured_runtimes(config['plugins']['entries']['friday_rework']['settings']['runtime']))=={'dsh','a0'}
    assert not (home(e)/'FRIDAY-INSTALL.json').exists()
    assert action(e,'qualify')['can_activate'] and calls==['dsh','a0']
    assert activate(e)['enabled'] and admitted(e)[0]


@pytest.mark.parametrize('bad',['dsh-unreaped','dsh-network','dsh-envelope','source','a0-caps','a0-web',
    'a0-route','a0-stopped','cancel','keys','expiry'])
def test_changed_native_evidence_cancel_keys_or_original_deadline_never_enables_or_replays(normal_env,monkeypatch,bad):
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch,bad=bad)
    with pytest.raises(Exception):action(e,'qualify')
    assert not row(e)['enabled'] and not (home(e)/scope.MARKER).exists()
    assert not (home(e)/join.PROOF).exists() or bad=='source'
    assert (home(e)/join.INTENT).exists()
    before=list(calls)
    with pytest.raises(Exception):action(e,'qualify')
    assert calls==before


@pytest.mark.parametrize('bad',['user','profile','bot','workspace'])
def test_foreign_native_probe_refuses_before_claim(normal_env,monkeypatch,bad):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch);p=json.loads(path.read_text())
    if bad=='workspace':p['association_binding']['workspace_reference']=str(e.home/'foreign')
    else:p['association_binding']['owner'][{'user':'user_id','profile':'profile','bot':'bot_id'}[bad]]='foreign'
    path.write_text(json.dumps(p))
    with pytest.raises(hr.HostUnavailable):action(e,'qualify')
    assert calls==[] and not (home(e)/join.FOLDER).exists()


@pytest.mark.parametrize('bad',['receipt','foreign-receipt','proof','original','input','credentials','policy-expired'])
def test_bare_hash_foreign_missing_changed_or_expired_proof_refused_at_activation(normal_env,monkeypatch,bad):
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch);assert action(e,'qualify')['can_activate']
    h=home(e)
    if bad=='receipt':(h/'workers/a0/runtime-receipt.json').write_text('{"ready":true}')
    elif bad=='foreign-receipt':
        prepare(e,'2');action(e,'prepare','2')
        (h/'workers/dsh/runtime-receipt.json').write_bytes((h/'workers/a0/runtime-receipt.json').read_bytes())
    elif bad=='proof':(h/join.PROOF).write_text('{"ready":true}')
    elif bad=='original':(h/join.INTENT).write_text('{}')
    elif bad=='input':(h/'workers/dsh/inputs/dsh-local.json').write_text('{}')
    elif bad=='credentials':(h/'.env').write_text('')
    else:
        p=h/'workers/dsh/inputs/web-policy.json';v=json.loads(p.read_text());v['expires_unix']=time.time()-1;p.write_text(json.dumps(v))
    try:r=activate(e);assert not r['enabled']
    except (ValueError,PermissionError,KeyError,RuntimeError):pass
    assert not row(e)['enabled'] and not (h/scope.MARKER).exists() and calls==['dsh','a0']


@pytest.mark.parametrize('bad',['session','cas','generation','transport','account'])
def test_normal_api_effect_boundaries_refuse_without_worker_writes(normal_env,bad):
    e=normal_env;prepare(e);change={}
    if bad=='session':change['session']=None
    elif bad=='cas':change['expected_config_sha256']='f'*64
    elif bad=='generation':change['generation']=row(e)['generation']+1
    elif bad=='transport':change['transport_profile']='foreign'
    else:change['account_id']='foreign'
    with pytest.raises(Exception):action(e,'prepare',**change)
    assert not (home(e)/'workers').exists() and not row(e)['enabled']


def test_partial_preparation_inspects_without_duplicate_or_salvage(normal_env,monkeypatch):
    e=normal_env;prepare(e)
    from friday_admin_controls import onboarding
    original=onboarding.Onboarding.prepare_worker
    def interrupted(self,*a,**kw):
        if kw['worker']=='a0':raise OSError('explicit fixture interruption')
        return original(self,*a,**kw)
    with monkeypatch.context() as m:
        m.setattr(onboarding.Onboarding,'prepare_worker',interrupted)
        with pytest.raises(OSError):action(e,'prepare')
    before=(home(e)/'workers/dsh/runtime-input.json').read_bytes()
    r=action(e,'prepare');assert not r['can_prepare_workers'] and not r['can_activate']
    assert (home(e)/'workers/dsh/runtime-input.json').read_bytes()==before
    assert not (home(e)/'workers/a0').exists()


def test_actual_signed_router_normal_prepare_pending_and_no_opaque_inputs(normal_env):
    e=normal_env;prepare(e);app,token=basic_app(e)
    body=dict(expected_config_sha256=cas(e),generation=row(e)['generation'],**ident())
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline') as c:
            url='/api/plugins/friday_rework/onboarding/workers/prepare?profile=default'
            assert (await c.post(url,json=body,headers={'Authorization':'Bearer forged'})).status_code==401
            headers={'Authorization':'Bearer '+token}
            assert (await c.post(url,json=body|{'runtime':{'ready':True}},headers=headers)).status_code==422
            r=await c.post(url,json=body,headers=headers);assert r.status_code==200,r.text
            assert r.json()['required_workers']==['dsh','a0'] and not r.json()['can_activate']
            r=await c.post(url.replace('/prepare?','/state?'),json=body,headers=headers)
            assert r.status_code==200 and r.json()['worker_execution']=='PENDING_OWN_A0_NATIVE_PROBE_AND_QUALIFICATION'
    asyncio.run(run())


@pytest.mark.parametrize('mode',['pending','qualified-fixture','uncertain'])
def test_shipped_ui_native_fetch_handlers_and_pending_requests_at_signed_router(normal_env,mode):
    e=normal_env;prepare(e);app,token=basic_app(e)
    import hermes_cli
    native=Path(hermes_cli.__file__).resolve().parents[1]/'web/src/lib/api.ts'
    assert native.is_file()
    result=subprocess.run(['/usr/bin/node',str(ROOT/'tests/onboarding_ui.cjs'),
        str(ROOT/'plugins/friday_rework/dashboard/index.js'),str(native)],
        input=json.dumps({'token':token,'normal_join':True,'config_sha256':cas(e),
            'normal_qualified':mode=='qualified-fixture','uncertain':mode=='uncertain'}),
        text=True,capture_output=True,timeout=5,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','NODE_OPTIONS':'--max-old-space-size=32'})
    assert result.returncode==0,result.stderr
    v=json.loads(result.stdout);assert 'NORMAL_DISABLED_WORKERS_CANNOT_ACTIVATE' in v['observations']
    assert v['browser_live']=='NOT_RUN'
    requests=[r for r in v['requests'] if '/onboarding/workers/' in r['url']]
    assert [r['url'].split('/workers/')[1].split('?')[0] for r in requests][:2]==['prepare','state']
    if mode=='qualified-fixture':assert 'QUALIFIED_REQUIRED_WORKERS_ENABLE_ACTIVATION' in v['observations']
    if mode=='uncertain':assert 'UNCERTAINTY_NO_RESUBMISSION' in v['observations']
    # Actual emitted native-client bytes, same principal/CAS/generation, at the
    # real protected router. Qualifier success remains the separate native-IO
    # fixture test above; no synthetic ready:true is sent as runtime evidence.
    async def replay():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline',
            cookies={'hermes_session_at':token,'hermes_session_provider':'basic'}) as c:
            for req in requests[:2]:
                r=await c.request(req['method'],req['url'],content=req['body'],headers=req['headers'])
                assert r.status_code==200,r.text
                assert r.json()['required_workers']==['dsh','a0'] and not r.json()['can_activate']
                assert r.json()['workers']['a0']['state']=='PREPARED_RUNTIME_UNOBSERVED'
    asyncio.run(replay())
