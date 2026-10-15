"""Effect-free controls: extract lifecycle functions without importing facade."""
import ast
import os
from pathlib import Path
import sys
import types

import pytest

SOURCE = Path(os.environ['FRIDAY_NATIVE_SOURCE']).resolve() / 'tools/browser_tool_lifecycle.py'


class NoLegacyAccess:
    def __getattr__(self, name):
        raise AssertionError('legacy access: ' + name)


@pytest.fixture
def lifecycle(monkeypatch):
    names = {'_scoped_lifecycle_only', '_emergency_cleanup_all_sessions',
             '_reap_orphaned_browser_sessions', '_start_browser_cleanup_thread',
             'cleanup_all_browsers'}
    source = ast.parse(SOURCE.read_text())
    tree = ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef)
                            and n.name in names], type_ignores=[])
    calls = []
    users = types.SimpleNamespace(_ENGAGED=True, current=lambda: None)
    monkeypatch.setitem(sys.modules, 'hermes_cli', types.SimpleNamespace(friday_user_scope=users))
    scoped = types.SimpleNamespace(cleanup=lambda: calls.append('owned_cleanup') or {'status': 'QUIESCENT'})
    monkeypatch.setitem(sys.modules, 'tools.browser_scoped', scoped)
    class AbsentMarker:
        def __truediv__(self, name):
            assert name == 'FRIDAY-INSTALL.json'
            return self
        def lstat(self):
            raise FileNotFoundError
    namespace = {'_bt': NoLegacyAccess(), '_real_profile': NoLegacyAccess(),
                 'Path': lambda unused: AbsentMarker(), 'get_hermes_home': lambda: 'fake-home'}
    exec(compile(tree, str(SOURCE), 'exec'), namespace)
    return namespace, users, scoped, calls


@pytest.mark.parametrize('entry', ['_emergency_cleanup_all_sessions',
                                 '_reap_orphaned_browser_sessions',
                                 '_start_browser_cleanup_thread', 'cleanup_all_browsers'])
def test_scoped_after_context_exit_never_touches_legacy_or_shared_processes(lifecycle, entry):
    namespace, users, scoped, calls = lifecycle
    assert users.current() is None  # ContextVar already reset at atexit.
    assert users._ENGAGED is True  # Native admission remains engaged.
    namespace[entry]()
    assert calls == (['owned_cleanup'] if entry in {
        '_emergency_cleanup_all_sessions', 'cleanup_all_browsers'} else [])


def test_active_scope_also_refuses_legacy_without_sticky_flag(lifecycle):
    namespace, users, scoped, calls = lifecycle
    users._ENGAGED = False
    users.current = lambda: object()
    namespace['_emergency_cleanup_all_sessions']()
    assert calls == ['owned_cleanup']


@pytest.mark.parametrize('marker', ['present', 'malformed', 'symlink', 'permission_error'])
def test_installed_host_before_first_user_never_enters_shared_cleanup(lifecycle, marker):
    namespace, users, scoped, calls = lifecycle
    users._ENGAGED = False
    users.current = lambda: None
    class ExistingMarker:
        def __truediv__(self, name):
            assert name == 'FRIDAY-INSTALL.json'
            return self
        def lstat(self):
            if marker == 'permission_error':
                raise PermissionError
            return object()  # Contents/type cannot grant shared cleanup.
    namespace['Path'] = lambda unused: ExistingMarker()
    for entry in ('_emergency_cleanup_all_sessions', '_reap_orphaned_browser_sessions',
                  '_start_browser_cleanup_thread', 'cleanup_all_browsers'):
        namespace[entry]()
    assert calls == ['owned_cleanup', 'owned_cleanup']


@pytest.mark.parametrize('entry', ['_emergency_cleanup_all_sessions', 'cleanup_all_browsers'])
def test_unconfirmed_owned_cleanup_never_falls_back_to_shared_sweep(lifecycle, entry):
    namespace, users, scoped, calls = lifecycle
    scoped.cleanup = lambda: {'status': 'STOP_UNCONFIRMED'}
    with pytest.raises(RuntimeError, match='STOP_UNCONFIRMED'):
        namespace[entry]()


def test_missing_shutdown_authority_fails_closed(lifecycle, monkeypatch):
    namespace, users, scoped, calls = lifecycle
    monkeypatch.setitem(sys.modules, 'hermes_cli', None)
    namespace['_emergency_cleanup_all_sessions']()
    assert calls == ['owned_cleanup']


def test_unmanaged_emergency_cleanup_preserves_native_actions_with_fakes(lifecycle):
    namespace, users, scoped, calls = lifecycle
    users._ENGAGED = False
    users.current = lambda: None
    assert namespace['_scoped_lifecycle_only']() is False
    namespace['_bt'] = types.SimpleNamespace(_cleanup_done=False, _active_sessions={})
    namespace['_real_profile'] = types.SimpleNamespace(
        _terminate_real_profile_chrome=lambda: calls.append('real_profile'))
    namespace['_stop_all_lightpanda'] = lambda: calls.append('lightpanda')
    namespace['_reap_orphaned_browser_sessions'] = lambda: calls.append('shared_reap')
    namespace['_best_effort'] = lambda label, action: action()
    namespace['_emergency_cleanup_all_sessions']()
    assert calls == ['real_profile', 'lightpanda', 'shared_reap']
    assert namespace['_bt']._cleanup_done is True


def test_facade_atexit_registration_targets_guarded_lifecycle():
    facade = ast.parse(SOURCE.with_name('browser_tool.py').read_text())
    registrations = [n for n in ast.walk(facade) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'register'
                     and isinstance(n.func.value, ast.Name) and n.func.value.id == 'atexit']
    assert any(isinstance(n.args[0], ast.Attribute)
               and n.args[0].attr == '_emergency_cleanup_all_sessions' for n in registrations)
