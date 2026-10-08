"""Real ordinary transaction/consumers with explicitly synthetic native IO.

Source Git, compiler, profile write/lock, archive/pins, installer inspection,
plan validation and fail-closed transitions are real. A0 native interfaces and
DSH bwrap outputs are synthetic; no installation or native acceptance runs.
"""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest
from scripts import worker_qualification as q, worker_install as workers, friday_install as entry
from scripts import friday_native as native, a0_runtime as a0, dsh_prepare
from scripts.install_containment import Budget
from plugins.friday_rework import host_runtime as hr
from test_native_installer import install_input, native_home as native_scope
from test_a0_service_install import service
from test_normal_worker_install import normal, materialized, doc, pin, write
from test_worker_web_admission import policy, observation


def probe(deployment):
    expected = a0.templates(deployment)['plugins/_model_config/presets.yaml'][0]
    return {'status':'NO_MODEL_STARTUP_PROBE_PASS','scope':'agent0/no-project/no-context',
        'configured_preset':expected['name'],'selected_preset':expected['name'],
        'temporary_test':deployment['name']=='legacy-local-test','hard_total_prompt_bound':False,
        'key_ready':{'openai':True,'other':True},'tokens':{'encoding':'cl100k_base','count':12,'approximate':13},
        'slots':{slot:{'provider':c['provider'],'transport_provider':'openai','name':c['name'],
            'api_base':c['api_base'],'ctx_length':c.get('ctx_length',0),'max_tokens':c['kwargs'].get('max_tokens'),
            'timeout':c['kwargs']['timeout'],'api_mode':c['kwargs'].get('a0_api_mode')}
            for slot in ('chat','utility','embedding') for c in [expected[slot]]}}


@pytest.fixture
def installed(normal,monkeypatch):
    s=normal
    s.claim=entry.partial_claim('f'*64,s.budget)
    doc(s.home/entry.MARKER,s.claim)
    protected=s.deploy/'a0_web.py'
    write(protected,(entry.ROOT/'plugins/friday_rework/adapters/a0_web.py').read_bytes())
    monkeypatch.setattr(a0,'WEB_SOURCE',protected)
    s.value['worker_install']['dsh']['web']['egress_evidence']=doc(s.deploy/'web-policy.json',policy(str(s.home),'default',time.time()))
    product=materialized(s)
    with native_scope(s.home):native.profile_write(s.home,product)
    source=s.home/'hermes-agent';source.mkdir(mode=0o700)
    from pm import paths,environments
    monkeypatch.setattr(paths,'repo_root',lambda:source)
    monkeypatch.setattr(environments,'project_python',lambda root:Path(os.sys.executable))
    monkeypatch.setattr(environments,'owning_home_root',lambda root:s.home)
    doc(s.home/'hermes-agent.source.json',{'classification':'SYNTHETIC_COMPOSITION_INTERFACE_ONLY'})
    # The composition boundary alone is synthetic. Every installed file,
    # project input, preparation, service receipt and worker consumer is real.
    monkeypatch.setattr(entry,'composition_checked',lambda *a,**kw:None)
    marker={'schema':entry.SCHEMA,'state':'INSTALLED_TEMPLATE_INCOMPLETE','home':str(s.home),
        'input_sha256':'f'*64,'original_attempt':entry.partial_claim('f'*64,s.budget),
        'source_receipt_sha256':pin(s.home/'hermes-agent.source.json')['sha256'],
        'profile_files':{name:pin(s.home/name)['sha256'] for name in ('config.yaml','SOUL.md','FRIDAY-PROFILE.json')},
        'plugin_files':{n:h for n,h in s.value['project_files'].items() if n.startswith('plugins/friday_rework/')},
        'worker_files':{str(p.relative_to(s.home)):pin(p)['sha256'] for p in (s.home/'workers').rglob('*') if p.is_file()},
        'a0_service_receipt_sha256':pin(s.home/'preparation/a0-service.receipt.json')['sha256'],
        'worker_state':'BOTH_CONFIGURED_QUALIFICATION_PENDING'}
    doc(s.home/entry.MARKER,marker);s.product=product;s.marker=marker;s.native=[];s.bad=None
    def dsh_io(argv,cwd,**kw):
        s.native.append(('dsh',list(argv)))
        assert argv[0]=='/usr/bin/systemd-run' and '--scope' in argv
        assert '/usr/bin/bwrap' in argv and '--unshare-pid' in argv and '--as-pid-1' in argv
        assert all(any(x.startswith('--property='+p+'=') for x in argv)
                   for p in ('MemoryMax','MemorySwapMax','CPUQuota','TasksMax','RuntimeMaxSec'))
        assert kw['deadline']==s.budget.deadline and kw['timeout']<=5
        assert 'EXA_API_KEY' not in kw['env'] and 'FRIDAY_LLM_API_KEY' not in kw['env']
        fd=argv[argv.index('--json-status-fd')+1]
        if s.bad!='namespace':os.write(int(fd),b'{"child-pid":123456}\n{"exit-code":0}\n')
        out=json.dumps(observation(json.loads(argv[-1]))) if 'web-network.mjs' in ' '.join(argv) else 'SYNTHETIC NO-MODEL CLI OUTPUT'
        if s.bad=='network':out='{"schema":"ready"}'
        return out,{'returncode':0,'timeout':False,'reaped':True}
    monkeypatch.setattr(dsh_prepare,'run',dsh_io)
    from scripts import rootless_docker_launch as launcher
    n={'schema':'friday.a0.local-network.v1','owner':'sol:qualification-fixture#1',
       'nonce':'c'*32,'name':'frw-a0-local-'+'c'*12,'id':'f'*64,'bridge':launcher.BRIDGE,
       'labels':{'friday.rework.owner':'sol:qualification-fixture#1','friday.rework.route':'c'*32},
       'endpoints':copy.deepcopy(launcher.ENDPOINTS),'launcher_sha256':'d'*64,
       'policy_sha256':launcher.policy_hash(),'request_sha256':'e'*64,
       'guard_receipt_sha256':'a'*64,'invocation_id':'b'*32,
       'namespaces':{'user':[4,501],'mnt':[4,502],'net':[4,503]}}
    n.update(launcher_sha256=product['runtime']['workers']['a0']['a0']['launcher']['sha256'],
             policy_sha256=product['runtime']['workers']['a0']['a0']['policy']['sha256'])
    n['web']=a0.web_module().route_web(s.value['worker_install']['a0']['web'])
    now=time.time()
    s.plan=a0.plan(now,now+300,assignment='qualification-fixture',generation=1,owner_slot='sol',
        original_budget_seconds=300,git_metadata=s.value['worker_install']['a0']['git_metadata'],
        network=n,deployment=s.value['product']['a0_deployment'],web=s.value['worker_install']['a0']['web'])
    s.plan_ref=doc(s.deploy/'current-plan.json',s.plan)
    class Boundary:
        """Explicit native-interface fixture, never a runtime implementation."""
        def __init__(self,plan,**kw):
            a0.validate(plan,budget=kw['budget']);s.native.append(('a0','construct'))
            self.reads=0
            self.supervisor=NS(observe=lambda row:NS(missing=False,quiescent=s.bad=='unit',invocation_id='b'*32))
        @contextmanager
        def locked(self):yield
        def receipt(self):
            self.reads+=1
            return {'container_id':('e' if s.bad=='replace' and self.reads>1 else 'd')*64,'invocation_id':'b'*32}
        def inspect(self,*args,**kw):return {'State':{'Running':s.bad!='stopped','Pid':123456}}
        def association(self,r):return {'supervisor':{'unit':s.plan['unit']}}
        def probe(self):s.native.append(('a0','probe'));return probe(s.value['product']['a0_deployment'])
        def observe(self):return {'running':True,'unit_quiescent':False,'caps':{'memory.max':str(a0.MEMORY),
            'memory.swap.max':'0','pids.max':str(a0.PIDS),'cpu.max':'200000 100000'}}
        def check_web(self,cid):
            s.native.append(('a0','web'));return None if s.bad=='web' else {
                'status':'CURRENT_NATIVE_WEB_SERVICE_CHECKED','version':s.value['worker_install']['a0']['web']['version'],
                'processes':[dict(name=name,pid=20+i,start=100,statename='RUNNING') for i,name in enumerate(('run_ui','run_searxng'))]}
        def check_network(self,**kw):s.native.append(('a0','route'));return {'status':'CURRENT_LOCAL_NETWORK_CHECKED','id':'f'*64}
    monkeypatch.setattr(a0,'Runtime',Boundary)
    monkeypatch.setattr(hr,'a0_runtime_module',lambda runtime:a0)
    return s


def transition(s):
    with native_scope(s.home):return native.qualify(s.value,'f'*64,s.plan_ref,s.budget)


def test_exact_transition_real_installer_profile_health_and_no_job_authority(installed,monkeypatch):
    s=installed;original_inputs={p:p.read_bytes() for p in (s.home/'workers').rglob('*') if p.is_file() and p.name!='runtime-receipt.json'}
    with native_scope(s.home):
        assert entry.inspect(s.value,'f'*64)['state']=='TEMPLATE_INCOMPLETE'
    r=transition(s);assert r['state']=='DEPLOYMENTS_QUALIFIED' and not r['ready']
    assert len([x for x in s.native if x[0]=='dsh'])==5
    with native_scope(s.home):
        assert entry.inspect(s.value,'f'*64)['state']=='DEPLOYMENTS_QUALIFIED'
        product=workers.installed_product(s.value,s.home)
        store=NS(state=NS(data_dir=s.home/'state'))
        for kind,c in product['runtime']['workers'].items():
            assert hr.check_runtime(c,store)==c
            assert hr.deployment_health(c)==c
        assert product['runtime']['workers']['a0']['a0']['capability'] is None
    assert all(p.read_bytes()==raw for p,raw in original_inputs.items())
    archive=entry.read_json(s.home/q.ORIGINAL)
    assert archive['marker']==s.marker and archive['marker']['original_attempt']['deadline_mono']==s.budget.deadline
    for kind in ('dsh','a0'):
        p=s.home/q.FOLDER/'original/workers'/kind/'runtime-receipt.json'
        assert entry.read_json(p)['ready'] is False
    from plugins.friday_rework import admin,startup_health
    class Owner:
        def profiles(self):return ['default']
        @contextmanager
        def scope(self,profile):
            with native_scope(s.home):yield s.home
    monkeypatch.setattr(admin,'Administration',Owner)
    report=startup_health.worker_health()
    assert not report['missing_workers'] and all(r['deployment_verified'] for r in report['workers'])
    assert report['runtime_ready'] is False and report['live_journeys']=='NOT_RUN'
    before=list(s.native)
    with pytest.raises(ValueError):transition(s)
    assert s.native==before
    # Native workspaces/artifacts/caches are mutable after qualification;
    # deployment inspection cannot freeze all future production job contents.
    for kind in ('a0','dsh'):
        for folder in ('jobs','staging','cache'):
            (s.home/'workers'/kind/folder/'retained-job-output').write_bytes(b'OWNED MUTABLE JOB BYTES')
    with native_scope(s.home):assert entry.inspect(s.value,'f'*64)['state']=='DEPLOYMENTS_QUALIFIED'


@pytest.mark.parametrize('kind',['dsh','a0'])
def test_pending_is_not_admission_and_start_has_no_implicit_qualification(installed,kind):
    s=installed;c=s.product['runtime']['workers'][kind]
    with native_scope(s.home),pytest.raises(hr.HostUnavailable):hr.check_runtime(c,NS(state=NS(data_dir=s.home/'state')))
    with native_scope(s.home),pytest.raises(ValueError,match='qualification_required'):
        entry.start(s.value,'f'*64,budget=s.budget,input_path=s.deploy/'unused')
    assert not s.native


@pytest.mark.parametrize('bad',['original','source','profile','receipt','credential-ref','home','input','expired','partial'])
def test_original_tamper_or_expiry_refuses_before_native_observation(installed,bad):
    s=installed
    if bad=='original':(s.home/'preparation/harness/dsh-smoke.json').write_text('{}')
    elif bad=='source':s.value['project_files']['scripts/worker_qualification.py']='0'*64
    elif bad=='profile':(s.home/'config.yaml').write_text('foreign: true')
    elif bad=='receipt':(s.home/'workers/a0/runtime-receipt.json').write_text('{"ready":true}')
    elif bad=='credential-ref':s.value['credential_sources']={'FOREIGN':'SECRET_CANARY_NOT_AUTHORITY'}
    elif bad=='home':s.value['home']=str(s.deploy)
    elif bad=='input':(s.home/'workers/a0/runtime-input.json').write_text('{}')
    elif bad=='expired':s.budget.deadline=0
    else:(s.home/q.FOLDER).mkdir(mode=0o700,parents=True)
    with pytest.raises((ValueError,RuntimeError,OSError,KeyError)):transition(s)
    assert not s.native


@pytest.mark.parametrize('bad',['namespace','network','unit','stopped','web','replace'])
def test_current_native_refusal_retains_original_pending_and_no_replay(installed,bad):
    s=installed;s.bad=bad
    with pytest.raises((ValueError,RuntimeError,OSError)):transition(s)
    assert entry.read_json(s.home/entry.MARKER)==s.marker
    assert entry.read_json(s.home/'workers/a0/runtime-receipt.json')['ready'] is False
    assert entry.read_json(s.home/q.ORIGINAL)['marker']==s.marker
    before=list(s.native)
    with pytest.raises(ValueError,match='partial_qualification'):transition(s)
    assert s.native==before


@pytest.mark.parametrize('boundary',['dsh-receipt','config','marker'])
def test_lost_publication_is_fail_closed_original_archive_retained(installed,monkeypatch,boundary):
    s=installed;real=os.replace
    def lose(src,dst):
        if ((boundary=='dsh-receipt' and Path(dst)==s.home/'workers/dsh/runtime-receipt.json')
                or (boundary=='config' and Path(dst)==s.home/'config.yaml')
                or (boundary=='marker' and Path(dst)==s.home/entry.MARKER)):
            raise OSError('SYNTHETIC PUBLICATION LOSS')
        return real(src,dst)
    monkeypatch.setattr(os,'replace',lose)
    with pytest.raises(OSError):transition(s)
    assert entry.read_json(s.home/q.ORIGINAL)['marker']==s.marker
    before=list(s.native)
    with native_scope(s.home),pytest.raises((ValueError,RuntimeError,OSError)):
        entry.start(s.value,'f'*64,budget=s.budget,input_path=s.deploy/'unused')
    with pytest.raises((ValueError,RuntimeError,OSError)):transition(s)
    assert s.native==before


@pytest.mark.parametrize('bad',['archive','original-input','qualified-receipt','profile','credentials','proof','marker','plan','expired-policy'])
def test_qualified_consumer_detects_tamper(installed,bad):
    s=installed;transition(s)
    path={'archive':s.home/q.FOLDER/'original/workers/dsh/runtime-receipt.json',
          'original-input':s.home/'workers/dsh/inputs/dsh-local.json',
          'qualified-receipt':s.home/'workers/a0/runtime-receipt.json','profile':s.home/'config.yaml',
          'credentials':s.home/'.env','proof':s.home/q.PROOF,'marker':s.home/entry.MARKER,
          'plan':Path(s.plan_ref['path']),
          'expired-policy':Path(s.value['worker_install']['dsh']['web']['egress_evidence']['path'])}[bad]
    if path.exists():path.chmod(0o600)
    path.write_text('SYNTHETIC FOREIGN BYTES');path.chmod(0o600)
    with native_scope(s.home),pytest.raises((ValueError,RuntimeError,OSError,KeyError)):
        entry.inspect(s.value,'f'*64)


def test_native_pm_foreign_generation_refuses_before_any_probe(installed,monkeypatch):
    from pm import paths
    s=installed;monkeypatch.setattr(paths,'repo_root',lambda:s.deploy)
    with pytest.raises(ValueError,match='native_pm_qualification_owner'):transition(s)
    assert not s.native and not (s.home/q.FOLDER).exists()


def test_opaque_ready_report_cannot_replace_actual_native_plan(installed):
    s=installed;s.plan_ref=doc(s.deploy/'opaque-ready.json',{'ready':True,'accepted':True,'evidence':['SYNTHETIC_LABEL']})
    with pytest.raises((ValueError,RuntimeError,KeyError)):transition(s)
    assert not [x for x in s.native if x[0]=='a0']


def test_native_control_timeout_keeps_inherited_outer_budget():
    r=a0.Runtime.__new__(a0.Runtime);calls=[];r.budget=lambda:0.25
    r.runner=lambda argv,timeout:calls.append((argv,timeout)) or 'SYNTHETIC OBSERVATION'
    assert r.docker('inspect','f'*64,timeout=10)=='SYNTHETIC OBSERVATION'
    assert calls[0][1]==0.25
    r.budget=lambda:0
    with pytest.raises(RuntimeError,match='budget_exhausted'):r.docker('inspect','f'*64)
    assert len(calls)==1


@pytest.mark.parametrize('entrypoint',['_stop','stop'])
def test_expired_probe_budget_preserves_existing_stop_only_checks(entrypoint):
    r=a0.Runtime.__new__(a0.Runtime);calls=[];expired=lambda:0;r.budget=expired
    r.runner=lambda argv,timeout:calls.append((argv,timeout)) or 'SYNTHETIC STOP BOUNDARY'
    def existing_checks(*args,**kw):
        return r.docker('inspect','f'*64,timeout=8)
    r._stop_checked=existing_checks;r._stop_native=existing_checks
    result=r._stop({}) if entrypoint=='_stop' else r.stop()
    assert result=='SYNTHETIC STOP BOUNDARY' and calls[0][1]==8
    assert r.budget is expired
    with pytest.raises(RuntimeError,match='budget_exhausted'):r.docker('inspect','f'*64)
    assert len(calls)==1


def test_public_prepared_package_requires_no_native_import_or_adoption(installed,monkeypatch):
    import builtins
    s=installed;real=builtins.__import__
    def no_native(name,*args,**kwargs):
        if name=='hermes_constants' or name.startswith('hermes_cli'):
            raise AssertionError('Public bootstrap imported native before selecting PM')
        return real(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',no_native)
    assert workers.installed_product(s.value,s.home)==s.product
    assert not s.native


@pytest.mark.parametrize('changed',[False,True])
def test_normal_start_consumes_exact_qualified_runtime_before_native_effects(installed,monkeypatch,changed):
    from scripts import friday_start
    from hermes_cli import source_build
    s=installed;transition(s);calls=[]
    with native_scope(s.home):product=workers.installed_product(s.value,s.home)
    value=dict(s.value,product=product)
    if changed:product['runtime']['workers']['a0']['budget_seconds']+=1
    monkeypatch.setattr(source_build,'source_product_current',lambda *a:calls.append(a) or False)
    before=list(s.native)
    reason='native_start_runtime_generation_changed' if changed else 'native_frontend_freshness_not_verified'
    with native_scope(s.home),pytest.raises(ValueError,match=reason):
        friday_start.prerequisites(value,s.budget)
    assert bool(calls) is (not changed) and s.native==before
    assert product['runtime']['workers']['a0']['a0']['capability'] is None


@pytest.mark.parametrize('field',['owner_slot','deployment','web','git_metadata','code_sha256','network','deadline_unix'])
def test_pinned_but_foreign_native_plan_is_not_readiness(installed,field):
    s=installed;p=copy.deepcopy(s.plan)
    if field=='owner_slot':p[field]='astra'
    elif field=='deadline_unix':p[field]=0
    elif field=='network':p[field]='none'
    elif field=='code_sha256':p[field]='0'*64
    else:p[field]={}
    s.plan_ref=doc(s.deploy/'foreign-plan.json',p)
    with pytest.raises((ValueError,RuntimeError,KeyError)):transition(s)
    assert not [x for x in s.native if x[0]=='a0']


def test_public_entry_forwards_exact_plan_and_original_deadline_without_new_install(installed,monkeypatch):
    from scripts import install_containment
    s=installed;original=s.budget.deadline
    class Custody:
        def __init__(self,pin,budget,env):assert budget.deadline==original
        def run(self,argv,cwd,**kw):return os.sys.executable,{}
    monkeypatch.setattr(install_containment,'Containment',Custody)
    source=s.deploy/'input.json';doc(source,s.value)
    # Bind this synthetic fixture marker to actual current input bytes.
    marker=entry.read_json(s.home/entry.MARKER);h=pin(source)['sha256'];marker['input_sha256']=h
    marker['original_attempt']['input_sha256']=h;doc(s.home/entry.MARKER,marker)
    receipt=entry.read_json(s.home/'preparation/a0-service.receipt.json');receipt['original_attempt']=marker['original_attempt'];doc(s.home/'preparation/a0-service.receipt.json',receipt)
    marker['a0_service_receipt_sha256']=pin(s.home/'preparation/a0-service.receipt.json')['sha256'];doc(s.home/entry.MARKER,marker)
    def execute(exe,argv,env):
        assert argv[3]=='qualify' and '--a0-plan' in argv and argv[argv.index('--a0-plan')+1]==s.plan_ref['path']
        assert float(argv[argv.index('--deadline')+1])==original
        raise RuntimeError('SYNTHETIC EXEC HANDOFF, NO LIVE EFFECT')
    monkeypatch.setattr(os,'execve',execute)
    with native_scope(s.home),pytest.raises(RuntimeError,match='SYNTHETIC EXEC'):
        entry.start(s.value,h,budget=s.budget,input_path=source,plan_ref=s.plan_ref,phase='qualify')
    assert not s.native


@pytest.mark.parametrize('bad', [None, 'memory', 'swap', 'cpu', 'tasks', 'unit', 'boot', 'expired', 'late'])
def test_scope_guard_checks_actual_caps_and_original_deadline_before_exec(bad):
    from pathlib import PurePosixPath
    import builtins
    guard = {'unit': 'friday-qualify-dsh-fixture.scope', 'memory_bytes': 1024,
             'cpu_percent': 200, 'tasks': 64, 'boot_id': 'fixture-boot', 'deadline': 10.0}
    group = '/user.slice/' + guard['unit']
    rows = {'/proc/sys/kernel/random/boot_id': 'fixture-boot', '/proc/self/cgroup': '0::' + group,
            '/sys/fs/cgroup'+group+'/memory.max': '1024', '/sys/fs/cgroup'+group+'/memory.swap.max': '0',
            '/sys/fs/cgroup'+group+'/cpu.max': '200000 100000', '/sys/fs/cgroup'+group+'/pids.max': '64'}
    changes = {'memory': ('memory.max', 'max'), 'swap': ('memory.swap.max', 'max'),
               'cpu': ('cpu.max', 'max 100000'), 'tasks': ('pids.max', 'max')}
    if bad in changes:
        leaf, value = changes[bad]; rows['/sys/fs/cgroup'+group+'/'+leaf] = value
    if bad == 'unit': rows['/proc/self/cgroup'] = '0::/foreign.scope'
    if bad == 'boot': rows['/proc/sys/kernel/random/boot_id'] = 'other-boot'
    ticks = iter([11.0,11.0] if bad == 'expired' else [1.0,11.0] if bad == 'late' else [1.0,2.0])
    class FakePath(PurePosixPath):
        def read_text(self): return rows[str(self)]
        def resolve(self): return self
    class Executed(Exception): pass
    calls=[]
    def execute(*args): calls.append(args); raise Executed()
    modules={'json':json, 'os':NS(environ={'PATH':'/usr/bin:/bin'},execve=execute),
             'sys':NS(argv=['guard',json.dumps(guard),'/usr/bin/bwrap','--fixture']),
             'time':NS(monotonic=lambda:next(ticks)), 'pathlib':NS(Path=FakePath)}
    context={'__builtins__':dict(vars(builtins),__import__=lambda name,*args:modules[name])}
    with pytest.raises(Executed if bad is None else AssertionError):
        exec(compile(q.DSH_SCOPE_GUARD,'scope-guard','exec'),context)
    assert len(calls)==(1 if bad is None else 0)


@pytest.mark.parametrize('phase',['probe','observe'])
def test_uncertain_a0_cleanup_reaches_public_custody_signal(installed,monkeypatch,phase):
    s=installed;Base=a0.Runtime
    class Boundary(Base):
        def probe(self):
            if phase=='probe': raise a0.RuntimeStopUnconfirmed('STOP_UNCONFIRMED')
            return super().probe()
        def observe(self):
            if phase=='observe': raise a0.RuntimeStopUnconfirmed('STOP_UNCONFIRMED')
            return super().observe()
    monkeypatch.setattr(a0,'Runtime',Boundary)
    with pytest.raises(dsh_prepare.StopUnconfirmed): transition(s)
    failure=entry.read_json(s.home/q.FOLDER/'failure.json')
    assert failure['state']=='STOP_UNCONFIRMED' and failure['retry_authorized'] is False
    assert failure['original_attempt']==s.marker['original_attempt']
    assert entry.read_json(s.home/entry.MARKER)==s.marker
    before=list(s.native)
    with pytest.raises(ValueError,match='partial_qualification'):transition(s)
    assert s.native==before
