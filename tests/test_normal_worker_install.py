"""Normal wiring with real private files/compiler/provisioning/native Git reads.

Build/smoke reports, Docker/manager, deployment metadata and web image are
explicit synthetic component fixtures. No model, build, network or live grant.
"""
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import worker_install as workers, dsh_prepare, a0_prepare, a0_runtime, friday_native as native
from scripts import friday_install as entry
from scripts.install_containment import Budget
from test_a0_service_install import service
from test_native_installer import install_input, native_home
from plugins.friday_rework.adapters.dsh import AdapterError
from plugins.friday_rework.host_runtime import configured_runtimes, check_runtime, HostUnavailable


REAL_DSH_RUN = dsh_prepare.run


def pin(p):
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def write(p, data):
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    p.write_bytes(data); p.chmod(0o600)
    return pin(p)


def doc(p, v):
    return write(p, (json.dumps(v, sort_keys=True, indent=2)+'\n').encode())


def git(repo, *args):
    return subprocess.run(['git','--no-optional-locks','-C',str(repo),*args], check=True,
                          capture_output=True, timeout=4).stdout.decode().strip()


def repository(p, files, url):
    p.mkdir(mode=0o700)
    for n, b in files.items(): write(p/n, b)
    git(p,'init','--template='); git(p,'add','.')
    git(p,'-c','user.name=Synthetic Fixture','-c','user.email=fixture@example.invalid',
        '-c','commit.gpgsign=false','commit','-m','Private fixture, no production donor')
    git(p,'checkout','--detach');git(p,'remote','add','origin',url)
    return {'commit':git(p,'rev-parse','HEAD'),'tree':git(p,'rev-parse','HEAD^{tree}'),
            'clone_url':url}


def web():
    return {'profile':'searxng-google','timeout_seconds':15,'dns':['1.1.1.1'],
        'version':'synthetic-component-only','image':'sha256:'+'a'*64,
        'source_pins':{'/exe/run_searxng.sh':'a'*64,
          '/usr/local/searxng/searxng-src/searx/webapp.py':'a'*64,
          '/usr/local/searxng/searxng-src/searx/settings_loader.py':'a'*64,
          '/a0/helpers/searxng.py':'4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
          '/a0/tools/search_engine.py':'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'}}


@pytest.fixture
def normal(service, monkeypatch):
    s=service;v=s.value;home=s.home
    fake_manager_run = dsh_prepare.run
    def dispatch(argv, cwd, **kw):
        if argv[0] == 'git': return REAL_DSH_RUN(argv, cwd, **kw)
        return fake_manager_run(argv, cwd, **kw)
    monkeypatch.setattr(dsh_prepare, 'run', dispatch)
    v['product']['runtime']={'enabled':False}
    h=home/'harness';a=Path(v['a0_donor'])
    dsh=repository(h, {'LICENSE':b'synthetic license','THIRD_PARTY_NOTICES.md':b'synthetic notices',
        'pnpm-lock.yaml':b'synthetic lock','package.json':b'{"version":"0.0.0-fixture"}',
        '.gitignore':b'apps/*/lib/\n'}, 'https://github.com/deepseek-ai/deepseek-harness.git')
    ap=repository(a, {'LICENSE':b'synthetic a0 license'}, 'https://github.com/agent0ai/agent-zero.git')
    lock=json.loads(Path(v['sources_lock']['path']).read_text())
    for r in lock['repositories']:
        if r['id']=='dsh': r.update(dsh)
        if r['id']=='a0': r.update(ap)
    v['sources_lock']=doc(s.deploy/'synthetic-sources.json',lock)
    cli=h/'apps/cli/lib/bin.js';write(cli,b'NEVER EXECUTED SYNTHETIC BUILD OUTPUT\n')
    node=s.deploy/'toolchain/bin/node';write(node,b'NEVER EXECUTED SYNTHETIC NODE\n')
    source=dsh_prepare.verify_source(h,dsh);source['source_lock_sha256']=v['sources_lock']['sha256']
    tool={'node_executable':str(node),'node_sha256':pin(node)['sha256']}
    inv=dsh_prepare.build_inventory(h);rows={'file_count':inv['file_count'],'sha256':inv['sha256']}
    ok={'returncode':0,'timeout':False,'reaped':True}
    for phase in ('source','toolchain','build','smoke'):
        report={'donor':str(h),'source':source,'toolchain':tool,'runtime_task':'NOT_RUN','inference':'NOT_RUN'}
        if phase in ('build','smoke'):report.update(cli=pin(cli),workspace_build_identity=rows)
        if phase=='build':report.update(install=ok,build=ok)
        if phase=='smoke':report['smoke']=[dict(kind=k,**ok) for k in ('version','help','headless-config','headless-help')]
        doc(home/'preparation/harness'/('dsh-'+phase+'.json'),report)
    doc(home/'preparation/harness/dsh-build-inventory.json',inv)
    identity,files=a0_prepare.check_checkout(a,ap)
    doc(home/'preparation/a0.json',{'donor':'a0','checkout':str(a),'source':identity,
                                  'source_lock_sha256':v['sources_lock']['sha256']})
    policy=write(s.deploy/'policy.json',b'SYNTHETIC DECLARATION, NO LIVE AUTHORITY')
    network={'name':'synthetic-existing-bridge','endpoints':[
        v['product']['a0_deployment']['chat']['endpoint'],v['product']['a0_deployment']['embedding']['endpoint']],
        'policy':policy}
    metadata=s.deploy/'runtime/git-metadata'/('b'*64)/'repo/.git'
    v['worker_install']={
      'dsh':{'budget_seconds':300,'max_file_bytes':1024,'max_total_bytes':4096,
             'toolchain_root':str(node.parent.parent),
             'resources':{'memory_bytes':2*1024**3,'cpu_percent':200,'tasks':64,'shutdown_seconds':2,'tmp_bytes':64*1024**2},
             'web':{'resolver':write(s.deploy/'resolver',b'nameserver 192.0.2.53\n'),
                    'trust_bundle':write(s.deploy/'trust',b'SYNTHETIC CA'), 'egress_evidence':policy}},
      'a0':{'budget_seconds':300,'max_file_bytes':1024,'max_total_bytes':4096,'docker':pin(a0_runtime.DOCKER),
            'policy':policy,'git_metadata':{'source':str(metadata),'manifest_sha256':'b'*64},
            'expected_files':[{'logical_name':'result.txt','media_type':'text/plain'}],
            'owner_slot':'sol','network':network,'web':web()}}
    import shutil
    shutil.rmtree(home/'worker-runtime-source')
    native.stage_worker_runtime(v,home)
    s.metadata_calls=[]
    def metadata_checked(value,**kw):
        s.metadata_calls.append(copy.deepcopy(value));kw['budget']()
        assert value==v['worker_install']['a0']['git_metadata']
    monkeypatch.setattr(a0_runtime,'check_git_metadata',metadata_checked)
    s.plugin=home/'plugins/friday_rework';s.plugin.parent.mkdir(mode=0o700)
    import shutil
    shutil.copytree(entry.ROOT/'plugins/friday_rework',s.plugin)
    for p in s.plugin.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
    return s


def prepared(s):
    return workers.prepared_product(s.value,s.home,s.budget)


def materialized(s):
    product,evidence=prepared(s)
    a0_prepare.install_service(dict(s.value,product=product),s.home,s.budget)
    return workers.materialize(s.value,s.home,product,evidence,s.budget)


def test_native_outputs_connect_both_actual_compiler_provisioning_and_refusing_admission(normal):
    s=normal;before=copy.deepcopy(s.value);product=materialized(s)
    assert s.value==before and len(s.metadata_calls)==1
    rows=configured_runtimes(product['runtime']);assert set(rows)=={'a0','dsh'}
    assert workers.installed_product(s.value,s.home)==product
    from tools.configure_product import compose_product
    bundle=compose_product(product)
    assert not bundle['contract']['ready']
    assert bundle['config']['plugins']['entries']['friday_rework']['settings']['runtime']==product['runtime']
    for w,c in rows.items():
        assert c['budget_seconds']==300 and c['runtime_home']==str(s.home) and c['runtime_profile']=='default'
        root=s.home/'workers'/w
        assert all((root/n).stat().st_mode&0o777==0o700 for n in ('jobs','staging','cache','inputs'))
        assert c['runtime_receipt']==pin(root/'runtime-receipt.json')
        assert entry.read_json(root/'runtime-receipt.json')['ready'] is False
        associations=SimpleNamespace(state=SimpleNamespace(data_dir=s.home/'state'))
        with native_home(s.home),pytest.raises(HostUnavailable,match='runtime_not_verified|a0_readiness_not_verified'):
            check_runtime(c,associations)
    assert rows['a0']['a0']['capability'] is None
    assert rows['dsh']['dsh']['node']==pin(s.deploy/'toolchain/bin/node')
    assert rows['dsh']['dsh']['cli']==pin(s.home/'harness/apps/cli/lib/bin.js')
    assert not (s.home/'.env').exists()
    assert all('--user' in x for x in s.calls) # Explicitly intercepted manager only.


@pytest.mark.parametrize('field',['dsh','a0'])
def test_normal_mode_cannot_omit_either_worker(normal,field):
    del normal.value['worker_install'][field]
    with pytest.raises(ValueError,match='both_worker'):prepared(normal)
    assert not (normal.home/'workers').exists() and not normal.calls


@pytest.mark.parametrize('phase',['source','toolchain','build','smoke'])
def test_missing_native_report_refuses_before_worker_materialization(normal,phase):
    (normal.home/'preparation/harness'/('dsh-'+phase+'.json')).unlink()
    with pytest.raises(OSError):prepared(normal)
    assert not (normal.home/'workers').exists() and not normal.calls


@pytest.mark.parametrize('mutation',['foreign-donor','wrong-source','stale-node','failed-smoke','missing-smoke','lost-build','inventory','cli-path','changed-cli','changed-tracked-source','changed-a0-source','wrong-a0-donor'])
def test_generated_provenance_or_incomplete_execution_refuses(normal,mutation):
    s=normal;p=s.home/'preparation/harness/dsh-smoke.json';r=entry.read_json(p)
    if mutation=='foreign-donor':r['donor']=str(s.deploy)
    elif mutation=='wrong-source':r['source']['commit']='0'*40
    elif mutation=='stale-node':r['toolchain']['node_sha256']='0'*64
    elif mutation=='failed-smoke':r['smoke'][0]['returncode']=1
    elif mutation=='missing-smoke':r['smoke'].pop()
    elif mutation=='lost-build':
        p=s.home/'preparation/harness/dsh-build.json';r=entry.read_json(p);r['build']['reaped']=False
    elif mutation=='inventory':
        p=s.home/'preparation/harness/dsh-build-inventory.json';r=entry.read_json(p);r['sha256']='0'*64
    elif mutation=='cli-path':r['cli']['path']=str(s.deploy/'foreign-cli')
    elif mutation=='changed-cli':(s.home/'harness/apps/cli/lib/bin.js').write_text('changed generated file')
    elif mutation=='changed-tracked-source':(s.home/'harness/LICENSE').write_text('changed source')
    elif mutation=='changed-a0-source':Path(s.value['a0_donor']).joinpath('LICENSE').write_text('changed source')
    else:
        p=s.home/'preparation/a0.json';r=entry.read_json(p);r['checkout']=str(s.deploy/'foreign-a0')
    p.write_text(json.dumps(r))
    with pytest.raises((ValueError,a0_prepare.Refusal)):prepared(s)
    assert not (s.home/'workers').exists() and not s.calls


@pytest.mark.parametrize('worker,key,val',[('dsh','budget_seconds',True),('a0','budget_seconds',214),
    ('a0','max_file_bytes',16*1024**2+1),('dsh','max_total_bytes',0)])
def test_original_explicit_limits_not_defaulted(normal,worker,key,val):
    normal.value['worker_install'][worker][key]=val
    with pytest.raises(ValueError):prepared(normal)
    assert not normal.calls


@pytest.mark.parametrize('mutation',['toolchain-overlap','ancestor-toolchain','foreign-policy','foreign-profile','existing-root','receipt-tamper','input-tamper','extra-receipt-field'])
def test_ownership_or_tampered_preparation_is_not_adopted(normal,mutation):
    s=normal
    if mutation in ('toolchain-overlap','ancestor-toolchain'):
        s.value['worker_install']['dsh']['toolchain_root']=str(s.home if mutation=='toolchain-overlap' else s.deploy.parent)
        with pytest.raises(ValueError,match='toolchain_root'):prepared(s)
    elif mutation=='foreign-policy':
        s.value['worker_install']['a0']['network']['policy']['sha256']='0'*64
        with pytest.raises(ValueError):prepared(s)
    elif mutation=='foreign-profile':
        product,evidence=prepared(s);product['runtime']['workers']['a0']['runtime_home']=str(s.deploy)
        with pytest.raises((HostUnavailable,ValueError)): workers.materialize(s.value,s.home,product,evidence,s.budget)
    elif mutation=='existing-root':
        product,evidence=prepared(s);(s.home/'workers').mkdir(mode=0o700)
        with pytest.raises(ValueError):workers.materialize(s.value,s.home,product,evidence,s.budget)
    else:
        materialized(s)
        if mutation=='input-tamper':p=s.home/'workers/dsh/inputs/dsh-local.json';p.write_text('foreign')
        else:
            p=s.home/'workers/dsh/runtime-receipt.json';r=entry.read_json(p)
            if mutation=='receipt-tamper':r['ready']=True
            else:r['opaque_attestation']='NOT AUTHORITY'
            p.write_text(json.dumps(r))
        with pytest.raises((ValueError,HostUnavailable,AdapterError)):workers.installed_product(s.value,s.home)


def test_expired_original_clock_admits_no_worker_write(normal):
    s=normal;s.budget.deadline=0
    with pytest.raises(ValueError,match='original_install_budget_exhausted'):prepared(s)
    assert not (s.home/'workers').exists() and not s.calls


def test_partial_lost_completion_never_replays_or_replaces_owned_workers(normal,monkeypatch):
    s=normal;product,evidence=prepared(s)
    a0_prepare.install_service(dict(s.value,product=product),s.home,s.budget)
    real=workers.publish;count=[]
    def lost(path,value,**kw):
        real(path,value,**kw);count.append(path)
        if path.name=='runtime-receipt.json':raise OSError('synthetic lost publication completion')
    monkeypatch.setattr(workers,'publish',lost)
    with pytest.raises(OSError):workers.materialize(s.value,s.home,product,evidence,s.budget)
    retained=(s.home/'workers/dsh/runtime-receipt.json').read_bytes()
    with pytest.raises(ValueError):workers.materialize(s.value,s.home,product,evidence,s.budget)
    assert (s.home/'workers/dsh/runtime-receipt.json').read_bytes()==retained and len(count)==1


@pytest.mark.parametrize('web_profile',['exa-paid','exa-keyless'])
def test_actual_normal_native_completion_uses_both_outputs_before_profile_and_keys(normal,monkeypatch,web_profile):
    """Real completion/compiler/inputs/config; explicitly fake PM/frontend/manager."""
    import shutil,sys
    from pm import paths,environments
    from gateway import host_rendezvous
    from hermes_cli import source_build,_launchers
    s=normal;s.value['product']['web']['profile']=web_profile
    source=s.home/'hermes-agent';source.mkdir(mode=0o700)
    shutil.rmtree(s.plugin);shutil.rmtree(s.home/'worker-runtime-source')
    monkeypatch.setattr(paths,'repo_root',lambda:source)
    monkeypatch.setattr(environments,'project_python',lambda root:Path(sys.executable))
    monkeypatch.setattr(environments,'owning_home_root',lambda root:s.home)
    monkeypatch.setattr(host_rendezvous,'read_record',lambda *a,**k:None)
    monkeypatch.setattr(source_build,'source_build_env',lambda **k:{})
    for name in ('prepare_source_dependencies','build_source_tui','build_source_web'):
        monkeypatch.setattr(source_build,name,lambda *a,**k:None)
    monkeypatch.setattr(source_build,'source_product_current',lambda *a,**k:True)
    monkeypatch.setattr(_launchers,'ensure_install_launchers',lambda *a,**k:list(_launchers.ENTRY_POINTS))
    monkeypatch.setattr(native,'install_stamp',lambda receipt:{'fixture':'PM_AND_FRONTEND_NOT_RUN'})
    before_profile=[];original=native.profile_write
    def final_profile(home,product):
        assert set(configured_runtimes(product['runtime']))=={'dsh','a0'}
        assert (home/'workers/dsh/runtime-input.json').is_file() and (home/'workers/a0/runtime-input.json').is_file()
        assert entry.read_json(home/'preparation/a0-service.receipt.json')['state']=='REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
        before_profile.append(copy.deepcopy(product));return original(home,product)
    monkeypatch.setattr(native,'profile_write',final_profile)
    with native_home(s.home): result=native.complete(s.value,s.home,{},budget=s.budget)
    assert result['state']=='TEMPLATE_INCOMPLETE' and result['ready'] is False
    assert len(before_profile)==1 and len(s.metadata_calls)==1
    product=workers.installed_product(s.value,s.home);assert product==before_profile[0]
    from hermes_cli.config import load_config_readonly
    with native_home(s.home):config=load_config_readonly()
    assert config['plugins']['entries']['friday_rework']['settings']['runtime']==product['runtime']
    assert not (s.home/'.env').exists()
    d=product['runtime']['workers']['dsh']['dsh']
    extra=[p for p in d['native_files'] if Path(p['path']).name=='friday-web-keyless.mjs']
    assert len(extra)==int(web_profile=='exa-keyless')
    if extra:
        assert extra[0]==pin(s.home/'harness/friday-web-keyless.mjs')
        assert (s.home/'harness/friday-web-keyless.mjs').read_bytes()==(entry.ROOT/'plugins/friday_rework/adapters/dsh_keyless_web.mjs').read_bytes()


def test_normal_plan_declares_conditional_a0_registration_without_any_native_effect(normal):
    s=normal
    # Fixture metadata/pins are synthetic, but the actual normal input validator
    # and argv generation must consume them without claiming/building a home.
    plan=entry.commands(s.value)
    assert plan['a0_service_effect_plan']['required'] is True
    assert plan['a0_service_effect_plan']['enable'] is plan['a0_service_effect_plan']['start'] is False
    assert plan['a0_service_effect_plan']['runtime_acceptance']=='NOT_ACCEPTED'
    assert not s.calls and not s.metadata_calls and not (s.home/'workers').exists()


@pytest.mark.parametrize('name', ['scripts/worker_install.py', 'tools/render_dsh_local.py'])
def test_new_helper_source_is_mandatory_and_pinned_before_effect(normal, name):
    s=normal;del s.value['project_files'][name]
    with pytest.raises(ValueError,match='complete_installer_plugin_inventory_required'):entry.spec_checked(s.value)
    assert not s.calls


@pytest.mark.parametrize('worker, index', [('dsh', 0), ('dsh', 1), ('dsh', 2), ('dsh', 3), ('a0', 0)])
@pytest.mark.parametrize('mutation', ['changed', 'missing'])
def test_installed_original_preparation_evidence_remains_pinned(normal, worker, index, mutation):
    s=normal;materialized(s)
    evidence=entry.read_json(s.home/'workers'/worker/'runtime-receipt.json')['evidence']
    path=Path(evidence[index]['path'])
    if mutation=='changed':path.write_text('{}\n')
    else:path.unlink()
    before=list(s.calls)
    with pytest.raises((OSError, ValueError)):workers.installed_product(s.value,s.home)
    assert s.calls==before


def test_parent_waits_for_preparer_outputs_and_retains_partial_without_replay(normal,monkeypatch):
    """Real parent order/claim/failure; explicit intercepted preparer/PM outputs."""
    from scripts import install_containment
    import sys
    s=normal;value=copy.deepcopy(s.value);home=s.deploy/'fresh-normal-home'
    value['home']=str(home);value['dsh_donor']=str(home/'harness')
    path=s.deploy/'fresh-input.json';doc(path,value);phases=[]
    class NoNativeEffects:
        def __init__(self,pin,budget,env):self.budget=budget
        def probe(self,*args): self.budget.check()
        def run(self,argv,cwd,**kwargs):
            self.budget.check();assert self.budget.deadline==deadline
            if '--destination' in argv:
                phases.append('compose');(home/'hermes-agent').mkdir(mode=0o700)
                doc(home/'hermes-agent.source.json',{'fixture':'SOURCE_ACCEPTANCE_INTERCEPTED'})
            elif '-c' in argv:return str(Path(sys.executable)),{}
            elif str(entry.ROOT/'scripts/dsh_prepare.py') in argv:
                phase=argv[3];phases.append('harness-'+phase)
                doc(home/'preparation/harness'/('dsh-'+phase+'.json'),{'fixture':phase})
            elif str(entry.ROOT/'scripts/a0_prepare.py') in argv:
                phases.append('a0');doc(home/'preparation/a0.json',{'fixture':'A0_INVENTORY_NOT_NATIVE'})
            elif str(entry.ROOT/'scripts/friday_native.py') in argv:
                phases.append('completion')
                assert phases[-6:]==['harness-source','harness-toolchain','harness-build','harness-smoke','a0','completion']
                assert all((home/'preparation/harness'/('dsh-'+p+'.json')).is_file() for p in ('source','toolchain','build','smoke'))
                assert (home/'preparation/a0.json').is_file()
                raise RuntimeError('synthetic lost completion; no replay')
            else:phases.append('PM')
            return '',{}
    budget=Budget(value['seconds']);deadline=budget.deadline
    monkeypatch.setattr(install_containment,'Containment',NoNativeEffects)
    monkeypatch.setattr(entry,'composition_checked',lambda *a,**kw:None)
    with pytest.raises(RuntimeError,match='synthetic lost completion'):entry.install(value,path,budget=budget)
    claim=entry.read_json(home/entry.MARKER)
    assert claim['state']=='PARTIAL' and claim['deadline_mono']==deadline
    assert entry.read_json(home/entry.FAILURE)['resume_allowed'] is False
    before=list(phases)
    with pytest.raises(ValueError,match='partial_install_requires_reconciliation'):entry.install(value,path,budget=budget)
    assert before==phases and (home/'preparation/a0.json').is_file()
