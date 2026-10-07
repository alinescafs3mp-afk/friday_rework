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
    assert stopped.value.observation is observation


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
