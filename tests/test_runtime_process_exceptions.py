"""Exceptional post-spawn custody. Live controls require an explicit finite opt-in."""
import hashlib
import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

import pytest
from scripts.friday_install import _source_runtime_module

runtime = _source_runtime_module('runtime_process')
custody = _source_runtime_module('runtime_containment')
CANARY = 'PRIVATE_EXCEPTION_CUSTODY_CANARY'


def _cleanup_owned(identities, monitors, deadline, *, send_signal=None,
                   select_ready=None, extra_fds=()):
    """Finite test cleanup: retain exact identities until death is observed."""
    import signal
    primary = sys.exc_info()[1]
    secondary = []
    send_signal = signal.pidfd_send_signal if send_signal is None else send_signal
    select_ready = select.select if select_ready is None else select_ready
    # Never let the first signal/readiness/wait/close error skip other ownership.
    for fd in identities:
        try:
            send_signal(fd, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            secondary.append(exc)
    for fd in identities:
        try:
            remaining = max(0, deadline - time.monotonic())
            if not select_ready([fd], [], [], remaining)[0]:
                raise AssertionError('test_owned_identity_STOP_UNCONFIRMED')
        except BaseException as exc:
            secondary.append(exc)
    for monitor in monitors:
        try:
            monitor.wait(timeout=max(0, deadline - time.monotonic()))
        except BaseException as exc:
            secondary.append(exc)
        for name in ('stdout', 'stderr'):
            try:
                stream = getattr(monitor, name, None)
                if stream is not None and not stream.closed:
                    stream.close()
            except BaseException as exc:
                secondary.append(exc)
    for fd in (*identities, *extra_fds):
        try:
            os.close(fd)
        except BaseException as exc:
            secondary.append(exc)
    if secondary:
        if primary is not None:
            primary.friday_test_cleanup_secondary = (
                getattr(primary, 'friday_test_cleanup_secondary', ()) + tuple(secondary))
        else:
            failure = AssertionError('test_owned_cleanup_STOP_UNCONFIRMED')
            failure.friday_test_cleanup_secondary = tuple(secondary)
            raise failure from None


class FatalSample(BaseException):
    pass


class Process:
    pid = 98765
    returncode = None

    def __init__(self, first=None):
        self.first = first
        self.waits = []
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()

    def communicate(self, timeout):
        self.waits.append(timeout)
        if self.first is not None:
            first, self.first = self.first, None
            raise first
        self.returncode = 137
        return b'bounded\n', b''

    def poll(self):
        return self.returncode


def fake_spawn(monkeypatch, process):
    def spawn(*args, **kwargs):
        assert kwargs['text'] is False
        return process
    monkeypatch.setattr(runtime.subprocess, 'Popen', spawn)
    monkeypatch.setattr(runtime, '_starttime', lambda pid: 456)


@pytest.mark.parametrize('cause', [OSError(CANARY), KeyboardInterrupt(CANARY), FatalSample(CANARY),
    UnicodeDecodeError('utf-8', b'\xff', 0, 1, CANARY)])
def test_postspawn_failure_stops_init_once_drains_and_redacts(monkeypatch, tmp_path, cause):
    process = Process(cause); fake_spawn(monkeypatch, process)
    stops = []; deadline = time.monotonic() + 1
    with pytest.raises(runtime.CommandFailed) as caught:
        runtime.run(['private-argv'], tmp_path, timeout=.1, deadline=deadline,
                    stop_on_timeout=lambda p, birth: stops.append((p, birth)))
    failure = caught.value
    assert stops == [(process, 456)] and len(process.waits) == 2
    assert 0 <= process.waits[0] <= .1 and 0 < process.waits[1] <= 1
    assert failure.friday_custody_primary is cause
    assert failure.friday_custody_secondary == ()
    assert failure.observation['reaped'] is True and failure.observation['timeout'] is False
    assert CANARY not in str(failure) and CANARY not in json.dumps(failure.observation)
    assert failure.__suppress_context__ is True
    assert process.stdout.closed and process.stderr.closed


def test_starttime_baseexception_recovers_identity_then_stops(monkeypatch, tmp_path):
    process = Process(); fake_spawn(monkeypatch, process)
    cause = FatalSample(CANARY); samples = []; stops = []
    def sample(pid):
        samples.append(pid)
        if len(samples) == 1: raise cause
        return 456
    monkeypatch.setattr(runtime, '_starttime', sample)
    with pytest.raises(runtime.CommandFailed) as caught:
        runtime.run(['private'], tmp_path, timeout=.1, deadline=time.monotonic()+1,
                    stop_on_timeout=lambda p, birth: stops.append(birth))
    assert samples == [98765, 98765] and stops == [456]
    assert caught.value.friday_custody_primary is cause and caught.value.observation['reaped']


def test_secondary_stop_error_preserves_first_cause(monkeypatch, tmp_path):
    cause = OSError(CANARY); cleanup = KeyboardInterrupt(CANARY)
    process = Process(cause); fake_spawn(monkeypatch, process)
    def stop(*args): raise cleanup
    with pytest.raises(runtime.StopUnconfirmed) as caught:
        runtime.run(['private'], tmp_path, timeout=.1, deadline=time.monotonic()+1,
                    stop_on_timeout=stop)
    assert caught.value.friday_custody_primary is cause
    assert caught.value.friday_custody_secondary == (cleanup,)
    assert caught.value.observation['reaped'] is True
    assert caught.value.friday_custody_state == 'UNCONFIRMED'
    assert CANARY not in str(caught.value)


def test_exhausted_original_deadline_refuses_before_spawn(monkeypatch, tmp_path):
    starts = []
    def spawn(*args, **kwargs):
        starts.append(args)
        raise AssertionError('expired budget started a process')
    monkeypatch.setattr(runtime.subprocess, 'Popen', spawn)
    with pytest.raises(ValueError, match='original_command_budget_exhausted'):
        runtime.run(['private'], tmp_path, timeout=.1, deadline=time.monotonic()-1)
    assert starts == []


def test_uncontained_exception_has_no_numeric_pid_or_group_fallback(monkeypatch, tmp_path):
    process = Process(OSError(CANARY)); fake_spawn(monkeypatch, process)
    exact = []
    monkeypatch.setattr(runtime, '_kill_exact_leader', lambda p, birth: exact.append((p, birth)))
    def unsafe(*a): raise AssertionError('numeric PID/PGID signal prohibited')
    monkeypatch.setattr(runtime.os, 'kill', unsafe)
    monkeypatch.setattr(runtime.os, 'killpg', unsafe)
    with pytest.raises(runtime.StopUnconfirmed) as caught:
        runtime.run(['private'], tmp_path, timeout=.1)
    assert exact == [(process, 456)] and len(process.waits) == 2
    assert 0 < process.waits[1] <= 10.1
    assert caught.value.observation['reaped'] is True
    assert caught.value.observation['custody_scope'] == 'leader_and_pipes_only'


def test_diagnostic_exception_is_redacted_and_already_reaped(monkeypatch, tmp_path):
    process = Process(); fake_spawn(monkeypatch, process)
    process.returncode = 0
    def communicate(timeout): return b'ok', b''
    process.communicate = communicate
    cause = OSError(CANARY)
    class BrokenLog:
        @property
        def parent(self): raise cause
    stops = []
    with pytest.raises(runtime.CommandFailed) as caught:
        runtime.run(['private'], tmp_path, log=BrokenLog(),
                    stop_on_timeout=lambda *args: stops.append(True))
    assert not stops and caught.value.friday_custody_primary is cause
    assert caught.value.observation['reaped'] is True
    assert CANARY not in str(caught.value)


LIVE = pytest.mark.skipif(os.environ.get('FRIDAY_RUN_EXCEPTION_CUSTODY_LIVE') != '1',
                          reason='explicit finite synthetic-process opt-in required')


@LIVE
def test_real_invalid_utf8_is_binary_drained_reaped_and_redacted(tmp_path):
    # No descendants or external resources; bounded even if decoding regresses.
    with pytest.raises(runtime.CommandFailed) as caught:
        runtime.run([sys.executable, '-B', '-c', 'import os; os.write(1, b"\\xff")'],
                    tmp_path, timeout=1, deadline=time.monotonic()+3)
    assert isinstance(caught.value.friday_custody_primary, UnicodeDecodeError)
    assert caught.value.observation['reaped'] is True
    assert caught.value.observation['stdout_bytes'] == 1
    assert caught.value.observation['stdout_sha256'] == hashlib.sha256(b'\xff').hexdigest()


@LIVE
@pytest.mark.parametrize('kind', ['oserror', 'keyboard', 'sample', 'refused_stop'])
def test_real_namespace_exception_drains_detached_child_and_keeps_monitor(
        monkeypatch, tmp_path, kind):
    """Native two-record witness AND pidfd readiness; detached child is essential."""
    test_started = time.monotonic()
    overall_deadline = test_started + 10
    binary = Path('/usr/bin/bwrap')
    assert binary.is_file(), 'required_native_bubblewrap_unavailable'
    pin = {'path': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    marker = tmp_path / 'detached-ready'
    child = ('import os,time; os.setsid(); '
             + 'open(' + repr(str(marker)) + ',"w").write(str(os.getpid())); time.sleep(6)')
    code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-B","-c",' + repr(child) + ']); time.sleep(6)'
    original_spawn = subprocess.Popen
    original_stop = custody._NamespaceStop.__call__
    original_sample = runtime._starttime
    monitors = []; identities = []; stop_calls = []; sample_calls = []
    cause = OSError(CANARY) if kind in ('oserror', 'refused_stop') else KeyboardInterrupt(CANARY)
    deadline = test_started + 4

    def ready():
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.005)
        assert marker.exists(), 'native_detached_child_not_started'

    def capture_init(stop, process, birth):
        stop_calls.append(process.pid)
        data = stop.read(); first = json.loads(data.splitlines()[0])
        init = first['child-pid']
        children = Path(f'/proc/{init}/task/{init}/children').read_text().split()
        assert len(children) == 1
        descendant = int(children[0])
        # Child must be a different session, and cannot be covered by killpg.
        assert os.getsid(descendant) == descendant and os.getsid(init) != descendant
        identities.append(os.pidfd_open(init))
        identities.append(os.pidfd_open(descendant))
        if kind == 'refused_stop':
            raise runtime.StopUnconfirmed('STOP_UNCONFIRMED: negative control refused init signal')
        return original_stop(stop, process, birth)

    def spawn(*args, **kwargs):
        process = original_spawn(*args, **kwargs); monitors.append(process)
        communicate = process.communicate; calls = []
        def injected(timeout):
            calls.append(timeout)
            if len(calls) == 1:
                ready()
                raise cause
            return communicate(timeout=timeout)
        if kind != 'sample': process.communicate = injected
        return process

    def sample(pid):
        sample_calls.append(pid)
        if kind == 'sample' and len(sample_calls) == 1:
            ready()
            raise cause
        return original_sample(pid)

    monkeypatch.setattr(runtime.subprocess, 'Popen', spawn)
    monkeypatch.setattr(runtime, '_starttime', sample)
    monkeypatch.setattr(custody._NamespaceStop, '__call__', capture_init)
    try:
        runner = custody.Containment(pin, custody.Budget(30, deadline=deadline),
                                     {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8'})
        expected = runtime.StopUnconfirmed if kind == 'refused_stop' else runtime.CommandFailed
        with pytest.raises(expected) as caught:
            runner.run([sys.executable, '-B', '-c', code], tmp_path, timeout=2)
        assert caught.value.friday_custody_primary is cause
        assert caught.value.observation.get('namespace_init_exit_verified') is (None if kind == 'refused_stop' else True)
        assert caught.value.observation['timeout'] is False
        assert len(stop_calls) == 1 and len(monitors) == 1
        assert len(identities) == 2
        if kind == 'refused_stop':
            assert caught.value.friday_custody_state == 'UNCONFIRMED'
            assert not any(select.select([fd], [], [], 0)[0] for fd in identities)
            assert monitors[0].returncode is None
        else:
            assert all(select.select([fd], [], [], 0)[0] for fd in identities)
            assert monitors[0].returncode == 137
        assert CANARY not in str(caught.value)
    finally:
        # Test-only exact identities; the literal child watchdog is no proof.
        _cleanup_owned(identities, monitors, overall_deadline)


def test_native_stop_missing_early_record_waits_only_original_deadline(monkeypatch):
    reader, writer = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
    calls = []
    def unsafe(*args): calls.append(args); raise AssertionError('untrusted init signal')
    monkeypatch.setattr(custody.os, 'pidfd_open', unsafe)
    deadline = time.monotonic() + .02
    try:
        stop = custody._NamespaceStop(reader, deadline=deadline)
        with pytest.raises(runtime.StopUnconfirmed):
            stop(Process(), 456)
        assert time.monotonic() >= deadline and not calls
    finally:
        os.close(writer); os.close(reader)


def test_native_stop_delayed_invalid_identity_never_signals(monkeypatch):
    reader, writer = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
    deadline = time.monotonic() + 1
    waits = []; signals = []
    def ready(readers, writers, errors, timeout):
        waits.append(timeout)
        os.write(writer, b'{"child-pid":true,"pid-namespace":789}\n')
        return readers, [], []
    monkeypatch.setattr(custody.select, 'select', ready)
    monkeypatch.setattr(custody.os, 'pidfd_open', lambda *args: signals.append(args))
    try:
        with pytest.raises(runtime.StopUnconfirmed):
            custody._NamespaceStop(reader, deadline=deadline)(Process(), 456)
        assert len(waits) == 1 and 0 < waits[0] <= 1 and not signals
    finally:
        os.close(writer); os.close(reader)


@LIVE
def test_real_immediate_sample_failure_waits_for_first_native_status(monkeypatch, tmp_path):
    """Early stop must preserve the exact native witness or report unknown."""
    import signal
    test_started = time.monotonic(); overall_deadline = test_started + 8
    deadline = test_started + 4
    binary = Path('/usr/bin/bwrap')
    assert binary.is_file(), 'required_native_bubblewrap_unavailable'
    pin = {'path': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    gate_reader, gate_writer = os.pipe2(os.O_CLOEXEC)
    original_spawn = subprocess.Popen
    original_sample = runtime._starttime
    original_select = select.select
    original_signal = signal.pidfd_send_signal
    original_witness = custody.namespace_exit
    original_stop = custody._NamespaceStop.__call__
    stop_calls = []
    diagnostic = {"witness_calls": []}
    wire_snapshots = []
    monitors = []; identities = []; samples = []; waits = []
    cause = FatalSample(CANARY)

    def spawn(args, **kwargs):
        # Test wrapper retains the exact monitor PID/starttime across exec.
        code = ('import os,select; fd=' + str(gate_reader)
                + '; assert select.select([fd],[],[],2)[0]; os.read(fd,1); os.close(fd); '
                + 'os.execv(' + repr(str(binary)) + ',' + repr(args) + ')')
        kwargs = dict(kwargs, pass_fds=(*kwargs['pass_fds'], gate_reader))
        monitor = original_spawn([sys.executable, '-B', '-c', code], **kwargs)
        monitors.append(monitor); identities.append(os.pidfd_open(monitor.pid))
        return monitor

    def sample(pid):
        samples.append(pid)
        if len(samples) == 1: raise cause
        return original_sample(pid)

    def ready(readers, writers, errors, timeout):
        waits.append(timeout)
        if len(waits) == 1: os.write(gate_writer, b'x')
        return original_select(readers, writers, errors, timeout)

    def exact_signal(fd, sig, *args):
        identities.append(os.dup(fd))
        return original_signal(fd, sig, *args)

    def stop_once(stop, process, birth):
        stop_calls.append((process.pid, birth))
        return original_stop(stop, process, birth)

    def witnessed(data, observation, *, stopped_init=None):
        # Only native integer protocol fields and the existing safe observation
        # whitelist may enter diagnostic text. Never raw pipe/exception text.
        record = {'observation': runtime.safe_observation(observation),
                  'stopped_init': (list(stopped_init) if type(stopped_init) is tuple
                                   and all(type(n) is int for n in stopped_init) else None)}
        if type(data) is bytes:
            record.update(native_wire_bytes=len(data),
                          native_wire_sha256=hashlib.sha256(data).hexdigest())
            try:
                rows = [json.loads(line) for line in data[:4097].splitlines() if line.strip()]
                record['native_rows'] = [
                    {key: value for key, value in row.items()
                     if key in ('child-pid', 'pid-namespace', 'exit-code') and type(value) is int}
                    if type(row) is dict else {'row_type': type(row).__name__}
                    for row in rows]
            except BaseException as exc:
                record['native_parse_error_type'] = type(exc).__name__
        else:
            record['native_wire_type'] = type(data).__name__
        diagnostic['witness_calls'].append(record)
        wire_snapshots.append(data)  # Private exact wire, never emitted as raw text.
        try:
            result = original_witness(data, observation, stopped_init=stopped_init)
            record['witness_is_true'] = result is True
            return result
        except BaseException as exc:
            record['witness_error_type'] = type(exc).__name__
            raise

    monkeypatch.setattr(runtime.subprocess, 'Popen', spawn)
    monkeypatch.setattr(runtime, '_starttime', sample)
    monkeypatch.setattr(custody.select, 'select', ready)
    monkeypatch.setattr(custody.signal, 'pidfd_send_signal', exact_signal)
    monkeypatch.setattr(custody, 'namespace_exit', witnessed)
    monkeypatch.setattr(custody._NamespaceStop, '__call__', stop_once)
    try:
        runner = custody.Containment(pin, custody.Budget(30, deadline=deadline),
                                     {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8'})
        code = 'import time; time.sleep(5)'
        later_work = []
        try:
            runner.run([sys.executable, '-B', '-c', code], tmp_path, timeout=2)
            later_work.append('unexpected_continuation')
        except (runtime.CommandFailed, runtime.StopUnconfirmed) as caught:
            outcome = caught
        else:
            pytest.fail('early_fault_returned_success')
        diagnostic['outcome_error_type'] = type(outcome).__name__
        diagnostic['callback_calls'] = stop_calls
        assert len(diagnostic['witness_calls']) == 1
        witness = diagnostic['witness_calls'][0]
        assert len(wire_snapshots) == 1
        wire = wire_snapshots[0]
        try:
            rows = ([json.loads(line) for line in wire.splitlines() if line.strip()]
                    if type(wire) is bytes and len(wire) <= 4096 else [])
        except (ValueError, TypeError):
            rows = []
        stopped = witness['stopped_init']
        # Independent OS-wire oracle: never derive expectations from the
        # namespace_exit validator under test. Physical death cannot supply row 2.
        complete_wire = (type(wire) is bytes and len(wire) <= 4096
                         and len(rows) == 2 and type(rows[0]) is dict
                         and type(rows[0].get('child-pid')) is int
                         and type(stopped) is list and len(stopped) == 2
                         and all(type(n) is int and n > 0 for n in stopped)
                         and rows[0]['child-pid'] == stopped[0]
                         and type(rows[1]) is dict and rows[1] == {'exit-code': 137}
                         and type(rows[1].get('exit-code')) is int
                         and monitors[0].returncode == 137
                         and witness['observation']['returncode'] == 137
                         and witness['observation']['reaped'] is True)
        diagnostic['independent_complete_wire'] = complete_wire
        assert witness['witness_is_true'] is complete_wire
        if complete_wire:
            assert type(outcome) is runtime.CommandFailed
            assert outcome.observation['namespace_init_exit_verified'] is True
        else:
            assert type(outcome) is runtime.StopUnconfirmed
            assert outcome.observation.get('namespace_init_exit_verified') is None
            assert outcome.friday_custody_state == 'UNCONFIRMED'
        assert outcome.friday_custody_primary is cause
        assert outcome.friday_custody_secondary == ()
        assert outcome.observation['reaped'] is True
        assert outcome.observation['returncode'] == 137
        assert outcome.observation['timeout'] is False
        assert stop_calls == [(monitors[0].pid, outcome.observation['starttime_ticks'])]
        assert later_work == [] and len(monitors) == 1
        assert len(waits) == 1 and 0 < waits[0] <= deadline-test_started
        assert monitors[0].returncode == 137
        assert len(identities) == 2
        assert all(original_select([fd], [], [], 0)[0] for fd in identities)
    except BaseException as unexpected:
        diagnostic['unexpected_error_type'] = type(unexpected).__name__
        diagnostic['primary_error_type'] = type(getattr(unexpected, 'friday_custody_primary', None)).__name__
        diagnostic['secondary_error_types'] = [type(exc).__name__ for exc in
                                              getattr(unexpected, 'friday_custody_secondary', ())]
        # Keep the original failing exception and the exact finally cleanup.
        unexpected.add_note('FRIDAY_NATIVE_DIAGNOSTIC ' + json.dumps(diagnostic, sort_keys=True))
        raise
    finally:
        # Originals bypass the test's signal-capture and gate-readiness wrappers.
        _cleanup_owned(identities, monitors, overall_deadline,
                       send_signal=original_signal, select_ready=original_select,
                       extra_fds=(gate_reader, gate_writer))


@LIVE
def test_real_uncontained_group_child_remains_explicitly_unknown(monkeypatch, tmp_path):
    """Negative control: a pidfd leader kill cannot prove its process group dead."""
    import signal
    test_started = time.monotonic(); overall_deadline = test_started + 8
    deadline = test_started + 2
    marker = tmp_path / 'group-child'
    child = ('import os,time; open(' + repr(str(marker))
             + ',"w").write(str(os.getpid())); time.sleep(6)')
    code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-B","-c",' + repr(child) + ']); time.sleep(6)'
    original_spawn = subprocess.Popen
    monitors = []; identities = []
    cause = OSError(CANARY)

    def spawn(*args, **kwargs):
        process = original_spawn(*args, **kwargs); monitors.append(process)
        communicate = process.communicate; calls = []
        def injected(timeout):
            calls.append(timeout)
            if len(calls) == 1:
                while time.monotonic() < deadline:
                    if marker.exists() and marker.read_text().strip().isdigit(): break
                    time.sleep(.005)
                child_pid = int(marker.read_text())
                assert os.getpgid(child_pid) == process.pid
                identities.append(os.pidfd_open(child_pid))
                raise cause
            return communicate(timeout=timeout)
        process.communicate = injected
        return process

    monkeypatch.setattr(runtime.subprocess, 'Popen', spawn)
    try:
        with pytest.raises(runtime.StopUnconfirmed) as caught:
            runtime.run([sys.executable, '-B', '-c', code], tmp_path,
                        timeout=1, deadline=deadline)
        assert caught.value.friday_custody_primary is cause
        assert caught.value.friday_custody_state == 'UNCONFIRMED'
        assert caught.value.observation['reaped'] is True
        assert caught.value.observation['custody_scope'] == 'leader_and_pipes_only'
        assert len(identities) == 1 and not select.select(identities, [], [], 0)[0]
    finally:
        _cleanup_owned(identities, monitors, overall_deadline)
