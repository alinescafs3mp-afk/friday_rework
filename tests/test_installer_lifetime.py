"""The native monitor must witness init exit; its own death is insufficient."""
import os
import json
import pytest

from scripts import dsh_prepare, install_containment as custody


def metadata(code=0, timeout=False, reaped=True):
    return dict(returncode=code, timeout=timeout, reaped=reaped, elapsed_seconds=0,
                stdout_sha256='0'*64, stderr_sha256='0'*64, stdout_bytes=0,
                stderr_bytes=0, pid=123, starttime_ticks=456, reason='command_nonzero_exit')


def native_status(kwargs, code):
    os.write(kwargs['pass_fds'][0], (json.dumps({'child-pid': 123}) + '\n'
                                  + json.dumps({'exit-code': code}) + '\n').encode())


@pytest.mark.parametrize('code,timeout,reaped', [(3, False, True), (-9, False, True),
    (0, True, True), (2, True, True), (2, False, False)])
def test_uncertain_monitor_never_releases_family(monkeypatch, tmp_path, code, timeout, reaped):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    failure = dsh_prepare.CommandFailed(metadata(code, timeout, reaped))
    observation = failure.observation
    def failed(*args, **kwargs):
        native_status(kwargs, code)
        raise failure
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(dsh_prepare.StopUnconfirmed) as stopped:
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)
    assert stopped.value.observation == observation


def test_ordinary_nonzero_retains_real_diagnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    failure = dsh_prepare.CommandFailed(metadata(2))
    def failed(*args, **kwargs):
        native_status(kwargs, 2)
        raise failure
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(RuntimeError) as error:
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)
    assert error.value is failure
    assert error.value.observation['namespace_init_exit_verified'] is True


@pytest.mark.parametrize('failure', [RuntimeError('old status unavailable'),
    OSError('transport failed'), KeyboardInterrupt()])
def test_missing_monitor_status_retains_custody(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    def failed(*args, **kwargs): raise failure
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(dsh_prepare.StopUnconfirmed):
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)


def test_finite_command_is_namespace_init():
    args = custody.argv('/usr/bin/bwrap', ['/reviewed/native', 'install'])
    assert '--unshare-pid' in args and '--as-pid-1' in args
    assert '--die-with-parent' in args
    assert args[args.index('--') + 1:] == ['/reviewed/native', 'install']


def test_read_only_uses_same_native_boundary_and_original_deadline(monkeypatch, tmp_path):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    budget = custody.Budget(30)
    calls = []
    def returned(args, cwd, **kwargs):
        calls.append((args, kwargs))
        native_status(kwargs, 0)
        return 'checked', metadata()
    monkeypatch.setattr(dsh_prepare, 'run', returned)
    result, proof = custody.Containment({}, budget, {}).run(
        ['/reviewed/python', '-B', 'verify'], tmp_path, timeout=5,
        read_only=True, log=tmp_path / 'private-preflight')
    args, options = calls[0]
    assert args.count('/usr/bin/bwrap') == 1
    assert '--ro-bind' in args and '--bind' not in args
    assert all(flag in args for flag in ('--as-pid-1', '--unshare-pid', '--die-with-parent'))
    assert args[args.index('--') + 1:] == ['/reviewed/python', '-B', 'verify']
    assert options['deadline'] == budget.deadline and options['timeout'] == 5
    assert options['log'] == tmp_path / 'private-preflight'
    assert result == 'checked' and proof['namespace_init_exit_verified'] is True


@pytest.mark.parametrize('flag', [None, 0, 1, 'false', 'true'])
def test_read_only_mode_does_not_accept_ambiguous_values(flag):
    with pytest.raises(ValueError, match='explicit_read_only_boolean_required'):
        custody.argv('/usr/bin/bwrap', ['/not-run'], read_only=flag)


def test_read_only_refusal_never_retries_writable(monkeypatch, tmp_path):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    calls = []
    def refused(args, cwd, **kwargs):
        calls.append(args)
        native_status(kwargs, 1)
        raise dsh_prepare.CommandFailed(metadata(1))
    monkeypatch.setattr(dsh_prepare, 'run', refused)
    with pytest.raises(dsh_prepare.CommandFailed) as failure:
        custody.Containment({}, custody.Budget(30), {}).run(
            ['/not-run'], tmp_path, read_only=True)
    assert len(calls) == 1 and '--ro-bind' in calls[0]
    assert failure.value.observation['namespace_init_exit_verified'] is True


@pytest.mark.parametrize('wire', [b'', b'{"exit-code":0}\n', b'{"child-pid":123}\n',
    b'{"child-pid":123}\n{"exit-code":1}\n', b'{"child-pid":true}\n{"exit-code":0}\n',
    b'{"child-pid":123}\n{"exit-code":false}\n', b'garbage', b'x'*4097])
def test_absent_or_wrong_native_barrier_refuses_even_zero_exit(monkeypatch, tmp_path, wire):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    def returned(*args, **kwargs):
        os.write(kwargs['pass_fds'][0], wire)
        return 'output', metadata()
    monkeypatch.setattr(dsh_prepare, 'run', returned)
    with pytest.raises(dsh_prepare.StopUnconfirmed):
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)


def test_native_barrier_allows_real_result_and_closes_descriptor(monkeypatch, tmp_path):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    fds = []
    def returned(args, *rest, **kwargs):
        fds.extend(kwargs['pass_fds'])
        assert args[args.index('--json-status-fd')+1] == str(fds[0])
        native_status(kwargs, 0)
        return 'result', metadata()
    monkeypatch.setattr(dsh_prepare, 'run', returned)
    result, observed = custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)
    assert result == 'result' and observed['namespace_init_exit_verified'] is True
    with pytest.raises(OSError): os.fstat(fds[0])


@pytest.mark.parametrize('wire', [b'', b'{"child-pid":123}\n{"exit-code":1}\n'])
def test_successful_monitor_with_invalid_status_redacts_failure_receipt(monkeypatch, tmp_path, wire):
    from scripts.friday_install import safe_diagnostic
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    private = 'PRIVATE_ARGV_OR_OUTPUT_CANARY'
    def returned(*args, **kwargs):
        os.write(kwargs['pass_fds'][0], wire)
        return private, dict(metadata(), argv=[private], stdout=private, env={'KEY': private})
    monkeypatch.setattr(dsh_prepare, 'run', returned)
    with pytest.raises(dsh_prepare.StopUnconfirmed) as stopped:
        custody.Containment({}, custody.Budget(30), {}).run([private], tmp_path)
    assert private not in json.dumps(stopped.value.observation)
    # Even an accidentally enriched exception must not expose extra metadata.
    stopped.value.observation.update(argv=[private], stderr=private)
    receipt = safe_diagnostic(stopped.value, 'compose')
    assert private not in json.dumps(receipt)
    assert receipt['reason'] == 'stop_unconfirmed'
    assert receipt['cessation'] == 'UNCONFIRMED'
    assert receipt['returncode'] == 0 and receipt['reaped'] is True
