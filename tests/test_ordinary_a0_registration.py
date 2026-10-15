"""SOURCE ONLY: installed registration with synthetic native manager/custody.

Production plan/compiler, staged/source custody, lock and publication paths run
against private fixtures. No actual systemd, namespace, network or model effect.
"""
import copy
import hashlib
import json
from pathlib import Path
import time

import pytest
from scripts import friday_ordinary_a0_registration as registration
from scripts import a0_prepare as prep, friday_install as entry, dsh_prepare
from scripts import a0_runtime as runtime, rootless_docker_launch as launcher
from scripts.install_containment import Budget
from test_ordinary_worker_preparation import installed, normal, service, install_input, doc, pin


@pytest.fixture
def receiver(installed, monkeypatch):
    s = installed
    current = copy.deepcopy(s.value); current['project_files'].pop(registration.SOURCE)
    current_ref = doc(s.deploy / 'registration-current.json', current)
    fresh_ref = doc(s.deploy / 'registration-input.json', s.value)
    marker = entry.read_json(s.home / entry.MARKER)
    marker['input_sha256'] = current_ref['sha256']
    doc(s.home / entry.MARKER, marker)
    s.registration_clock = dict(schema=registration.CLOCK, seconds=180, cleanup_seconds=30,
        started_mono=time.monotonic(), boot_id='source-fixture-boot', gnu_pid=42, gnu_starttime_ticks=777)
    s.registration_clock.update(deadline_mono=s.registration_clock['started_mono']+180,
                                useful_deadline_mono=s.registration_clock['started_mono']+150)
    s.registration_request = {'schema':registration.SCHEMA, 'request_id':'source-finite-1', 'seconds':180,
        'home':str(s.home), 'unit':'friday-rework-ordinary-a0-registration-source-finite-1.service',
        'current_input':current_ref, 'registration_input':fresh_ref,
        'marker':pin(s.home/entry.MARKER), 'source_receipt':pin(s.home/'hermes-agent.source.json'),
        'configuration':pin(s.home/'config.yaml'), 'profile':pin(s.home/'FRIDAY-PROFILE.json'),
        'history':s.request['history']}
    s.registration_path = s.deploy/'registration-request.json'; doc(s.registration_path,s.registration_request)
    s.native_owner_calls=[]
    def fake_owner(request, clock):
        s.native_owner_calls.append((copy.deepcopy(request),copy.deepcopy(clock)))
        return {'unit':request['unit'], 'invocation_id':'f'*32, 'cgroup':'/source-only','caps':registration.CAPS}
    monkeypatch.setattr(registration, 'native_owner', fake_owner)
    def fake_run(argv, cwd, **kw):
        assert argv[0]=='/usr/bin/systemctl' and cwd==s.deploy
        assert kw['deadline']==s.registration_clock['deadline_mono'] and 0<kw['timeout']<=10
        assert kw['env'] is runtime.ENV
        assert kw['log'].parent.name=='ordinary-a0-registration-source-finite-1'
        s.calls.append(list(argv)); phase='show' if 'show' in argv else 'link' if 'link' in argv else 'reload'
        out=''
        if phase=='link':
            assert '--no-reload' in argv
            launcher.INSTALLED_UNIT.symlink_to(argv[-1])
        elif phase=='reload':
            assert argv==['/usr/bin/systemctl','--user','daemon-reload']
            s.fields.update(LoadState='loaded',FragmentPath=str(launcher.INSTALLED_UNIT),Restart='no',
                KillMode='control-group',SendSIGKILL='yes',DelegateSubgroup='dockerd',
                MemoryMax=str(20*1024**3),TasksMax='2048',CPUQuotaPerSecUSec='8s',
                RuntimeMaxUSec='2min',TimeoutStartUSec='45s',TimeoutStopUSec='20s')
        else:out='\n'.join(k+'='+v for k,v in s.fields.items())+'\n'
        if s.effect_hook:s.effect_hook(phase)
        if s.lost==phase:raise RuntimeError('SOURCE synthetic lost manager acknowledgement')
        return out,dict(returncode=0,elapsed_seconds=.001,timeout=False,reaped=True,
            stdout_sha256=hashlib.sha256(out.encode()).hexdigest(),stderr_sha256=hashlib.sha256(b'').hexdigest(),
            stdout_bytes=len(out),stderr_bytes=0,reason='command_succeeded')
    monkeypatch.setattr(dsh_prepare,'run',fake_run)
    s.before={str(p):p.read_bytes() for p in [s.home/entry.MARKER,s.home/'config.yaml',
              s.home/'FRIDAY-PROFILE.json',s.home/'hermes-agent.source.json',Path(s.request['history'][0]['path'])]}
    return s


def execute(s):
    return registration.register(s.registration_request,s.registration_path,clock=s.registration_clock)


def rewrite(s):doc(s.registration_path,s.registration_request)


def unchanged(s):
    assert all(Path(path).read_bytes()==raw for path,raw in s.before.items())


def test_installed_receiver_registers_once_without_fabricating_claim_or_changing_old_clock(receiver):
    s=receiver; result=execute(s)
    assert result['schema']==registration.RECEIPT
    assert result['original_attempt']['clock']==s.registration_clock
    assert result['original_attempt']['marker']==s.registration_request['marker']
    assert result['original_attempt'] != entry.read_json(s.home/entry.MARKER)['original_attempt']
    assert result['state']=='REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
    assert result['runtime_acceptance']=='NOT_ACCEPTED' and result['resume_allowed'] is False
    assert sum('link' in c for c in s.calls)==sum('daemon-reload' in c for c in s.calls)==1
    assert not any('start' in c or 'enable' in c for c in s.calls)
    unchanged(s)
    before=list(s.calls)
    with pytest.raises(ValueError,match='consumed_requires_reconciliation'):execute(s)
    assert s.calls==before
    assert not (s.home/'preparation/a0-service.receipt.json').exists()
    # Old normal receipt consumer must not treat the separate installed schema
    # or a fabricated expired install claim as accepted normal installation.
    entry.publish(s.home/'preparation/a0-service.receipt.json', result)
    effective=registration.installed(s.registration_request,Budget(180))[2]
    with pytest.raises(ValueError,match='a0_service_receipt_changed'):
        prep.service_receipt_checked(effective,s.home,original_attempt=result['original_attempt'])


def test_receiver_predating_worker_installer_keeps_complete_reviewed_package(receiver):
    s=receiver
    current_path=Path(s.registration_request['current_input']['path'])
    current=json.loads(current_path.read_text())
    current['project_files'].pop('scripts/friday_worker_preparation.py')
    for name in ('scripts/friday_install.py','scripts/friday_ordinary_install.py','scripts/worker_install.py'):
        current['project_files'][name]='0'*64
    s.registration_request['current_input']=doc(current_path,current)
    marker=entry.read_json(s.home/entry.MARKER)
    marker['input_sha256']=s.registration_request['current_input']['sha256']
    doc(s.home/entry.MARKER,marker)
    s.registration_request['marker']=pin(s.home/entry.MARKER)
    s.before[str(s.home/entry.MARKER)]=(s.home/entry.MARKER).read_bytes()
    rewrite(s)
    result=execute(s)
    assert result['state']=='REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
    unchanged(s)


def test_supported_cli_uses_native_clock_before_request_io(receiver,monkeypatch,capsys):
    import sys
    s=receiver;clock_seen=[];original=entry.owned_file
    def clock():
        clock_seen.append(True)
        return s.registration_clock
    def read(path,*args,**kwargs):
        if Path(path)==s.registration_path:assert clock_seen
        return original(path,*args,**kwargs)
    monkeypatch.setattr(registration,'registration_clock',clock)
    monkeypatch.setattr(entry,'owned_file',read)
    monkeypatch.setattr(sys,'argv',['friday_install.py','register-ordinary-a0','--input',str(s.registration_path)])
    entry.main()
    assert json.loads(capsys.readouterr().out)['schema']==registration.RECEIPT
    assert len(clock_seen)==1
    assert sum('link' in c for c in s.calls)==sum('daemon-reload' in c for c in s.calls)==1
    unchanged(s)


def test_supported_cli_refuses_missing_native_owner_before_request_io(receiver,monkeypatch):
    import sys
    s=receiver
    def refuse():raise entry.Refused('installed_cli_direct_gnu180_required')
    def no_read(*args,**kwargs):pytest.fail('request read before native clock admission')
    monkeypatch.setattr(registration,'registration_clock',refuse)
    monkeypatch.setattr(entry,'owned_file',no_read)
    monkeypatch.setattr(sys,'argv',['friday_install.py','register-ordinary-a0','--input',str(s.registration_path)])
    with pytest.raises(entry.InstallerExit) as exc:entry.main()
    assert exc.value.code==2 and not s.calls and not s.native_owner_calls


@pytest.mark.parametrize('field',['marker','configuration','profile','source_receipt','current_input','registration_input'])
def test_changed_immutable_current_identity_refuses_before_native(receiver,field):
    s=receiver;p=Path(s.registration_request[field]['path']);p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError):execute(s)
    assert not s.calls and not s.native_owner_calls
    assert not list((s.home/'preparation').glob('ordinary-a0-registration-*'))


@pytest.mark.parametrize('field,value',[('ActiveState','active'),('SubState','failed'),('MainPID','9'),
    ('ControlPID','9'),('InvocationID','f'*32),('ControlGroup','/foreign'),('DropInPaths','/foreign'),
    ('LoadState','loaded'),('FragmentPath','/foreign')])
def test_exact_unregistered_inactive_native_precondition(receiver,field,value):
    s=receiver;s.fields[field]=value
    with pytest.raises(ValueError):execute(s)
    unchanged(s)
    assert all('link' not in c and 'daemon-reload' not in c for c in s.calls)


@pytest.mark.parametrize('name',['launcher','unit','registration','request','guard','namespace','stale-state'])
def test_retained_sources_route_or_namespace_refuse_without_overwrite_adoption(receiver,name):
    s=receiver;p={'launcher':runtime.LAUNCHER,'unit':s.root/'supervisor'/runtime.DAEMON,
        'registration':launcher.INSTALLED_UNIT,'request':launcher.REQUEST,'guard':launcher.GUARD,
        'namespace':launcher.STATE/'rootlesskit','stale-state':launcher.STATE/'old-child-pid'}[name]
    p.write_text('foreign preserved SOURCE state\n');p.chmod(0o600)
    with pytest.raises(ValueError):execute(s)
    assert p.read_text()=='foreign preserved SOURCE state\n';unchanged(s)
    assert not any('link' in c or 'daemon-reload' in c for c in s.calls)


@pytest.mark.parametrize('phase',['link','reload'])
def test_uncertain_native_registration_is_retained_and_different_id_cannot_retry(receiver,phase):
    s=receiver;s.lost=phase
    with pytest.raises(dsh_prepare.StopUnconfirmed):execute(s)
    tx=s.home/'preparation/ordinary-a0-registration-source-finite-1'
    assert entry.read_json(tx/'failure.json')['resume_allowed'] is False
    assert entry.read_json(tx/'a0-service.failure.json')['resume_allowed'] is False
    assert launcher.INSTALLED_UNIT.is_symlink() and not (tx/'result.json').exists()
    before=list(s.calls);s.registration_request['request_id']='source-finite-2'
    s.registration_request['unit']='friday-rework-ordinary-a0-registration-source-finite-2.service';rewrite(s)
    with pytest.raises(ValueError,match='consumed_requires_reconciliation'):execute(s)
    assert s.calls==before;unchanged(s)


@pytest.mark.parametrize('where',['marker','configuration','source','staged','native-limit'])
def test_identity_and_effective_boundary_drift_preserves_uncertainty(receiver,where):
    s=receiver
    def drift(phase):
        if phase!='link':return
        if where=='native-limit':
            s.fields['ControlGroup']='/unexpected';return
        p={'marker':s.home/entry.MARKER,'configuration':s.home/'config.yaml','source':runtime.LAUNCHER,
           'staged':s.home/'worker-runtime-source/scripts/a0_runtime.py'}[where]
        p.chmod(0o600);p.write_bytes(p.read_bytes()+b' ')
    s.effect_hook=drift
    with pytest.raises(dsh_prepare.StopUnconfirmed):execute(s)
    assert not list((s.home/'preparation').glob('ordinary-a0-registration-*/result.json'))
    if where!='native-limit':assert all('daemon-reload' not in c for c in s.calls)


@pytest.mark.parametrize('change',['expiry','clock-reset','boot-shape','missing-history','source-delta','runtime','partial-marker'])
def test_unbounded_or_noninstalled_registration_refuses(receiver,change):
    s=receiver
    if change=='expiry':
        s.registration_clock['started_mono']=time.monotonic()-181
        s.registration_clock.update(deadline_mono=s.registration_clock['started_mono']+180,
                                    useful_deadline_mono=s.registration_clock['started_mono']+150)
    elif change=='clock-reset':s.registration_clock['deadline_mono']+=1
    elif change=='boot-shape':s.registration_clock['gnu_pid']=True
    elif change=='missing-history':s.registration_request['history']=[];rewrite(s)
    elif change=='partial-marker':
        p=s.home/entry.MARKER;doc(p,entry.partial_claim('b'*64,Budget(180)))
        s.registration_request['marker']=pin(p);rewrite(s)
    else:
        p=Path(s.registration_request['registration_input']['path']);value=entry.read_json(p)
        if change=='runtime':value['product']['runtime']={'enabled':True}
        else:value['product']['inference']['model']='changed-by-registration'
        s.registration_request['registration_input']=doc(p,value);rewrite(s)
    with pytest.raises(ValueError):execute(s)
    assert not s.calls and not s.native_owner_calls


def test_exclusive_runtime_lock_prevents_registration(receiver):
    import fcntl,os
    s=receiver;fd=os.open(runtime.RUNTIME/'runtime.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):execute(s)
    finally:os.close(fd)
    assert not s.calls;unchanged(s)


def test_fresh_install_entry_still_requires_its_exact_partial_claim(receiver):
    s=receiver;effective=registration.installed(s.registration_request,Budget(180))[2]
    with pytest.raises(ValueError,match='fresh_install_claim_required'):
        prep.install_service(effective,s.home,Budget(180))
    assert not s.calls;unchanged(s)


REAL_NATIVE_OWNER=registration.native_owner


@pytest.fixture
def custody(tmp_path,monkeypatch):
    """Synthetic proc/cgroup/bus observations; production custody validator."""
    import os,resource
    from types import SimpleNamespace
    tmp_path.chmod(0o700)
    tree=tmp_path/'native';tree.mkdir(mode=0o700)
    procroot=tree/'proc';procroot.mkdir(mode=0o700)
    proc=procroot/'42';proc.mkdir(mode=0o700)
    ticks=777;pid=42
    (proc/'stat').write_text('42 (source GNU) '+' '.join(['S']+['0']*18+[str(ticks)])+'\n')
    (proc/'exe').symlink_to('/usr/bin/gnutimeout')
    (proc/'cmdline').write_bytes(b'\0'.join([b'gnutimeout',b'--signal=TERM',b'--kill-after=2s',b'180s',b'python'])+b'\0')
    request={'request_id':'native-source-1','unit':'friday-rework-ordinary-a0-registration-native-source-1.service'}
    group='/user.slice/source/'+request['unit']
    (proc/'cgroup').write_text('0::'+group+'\n')
    member=tree/'membership';member.write_text('0::'+group+'\n')
    boot=tree/'boot';boot.write_text('source-boot\n')
    cgroot=tree/'cgroup';root=cgroot/group.lstrip('/');root.mkdir(mode=0o700,parents=True)
    for name,value in registration.CAPS.items():(root/name).write_text(value+'\n')
    busroot=tree/'manager';busroot.mkdir(mode=0o700);(busroot/'bus').write_text('synthetic socket metadata only')
    started=time.monotonic()
    clock=dict(schema=registration.CLOCK,seconds=180,cleanup_seconds=30,started_mono=started,
        deadline_mono=started+180,useful_deadline_mono=started+150,boot_id='source-boot',gnu_pid=pid,
        gnu_starttime_ticks=ticks)
    observed=dict(Id=request['unit'],InvocationID='b'*32,ActiveState='active',SubState='running',
        MainPID=str(pid),ControlPID='0',ControlGroup=group,RuntimeMaxUSec='2min 28s',
        TimeoutStopUSec='30s',KillMode='control-group',ExecMainStartTimestampMonotonic=str(int(started*1000000)))
    mapping={'/proc':procroot,'/proc/self/cgroup':member,'/proc/sys/kernel/random/boot_id':boot,
             '/sys/fs/cgroup':cgroot,'/run/user/'+str(os.getuid()):busroot}
    def source_path(path):return mapping.get(str(path),Path(path))
    monkeypatch.setattr(registration,'Path',source_path)
    monkeypatch.setattr(registration.os,'getppid',lambda:pid)
    monkeypatch.setattr(registration.os,'sched_getaffinity',lambda who:{0,1})
    monkeypatch.setattr(registration.resource,'getrlimit',lambda which:(0,0) if which==resource.RLIMIT_CORE else (268435456,268435456))
    monkeypatch.setattr(registration.stat,'S_ISSOCK',lambda mode:True)
    calls=[]
    def fake_native(argv,cwd,**kw):
        calls.append(argv)
        assert argv[:4]==['/usr/bin/systemctl','--user','show',request['unit']]
        assert kw['deadline']==clock['useful_deadline_mono'] and kw['env'] is runtime.ENV
        return '\n'.join(k+'='+v for k,v in observed.items())+'\n',{}
    monkeypatch.setattr(dsh_prepare,'run',fake_native)
    return SimpleNamespace(request=request,clock=clock,proc=proc,root=root,boot=boot,member=member,
                           observed=observed,calls=calls)


def test_production_native_owner_accepts_only_exact_synthetic_current_scope(custody):
    s=custody;result=REAL_NATIVE_OWNER(s.request,s.clock)
    assert result['unit']==s.request['unit'] and result['invocation_id']=='b'*32
    assert result['caps']==registration.CAPS and len(s.calls)==1


@pytest.mark.parametrize('case',['boot','ticks','argv','parent-cgroup','self-cgroup','memory','pids','cpu',
    'affinity','core','fsize','bus','MainPID','ControlPID','InvocationID','RuntimeMaxUSec','TimeoutStopUSec',
    'KillMode','ExecMainStartTimestampMonotonic','ActiveState','unknown-field'])
def test_production_native_owner_rejects_unowned_or_unbounded_synthetic_observations(custody,monkeypatch,case):
    import resource
    s=custody
    if case=='boot':s.boot.write_text('foreign-boot\n')
    elif case=='ticks':s.clock['gnu_starttime_ticks']+=1
    elif case=='argv':(s.proc/'cmdline').write_bytes(b'not-the-original-gnu\0')
    elif case=='parent-cgroup':(s.proc/'cgroup').write_text('0::/foreign\n')
    elif case=='self-cgroup':s.member.write_text('0::/foreign\n')
    elif case in ('memory','pids','cpu'):
        (s.root/{'memory':'memory.max','pids':'pids.max','cpu':'cpu.max'}[case]).write_text('max\n')
    elif case=='affinity':monkeypatch.setattr(registration.os,'sched_getaffinity',lambda who:{0})
    elif case in ('core','fsize'):
        monkeypatch.setattr(registration.resource,'getrlimit',lambda which:(1,1))
    elif case=='bus':monkeypatch.setattr(registration.stat,'S_ISSOCK',lambda mode:False)
    elif case=='unknown-field':s.observed['ForeignProperty']='unreviewed'
    else:s.observed[case]={'MainPID':'99','ControlPID':'99','InvocationID':'not-a-native-id',
        'RuntimeMaxUSec':'infinity','TimeoutStopUSec':'infinity','KillMode':'process',
        'ExecMainStartTimestampMonotonic':'1','ActiveState':'inactive'}[case]
    with pytest.raises((ValueError,OSError)):REAL_NATIVE_OWNER(s.request,s.clock)
