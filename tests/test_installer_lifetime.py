"""The native monitor must witness init exit; its own death is insufficient."""
import pytest

from scripts import dsh_prepare, install_containment as custody


@pytest.mark.parametrize('code,timeout,reaped', [(3, False, True), (-9, False, True),
    (0, True, True), (2, True, True), (2, False, False)])
def test_uncertain_monitor_never_releases_family(monkeypatch, tmp_path, code, timeout, reaped):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    observation = {'returncode': code, 'timeout': timeout, 'reaped': reaped}
    failure = RuntimeError('opaque native failure'); failure.observation = observation
    def failed(*args, **kwargs): raise failure
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(dsh_prepare.StopUnconfirmed) as stopped:
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)
    assert stopped.value.observation is observation


def test_ordinary_nonzero_retains_real_diagnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(custody, 'checked_binary', lambda pin: '/usr/bin/bwrap')
    failure = RuntimeError('stable diagnostic')
    failure.observation = {'returncode': 2, 'timeout': False, 'reaped': True}
    def failed(*args, **kwargs): raise failure
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(RuntimeError) as error:
        custody.Containment({}, custody.Budget(30), {}).run(['unused'], tmp_path)
    assert error.value is failure


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
