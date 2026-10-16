"""Offline user-bus transport and refusal controls for closed-native observations."""
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import friday_install as f, friday_worker_preparation as recovery
from scripts.install_containment import Budget


@pytest.fixture
def closed_user_bus(tmp_path, monkeypatch):
    """A private local socket, without observing or connecting to the host bus."""
    runtime = tmp_path / 'user-runtime' / str(os.getuid()); runtime.mkdir(mode=0o700, parents=True)
    sock = socket.socket(socket.AF_UNIX)
    with monkeypatch.context() as local:
        local.chdir(runtime)
        sock.bind('bus')
    monkeypatch.setattr(recovery, 'Path', lambda path: runtime.parent if path == '/run/user' else Path(path))
    try:
        yield runtime
    finally:
        sock.close()


@pytest.fixture
def closed_native_observation(tmp_path, closed_user_bus):
    """Only disposable paths and historical stopped-unit data, with no DB."""
    home = tmp_path / 'home'; profile = home / 'profiles/test'
    for kind in ('dsh', 'a0'):
        for name in ('jobs', 'staging', 'cache'):
            (profile / 'workers' / kind / name).mkdir(mode=0o700, parents=True)
    unit = 'friday-qualify-dsh-' + f.digest(str(profile / 'workers/qualification/dsh-safety').encode())[:24] + '-1.scope'
    units = {unit: dict(returncode=0, properties=dict(LoadState='not-found', ActiveState='inactive',
        SubState='dead', ControlGroup='', InvocationID='')),
        'friday-rework-docker.service': dict(returncode=0, properties=dict(LoadState='loaded',
            ActiveState='inactive', SubState='dead', ControlGroup='', InvocationID='', MainPID='0', ControlPID='0'))}
    absent = [profile / 'workers' / name for name in ('a0/bootstrap', 'a0/probe-plan.json',
        'a0/runtime-receipt.json', 'dsh/runtime-receipt.json')]
    absent += [home.parent / 'rootless-docker/config/local-route.json',
        closed_user_bus / 'friday-rework-docker/rootlesskit/child_pid',
        closed_user_bus / 'friday-rework-docker/route-guard.json']
    return SimpleNamespace(home=home, profile=profile, runtime=closed_user_bus, unit=unit,
        cessation=dict(actual_units=units, absences={str(path): True for path in absent}))


def _closed_observation_output(s, command):
    assert command[:6] == ['/usr/bin/env', 'XDG_RUNTIME_DIR=' + str(s.runtime),
        'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(s.runtime / 'bus'),
        '/usr/bin/systemctl', '--user', 'show']
    properties = s.cessation['actual_units'][command[6]]['properties']
    assert command[7:] == ['--property=' + ','.join(properties)]
    return '\n'.join(k + '=' + v for k, v in properties.items()), {}


def test_closed_native_bus_wrapper_executes_with_clean_environment(closed_native_observation, monkeypatch):
    """Real env/process boundary; replace only systemctl with an offline observer."""
    from scripts import dsh_prepare
    s = closed_native_observation; run = dsh_prepare.run; budget = Budget(30)
    for name in ('OPENAI_API_KEY', 'HERMES_MODEL', 'MODEL', 'PYTHONPATH',
            'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'SYSTEMCTL_FORCE_BUS'):
        monkeypatch.setenv(name, 'UNTRUSTED_AMBIENT_VALUE')
    backend = '''import json, os, sys
if 'XDG_RUNTIME_DIR' not in os.environ or 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
    sys.exit(23)
data = json.loads(sys.argv[1])
assert os.environ['XDG_RUNTIME_DIR'] == data['runtime']
assert os.environ['DBUS_SESSION_BUS_ADDRESS'] == 'unix:path=' + data['runtime'] + '/bus'
assert not set(('OPENAI_API_KEY', 'HERMES_MODEL', 'MODEL', 'PYTHONPATH', 'SYSTEMCTL_FORCE_BUS')) & os.environ.keys()
assert sys.argv[2:4] == ['--user', 'show']
properties = data['units'][sys.argv[4]]['properties']
assert sys.argv[5:] == ['--property=' + ','.join(properties)]
print('\\n'.join(k + '=' + v for k, v in properties.items()))
'''
    # The old direct clean-env transport cannot obtain a bus, even with ambient
    # variables present. No connection to any actual user bus is attempted.
    with pytest.raises(dsh_prepare.CommandFailed) as failure:
        run([sys.executable, '-B', '-c', backend], f.ROOT,
            timeout=2, env=f.clean_environment(s.home), deadline=budget.deadline)
    assert failure.value.observation['returncode'] == 23
    observations = []
    def native(command, donor, **kw):
        _closed_observation_output(s, command)
        assert donor == f.ROOT and kw['deadline'] == budget.deadline
        assert 0 < kw['timeout'] <= 15
        data = json.dumps(dict(runtime=str(s.runtime), units=s.cessation['actual_units']))
        output = run(command[:3] + [sys.executable, '-B', '-c', backend, data] + command[4:], donor, **kw)
        observations.append(output[1]); return output
    monkeypatch.setattr(dsh_prepare, 'run', native)
    recovery._closed_native_absent(s.home, s.profile, s.cessation, budget)
    assert observations and all(o['returncode'] == 0 and o['reaped'] for o in observations)


@pytest.mark.parametrize('fault', ['missing-unit', 'historical-active', 'active', 'duplicate', 'missing-property',
    'transport', 'expired', 'expires-between-units', 'bus-file', 'bus-symlink', 'bus-missing', 'bus-hardlink',
    'bus-foreign-owner', 'runtime-mode', 'absence', 'worker-job'])
def test_closed_native_bus_fix_retains_refusals(closed_native_observation, monkeypatch, fault):
    from scripts import dsh_prepare
    import time
    s = closed_native_observation; budget = Budget(30); commands = []
    if fault == 'missing-unit': s.cessation['actual_units'].pop(s.unit)
    elif fault == 'historical-active': s.cessation['actual_units'][s.unit]['properties']['ActiveState'] = 'active'
    elif fault == 'expired': budget.deadline = time.monotonic() - 1
    elif fault in ('bus-file', 'bus-symlink'):
        bus = s.runtime / 'bus'; bus.unlink()
        if fault == 'bus-file': bus.write_bytes(b'not a socket')
        else: bus.symlink_to('absent-bus')
    elif fault == 'bus-missing': (s.runtime / 'bus').unlink()
    elif fault == 'bus-hardlink': (s.runtime / 'bus-alias').hardlink_to(s.runtime / 'bus')
    elif fault == 'bus-foreign-owner':
        lstat = Path.lstat
        def foreign_owner(path, *args, **kw):
            info = lstat(path, *args, **kw)
            return SimpleNamespace(st_mode=info.st_mode, st_uid=os.getuid() + 1, st_nlink=info.st_nlink) \
                if path == s.runtime / 'bus' else info
        monkeypatch.setattr(Path, 'lstat', foreign_owner)
    elif fault == 'runtime-mode': s.runtime.chmod(0o755)
    elif fault == 'absence': (s.profile / 'workers/a0/bootstrap').mkdir(mode=0o700)
    elif fault == 'worker-job': (s.profile / 'workers/dsh/jobs/job').write_bytes(b'pending')
    def native(command, donor, **kw):
        commands.append(command)
        output, observation = _closed_observation_output(s, command)
        if fault == 'transport':
            # Exercise the actual bounded process runner's nonzero contract.
            return run(['/usr/bin/env', sys.executable, '-B', '-c', 'raise SystemExit(37)'], donor, **kw)
        if fault == 'active': output = output.replace('ActiveState=inactive', 'ActiveState=active')
        elif fault == 'duplicate': output += '\nActiveState=inactive'
        elif fault == 'missing-property': output = '\n'.join(output.splitlines()[1:])
        elif fault == 'expires-between-units': budget.deadline = time.monotonic() - 1
        return output, observation
    run = dsh_prepare.run
    monkeypatch.setattr(dsh_prepare, 'run', native)
    with pytest.raises((f.Refused, ValueError, OSError, dsh_prepare.CommandFailed)):
        recovery._closed_native_absent(s.home, s.profile, s.cessation, budget)
    if fault in ('missing-unit', 'historical-active', 'expired', 'bus-file', 'bus-symlink',
            'bus-missing', 'bus-hardlink', 'bus-foreign-owner', 'runtime-mode'):
        assert not commands
    if fault == 'expires-between-units': assert len(commands) == 1


def test_closed_native_bus_fix_uses_remaining_original_budget(closed_native_observation, monkeypatch):
    from scripts import dsh_prepare
    import time
    s = closed_native_observation; budget = Budget(30); budget.deadline = time.monotonic() + 2
    deadline = budget.deadline
    def native(command, donor, **kw):
        assert kw['deadline'] == deadline == budget.deadline
        assert 0 < kw['timeout'] <= 1
        return _closed_observation_output(s, command)
    monkeypatch.setattr(dsh_prepare, 'run', native)
    recovery._closed_native_absent(s.home, s.profile, s.cessation, budget)
