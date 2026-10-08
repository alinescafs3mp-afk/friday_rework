"""F1/F2/F3 through shipped ownership/installer consumers, offline native IO."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import time

import pytest
from test_own_a0_bootstrap import normal_env, env, installed, normal, service, install_input
from test_normal_user_worker_join import pending, fixture_native, action
from test_user_onboarding import home, row
from test_native_installer import native_home
from test_worker_qualification import probe
from scripts import a0_runtime as native, friday_install as entry, friday_native
from scripts import worker_install, worker_qualification as qualification
from scripts.dsh_prepare import StopUnconfirmed
from plugins.friday_rework import a0_bootstrap as install_bootstrap, host_runtime as install_hr
from plugins.friday_rework.adapters.a0_config import KEY_REFERENCES
from friday_admin_controls import a0_bootstrap as bootstrap, user_worker_join as join


def installer_transport(s, monkeypatch):
    """Only kernel/control IO substituted; real planner, qualifier and pins."""
    values = {n: 'synthetic-own-' + n for n in KEY_REFERENCES.values()}
    values['SEARXNG_SECRET'] = 'synthetic-' + 'x'*64
    p = s.home / '.env'; p.write_text(''.join(n+'='+v+'\n' for n,v in values.items())); p.chmod(0o600)
    events = []; network = copy.deepcopy(s.plan['network'])
    monkeypatch.setattr(install_bootstrap, 'a0_runtime_module', lambda c: native)
    def preflight(*args, budget): budget(); events.append('PREFLIGHT')
    def route(identity, acceptance, a, *, retain, budget):
        budget(); events.append('ROUTE')
        network['owner'] = a['owner_slot'] + ':' + identity['existing_task_id'] + '#1'
        network['labels']['friday.rework.owner'] = network['owner']
        source = Path(identity['workspace_reference']) / 'offline-route-stop.py'
        source.write_text("def stop_route(route, *, retain, container_id=None):\n"
                          " route['settlement']={'status':'STOP_CONFIRMED'}\n retain(route)\n")
        source.chmod(0o400)
        retain({'association':identity, 'acceptance':acceptance, 'pending':None,
                'network':network, 'settlement':None, 'stop_source':install_bootstrap.pin(source)})
    monkeypatch.setattr(native, 'route_preflight', preflight)
    monkeypatch.setattr(native, 'prepare_route', route)
    monkeypatch.setattr(native, 'current_network', lambda *a, **kw: copy.deepcopy(network))
    class Transport:
        def __init__(self, plan, *, budget):
            self.p = native.validate(plan, budget=budget); self.budget = budget
            self.root = Path(plan['association_binding']['workspace_reference']) / 'offline-native'
            self.receipt_path = self.root / 'native.json'; self.create_attempted = False
            self.known = entry.read_json(self.receipt_path) if self.receipt_path.exists() else None
            self.supervisor = NS(observe=lambda row:NS(missing=False,quiescent=not s.running,invocation_id='b'*32))
        def locked(self): return nullcontext()
        def association(self, r): return r
        def receipt(self): return self.known
        def start(self, path, sha, *, before_ui, on_created):
            self.budget(); events.append('START'); self.root.mkdir(mode=0o700)
            usr = self.root / 'usr'; usr.mkdir(mode=0o700); (usr/'web').mkdir(mode=0o700)
            (usr/'.env').write_text(''); (usr/'.env').chmod(0o600)
            before_ui(usr); self.create_attempted = True
            self.known = {'container_id':'e'*64,'invocation_id':'b'*32,
                          'plan_sha256':native.digest(self.p),'observations':[]}
            s.running = True; on_created(self.known); native.write_json(self.receipt_path,self.known)
        def inspect(self, r, **kw): return {'State':{'Running':s.running,'Pid':77 if s.running else 0}}
        def snapshot_container(self, obj):
            return {'group':'/user.slice/EXPLICIT-OFFLINE','populated':True,
                    'processes':[{'pid':77,'start_ticks':1}]}
        def docker(self, *args, **kw):
            assert args[0]=='exec'
            return json.dumps({'http':200,'gitinfo_present':True,'native_error_present':False})
        def probe(self): events.append('OBSERVE_A0'); return probe(self.p['deployment'])
        def observe(self):
            return {'running':s.running,'unit_quiescent':not s.running,'caps':{
                'memory.max':str(native.MEMORY),'memory.swap.max':'0',
                'pids.max':str(native.PIDS),'cpu.max':'200000 100000'}}
        def check_web(self, cid):
            return {'status':'CURRENT_NATIVE_WEB_SERVICE_CHECKED','version':self.p['web']['version'],
                    'processes':[dict(name=n,pid=i+1,start=1,statename='RUNNING')
                                 for i,n in enumerate(('run_ui','run_searxng'))]}
        def check_network(self, **kw): return {'status':'CURRENT_LOCAL_NETWORK_CHECKED','id':network['id']}
        def stop(self):
            events.append('STOP'); s.running=False
            return {'status':'STOP_CONFIRMED','container_id':'e'*64,'native_container_stopped':True}
        def retire_initial_probe(self):
            assert not s.running; events.append('RETIRE')
            return {'status':'INITIAL_PROBE_RETIRED','container_id':'e'*64}
    s.running=False; monkeypatch.setattr(native,'Runtime',Transport)
    return events


def test_default_native_installer_producer_observer_settlement_and_consumers(installed, monkeypatch):
    s=installed; events=installer_transport(s,monkeypatch)
    original = copy.deepcopy(s.marker['original_attempt'])
    with native_home(s.home):
        result=friday_native.qualify(s.value,'f'*64,None,s.budget)
        assert result['state']=='DEPLOYMENTS_QUALIFIED' and result['per_job_authority']=='NOT_GRANTED'
        assert entry.inspect(s.value,'f'*64)['state']=='DEPLOYMENTS_QUALIFIED'
        product=worker_install.installed_product(s.value,s.home)
        for c in product['runtime']['workers'].values(): assert install_hr.deployment_health(c)==c
    assert events==['PREFLIGHT','ROUTE','START','OBSERVE_A0','STOP','RETIRE'] and not s.running
    assert len([v for v in s.native if v[0]=='dsh'])==5
    state=entry.read_json(s.home/install_bootstrap.FOLDER/'state.json')
    retained=entry.read_json(s.home/install_bootstrap.FOLDER/'original.json')
    assert retained['inherited_attempt']==original and retained['deadline_monotonic']<=original['deadline_mono']
    assert state['phase']=='STOPPED' and not state['sampling_uncertainty']
    assert state['settlement']['keys']=='REMOVED'
    keys=Path(state['key_directory']); assert (keys/'.env').read_bytes()==b''
    assert (keys/'web/secret.env').read_bytes()==b''
    proof=entry.read_json(s.home/qualification.PROOF)
    assert proof['bootstrap_custody']['settlement']==install_bootstrap.pin(s.home/install_bootstrap.FOLDER/'state.json')
    before=list(events)
    with native_home(s.home),pytest.raises(ValueError): friday_native.qualify(s.value,'f'*64,None,s.budget)
    assert events==before


@pytest.mark.parametrize('bad',['extra-root','extra-bootstrap','original','plan','uncertainty','symlink'])
def test_retained_installer_inventory_or_custody_tamper_never_grants_or_replays(installed,monkeypatch,bad):
    s=installed; events=installer_transport(s,monkeypatch)
    with native_home(s.home):friday_native.qualify(s.value,'f'*64,None,s.budget)
    folder=s.home/install_bootstrap.FOLDER
    if bad=='extra-root': (s.home/'workers/a0/foreign').mkdir(mode=0o700)
    elif bad=='extra-bootstrap': (folder/'foreign.json').write_text('{}')
    elif bad=='symlink':
        p=folder/'state.json'; p.rename(folder/'retained.json'); p.symlink_to(folder/'retained.json')
    else:
        p=s.home/install_bootstrap.PLAN if bad=='plan' else folder/('original.json' if bad=='original' else 'state.json')
        value=entry.read_json(p)
        if bad=='original':value['binding']['user_id']='foreign-owner'
        elif bad=='plan':value['association_binding']['owner']['user_id']='foreign-owner'
        else:value['sampling_uncertainty']=True
        p.write_text(json.dumps(value))
    before=list(events)
    with native_home(s.home),pytest.raises((ValueError,RuntimeError,PermissionError,OSError)):
        entry.inspect(s.value,'f'*64)
    with native_home(s.home),pytest.raises((ValueError,RuntimeError,PermissionError,OSError)):
        friday_native.qualify(s.value,'f'*64,None,s.budget)
    assert events==before and not s.running


@pytest.mark.parametrize('later_sample',[False,True])
def test_interrupted_descendant_history_stays_unknown_after_later_cleanup_sample(normal_env,monkeypatch,later_sample):
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch)
    cls=e.native_fixture.Runtime; snapshot=cls.snapshot_container; stop=cls.stop; samples=[]
    def interrupted(self,obj):
        samples.append('sample')
        if len(samples)==1:raise OSError('explicit offline interrupted historical sample')
        return snapshot(self,obj)
    def cleanup(self):
        if later_sample:self.snapshot_container(self.inspect(self.known))
        return stop(self)
    monkeypatch.setattr(cls,'snapshot_container',interrupted);monkeypatch.setattr(cls,'stop',cleanup)
    with pytest.raises(StopUnconfirmed):action(e,'qualify')
    state=entry.read_json(home(e)/bootstrap.FOLDER/'state.json')
    assert state['phase']=='STOP_UNCONFIRMED' and state['settlement'] is None and state['sampling_uncertainty']
    assert state['sample_attempts'][0]=={'index':0,'phase':'UNKNOWN','error':'OSError'}
    assert len(samples)==(2 if later_sample else 1)
    assert state['pending_sample'] is (not later_sample)
    assert 'STOP' in e.native_fixture.effect_calls and 'RETIRE_STOPPED_PROBE' not in e.native_fixture.effect_calls
    assert Path(state['key_directory'],'.env').read_bytes() and not e.native_fixture.owned_running
    assert not (home(e)/join.PROOF).exists() and calls==[] and not row(e)['enabled']
    original=entry.read_json(home(e)/bootstrap.FOLDER/'original.json'); before=list(e.native_fixture.effect_calls)
    with pytest.raises(RuntimeError):action(e,'qualify')
    assert before==e.native_fixture.effect_calls
    assert original==entry.read_json(home(e)/bootstrap.FOLDER/'original.json')


@pytest.mark.parametrize('bad',[None,'replaced','quiescent','missing','terminal','expired'])
def test_delayed_container_start_waits_only_for_exact_current_original_owner(normal_env,monkeypatch,bad):
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch)
    cls=e.native_fixture.Runtime; original=cls.inspect; observations=[]; contexts=[]
    constructor=cls.__init__
    def create(self,*args,**kw):
        constructor(self,*args,**kw); contexts.append(self)
        self.supervisor=NS(observe=lambda r:NS(missing=bad=='missing',quiescent=bad=='quiescent',
            invocation_id=('c' if bad=='replaced' else 'b')*32))
    def delayed(self,r,**kw):
        observations.append('inspect')
        if len(observations)<3:
            return {'State':{'Running':False,'Pid':0,'Status':'exited' if bad=='terminal' else 'created'}}
        return original(self,r,**kw)
    monkeypatch.setattr(cls,'__init__',create);monkeypatch.setattr(cls,'inspect',delayed)
    actual_sleep=bootstrap.time.sleep; probes=[]; init=bootstrap.InitialProbe.__init__
    def remember(self,*args,**kw):init(self,*args,**kw);probes.append(self)
    monkeypatch.setattr(bootstrap.InitialProbe,'__init__',remember)
    def pause(seconds):
        if bad=='expired':probes[-1].budget.deadline=time.monotonic()-1
        actual_sleep(seconds)
    monkeypatch.setattr(bootstrap.time,'sleep',pause)
    if bad is None:
        assert action(e,'qualify')['can_activate'] and len(observations)>=3 and calls==['a0','dsh']
    else:
        with pytest.raises((RuntimeError,TimeoutError,ValueError)):action(e,'qualify')
        assert calls==[] and not (home(e)/join.PROOF).exists()
    assert e.native_fixture.effect_calls.count('START')==1 and not e.native_fixture.owned_running


def test_real_observer_second_runtime_sample_error_remains_initial_owner_uncertainty(normal_env,monkeypatch):
    original_observer=qualification.a0_observe
    e=normal_env;pending(e);calls,_=fixture_native(e,monkeypatch)
    monkeypatch.setattr(qualification,'a0_observe',original_observer)
    monkeypatch.setattr(install_hr,'a0_runtime_module',lambda c:e.native_fixture)
    cls=e.native_fixture.Runtime; instances=[]; samples=[]
    ctor=cls.__init__; snapshot=cls.snapshot_container; observe=cls.observe; stop=cls.stop
    def construct(self,*args,**kw):ctor(self,*args,**kw);instances.append(self)
    def interrupted(self,obj):
        samples.append(instances.index(self))
        if len(instances)>1 and self is instances[1]:raise OSError('explicit observer historical sample interrupted')
        return snapshot(self,obj)
    def sample_observer(self):self.snapshot_container(self.inspect(self.known));return observe(self)
    def later_cleanup(self):self.snapshot_container(self.inspect(self.known));return stop(self)
    monkeypatch.setattr(cls,'__init__',construct);monkeypatch.setattr(cls,'snapshot_container',interrupted)
    monkeypatch.setattr(cls,'observe',sample_observer);monkeypatch.setattr(cls,'stop',later_cleanup)
    with pytest.raises(StopUnconfirmed):action(e,'qualify')
    state=entry.read_json(home(e)/bootstrap.FOLDER/'state.json')
    assert len(instances)==2 and samples==[0,1,0]
    assert [v['phase'] for v in state['sample_attempts']]==['OBSERVED','UNKNOWN','OBSERVED']
    assert state['sampling_uncertainty'] and not state['pending_sample']
    assert state['phase']=='STOP_UNCONFIRMED' and state['settlement'] is None
    assert Path(state['key_directory'],'.env').read_bytes()
    assert 'RETIRE_STOPPED_PROBE' not in e.native_fixture.effect_calls and not e.native_fixture.owned_running
    assert calls==[] and not (home(e)/join.PROOF).exists() and not row(e)['enabled']
