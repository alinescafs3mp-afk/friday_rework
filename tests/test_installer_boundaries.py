"""Deadline and containment refusals; native commands are never executed here."""
import json
import os
from pathlib import Path
import time

import pytest
from scripts import friday_install as entry, install_containment as custody
from test_native_installer import install_input


class AdmissionClock(custody.Budget):
    """Controlled phase-boundary exhaustion; does not alter the native clock."""
    expired = False
    def check(self, **kwargs):
        if self.expired:
            raise ValueError('original_install_budget_exhausted')
        return super().check(**kwargs)


def test_required_namespace_refuses_before_home_claim(install_input, tmp_path, monkeypatch):
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    from scripts import dsh_prepare
    def refuse(*a, **k): raise RuntimeError('required unshare PID capability absent')
    monkeypatch.setattr(dsh_prepare, 'run', refuse)
    with pytest.raises(RuntimeError, match='capability absent'):
        entry.install(install_input, path)
    assert not Path(install_input['home']).exists()


@pytest.mark.parametrize('replacement', [None, {}, {'path':'/tmp/bwrap','sha256':'0'*64},
                                        {'path':'/usr/bin/bwrap','sha256':'0'*64}])
def test_no_unpinned_or_weaker_containment(install_input, replacement):
    install_input['containment'] = replacement
    with pytest.raises((ValueError, OSError)):
        entry.commands(install_input)
    assert not Path(install_input['home']).exists()


def test_original_intake_clock_precedes_claim(install_input, tmp_path, monkeypatch):
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    budget = AdmissionClock(30); original = entry.spec_checked
    def checked(value):
        result = original(value); budget.expired = True; return result
    monkeypatch.setattr(entry, 'spec_checked', checked)
    with pytest.raises(ValueError, match='budget_exhausted'):
        entry.install(install_input, path, budget=budget)
    assert not Path(install_input['home']).exists()


@pytest.mark.parametrize('phase', ['serialization', 'file_fsync', 'directory_fsync'])
def test_late_publication_never_returns_success(phase, tmp_path, monkeypatch):
    budget = AdmissionClock(30); path = tmp_path / 'receipt.json'
    if phase == 'serialization':
        original = entry.json.dumps
        def dumps(*a, **kw):
            result = original(*a, **kw); budget.expired = True; return result
        monkeypatch.setattr(entry.json, 'dumps', dumps)
    else:
        original = entry.os.fsync; calls = []
        def sync(fd):
            original(fd); calls.append(fd)
            if len(calls) == (1 if phase == 'file_fsync' else 2): budget.expired = True
        monkeypatch.setattr(entry.os, 'fsync', sync)
    with pytest.raises(ValueError, match='budget_exhausted'):
        entry.publish(path, {'state':'TEST_OBSERVATION'}, budget=budget)
    assert path.exists() == (phase != 'serialization')


def test_late_replace_is_observation_not_success(tmp_path):
    budget = AdmissionClock(30); pending = tmp_path / 'pending'; target = tmp_path / 'receipt'
    pending.write_text('admitted IO observation')
    def replace():
        os.replace(pending, target); budget.expired = True
    with pytest.raises(ValueError, match='budget_exhausted'):
        budget.call(replace)
    assert target.read_text() == 'admitted IO observation'


def test_cleanup_reserve_uses_original_deadline(install_input, tmp_path, monkeypatch):
    budget = custody.Budget(30)
    from scripts import dsh_prepare
    calls = []
    monkeypatch.setattr(dsh_prepare, 'run', lambda *a, **kw: (calls.append((a, kw)) or ('ok', {})))
    runner = custody.Containment(install_input['containment'], budget, {})
    runner.run(['/not-executed'], tmp_path, timeout=100)
    a, kw = calls[0]
    assert kw['deadline'] == budget.deadline
    assert 0 < kw['timeout'] < 29 and a[0][1:4] == ['--unshare-pid','--die-with-parent','--new-session']


def test_cleanup_deadline_failure_is_stop_unconfirmed(monkeypatch, tmp_path):
    import subprocess
    from scripts import dsh_prepare
    class Process:
        pid = 98765
        def communicate(self, timeout): raise subprocess.TimeoutExpired('synthetic', timeout)
    monkeypatch.setattr(dsh_prepare.subprocess, 'Popen', lambda *a, **k: Process())
    killed = []
    monkeypatch.setattr(dsh_prepare.os, 'killpg', lambda *a: killed.append(a))
    with pytest.raises(RuntimeError, match='STOP_UNCONFIRMED'):
        dsh_prepare.run(['/not-executed'], tmp_path, timeout=.1, deadline=time.monotonic()+1)
    assert killed == [(98765, dsh_prepare.signal.SIGKILL)]


def test_actual_original_30s_final_verification_refuses_success(install_input, tmp_path, monkeypatch):
    """Real minimum deadline, original clock, actual full source/config IO."""
    from test_native_installer import test_whole_finite_composition_and_completed_idempotence_with_native_config as fixture
    install_input['seconds'] = 30
    original_install = entry.install; original_check = entry.composition_checked
    clocks = {}; checks = []
    def install(value, path):
        budget = custody.Budget(30)
        clocks.update(started=time.monotonic(), deadline=budget.deadline)
        return original_install(value, path, budget=budget)
    def verify(*args, **kw):
        result = original_check(*args, **kw); checks.append(True)
        if len(checks) == 2:
            # Finite actual CPU delay at the originally uncovered boundary.
            while time.monotonic() <= clocks['deadline'] + .02: pass
        return result
    monkeypatch.setattr(entry, 'install', install)
    monkeypatch.setattr(entry, 'composition_checked', verify)
    with pytest.raises(ValueError, match='original_install_budget_exhausted'):
        fixture(install_input, tmp_path, monkeypatch)
    home = Path(install_input['home']); marker = entry.read_json(home / entry.MARKER)
    assert len(checks) == 2 and marker['state'] == 'PARTIAL'
    assert not (home / (entry.MARKER + '.completed')).exists()
    elapsed = time.monotonic() - clocks['started']; assert elapsed >= 30
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']) / 'original-30s-observation.json'
    evidence.write_text(json.dumps(dict(clocks, elapsed=elapsed, state=marker['state'],
        source_verifications=len(checks), clock_replaced=False, pm_build_runtime_executed=False), indent=2)+'\n')


@pytest.mark.parametrize('change', ['deadline', 'boot'])
def test_internal_completion_cannot_reset_original_claim(install_input, tmp_path, monkeypatch, change):
    from scripts import friday_native
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    home = Path(install_input['home']); home.mkdir(mode=0o700)
    budget = custody.Budget(30)
    claim = entry.partial_claim(entry.digest(path.read_bytes()), budget)
    deadline = budget.deadline
    if change == 'deadline': deadline += 5
    else: claim['boot_id'] = 'another-system-boot'
    entry.publish(home / entry.MARKER, claim)
    before = (home / entry.MARKER).read_bytes()
    monkeypatch.setattr('sys.argv', ['friday-native','install','--input',str(path),'--deadline',str(deadline)])
    with pytest.raises(ValueError, match='fresh_install_claim_required'):
        friday_native.main()
    assert (home / entry.MARKER).read_bytes() == before
    assert not (home / 'hermes-agent').exists()


@pytest.mark.parametrize('late_boundary', ['serialization', 'stdout_flush'])
def test_cli_checks_final_success_after_serialization_and_flush(install_input, tmp_path, monkeypatch, capsys, late_boundary):
    import builtins
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    budget = AdmissionClock(30)
    received = []
    def construct(seconds, *, started):
        assert started <= time.monotonic()
        received.append(started); return budget
    monkeypatch.setattr(custody, 'Budget', construct)
    def installed(*a, **kw):
        assert kw['budget'] is budget
        return {'state':'SYNTHETIC_RESULT_OBSERVATION'}
    monkeypatch.setattr(entry, 'install', installed)
    if late_boundary == 'serialization':
        original = entry.json.dumps
        def dumps(*a, **kw):
            result = original(*a, **kw); budget.expired = True; return result
        monkeypatch.setattr(entry.json, 'dumps', dumps)
    else:
        original = builtins.print
        def output(*a, **kw):
            assert kw.get('flush') is True
            original(*a, **kw); budget.expired = True
        monkeypatch.setattr(builtins, 'print', output)
    monkeypatch.setattr('sys.argv', ['friday','install','--input',str(path)])
    with pytest.raises(SystemExit) as exc: entry.main()
    assert exc.value.code == 2 and len(received) == 1
    captured = capsys.readouterr()
    assert ('SYNTHETIC_RESULT_OBSERVATION' in captured.out) == (late_boundary == 'stdout_flush')
    assert 'Friday entry refused' in captured.err


def test_command_return_after_original_deadline_is_refused(install_input, tmp_path, monkeypatch):
    from scripts import dsh_prepare
    budget = AdmissionClock(30)
    runner = custody.Containment(install_input['containment'], budget, {})
    def late(*a, **kw):
        budget.expired = True; return 'late observation', {}
    monkeypatch.setattr(dsh_prepare, 'run', late)
    with pytest.raises(ValueError, match='budget_exhausted'):
        runner.run(['/not-executed'], tmp_path)


@pytest.mark.parametrize('stage', ['probe', 'compose'])
@pytest.mark.parametrize('cause', ['unreaped', 'cleanup_budget_exhausted'])
def test_actual_cli_preserves_unknown_cessation_and_existing_claim(
        install_input, tmp_path, monkeypatch, capsys, stage, cause):
    from types import SimpleNamespace
    import subprocess
    from scripts import dsh_prepare
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    starts = []; killed = []; waits = []
    now = time.monotonic()
    class Process:
        pid = 98765
        returncode = 0
        def __init__(self): self.number = len(starts)
        def communicate(self, timeout):
            waits.append(timeout)
            if stage == 'compose' and self.number == 1:
                return 'FRIDAY_PID_NAMESPACE_OK', ''
            if cause == 'cleanup_budget_exhausted':
                monkeypatch.setattr(dsh_prepare, 'time', SimpleNamespace(monotonic=lambda: now + 8000))
            raise subprocess.TimeoutExpired('PRIVATE_PROCESS_CANARY', timeout)
    def spawn(*a, **kw):
        starts.append(True); return Process()
    monkeypatch.setattr(dsh_prepare.subprocess, 'Popen', spawn)
    monkeypatch.setattr(dsh_prepare.os, 'killpg', lambda *a: killed.append(a))
    monkeypatch.setattr('sys.argv', ['friday', 'install', '--input', str(path)])
    with pytest.raises(SystemExit) as exc: entry.main()
    out = capsys.readouterr()
    assert exc.value.code == 3 and not out.out
    assert out.err.startswith('STOP_UNCONFIRMED:') and 'do not retry' in out.err
    assert 'PRIVATE_PROCESS_CANARY' not in out.err and 'Traceback' not in out.err
    assert len(starts) == (1 if stage == 'probe' else 2)
    assert killed == [(98765, dsh_prepare.signal.SIGKILL)]
    assert len(waits) == len(starts) + (cause == 'unreaped')
    home = Path(install_input['home'])
    if stage == 'probe': assert not home.exists()
    else:
        claim = entry.read_json(home / entry.MARKER)
        assert claim['state'] == 'PARTIAL'
        assert claim['input_sha256'] == entry.digest(path.read_bytes())
        assert not (home / (entry.MARKER + '.completed')).exists()


def test_untrusted_error_text_cannot_impersonate_stop_status(install_input, tmp_path, monkeypatch, capsys):
    path = tmp_path / 'input.json'; entry.publish(path, install_input)
    def fail(*a, **kw): raise RuntimeError('STOP_UNCONFIRMED: PRIVATE_ERROR_CANARY')
    monkeypatch.setattr(custody.Containment, 'probe', fail)
    monkeypatch.setattr('sys.argv', ['friday', 'install', '--input', str(path)])
    with pytest.raises(SystemExit) as exc: entry.main()
    out = capsys.readouterr()
    assert exc.value.code == 2 and not out.out
    assert 'STOP_UNCONFIRMED' not in out.err and 'PRIVATE_ERROR_CANARY' not in out.err


def test_late_final_output_keeps_attempt_provenance_and_readonly_idempotence(install_input, tmp_path, monkeypatch):
    from test_native_installer import test_whole_finite_composition_and_completed_idempotence_with_native_config as fixture
    from scripts import dsh_prepare
    original_install = entry.install; original_replace = entry.os.replace
    budget = AdmissionClock(1800); home = Path(install_input['home'])
    def install(value, path): return original_install(value, path, budget=budget)
    def replace(src, dst, *a, **kw):
        out = original_replace(src, dst, *a, **kw)
        if Path(dst) == home / entry.MARKER: budget.expired = True
        return out
    monkeypatch.setattr(entry, 'install', install); monkeypatch.setattr(entry.os, 'replace', replace)
    with pytest.raises(ValueError, match='budget_exhausted'): fixture(install_input, tmp_path, monkeypatch)
    marker = entry.read_json(home / entry.MARKER)
    claim = marker['original_attempt']
    assert claim['state'] == 'PARTIAL' and claim['deadline_mono'] == budget.deadline
    assert claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert claim['input_sha256'] == entry.digest((tmp_path / 'input.json').read_bytes())
    assert marker['invocation_completion'] == 'NOT_PROVEN_BY_OUTPUT_RECEIPT'
    before = (home / entry.MARKER).read_bytes()
    def no_execution(*a, **kw): raise AssertionError('read-only inspection executed a command')
    monkeypatch.setattr(dsh_prepare, 'run', no_execution)
    out = original_install(install_input, tmp_path / 'input.json')
    assert out['effects'] == 'NONE' and out['ready'] is False
    assert out['invocation_completion'] == 'NOT_PROVEN_BY_OUTPUT_RECEIPT'
    assert (home / entry.MARKER).read_bytes() == before
