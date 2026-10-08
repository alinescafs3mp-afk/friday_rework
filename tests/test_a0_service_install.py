"""Real installer publication/custody, explicitly fake native manager responses.

No service registration/reload/start, namespace, network or secret effect runs.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from scripts import a0_prepare as prep, a0_runtime as runtime, rootless_docker_launch as launcher
from scripts import friday_install as entry, friday_native as native, dsh_prepare
from scripts.install_containment import Budget
from plugins.friday_rework.adapters.a0_profile import legacy_profile
from test_native_installer import install_input


@pytest.fixture
def service(install_input, tmp_path, monkeypatch):
    value = copy.deepcopy(install_input)
    home = Path(value['home']); home.mkdir(mode=0o700)
    deploy = tmp_path / 'deployment'; deploy.mkdir(mode=0o700)
    root = deploy / '.runtime/rootless-docker'; root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
    for name in ('supervisor', 'config'): (root / name).mkdir(mode=0o700)
    registered = deploy / 'systemd'; registered.mkdir(mode=0o700)
    state = deploy / 'state'; state.mkdir(mode=0o700)
    custody = deploy / 'runtime'; custody.mkdir(mode=0o700)
    docker = deploy / 'docker'; docker.write_text('SYNTHETIC DOCKER PIN; NEVER EXECUTED\n'); docker.chmod(0o700)
    config = root / 'config/daemon.json'; config.write_text('synthetic daemon input\n'); config.chmod(0o600)
    script = deploy / '.runtime/docker-29.8.2/docker-rootless-extras/dockerd-rootless.sh'
    script.parent.mkdir(mode=0o700, parents=True); script.write_text('NEVER EXECUTED\n'); script.chmod(0o700)
    # Git worktrees may be group-writable; the native loader intentionally
    # accepts only protected source. Copy the exact reviewed bytes inside the
    # private fixture rather than bypassing that loader or changing a checkout.
    profile_source = deploy / 'a0_profile.py'
    raw = (entry.ROOT / 'plugins/friday_rework/adapters/a0_profile.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == value['project_files']['plugins/friday_rework/adapters/a0_profile.py']
    profile_source.write_bytes(raw); profile_source.chmod(0o600)
    monkeypatch.setattr(runtime, 'PROFILE_SOURCE', profile_source)
    monkeypatch.setattr(runtime, 'PROJECT', deploy)
    monkeypatch.setattr(runtime, 'RUNTIME', custody)
    monkeypatch.setattr(runtime, 'LAUNCHER', root / 'launch.py')
    monkeypatch.setattr(runtime, 'DOCKER', docker)
    monkeypatch.setattr(launcher, 'ROOT', root)
    monkeypatch.setattr(launcher, 'INSTALLED_UNIT', registered / runtime.DAEMON)
    monkeypatch.setattr(launcher, 'REQUEST', root / 'config/local-route.json')
    monkeypatch.setattr(launcher, 'GUARD', state / 'route-guard.json')
    monkeypatch.setattr(launcher, 'STATE', state)
    monkeypatch.setattr(launcher, 'CONFIG_SHA256', hashlib.sha256(config.read_bytes()).hexdigest())
    monkeypatch.setattr(launcher, 'SCRIPT_SHA256', hashlib.sha256(script.read_bytes()).hexdigest())
    profile = legacy_profile()
    value['product']['a0_deployment'] = copy.deepcopy(profile)
    value['product']['inference'].update(base_url=profile['chat']['endpoint'], model='dispatcher',
        key_env='FRIDAY_LLM_API_KEY', context=40960, max_input=36000)
    pin = {'path': str(deploy / 'unqueried-fixture'), 'sha256': 'a'*64}
    value['product']['runtime'] = dict(enabled=True, runtime_profile='default', runtime_home=str(home),
        workspace_root=str(deploy / 'jobs'), staging_root=str(deploy / 'staging'),
        cache_roots=[str(deploy / 'cache')], budget_seconds=300, max_file_bytes=1024, max_total_bytes=4096,
        runtime_receipt=pin, a0=dict(runtime={'path':str(home/'worker-runtime-source/scripts/a0_runtime.py'),
            'sha256':value['project_files']['scripts/a0_runtime.py']},
            launcher={'path':str(runtime.LAUNCHER), 'sha256':value['project_files']['scripts/rootless_docker_launch.py']},
            daemon_unit={'path':str(root/'supervisor'/runtime.DAEMON),'sha256':value['project_files'][prep.SERVICE_SOURCE]},
            docker={'path':str(docker),'sha256':hashlib.sha256(docker.read_bytes()).hexdigest()},
            policy=pin, owner_slot='sol', capability=None,
            git_metadata={'source':str(deploy/'metadata'), 'manifest_sha256':'b'*64},
            expected_files=[{'logical_name':'result.txt','media_type':'text/plain'}], deployment=profile))
    budget = Budget(1800)
    claim = entry.partial_claim('b'*64, budget); entry.publish(home / entry.MARKER, claim)
    native.stage_worker_runtime(value, home)
    fields = {name:'' for name in ('Id','LoadState','ActiveState','SubState','MainPID','ControlPID',
        'InvocationID','ControlGroup','FragmentPath','DropInPaths','Restart','KillMode','SendSIGKILL',
        'DelegateSubgroup','MemoryMax','TasksMax','CPUQuotaPerSecUSec','RuntimeMaxUSec',
        'TimeoutStartUSec','TimeoutStopUSec')}
    fields.update(Id=runtime.DAEMON, LoadState='not-found', ActiveState='inactive', SubState='dead',
                  MainPID='0', ControlPID='0')
    s = SimpleNamespace(value=value, home=home, root=root, deploy=deploy, budget=budget, claim=claim,
                        fields=fields, calls=[], effect_hook=None, lost=None)
    def fake_run(argv, cwd, **kw):
        assert argv[0] == '/usr/bin/systemctl' and cwd == deploy
        assert 0 < kw['timeout'] <= 10 and kw['deadline'] == budget.deadline
        assert kw['env'] is runtime.ENV and kw['log'].parent == home/'preparation'
        s.calls.append(list(argv))
        phase = 'show' if 'show' in argv else 'link' if 'link' in argv else 'reload'
        out = ''
        if phase == 'link':
            assert '--no-reload' in argv and argv[-1] == str(root/'supervisor'/runtime.DAEMON)
            launcher.INSTALLED_UNIT.symlink_to(argv[-1])
        elif phase == 'reload':
            assert argv == ['/usr/bin/systemctl','--user','daemon-reload']
            fields.update(LoadState='loaded', FragmentPath=str(launcher.INSTALLED_UNIT), Restart='no',
                KillMode='control-group', SendSIGKILL='yes', DelegateSubgroup='dockerd',
                MemoryMax=str(20*1024**3), TasksMax='2048', CPUQuotaPerSecUSec='8s',
                RuntimeMaxUSec='2min', TimeoutStartUSec='45s', TimeoutStopUSec='20s')
        else: out = '\n'.join(k+'='+v for k,v in fields.items())+'\n'
        if s.effect_hook: s.effect_hook(phase)
        if s.lost == phase: raise RuntimeError('synthetic lost manager acknowledgement')
        return out, dict(returncode=0, elapsed_seconds=.001, timeout=False, reaped=True,
            stdout_sha256=hashlib.sha256(out.encode()).hexdigest(), stderr_sha256=hashlib.sha256(b'').hexdigest(),
            stdout_bytes=len(out), stderr_bytes=0, reason='command_succeeded')
    monkeypatch.setattr(dsh_prepare, 'run', fake_run)
    return s


def install(s): return prep.install_service(s.value, s.home, s.budget)


def test_ordinary_source_inventory_unit_launcher_consumer_and_effect_plan(service):
    s=service; plan=prep.service_plan(s.value,s.home)
    assert plan['required'] and plan['native_limits']==dict(runtime_seconds=120,start_seconds=45,stop_seconds=20)
    assert plan['whole_user_manager_reload'] is True and plan['enable'] is plan['start'] is False
    assert plan['source_files'][prep.SERVICE_SOURCE]==launcher.UNIT_SHA256
    assert not s.calls and not runtime.LAUNCHER.exists()


def test_ordinary_install_registers_exact_inactive_source_once_with_original_clock(service):
    s=service; result=install(s)
    assert result['state']=='REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
    assert result['original_attempt']==s.claim and result['runtime_acceptance']=='NOT_ACCEPTED'
    assert runtime.LAUNCHER.read_bytes()==(prep.ROOT/'scripts/rootless_docker_launch.py').read_bytes()
    assert runtime.LAUNCHER.stat().st_mode&0o777==0o400
    assert sum('link' in c for c in s.calls)==sum('daemon-reload' in c for c in s.calls)==1
    assert all('start' not in c and 'enable' not in c for c in s.calls)
    assert not launcher.REQUEST.exists() and not launcher.GUARD.exists()
    assert prep.service_receipt_checked(s.value,s.home,original_attempt=s.claim)==result
    prior=list(s.calls)
    with pytest.raises(ValueError,match='requires_reconciliation'):install(s)
    assert s.calls==prior


@pytest.mark.parametrize('field,value',[('ActiveState','active'),('SubState','failed'),('MainPID','23'),
    ('ControlPID','42'),('InvocationID','f'*32),('ControlGroup','/foreign'),('DropInPaths','/foreign/drop.conf'),
    ('LoadState','loaded'),('FragmentPath','/foreign/unit')])
def test_active_foreign_or_previous_native_unit_refuses_before_publication(service,field,value):
    s=service;s.fields[field]=value
    with pytest.raises(ValueError):install(s)
    assert not runtime.LAUNCHER.exists() and not (s.home/'preparation/a0-service.intent.json').exists()
    assert all('link' not in c and 'daemon-reload' not in c for c in s.calls)


@pytest.mark.parametrize('name',['launcher','unit','registration','request','guard','namespace','other_state'])
def test_existing_sources_requests_guards_namespaces_are_preserved_without_adoption(service,name):
    s=service
    paths={'launcher':runtime.LAUNCHER,'unit':s.root/'supervisor'/runtime.DAEMON,
        'registration':launcher.INSTALLED_UNIT,'request':launcher.REQUEST,'guard':launcher.GUARD,
        'namespace':launcher.STATE/'rootlesskit','other_state':launcher.STATE/'foreign.sock'}
    path=paths[name];path.write_text('preserved foreign/old state\n');path.chmod(0o600)
    with pytest.raises(ValueError):install(s)
    assert path.read_text()=='preserved foreign/old state\n'
    assert not (s.home/'preparation/a0-service.intent.json').exists()
    assert all('link' not in c and 'daemon-reload' not in c for c in s.calls)


@pytest.mark.parametrize('phase',['link','reload'])
def test_lost_registration_reload_ack_is_retained_unknown_never_replayed(service,phase):
    s=service;s.lost=phase
    with pytest.raises(dsh_prepare.StopUnconfirmed):install(s)
    failure=entry.read_json(s.home/'preparation/a0-service.failure.json')
    assert failure['original_attempt']==s.claim and failure['resume_allowed'] is False
    assert failure['state']=='STOP_UNCONFIRMED_REGISTRATION_REQUIRES_RECONCILIATION'
    assert runtime.LAUNCHER.exists() and launcher.INSTALLED_UNIT.is_symlink()
    assert not (s.home/'preparation/a0-service.receipt.json').exists()
    prior=list(s.calls)
    with pytest.raises(ValueError,match='requires_reconciliation'):install(s)
    assert s.calls==prior


@pytest.mark.parametrize('field,value',[('RuntimeMaxUSec','infinity'),('RuntimeMaxUSec','121s'),
    ('TimeoutStartUSec','infinity'),('TimeoutStopUSec','21s'),('MemoryMax','max'),('TasksMax','4096'),
    ('CPUQuotaPerSecUSec','9s'),('DelegateSubgroup','foreign'),('KillMode','process')])
def test_effective_deadline_or_native_control_drift_cannot_be_accepted(service,field,value):
    s=service
    def drift(phase):
        if phase=='reload':s.fields[field]=value
    s.effect_hook=drift
    with pytest.raises(dsh_prepare.StopUnconfirmed):install(s)
    assert (s.home/'preparation/a0-service.failure.json').exists()
    assert not (s.home/'preparation/a0-service.receipt.json').exists()


@pytest.mark.parametrize('where',['stage','launcher_after_link','unit_after_link','claim'])
def test_stale_source_or_original_claim_refuses_and_preserves_uncertainty(service,where):
    s=service
    if where=='stage':(s.home/'worker-runtime-source/scripts/rootless_docker_launch.py').chmod(0o600);(s.home/'worker-runtime-source/scripts/rootless_docker_launch.py').write_text('foreign bytes')
    elif where=='claim':
        claim=dict(s.claim,deadline_mono=s.budget.deadline+1)
        (s.home/entry.MARKER).write_text(json.dumps(claim))
    else:
        def drift(phase):
            if phase=='link':
                p=runtime.LAUNCHER if where=='launcher_after_link' else s.root/'supervisor'/runtime.DAEMON
                p.chmod(0o600);p.write_text('foreign bytes')
        s.effect_hook=drift
    with pytest.raises((ValueError,dsh_prepare.StopUnconfirmed)):install(s)
    assert not (s.home/'preparation/a0-service.receipt.json').exists()
    assert all('daemon-reload' not in c for c in s.calls)


def test_exhausted_original_budget_admits_no_native_or_publication(service):
    s=service;s.budget.deadline=time.monotonic()-1
    with pytest.raises(ValueError,match='original_install_budget_exhausted'):install(s)
    assert not s.calls and not runtime.LAUNCHER.exists()


def test_budget_expiring_after_link_keeps_actual_registration_without_retry(service):
    s=service
    def expire(phase):
        if phase=='link':s.budget.deadline=time.monotonic()-1
    s.effect_hook=expire
    with pytest.raises(dsh_prepare.StopUnconfirmed):install(s)
    assert launcher.INSTALLED_UNIT.is_symlink()
    assert (s.home/'preparation/a0-service.failure.json').exists()
    assert all('daemon-reload' not in c for c in s.calls)


@pytest.mark.parametrize('change',['missing_profile','unsupported_endpoint','budget','unit_pin','launcher_pin','runtime_path','docker_pin'])
def test_unsupported_or_unpinned_config_refuses_before_any_effect(service,change):
    s=service;c=s.value['product']['runtime']['a0']
    if change=='missing_profile':del c['deployment']
    elif change=='unsupported_endpoint':
        c['deployment']['chat']['endpoint']='http://192.168.2.9:8001/v1'
        s.value['product']['a0_deployment']=copy.deepcopy(c['deployment'])
    elif change=='budget':s.value['product']['runtime']['budget_seconds']=214
    elif change=='unit_pin':c['daemon_unit']['sha256']='f'*64
    elif change=='launcher_pin':c['launcher']['sha256']='f'*64
    elif change=='docker_pin':c['docker']['sha256']='f'*64
    else:c['runtime']['path']='/foreign/source.py'
    with pytest.raises((ValueError,RuntimeError)):install(s)
    assert not s.calls and not runtime.LAUNCHER.exists()


def test_missing_unit_deadline_even_rehashed_launcher_cannot_stage(tmp_path):
    source=tmp_path/'source';source.mkdir(mode=0o700);pins={}
    for name in prep.SERVICE_FILES:
        p=source/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        data=(prep.ROOT/name).read_bytes()
        if name==prep.SERVICE_SOURCE:data=data.replace(b'RuntimeMaxSec=120s\n',b'')
        p.write_bytes(data);p.chmod(0o600);pins[name]=hashlib.sha256(data).hexdigest()
    p=source/'scripts/rootless_docker_launch.py'
    p.write_text(p.read_text().replace(launcher.UNIT_SHA256,pins[prep.SERVICE_SOURCE]))
    pins['scripts/rootless_docker_launch.py']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='a0_service_native_boundary_changed'):prep.service_sources(pins,root=source)


def effective_launcher_fields():
    return dict(RuntimeMaxUSec='2min', TimeoutStartUSec='45s', TimeoutStopUSec='20s',
        Restart='no', KillMode='control-group', SendSIGKILL='yes', DelegateSubgroup='dockerd',
        MemoryMax=str(20*1024**3), TasksMax='2048', CPUQuotaPerSecUSec='8s', DropInPaths='',
        MainPID=str(os.getpid()), InvocationID='c'*32, ControlGroup=launcher.SERVICE_GROUP)


def test_launcher_checks_own_current_effective_native_boundary(monkeypatch):
    fields=effective_launcher_fields();calls=[]
    def fake(argv,**kwargs):
        calls.append(argv);assert kwargs=={}
        assert argv[:4]==['/usr/bin/systemctl','--user','show','friday-rework-docker.service']
        assert set(argv[-1].split('=',1)[1].split(','))==set(fields)
        return '\n'.join(k+'='+v for k,v in fields.items())
    monkeypatch.setattr(launcher,'native_call',fake)
    assert launcher.checked_native_service_limits()==fields and len(calls)==1


@pytest.mark.parametrize('name,value',[('RuntimeMaxUSec','infinity'),('RuntimeMaxUSec','0s'),
    ('RuntimeMaxUSec','121s'),('TimeoutStartUSec','46s'),('TimeoutStopUSec','infinity'),
    ('KillMode','process'),('MainPID','1'),('InvocationID',''),('DropInPaths','/foreign.conf'),
    ('ControlGroup','/foreign'),('MemoryMax','max'),('CPUQuotaPerSecUSec','9s')])
def test_launcher_refuses_stale_cached_deadline_or_foreign_native_boundary(monkeypatch,name,value):
    fields=effective_launcher_fields();fields[name]=value
    monkeypatch.setattr(launcher,'native_call',lambda *a,**k:'\n'.join(n+'='+v for n,v in fields.items()))
    with pytest.raises(RuntimeError):launcher.checked_native_service_limits()


def test_installed_launcher_refuses_infinite_cache_before_memory_write_or_exec(service,monkeypatch):
    s=service;install(s);fields=effective_launcher_fields();fields['RuntimeMaxUSec']='infinity';effects=[]
    monkeypatch.setattr(launcher,'__file__',str(runtime.LAUNCHER))
    monkeypatch.setattr(launcher.sys,'argv',[str(runtime.LAUNCHER)])
    monkeypatch.delenv('_DOCKERD_ROOTLESS_CHILD',raising=False)
    monkeypatch.setattr(launcher,'native_call',lambda *a,**k:'\n'.join(n+'='+v for n,v in fields.items()))
    monkeypatch.setattr(launcher,'prepare_memory',lambda:effects.append('memory-write'))
    monkeypatch.setattr(launcher.os,'execve',lambda *a:effects.append('daemon-exec'))
    with pytest.raises(RuntimeError,match='launch_finite_native_deadline_required'):launcher.main()
    assert not effects


def test_normal_native_completion_installs_service_before_profile_or_keys(service,monkeypatch):
    """Actual completion wiring/files; PM/frontend/profile IO is explicitly fake."""
    import shutil, sys
    import hermes_constants
    from pm import paths, environments
    from gateway import host_rendezvous
    from hermes_cli import source_build, _launchers
    from tools import configure_product
    s=service;source=s.home/'hermes-agent';source.mkdir(mode=0o700)
    # The fixture's pre-staged source is removed only inside its own tmp tree;
    # ordinary completion must produce it itself before the real preparer call.
    shutil.rmtree(s.home/'worker-runtime-source')
    monkeypatch.setattr(hermes_constants,'get_hermes_home',lambda:s.home)
    monkeypatch.setattr(paths,'repo_root',lambda:source)
    monkeypatch.setattr(environments,'project_python',lambda root:Path(sys.executable))
    monkeypatch.setattr(environments,'owning_home_root',lambda root:s.home)
    monkeypatch.setattr(host_rendezvous,'read_record',lambda *a,**k:None)
    monkeypatch.setattr(source_build,'source_build_env',lambda **k:{})
    for name in ('prepare_source_dependencies','build_source_tui','build_source_web'):
        monkeypatch.setattr(source_build,name,lambda *a,**k:None)
    monkeypatch.setattr(source_build,'source_product_current',lambda *a,**k:True)
    monkeypatch.setattr(_launchers,'ensure_install_launchers',lambda *a,**k:list(_launchers.ENTRY_POINTS))
    bundle={'config':{},'contract':{},'soul':''}
    monkeypatch.setattr(configure_product,'compose_product',lambda spec:bundle)
    monkeypatch.setattr(native,'native_profile_check',lambda *a,**k:{'state':'TEMPLATE_INCOMPLETE','ready':False})
    monkeypatch.setattr(native,'install_stamp',lambda receipt:{'fixture':'NATIVE_PM_BUILD_NOT_RUN'})
    observed=[]
    def profile_write(home,spec):
        receipt=entry.read_json(home/'preparation/a0-service.receipt.json')
        assert receipt['state']=='REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
        observed.append('profile-after-registration');return bundle
    monkeypatch.setattr(native,'profile_write',profile_write)
    result=native.complete(s.value,s.home,{},budget=s.budget)
    assert result['ready'] is False and observed==['profile-after-registration']
    assert sum('link' in c for c in s.calls)==sum('daemon-reload' in c for c in s.calls)==1
