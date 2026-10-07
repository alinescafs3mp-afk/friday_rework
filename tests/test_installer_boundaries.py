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
