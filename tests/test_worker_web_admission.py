"""Current producers and ordinary host join. Native transport stays synthetic."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_host_native import (setup, isolated, native, offline_boundary, pin,
                              ingress, invoke, settle)
from test_a0_runtime import a0
import test_worker_web as web_fixture
from friday_dsh_adapter_test.worker_web import DshNetworkCheck, WorkerWebError, web_policy
from friday_dsh_adapter_test.adapters.a0_web import checked_web, route_web, service_files, service_probe
from friday_dsh_adapter_test.adapters.a0_config import prepare_keys, prepare_web_keys, A0Error
from friday_dsh_adapter_test.adapters.a0_profile import legacy_profile, checked_profile
from tools.render_dsh_local import build_patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('candidate_web_guard',ROOT/'scripts/rootless_docker_launch.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)


def spec_web():
    return {'profile':'searxng-google','timeout_seconds':15,'dns':['1.1.1.1'],'version':'synthetic-pinned',
            'image':'sha256:'+'c'*64,'source_pins':{
                '/exe/run_searxng.sh':'a'*64,
                '/usr/local/searxng/searxng-src/searx/webapp.py':'b'*64,
                '/usr/local/searxng/searxng-src/searx/settings_loader.py':'c'*64,
                '/a0/helpers/searxng.py':'4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
                '/a0/tools/search_engine.py':'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'}}


def policy(home,profile,now):
    st=Path('/proc/self/ns/net').stat()
    return dict(schema='friday.worker-web.policy.v1',runtime_home=home,runtime_profile=profile,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                net_namespace=[st.st_dev,st.st_ino],expires_unix=now+600,
                allow_public_https=True,document_probes=['https://docs.python.org/3/library/asyncio-task.html'])


def observation(urls):
    return {'schema':'friday.dsh-web-observation.v1','rows':[dict(url=u,address='93.184.216.34',status=200,tls=True) for u in urls]}


@pytest.fixture
def producer():
    fixture=web_fixture.WorkerWeb();fixture.setUp()
    f=fixture.f
    config={'runtime_home':str(f.root),'runtime_profile':'default'}
    f.row['host']={'binding':{'runtime':copy.deepcopy(config)}}
    # Actual adapter's admission, bounds, pins and sandbox; existing row fixture
    # has no native host metadata schema, so only its row-reader is substituted.
    f.adapter._row=lambda original:(copy.deepcopy(f.row),Path(f.row['workspace_reference']))
    p=policy(str(f.root),'default',f.now);fixture.web.egress_evidence.path.write_text(json.dumps(p));fixture.web.egress_evidence.path.chmod(0o600)
    fixture.web=copy.copy(fixture.web)
    object.__setattr__(fixture.web,'egress_evidence',type(fixture.web.egress_evidence)(fixture.web.egress_evidence.path,hashlib.sha256(fixture.web.egress_evidence.path.read_bytes()).hexdigest()))
    from dataclasses import replace
    f.adapter.config=replace(f.adapter.config,web=fixture.web)
    root=Path(f.row['workspace_reference']);root.mkdir(mode=0o700,exist_ok=True);(root/'inputs').mkdir(mode=0o700)
    from friday_dsh_adapter_test.worker_web import DSH_NETWORK_PROBE
    (root/'inputs/web-network.mjs').write_text(DSH_NETWORK_PROBE)
    check=DshNetworkCheck(config,SimpleNamespace(clock=lambda:f.now),f.adapter)
    yield fixture,check,p
    f.doCleanups()


def test_current_dns_tls_producer_uses_exact_sandbox_without_keys(producer):
    f,c,p=producer;calls=[]
    def run(argv,**kwargs):
        calls.append((argv,kwargs)); assert argv[0]=='/usr/bin/bwrap';assert '/etc/resolv.conf' in argv
        assert 'EXA_API_KEY' not in kwargs['env'];assert kwargs['timeout']<=5
        return subprocess.CompletedProcess(argv,0,json.dumps(observation(json.loads(argv[-1]))).encode(),b'')
    with patch('subprocess.run',run):r=c(f.f.row,f.web)
    assert r['identity']['existing_task_id']==f.f.row['existing_task_id'];assert len(calls)==1
    assert r['policy_sha256']==f.web.egress_evidence.sha256


@pytest.mark.parametrize('field,bad',[('runtime_home','/foreign'),('runtime_profile','foreign'),('expires_unix',0),
    ('boot_id','foreign'),('net_namespace',[1,1]),('allow_public_https',False),('schema','ready'),
    ('document_probes',['http://docs.python.org/']),('document_probes',['https://user:key@docs.python.org/']),
    ('document_probes',['https://docs.python.org/?secret=value']),('document_probes',['https://docs.python.org/#']),
    ('document_probes',['https://127.0.0.1/'])])
def test_policy_stale_foreign_secret_routes_refuse_before_process(producer,field,bad):
    f,c,p=producer;p[field]=bad;f.web.egress_evidence.path.write_text(json.dumps(p))
    object.__setattr__(f.web.egress_evidence,'sha256',hashlib.sha256(f.web.egress_evidence.path.read_bytes()).hexdigest())
    with patch('subprocess.run') as run,pytest.raises((WorkerWebError,ValueError)):c(f.f.row,f.web)
    run.assert_not_called()


@pytest.mark.parametrize('kind',['private','wrong-url','no-tls','http-fail','extra','timeout','cancel','expired','runtime-drift'])
def test_native_transport_negative_and_changed_owner_refuse(producer,kind):
    f,c,p=producer
    def run(argv,**kwargs):
        v=observation(json.loads(argv[-1]))
        if kind=='private':v['rows'][0]['address']='127.0.0.1'
        if kind=='wrong-url':v['rows'][0]['url']='https://foreign.example/'
        if kind=='no-tls':v['rows'][0]['tls']=False
        if kind=='http-fail':v['rows'][0]['status']=503
        if kind=='extra':v['inline_key']='foreign'
        if kind=='timeout':raise subprocess.TimeoutExpired(argv,5)
        if kind=='cancel':f.f.row['stop_intent']='cancel'
        if kind=='expired':f.f.now+=601
        if kind=='runtime-drift':f.f.row['host']['binding']['runtime']['runtime_profile']='foreign'
        return subprocess.CompletedProcess(argv,0,json.dumps(v).encode(),b'')
    with patch('subprocess.run',run),pytest.raises((RuntimeError,ValueError)):c(f.f.row,f.web)


@pytest.mark.asyncio
async def test_ordinary_native_host_calls_concrete_producer_twice_then_same_worker(setup,tmp_path,monkeypatch):
    config=copy.deepcopy(setup.runtime);d=config['dsh']; fields={}
    data={'resolver':b'nameserver 1.1.1.1\n','trust_bundle':b'SYNTHETIC CA\n',
          'egress_evidence':json.dumps(policy(str(setup.home),'default',setup.host.store.clock())).encode(),
          'research_policy':(ROOT/'config/RESEARCH.md').read_bytes()}
    for key,b in data.items():
        p=tmp_path/(key+'.input');p.write_bytes(b);p.chmod(0o600);fields[key]=pin(p)
    d['web']={'profile':'exa-paid',**fields}
    rows=build_patch(purpose='temporary-local-test',api='openai-completions',base_url='http://127.0.0.1:8011/v1',
        model='local-fixture',context_window=40960,max_tokens=4096,summary_max_tokens=2048,headroom_tokens=4096,
        api_key_env=d['key_name'],web_profile='exa-paid')
    p=tmp_path/'patch.json';p.write_text(json.dumps(rows));d['patch']=pin(p)
    module=sys.modules[setup.module.__name__.rsplit('.',1)[0]+'.host_runtime']
    import tools.web_profile as helper
    receipt=dict(schema='friday-rework.dsh-runtime.v1',ready=True,
        runtime_sha256=setup.record.digest({k:v for k,v in config.items() if k!='runtime_receipt'}),
        adapter_sha256=pin(Path(module.__file__).parent/'adapters/dsh.py')['sha256'],evidence=[fields['egress_evidence']],
        web_source_pins={'plugins/friday_rework/worker_web.py':pin(Path(module.__file__).parent/'worker_web.py')['sha256'],
                         'tools/web_profile.py':pin(Path(helper.__file__))['sha256'],'config/RESEARCH.md':fields['research_policy']['sha256']})
    p=tmp_path/'receipt.json';p.write_text(json.dumps(receipt));config['runtime_receipt']=pin(p);setup.configure(config)
    with (setup.home/'.env').open('a') as out:out.write('EXA_API_KEY=SYNTHETIC_EXA\n')
    prior=subprocess.run;seen=[]
    def run(argv,**kw):
        if argv[0]=='/usr/bin/bwrap':
            seen.append(argv);assert 'EXA_API_KEY' not in kw['env']
            return subprocess.CompletedProcess(argv,0,json.dumps(observation(json.loads(argv[-1]))).encode(),b'')
        assert kw['env']['EXA_API_KEY']=='SYNTHETIC_EXA'
        return prior(argv,**kw)
    monkeypatch.setattr(subprocess,'run',run)
    proof=await ingress(setup);r=invoke(setup,proof);await settle(setup)
    assert r['accepted'];assert len(seen)==2;assert len(setup.boundary.launches)==1
    row=setup.host.store.snapshot()[r['reference']];assert row['host']['quiescence'] and row['host']['terminal']['state']=='completed'
    assert row['budget_seconds']==60 and 0 < row['deadline_unix']-row['created_at_unix'] <= 60


@pytest.mark.parametrize('name',['sentence-transformers/all-MiniLM-L6-v2','huggingface/sentence-transformers/all-MiniLM-L6-v2'])
def test_native_embedding_rewrite_cannot_escape_selected_local_provider(name):
    p=legacy_profile();p['name']='future';p['embedding']['model']=name
    with pytest.raises(ValueError,match='provider_alias'):checked_profile(p)


def test_accepted_ula_reaches_actual_product_capacity_validator():
    from tools.configure_local_test import build_config
    c=build_config(base_url='http://[fd00::42]:18001/v1',model='declared-local',key_env='FRIDAY_LLM_API_KEY',
        context=262144,max_input=260000,main_output=16384,summary_output=8192,margin=1000,template_overhead=1000)
    assert c['model']['base_url']=='http://[fd00::42]:18001/v1'


@pytest.mark.parametrize('field,bad',[('dns',['127.0.0.1']),('dns',['10.0.0.1']),('dns',['fd00::1']),
    ('profile','auto'),('timeout_seconds',True),('version',''),('image','latest'),('source_pins',{})])
def test_a0_web_configuration_refuses_missing_service_and_foreign_routes(field,bad):
    v=spec_web();v[field]=bad
    with pytest.raises(ValueError):checked_web(v)


def nft_data(web):
    rows=[{'table':{'family':'inet','name':'frw_a0_local'}}]
    for chain, expressions in guard.expected_rules(web).items():
        rows.append({'chain':{'family':'inet','table':'frw_a0_local','name':chain,'type':'filter','hook':chain,'prio':-10,'policy':'drop'}})
        for expr in expressions:
            expr=copy.deepcopy(expr)
            for x in expr:
                if 'counter' in x:x['counter']={'packets':0,'bytes':0}
            rows.append({'rule':{'family':'inet','table':'frw_a0_local','chain':chain,'expr':expr}})
    return {'nftables':rows}


def test_explicit_web_nft_semantics_preserve_default_drop_and_local_model_rules():
    w=route_web(spec_web());assert guard.checked_policy(json.dumps(nft_data(w)),w)==guard.policy_hash(w)
    assert guard.policy_hash()!=guard.policy_hash(w)
    for chain in guard.expected_rules(w):
        assert guard.expected_rules(w)[chain][-1]==[{'counter':None},{'drop':None}]
        assert guard.expected_rules(w)[chain][:2]==guard.expected_rules()[chain][:2]
    text=guard.policy(w);assert 'udp dport 53' in text and 'tcp dport 443' in text
    assert '192.168.0.0/16' in text and 'policy drop' in text
    with pytest.raises(RuntimeError,match='semantics'):guard.checked_policy(json.dumps(nft_data(w)))


@pytest.mark.parametrize('kind',['accept-all','private-https','foreign-dns','missing-drop','extra-service'])
def test_explicit_web_kernel_readback_negatives(kind):
    w=route_web(spec_web());v=nft_data(w);rules=[r['rule'] for r in v['nftables'] if 'rule' in r]
    if kind=='accept-all':rules[-1]['expr']=[{'accept':None}]
    if kind=='missing-drop':v['nftables'].pop()
    if kind=='extra-service':v['nftables'].append(copy.deepcopy(v['nftables'][-1]))
    if kind in ('private-https','foreign-dns'):
        rule=next(r for r in rules if any(x.get('match',{}).get('right')=={'set':['1.1.1.1']} for x in r['expr']))
        rule['expr'][2]['match']['right']='10.0.0.1'
    with pytest.raises(RuntimeError):guard.checked_policy(json.dumps(v),w)


def test_a0_native_config_secret_and_supervisor_compose_only_two_services(tmp_path):
    v=spec_web(); files=service_files(v);assert files['web/settings.yml']['use_default_settings']['engines']['keep_only']==['google']
    assert files['plugins/_document_query/config.json']['fetch_retries']==1
    conf=files['web/supervisord.conf'];assert conf.count('[program:')==2;assert 'run_sshd' not in conf
    assert 'autorestart=false' in conf;assert '/exe/run_searxng.sh' in conf
    usr=tmp_path/'usr';a0.materialize(usr,web=v)
    assert json.loads((usr/'web/settings.yml').read_text())==files['web/settings.yml']
    base=prepare_keys(usr,lambda n:'synthetic-local-model-key')
    secret='SYNTHETIC_PRIVATE_SERVICE_SECRET_0123456789'
    keys=prepare_web_keys(base,usr,lambda n:secret);keys.ready()
    assert set(keys.admitted())=={'API_KEY_OPENAI','API_KEY_OTHER'}
    assert oct(keys.secret_path.stat().st_mode&0o777)=='0o600'
    with pytest.raises(A0Error):keys.remove(cessation_confirmed=False)
    keys.remove(cessation_confirmed=True);assert not keys.secret_path.read_bytes()
    assert secret not in json.dumps(files) and secret not in service_probe(v)


@pytest.mark.parametrize('value',['','ultrasecretkey','changeme','short','x\nFOREIGN=value'])
def test_missing_default_or_injected_a0_secret_refuses_before_write(tmp_path,value):
    usr=tmp_path/'usr';a0.materialize(usr,web=spec_web());base=prepare_keys(usr,lambda n:'synthetic-model-key')
    with pytest.raises(A0Error):prepare_web_keys(base,usr,lambda n:value)
    assert not (usr/'web/secret.env').exists()
    base.remove(cessation_confirmed=True)


def test_a0_web_plan_binds_image_service_source_and_route_permission(tmp_path):
    from test_original_route import network
    n=network();w=spec_web();n['web']=route_web(w);n['policy_sha256']=guard.policy_hash(n['web'])
    with patch.object(a0,'RUNTIME',tmp_path):
        now=time.time();p=a0.plan(now,now+1800,assignment='fixture',generation=1,owner_slot='astra',original_budget_seconds=1800,network=n,web=w)
        assert p['image']==w['image'] and p['web_source_sha256']==hashlib.sha256(a0.WEB_SOURCE.read_bytes()).hexdigest()
        assert a0.create_argv(p)[-1]==a0.web_module().START_SCRIPT
        assert '/etc/searxng/settings.yml,readonly' in ' '.join(a0.create_argv(p))
        old=copy.deepcopy(p);old['web']['version']='stale'
        with pytest.raises(RuntimeError):a0.validate(old)
        n.pop('web')
        with pytest.raises(RuntimeError):a0.plan(now,now+1800,assignment='fixture',generation=1,owner_slot='astra',original_budget_seconds=1800,network=n,web=w)


@pytest.mark.parametrize('bad',['wrong-version','extra-process','not-running','replaced','input-drift'])
def test_a0_current_service_consumer_refuses_stale_effective_boundary(tmp_path,bad):
    w=spec_web();usr=tmp_path/'usr';a0.materialize(usr,web=w)
    now=time.time();rt=a0.Runtime.__new__(a0.Runtime)
    rt.p={'web':w,'state_dir':str(usr),'accepted_unix':now,'deadline_unix':now+1800,'original_budget_seconds':1800}
    network=[];rt.check_network=lambda **kw:network.append(kw)
    report={'status':'CURRENT_NATIVE_WEB_SERVICE_CHECKED','version':w['version'],
        'processes':[{'name':name,'pid':10+i,'start':100,'statename':'RUNNING'} for i,name in enumerate(('run_ui','run_searxng'))]}
    rt.docker=lambda *args,**kw:json.dumps(report)
    assert rt.check_web('a'*64)==report;assert len(network)==2
    if bad=='wrong-version':report['version']='foreign'
    if bad=='extra-process':report['processes'].append(dict(report['processes'][0],name='foreign'))
    if bad=='not-running':report['processes'][0]['statename']='STOPPED'
    if bad=='replaced':report['processes'][0]['start']+=1
    if bad=='input-drift':(usr/'web/settings.yml').write_text('{}')
    with pytest.raises(RuntimeError):rt.check_web('a'*64)


def test_a0_service_secret_drift_cannot_be_cleaned_as_own_original(tmp_path):
    usr=tmp_path/'usr';a0.materialize(usr,web=spec_web());base=prepare_keys(usr,lambda n:'synthetic-model')
    keys=prepare_web_keys(base,usr,lambda n:'SYNTHETIC_WEB_SECRET_0123456789012345')
    keys.secret_path.write_text('SEARXNG_SECRET=FOREIGN_ROTATED_VALUE\n')
    with pytest.raises(A0Error):keys.ready()
    with pytest.raises(A0Error):keys.remove(cessation_confirmed=True)
    assert keys.secret_path.read_text().endswith('FOREIGN_ROTATED_VALUE\n')


def test_normal_install_ships_pinned_helpers_without_touching_live_launcher(tmp_path,monkeypatch):
    from scripts import friday_native
    source=tmp_path/'source'; source.mkdir(mode=0o700)
    names=['scripts/a0_runtime.py','scripts/rootless_docker_launch.py','plugins/friday_rework/adapters/a0_profile.py','plugins/friday_rework/adapters/a0_web.py']
    pins={}
    for name in names:
        p=source/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes());p.chmod(0o600);pins[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(friday_native,'ROOT',source)
    home=tmp_path/'product';home.mkdir(mode=0o700)
    dest=friday_native.stage_worker_runtime({'project_files':pins},home)
    for name in names:
        p=dest/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==pins[name];assert p.stat().st_mode&0o777==0o400
    with pytest.raises(ValueError):friday_native.stage_worker_runtime({'project_files':pins},home)
    assert not (home/'.runtime').exists()



def test_normal_a0_profile_propagates_explicit_scoped_native_service_names():
    from test_product_profile import inputs
    from tools.configure_product import compose_product
    spec=inputs();spec['inference']['key_env']='FRIDAY_LLM_API_KEY'
    pin=dict(path='/private/operator/source',sha256='a'*64)
    spec['runtime']=dict(enabled=True,runtime_profile='default',runtime_home='/private/operator',
        workspace_root='/private/jobs',staging_root='/private/staging',cache_roots=['/private/cache'],
        budget_seconds=120,max_file_bytes=1024,max_total_bytes=4096,runtime_receipt=pin,
        a0=dict(runtime=pin,launcher=pin,docker=pin,daemon_unit=pin,policy=pin,owner_slot='astra',
            capability=None,git_metadata={'source':'/private/metadata','manifest_sha256':'b'*64},
            expected_files=[{'logical_name':'result.txt','media_type':'text/plain'}],web=spec_web()))
    result=compose_product(spec)
    names=result['contract']['required_scoped_names']['inference_web']
    assert names==['FRIDAY_LLM_API_KEY','EXA_API_KEY','FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET']
    assert result['contract']['ready'] is False
    spec['inference']['key_env']='OTHER_KEY'
    with pytest.raises(ValueError,match='scoped_inference_key'):compose_product(spec)
