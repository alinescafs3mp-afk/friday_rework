"""Actual entry boundaries and conservative failure/clock reconciliation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from scripts import friday_install as entry, install_containment as custody, dsh_prepare
from test_native_installer import install_input


def input_file(tmp_path, value):
    path = tmp_path / 'input.json'
    entry.publish(path, value)
    return path


def claim_home(value, path, *, seconds=30):
    home = Path(value['home']); home.mkdir(mode=0o700)
    claim = entry.partial_claim(entry.digest(path.read_bytes()), custody.Budget(seconds))
    entry.publish(home / entry.MARKER, claim)
    return home, claim


@pytest.mark.parametrize('command', [['/reviewed/python', '-B', '/reviewed/helper.py'], ['git', 'rev-parse', 'HEAD']])
def test_containment_has_private_devices_and_same_lifetime(command):
    args = custody.argv('/usr/bin/bwrap', command)
    assert args[:4] == ['/usr/bin/bwrap', '--unshare-pid', '--die-with-parent', '--new-session']
    assert args[args.index('--dev') + 1] == '/dev'
    assert '--dev-bind' not in args and args[args.index('--') + 1:] == command


def test_probe_checks_real_device_io_before_home_admission(install_input, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(dsh_prepare, 'run', lambda args, *a, **k: (calls.append(args) or ('FRIDAY_PID_NAMESPACE_OK', {})))
    custody.Containment(install_input['containment'], custody.Budget(30), {}).probe('/bootstrap', tmp_path)
    code = calls[0][-1]
    assert 'os.O_RDWR' in code and 'os.read(fd,1)' in code and 'os.write(fd,b"probe")' in code


def test_native_source_consumer_does_not_reinterpret_host_uid_but_admission_checks_it(install_input, tmp_path, monkeypatch):
    def refuse(*a): raise ValueError('protected_system_bubblewrap_required')
    monkeypatch.setattr(custody, 'checked_binary', refuse)
    # This consumer performs no command or weaker launcher selection.
    home, _ = entry.spec_checked(install_input)
    assert str(home) == install_input['home']
    with pytest.raises(ValueError, match='protected_system_bubblewrap_required'):
        entry.commands(install_input)
    with pytest.raises(ValueError, match='protected_system_bubblewrap_required'):
        entry.install(install_input, input_file(tmp_path, install_input))
    assert not home.exists()


@pytest.mark.parametrize('code,stderr,reason', [
    (128, "fatal: could not open '/dev/null' for reading and writing: Permission denied\n", 'device_null_unavailable'),
    (2, 'FRIDAY_SOURCE_REFUSED reason=git_source_operation_failed\n', 'source_git_operation_failed'),
    (2, 'FRIDAY_SOURCE_REFUSED reason=secret_canary\n', 'command_nonzero_exit'),
    (17, 'Authorization: Bearer SECRET_CANARY /private/credential.key\n', 'command_nonzero_exit'),
])
def test_reaped_failures_keep_metadata_not_argv_or_raw_output(monkeypatch, tmp_path, code, stderr, reason):
    class Process:
        pid = 98765
        returncode = code
        def communicate(self, timeout): return 'SECRET_STDOUT', stderr
    monkeypatch.setattr(dsh_prepare.subprocess, 'Popen', lambda *a, **k: Process())
    with pytest.raises(dsh_prepare.CommandFailed) as failed:
        dsh_prepare.run(['/private/SECRET_ARGV'], tmp_path)
    observation = failed.value.observation
    assert observation['returncode'] == code and observation['reaped'] is True
    assert observation['reason'] == reason and observation['stderr_sha256'] == hashlib.sha256(stderr.encode()).hexdigest()
    assert observation['stdout_bytes'] == len('SECRET_STDOUT')
    assert not any(x in str(failed.value) + json.dumps(observation) for x in ('SECRET_', 'Authorization', '/private/', 'argv'))


@pytest.mark.parametrize('child_code,reason', [(128, 'device_null_unavailable'), (3, 'stop_unconfirmed')])
def test_cli_failed_phase_original_identity_and_custody(install_input, tmp_path, monkeypatch, capsys, child_code, reason):
    path = input_file(tmp_path, install_input); calls = []
    class Process:
        pid = 98765
        def __init__(self):
            self.returncode = 0 if not calls else child_code
            calls.append(self)
        def communicate(self, timeout):
            if self.returncode == 0: return 'FRIDAY_PID_NAMESPACE_OK', ''
            return 'PRIVATE_STDOUT', "fatal: could not open '/dev/null' for reading and writing: Permission denied\nPRIVATE_CANARY"
    monkeypatch.setattr(dsh_prepare.subprocess, 'Popen', lambda *a, **k: Process())
    monkeypatch.setattr(sys, 'argv', ['friday', 'install', '--input', str(path)])
    with pytest.raises(SystemExit) as failed: entry.main()
    out = capsys.readouterr()
    assert failed.value.code == (3 if child_code == 3 else 2)
    assert 'phase=compose' in out.err and f'reason={reason}' in out.err
    assert f'child_exit={child_code}' in out.err and 'reaped=true' in out.err
    assert 'attempt=' + entry.digest(path.read_bytes()) in out.err
    assert 'PRIVATE_' not in out.err and not out.out
    home = Path(install_input['home']); original = (home / entry.MARKER).read_bytes()
    failure = entry.read_json(home / entry.FAILURE)
    assert failure['original_attempt'] == entry.read_json(home / entry.MARKER)
    assert failure['resume_allowed'] is False and failure['diagnostic']['phase'] == 'compose'
    result = entry.reconcile(install_input, entry.digest(path.read_bytes()))
    assert result['resume_allowed'] is False and result['historical_failure_receipt_bound'] is True
    with pytest.raises(ValueError, match='partial_install_requires_reconciliation'):
        entry.install(install_input, path)
    assert len(calls) == 2 and (home / entry.MARKER).read_bytes() == original


@pytest.mark.parametrize('case', ['live_clock', 'expired_clock', 'retained_work', 'pause', 'cancel'])
def test_partial_observation_is_readonly_and_never_resets_or_admits(install_input, tmp_path, monkeypatch, case):
    path = input_file(tmp_path, install_input); home, claim = claim_home(install_input, path)
    if case == 'expired_clock':
        claim['deadline_mono'] = time.monotonic() - 1
        (home / entry.MARKER).write_text(json.dumps(claim))
    if case in ('retained_work', 'pause', 'cancel'):
        (home / case).write_text('retain exact stop/work intent')
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    monkeypatch.setattr(dsh_prepare, 'run', lambda *a, **k: pytest.fail('reconciliation launched a command'))
    result = entry.reconcile(install_input, entry.digest(path.read_bytes()))
    assert result['original_attempt'] == claim and result['resume_allowed'] is False and result['ready'] is False
    assert result['original_budget_expired'] == (case == 'expired_clock')
    assert result['contains_other_files'] == (case in ('retained_work', 'pause', 'cancel'))
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


@pytest.mark.parametrize('change,reason', [('boot', 'original_install_boot_changed'), ('input', 'exact_original_partial'),
    ('state', 'exact_original_partial'), ('deadline_nan', 'original_install_deadline'), ('deadline_bool', 'original_install_deadline'),
    ('claim_link', 'real_absolute_path'), ('receipt', 'failure_receipt_not_bound')])
def test_changed_partial_or_ambiguous_receipt_refuses(install_input, tmp_path, change, reason):
    path = input_file(tmp_path, install_input); home, claim = claim_home(install_input, path)
    marker = home / entry.MARKER
    if change == 'boot': claim['boot_id'] = 'old-boot'
    elif change == 'input': claim['input_sha256'] = '0' * 64
    elif change == 'state': claim['state'] = 'CANCELLED'
    elif change == 'deadline_nan': claim['deadline_mono'] = float('nan')
    elif change == 'deadline_bool': claim['deadline_mono'] = True
    elif change == 'receipt': entry.publish(home / entry.FAILURE, {'original_attempt': 'foreign'})
    elif change == 'claim_link':
        marker.rename(home / 'saved-claim'); marker.symlink_to(home / 'saved-claim')
    if change != 'claim_link': marker.write_text(json.dumps(claim))
    before = marker.read_bytes()
    with pytest.raises(ValueError, match=reason): entry.reconcile(install_input, entry.digest(path.read_bytes()))
    assert marker.read_bytes() == before


@pytest.mark.parametrize('script', ['friday_install.py', 'friday_native.py', 'hermes_prepare.py', 'dsh_prepare.py'])
def test_actual_clean_cli_help_without_preloaded_project_packages(tmp_path, script):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE'])
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts' / script), '--help'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=8)
    assert result.returncode == 0 and 'usage:' in result.stdout and not result.stderr


@pytest.mark.parametrize('phase', ['plan', 'install', 'check', 'reconcile', 'start'])
def test_actual_bare_cli_refusal_does_not_echo_private_input(tmp_path, phase):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); path = tmp_path / 'private-input.json'
    path.write_text('{"password":"PRIVATE_CREDENTIAL_CANARY"}'); path.chmod(0o600)
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts/friday_install.py'),
                             phase, '--input', str(path)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=8)
    assert result.returncode == 2 and 'Friday entry refused:' in result.stderr
    assert 'PRIVATE_' not in result.stderr and 'Traceback' not in result.stderr and not result.stdout


def test_actual_reconcile_cli_uses_original_attempt_without_source_or_secret_reads(install_input, tmp_path):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); path = input_file(tmp_path, install_input)
    home, claim = claim_home(install_input, path); before = (home / entry.MARKER).read_bytes()
    # Even deliberately unusable credential/source references are not opened.
    install_input['dashboard_tls'] = {'keyfile': {'path': '/forbidden/private.key', 'sha256': '0' * 64}}
    path.write_text(json.dumps(install_input)); claim['input_sha256'] = entry.digest(path.read_bytes())
    (home / entry.MARKER).write_text(json.dumps(claim)); before = (home / entry.MARKER).read_bytes()
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts/friday_install.py'),
                             'reconcile', '--input', str(path)], cwd=tmp_path,
                            env={'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'},
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['original_attempt'] == claim and out['resume_allowed'] is False
    assert (home / entry.MARKER).read_bytes() == before and '/forbidden/' not in result.stdout


def test_actual_cli_plan_validates_current_inventory_without_native_package_preload(install_input, tmp_path):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); path = input_file(tmp_path, install_input)
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts/friday_install.py'),
                             'plan', '--input', str(path)], cwd=tmp_path,
                            env={'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'},
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['state'] == 'PLANNED_NOT_EXECUTED' and out['ready'] is False
    assert out['commands']['tools'][3:] == ['pm.cli', 'install', '--tools-only']
    assert not Path(install_input['home']).exists()


@pytest.mark.parametrize('script', ['friday_install.py', 'friday_native.py', 'hermes_prepare.py'])
def test_actual_cli_invalid_arguments_do_not_echo_private_values(tmp_path, script):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE'])
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts' / script),
                             '--PRIVATE_CREDENTIAL_CANARY=/private/secret.key'], cwd=tmp_path,
                            env={'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'},
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 2 and 'invalid_cli_arguments' in result.stderr
    assert 'PRIVATE_' not in result.stderr and '/private/' not in result.stderr and 'Traceback' not in result.stderr


def test_source_cli_retained_destination_refuses_without_export_or_traceback(tmp_path):
    evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); destination = tmp_path / 'retained'; destination.mkdir()
    (destination / 'owner-work').write_text('preserve')
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'), str(entry.ROOT / 'scripts/hermes_prepare.py'),
                             '--repository', str(entry.ROOT), '--donor', str(tmp_path / 'absent'),
                             '--destination', str(destination), '--seconds', '5'], cwd=tmp_path,
                            env={'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'},
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 2 and result.stderr.strip() == 'FRIDAY_SOURCE_REFUSED reason=fresh_destination_required'
    assert not result.stdout and (destination / 'owner-work').read_text() == 'preserve'
