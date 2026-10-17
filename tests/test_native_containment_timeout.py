"""Real native init/setsid teardown and fail-closed timeout witnesses."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from scripts.friday_install import _source_runtime_module
c = _source_runtime_module('runtime_containment')
p = _source_runtime_module('runtime_process')


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return pid, int(fields[19]), int(fields[3])
    except FileNotFoundError:
        return None


def family(pid):
    found = []
    current = identity(pid)
    if current:
        found.append(current)
        for child in Path(f'/proc/{pid}/task/{pid}/children').read_text().split():
            found.extend(family(int(child)))
    return found


@pytest.mark.parametrize('detached', [False, True])
def test_real_timeout_drains_namespace_before_deferred_write(tmp_path, monkeypatch, detached):
    """The original monitor-group kill permits these +1s synthetic writes."""
    pin = {'path': '/usr/bin/bwrap',
           'sha256': hashlib.sha256(Path('/usr/bin/bwrap').read_bytes()).hexdigest()}
    single = "import time,pathlib;time.sleep(1);pathlib.Path('late').touch();time.sleep(1)"
    nested = '''import os,time,pathlib
child=os.fork()
if child==0:
 os.setsid()
 grandchild=os.fork()
 if grandchild==0:
  os.setsid();time.sleep(1);pathlib.Path('late-grandchild').touch();time.sleep(1)
 else:
  time.sleep(1);pathlib.Path('late-child').touch();time.sleep(1)
 os._exit(0)
time.sleep(2)
'''
    observed = []
    popen = subprocess.Popen
    class WitnessProcess(popen):
        def communicate(self, *args, **kwargs):
            try:
                return super().communicate(*args, **kwargs)
            except subprocess.TimeoutExpired:
                if not observed:
                    observed.extend(family(self.pid))
                raise
    monkeypatch.setattr(subprocess, 'Popen', WitnessProcess)
    env = {'HOME': str(tmp_path), 'TMPDIR': str(tmp_path), 'PATH': '/usr/bin:/bin',
           'PYTHONDONTWRITEBYTECODE': '1'}
    started = time.monotonic()
    budget = c.Budget(30, deadline=started+1.25)
    original_deadline = budget.deadline
    with pytest.raises(p.CommandFailed) as caught:
        c.Containment(pin, budget, env).run(
            ['/usr/bin/python3', '-B', '-c', nested if detached else single], tmp_path, timeout=.1)
    elapsed = time.monotonic() - started
    observation = caught.value.observation
    assert observation['timeout'] and observation['reaped']
    assert observation['returncode'] == 137 and observation['namespace_init_exit_verified']
    assert elapsed < .9 and budget.deadline == original_deadline
    assert len(observed) >= (4 if detached else 2)
    assert all(identity(pid) != row for row in observed for pid in [row[0]])
    if detached:
        assert len({row[2] for row in observed}) >= 3
    time.sleep(max(0, started+1.15-time.monotonic()))
    assert not list(tmp_path.glob('late*'))


@pytest.mark.parametrize('changed', ['missing-exit', 'wrong-pid', 'wrong-status', 'unreaped', 'no-local-stop'])
def test_timeout_witness_requires_matching_native_exit_and_local_stop(changed):
    wire = b'{"child-pid":123}\n{"exit-code":137}\n'
    observation = dict(returncode=137, timeout=True, reaped=True)
    stop = (123, 456)
    assert c.namespace_exit(wire, observation, stopped_init=stop)
    if changed == 'missing-exit': wire = wire.splitlines()[0]+b'\n'
    elif changed == 'wrong-pid': stop = (124, 456)
    elif changed == 'wrong-status': observation['returncode'] = 0
    elif changed == 'unreaped': observation['reaped'] = False
    elif changed == 'no-local-stop': stop = None
    assert not c.namespace_exit(wire, observation, stopped_init=stop)


def test_stop_and_communicate_errors_preserve_timeout_cause(monkeypatch, tmp_path):
    class Process:
        pid = 98765
        returncode = None
        calls = 0
        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1: raise subprocess.TimeoutExpired('private-canary', timeout)
            raise OSError('synthetic cleanup IO')
    monkeypatch.setattr(p.subprocess, 'Popen', lambda *a, **kw: Process())
    def refused(*args): raise PermissionError('synthetic signal denial')
    with pytest.raises(p.StopUnconfirmed) as caught:
        p.run(['/not-executed'], tmp_path, timeout=.1, deadline=time.monotonic()+1,
              stop_on_timeout=refused)
    error = caught.value
    assert isinstance(error.friday_custody_primary, p.CommandFailed)
    assert error.__cause__ is error.friday_custody_primary
    assert error.observation['timeout'] and not error.observation['reaped']
    assert [type(exc) for exc in error.friday_custody_secondary] == [PermissionError, OSError]
    assert 'private-canary' not in json.dumps(error.observation)


def test_log_failure_preserves_original_nonzero_cause(monkeypatch, tmp_path):
    class Process:
        pid = 98765
        returncode = 17
        def communicate(self, timeout): return '', ''
    monkeypatch.setattr(p.subprocess, 'Popen', lambda *a, **kw: Process())
    obstructed = tmp_path/'log-parent'
    obstructed.write_text('synthetic obstruction')
    with pytest.raises(p.StopUnconfirmed) as caught:
        p.run(['/not-executed'], tmp_path, log=obstructed/'diagnostic')
    error = caught.value
    assert isinstance(error.friday_custody_primary, p.CommandFailed)
    assert error.__cause__ is error.friday_custody_primary
    assert error.observation['returncode'] == 17 and error.observation['reaped']
    assert len(error.friday_custody_secondary) == 1
    assert isinstance(error.friday_custody_secondary[0], FileExistsError)


@pytest.mark.parametrize('expired', [False, True])
def test_unconfirmed_releases_owned_streams_without_fresh_wait(monkeypatch, tmp_path, expired):
    class Process:
        pid = 98765
        returncode = None
        calls = 0
        polls = 0
        stdout = io.StringIO()
        stderr = io.StringIO()
        def communicate(self, timeout):
            self.calls += 1
            raise subprocess.TimeoutExpired('synthetic', timeout)
        def poll(self):
            self.polls += 1
            return None
    process = Process()
    monkeypatch.setattr(p.subprocess, 'Popen', lambda *a, **kw: process)
    with pytest.raises(p.StopUnconfirmed) as caught:
        p.run(['/not-executed'], tmp_path, timeout=.1,
              deadline=0 if expired else time.monotonic()+1, stop_on_timeout=lambda *a: None)
    assert process.stdout.closed and process.stderr.closed
    assert process.calls == (1 if expired else 2) and process.polls == 1
    assert caught.value.observation['timeout'] and not caught.value.observation['reaped']
    assert isinstance(caught.value.friday_custody_primary, p.CommandFailed)


def test_pidfd_signal_and_close_errors_both_survive(monkeypatch):
    def stat(pid, parent, birth):
        fields = ['S']+['0']*19
        fields[1] = str(parent); fields[19] = str(birth)
        return f'{pid} (synthetic) '+' '.join(fields)
    class FakePath:
        def __init__(self, path): self.path = path
        def read_text(self):
            return {'/proc/100/stat': stat(100, 10, 50),
                    '/proc/101/stat': stat(101, 100, 50),
                    '/proc/self/fdinfo/33': 'Pid:\t101\nNSpid:\t101\t1\n'}[self.path]
    signal_error = PermissionError('synthetic signal denial')
    close_error = OSError('synthetic close failure')
    def denied(*args): raise signal_error
    def close(*args): raise close_error
    stop = c._NamespaceStop(30)
    stop.read = lambda: b'{"child-pid":101,"pid-namespace":22}\n'
    with monkeypatch.context() as patch:
        patch.setattr(c, 'Path', FakePath)
        patch.setattr(c.os, 'pidfd_open', lambda pid: 33)
        patch.setattr(c.os, 'readlink', lambda path: 'pid:[22]' if '/101/' in path else 'pid:[11]')
        patch.setattr(c.signal, 'pidfd_send_signal', denied)
        patch.setattr(c.os, 'close', close)
        with pytest.raises(PermissionError) as caught:
            stop(SimpleNamespace(pid=100), 50)
    assert caught.value is signal_error
    assert caught.value.friday_custody_secondary == (close_error,)
    assert stop.stopped_init is None
