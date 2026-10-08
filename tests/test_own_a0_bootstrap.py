"""Own setup producer/consumer join; native interfaces are explicit fixtures.

Signed operator/session/CAS, native private-home preparation, source identity,
initial producer, credential injection/removal, custody and result consumers
run as shipped. No native service, network, model or real key is executed.
"""
import copy
import json
from pathlib import Path
import time

import pytest
from test_normal_user_worker_join import normal_env, pending, fixture_native, action, prepare
from test_user_onboarding import env, home, row, activate, ident, grant, secrets
from friday_admin_controls import a0_bootstrap as bootstrap, host_runtime as hr, user_worker_join as join
from scripts.dsh_prepare import StopUnconfirmed
from test_worker_qualification import installed
from test_normal_worker_install import normal
from test_a0_service_install import service
from test_native_installer import install_input


def test_initial_setup_consumes_real_existing_a0_observer_without_prequalified_job_runtime(normal_env,monkeypatch):
    from scripts import worker_qualification as q
    from plugins.friday_rework import host_runtime as installed_hr
    original=q.a0_observe
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    monkeypatch.setattr(q,'a0_observe',original)
    monkeypatch.setattr(installed_hr,'a0_runtime_module',lambda c:e.native_fixture)
    original_check=hr.check_a0_runtime
    def after_qualification(*args):
        assert (home(e)/join.PROOF).exists(), 'circular ordinary job admission before own qualification'
        state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
        assert state['phase']=='STOPPED' and state['settlement']['keys']=='REMOVED'
        return original_check(*args)
    monkeypatch.setattr(hr,'check_a0_runtime',after_qualification)
    result=action(e,'qualify')
    assert result['can_activate'] and calls==['dsh']
    assert e.native_fixture.effect_calls==['READONLY_PREFLIGHT','ROUTE','START','STOP','RETIRE_STOPPED_PROBE']
    state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
    assert state['phase']=='STOPPED' and state['settlement']['keys']=='REMOVED'
    assert not e.native_fixture.owned_running and (Path(json.loads((home(e)/bootstrap.FOLDER/'original.json').read_text())['association']['workspace_reference'])/'native-fixture/usr/.env').read_bytes()==b''
    assert (Path(json.loads((home(e)/bootstrap.FOLDER/'original.json').read_text())['association']['workspace_reference'])/'native-fixture/usr/web/secret.env').read_bytes()==b''
    proof=json.loads((home(e)/join.PROOF).read_text())
    assert proof['per_job_authority']=='NOT_GRANTED' and proof['workers']['a0']['plan']['path']==str(path)
    assert proof['bootstrap_custody']['original']['path']==str(home(e)/bootstrap.FOLDER/'original.json')


@pytest.mark.parametrize('code',['native_registration_missing','a0_route_native_deadline_unavailable',
    'foreign_or_active_daemon_blocks_route','kernel_namespace_not_admitted'])
def test_unavailable_native_authority_is_pending_before_claim_start_or_observers(normal_env,monkeypatch,code):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    def refused(*args,**kw):raise RuntimeError(code)
    monkeypatch.setattr(e.native_fixture,'route_preflight',refused)
    result=action(e,'qualify')
    assert result['state']=='DISABLED_OWN_A0_NATIVE_PREREQUISITES_PENDING'
    assert calls==[] and e.native_fixture.effect_calls==[]
    assert not (home(e)/bootstrap.FOLDER).exists() and not path.exists() and not (home(e)/join.FOLDER).exists()


def test_missing_own_credentials_never_borrows_process_or_operator_values(normal_env,monkeypatch):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    keys=home(e)/'.env'
    keys.write_text('\n'.join(line for line in keys.read_text().splitlines()
        if not line.startswith('SEARXNG_SECRET='))+'\n')
    monkeypatch.setenv('FRIDAY_EMBEDDINGS_API_KEY','ambient-key-not-owned')
    monkeypatch.setenv('SEARXNG_SECRET','ambient-'+('a'*64))
    from hermes_cli.friday_user_scope import ScopeDenied
    # Missing a base onboarding credential is rejected even before the
    # native producer; ambient/operator keys cannot repair that ownership.
    with pytest.raises(ScopeDenied):action(e,'qualify')
    assert e.native_fixture.effect_calls==[] and calls==[] and not (home(e)/bootstrap.FOLDER).exists()


def test_two_users_receive_distinct_probes_clocks_native_owners_and_custody(normal_env,monkeypatch):
    e=normal_env;originals=[]
    for uid in ('1','2'):
        pending(e,uid);calls,_=fixture_native(e,monkeypatch,uid)
        assert action(e,'qualify',uid)['can_activate']
        v=json.loads((home(e,uid)/bootstrap.FOLDER/'original.json').read_text());originals.append(v)
        assert v['binding']['user_id']==uid and v['association']['owner']['user_id']==uid
        assert v['association']['owner']['profile']=='user-'+uid
        assert v['association']['owner']['bot_id']=='bot-A'
        assert Path(v['association']['workspace_reference']).is_relative_to(home(e,uid)/'workers/a0/jobs')
        assert v['retry_authorized'] is False and v['seconds']==215
        assert 0<time.monotonic()-v['acceptance']['accepted_monotonic_ns']/1e9<215
        assert v['deadline_monotonic']==pytest.approx(v['acceptance']['accepted_monotonic_ns']/1e9+215)
        assert calls==['a0','dsh'] and not e.native_fixture.owned_running
    assert originals[0]['association']['existing_task_id']!=originals[1]['association']['existing_task_id']
    assert originals[0]['preparations']!=originals[1]['preparations']


def test_lost_start_reply_stops_exact_custody_and_blocks_any_duplicate(normal_env,monkeypatch):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    original=e.native_fixture.Runtime.start
    def lost(self,*args,**kw):
        original(self,*args,**kw)
        raise RuntimeError('explicit fixture: reply lost after create/start')
    monkeypatch.setattr(e.native_fixture.Runtime,'start',lost)
    with pytest.raises(RuntimeError):action(e,'qualify')
    assert e.native_fixture.effect_calls==['READONLY_PREFLIGHT','ROUTE','START','STOP','RETIRE_STOPPED_PROBE']
    assert not e.native_fixture.owned_running and calls==[]
    state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
    assert state['phase']=='FAILED_STOPPED_NO_REPLAY' and state['created']['container_id']=='e'*64
    before=list(e.native_fixture.effect_calls)
    with pytest.raises(hr.HostUnavailable):action(e,'qualify')
    assert e.native_fixture.effect_calls==before and not (home(e)/join.PROOF).exists()


def test_uncertain_stop_never_publishes_readiness_or_restarts(normal_env,monkeypatch):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    def unknown(self):raise RuntimeError('explicit fixture: stop outcome unconfirmed')
    monkeypatch.setattr(e.native_fixture.Runtime,'stop',unknown)
    with pytest.raises(StopUnconfirmed):action(e,'qualify')
    state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
    assert state['phase']=='STOP_UNCONFIRMED' and state['settlement'] is None
    assert (Path(json.loads((home(e)/bootstrap.FOLDER/'original.json').read_text())['association']['workspace_reference'])/'native-fixture/usr/.env').read_bytes()
    assert calls==['a0'] and not (home(e)/join.PROOF).exists()
    before=list(e.native_fixture.effect_calls)
    with pytest.raises(hr.HostUnavailable):action(e,'qualify')
    assert e.native_fixture.effect_calls==before and not row(e)['enabled']


def test_partial_key_preparation_retains_cleanup_uncertainty_before_create(normal_env,monkeypatch):
    # The alias module is the actual protected plugin's adapter package.
    from friday_admin_controls.adapters import a0_config as owning_config
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    original=owning_config.prepare_web_keys
    def partial(*args,**kw):
        original(*args,**kw)
        raise OSError('explicit fixture: persistence reply lost after private web key write')
    monkeypatch.setattr(owning_config,'prepare_web_keys',partial)
    with pytest.raises(StopUnconfirmed):action(e,'qualify')
    state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
    assert state['phase']=='STOP_UNCONFIRMED' and state['created'] is None
    assert calls==[] and not (home(e)/join.PROOF).exists()
    assert (Path(json.loads((home(e)/bootstrap.FOLDER/'original.json').read_text())['association']['workspace_reference'])/'native-fixture/usr/web/secret.env').read_bytes()


@pytest.mark.parametrize('changed',['generation','preparation','plan','settlement','source'])
def test_changed_bootstrap_owner_revision_plan_stop_or_source_refuses_activation(normal_env,monkeypatch,changed):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    assert action(e,'qualify')['can_activate']
    if changed in ('generation','preparation'):
        p=home(e)/bootstrap.FOLDER/'original.json';v=json.loads(p.read_text())
        if changed=='generation':v['generation']+=1
        else:v['preparations']['a0']['sha256']='f'*64
        p.write_text(json.dumps(v))
    elif changed=='plan':
        v=json.loads(path.read_text());v['association_binding']['owner']['user_id']='other-user';path.write_text(json.dumps(v))
    elif changed=='settlement':
        p=home(e)/bootstrap.FOLDER/'state.json';v=json.loads(p.read_text());v['settlement']['keys']='PREPARED';p.write_text(json.dumps(v))
    else:monkeypatch.setattr(bootstrap,'_source',lambda:{'path':str(home(e)/'other-code'),'sha256':'f'*64})
    try:result=activate(e);assert not result['enabled']
    except (ValueError,PermissionError,RuntimeError,KeyError):pass
    assert not row(e)['enabled'] and not e.native_fixture.owned_running and calls==['a0','dsh']


def test_revoked_operator_during_route_preparation_stops_without_launch(normal_env,monkeypatch):
    e=normal_env;pending(e);calls,path=fixture_native(e,monkeypatch)
    original=e.native_fixture.prepare_route
    def revoked(*args,**kw):
        result=original(*args,**kw)
        e.admin.set_user('default',**ident(),enabled=False,role='user')
        return result
    monkeypatch.setattr(e.native_fixture,'prepare_route',revoked)
    with pytest.raises(Exception):action(e,'qualify')
    assert e.native_fixture.effect_calls==['READONLY_PREFLIGHT','ROUTE']
    assert calls==[] and not e.native_fixture.owned_running and not (home(e)/join.PROOF).exists()
    state=json.loads((home(e)/bootstrap.FOLDER/'state.json').read_text())
    assert state['phase']=='FAILED_STOPPED_NO_REPLAY' and state['settlement']['route']['status']=='STOP_CONFIRMED'


@pytest.mark.parametrize('bad',[None,'active','infinite','prior-request','resource','tool','clock'])
def test_actual_native_readonly_preflight_preserves_registration_resources_clock_and_exclusivity(tmp_path,monkeypatch,bad):
    """The real preflight/helpers; only native systemd/cgroup observations fake."""
    from scripts import a0_runtime as m
    from types import SimpleNamespace
    import hashlib
    root=tmp_path/'native-preflight';root.mkdir(mode=0o700)
    tools={}
    for name in ('dockerd','rootlesskit','slirp4netns','nft','nsenter'):
        path=root/name;path.write_text('EXPLICIT OFFLINE EXECUTABLE, NEVER EXECUTED');path.chmod(0o500);tools[name]=path
    docker=root/'docker';docker.write_text('NEVER EXECUTED');docker.chmod(0o500)
    monkeypatch.setattr(m,'DOCKER',docker)
    l={'ROOT':root,'INSTALLED_UNIT':root/'installed.service','SERVICE_GROUP':'/user.slice/OFFLINE',
       'REQUEST':root/'request.json','GUARD':root/'guard.json','STATE':root/'state',
       'ENDPOINTS':m.LOCAL_ENDPOINTS,'tool_paths':lambda:tools}
    events=[];l['checked_unit_registration']=lambda:events.append('REGISTERED_SOURCE_CHECK')
    monkeypatch.setattr(m,'checked_launcher',lambda sha:l)
    monkeypatch.setattr(m,'native_supervisor',lambda:SimpleNamespace(observe=lambda row:SimpleNamespace(missing=True,quiescent=True)))
    monkeypatch.setattr(m,'cgroup_snapshot',lambda group:{'populated':False})
    fields={'ActiveState':'active' if bad=='active' else 'inactive','InvocationID':'','MainPID':'1' if bad=='active' else '0',
        'ControlGroup':'','FragmentPath':str(root/'supervisor'/m.DAEMON),'DropInPaths':'','Restart':'no',
        'KillMode':'control-group','SendSIGKILL':'yes','DelegateSubgroup':'dockerd','MemoryMax':str(20*1024**3),
        'TasksMax':'2048','CPUQuotaPerSecUSec':'8s','RuntimeMaxUSec':'infinity' if bad=='infinite' else '5s',
        'TimeoutStartUSec':'1s','TimeoutStopUSec':'1s','ActiveEnterTimestampMonotonic':'0'}
    def control(argv,timeout):
        assert argv[:4]==['/usr/bin/systemctl','--user','show',m.DAEMON] and timeout<=5
        events.append('READONLY_NATIVE_SHOW');return ''.join(k+'='+v+'\n' for k,v in fields.items())
    monkeypatch.setattr(m.Runtime,'_command',staticmethod(control))
    now=time.time();task='native-'+('a'*64)
    identity={'existing_task_id':task,'admission_hash':hashlib.sha256(task.encode()).hexdigest(),
        'owner':dict(bot_id='owned-bot',user_id='owned-user',profile='owned-profile',chat_id='',thread_id='',
                     message_id='',session_key='initial-probe',session_id='owned-setup'),
        'worker_kind':'a0','brief_sha256':'b'*64,'workspace_reference':str(root/'workspace'),
        'supervisor':{'scope':'user','unit':'friday-rework-worker-'+task[7:39]+'.service'},
        'created_at_unix':now,'budget_seconds':60,'deadline_unix':now+60}
    acceptance={'accepted_unix':now,'accepted_monotonic_ns':time.monotonic_ns(),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    if bad=='prior-request':l['REQUEST'].write_text('retained uncertain original request')
    if bad=='resource':fields['CPUQuotaPerSecUSec']='infinity'
    if bad=='tool':tools['nft'].chmod(0o700|0o020)
    if bad=='clock':acceptance['accepted_monotonic_ns']+=10**12
    native={'launcher':{'sha256':'c'*64},'docker':{'sha256':m.sha(docker)}}
    if bad is None:m.route_preflight(identity,acceptance,native,budget=lambda:35)
    else:
        with pytest.raises(m.RuntimeErrorBoundary):m.route_preflight(identity,acceptance,native,budget=lambda:35)
    assert not (root/'workspace').exists() and set(events)<= {'REGISTERED_SOURCE_CHECK','READONLY_NATIVE_SHOW'}


@pytest.mark.parametrize('bad',[None,'ordinary-job','running','replaced-unit','alive-descendant','missing-stop','lost-ack','unknown-sample'])
def test_actual_native_probe_retirement_requires_exact_cessation_and_never_forces_or_removes_state(tmp_path,monkeypatch,bad):
    from scripts import a0_runtime as m
    from types import SimpleNamespace
    from contextlib import nullcontext
    root=tmp_path/'retirement';root.mkdir(mode=0o700)
    state=root/'usr';state.mkdir(mode=0o700);artifact=state/'retain-inputs.txt';artifact.write_text('retained native setup inputs')
    r={'container_id':'d'*64,'invocation_id':'b'*32,'observations':[{'group':'/user.slice/OFFLINE','processes':[]} ]}
    if bad!='missing-stop':m.write_json(root/'stop.json',{'status':'STOP_CONFIRMED',
        'container_id':r['container_id'],'native_container_stopped':True,
        'current_sampling':'UNKNOWN' if bad=='unknown-sample' else 'OBSERVED_OR_ALREADY_EXITED'})
    boundary=m.Runtime.__new__(m.Runtime)
    boundary.p={'association_binding':{'owner':{'session_key':'ordinary-job' if bad=='ordinary-job' else 'own-profile-initial-probe'}}}
    expired=lambda:(_ for _ in ()).throw(ValueError('original clock exhausted'))
    boundary.budget=expired;boundary.directory=root;boundary.locked=lambda:nullcontext();boundary.receipt=lambda:r
    boundary.inspect=lambda row,**kw:{'State':{'Running':bad=='running','Pid':1 if bad=='running' else 0}}
    boundary.association=lambda row:row
    boundary.supervisor=SimpleNamespace(observe=lambda row:SimpleNamespace(quiescent=True,missing=False,
        invocation_id='c'*32 if bad=='replaced-unit' else r['invocation_id']))
    monkeypatch.setattr(m,'cessation',lambda sample:{'confirmed':bad!='alive-descendant'})
    calls=[]
    def docker(*argv,**kw):
        assert boundary.budget is None and kw=={'timeout':5};calls.append(argv)
        return 'ACK LOST' if bad=='lost-ack' else r['container_id']
    boundary.docker=docker
    if bad is None:
        result=boundary.retire_initial_probe()
        assert result['status']=='INITIAL_PROBE_RETIRED' and result['host_state_retained']
        assert result['image_retained'] and not result['volumes_removed']
    else:
        with pytest.raises((m.RuntimeErrorBoundary,OSError)):boundary.retire_initial_probe()
        assert not (root/'retirement.json').exists()
    assert calls==([('rm',r['container_id'])] if bad in (None,'lost-ack') else [])
    assert artifact.read_text()=='retained native setup inputs' and boundary.budget is expired


@pytest.mark.parametrize('bad',['expired','unavailable-credentials','multiple-accounts'])
def test_normal_install_default_producer_cannot_reset_clock_or_borrow_authority(installed,monkeypatch,bad):
    from test_native_installer import native_home
    from scripts import worker_qualification as q
    from plugins.friday_rework.a0_bootstrap import PrerequisitePending
    s=installed;before=copy.deepcopy(s.marker['original_attempt'])
    if bad=='expired':s.budget.deadline=time.monotonic()-1
    if bad=='multiple-accounts':
        # Declared product identity, never select an account behind the owner.
        from plugins.friday_rework import a0_bootstrap as owning
        value=copy.deepcopy(s.product);value['accounts'].append(dict(value['accounts'][0],account_id='other-owned-account'))
        with native_home(s.home),pytest.raises(PrerequisitePending):
            owning.installation_probe(value,s.home,before,s.budget,verify=lambda:None)
    else:
        with native_home(s.home),pytest.raises((PrerequisitePending,ValueError)):
            q.qualify(s.value,'f'*64,None,s.budget)
    assert not (s.home/q.FOLDER).exists() and not (s.home/bootstrap.FOLDER).exists()
    assert s.marker['original_attempt']==before and s.native==[]
