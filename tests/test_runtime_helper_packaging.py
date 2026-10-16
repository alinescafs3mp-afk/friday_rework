"""Installed plugin helpers retain one implementation and local type identity."""
import importlib
import sys
import subprocess
import textwrap
from pathlib import Path

import pytest
from hermes_cli.plugin_host_child import _import_plugin
from scripts import dsh_prepare, friday_install, install_containment, worker_qualification


def test_installer_exports_share_runtime_objects():
    runtime_primitives = friday_install._source_runtime_module('runtime_primitives')
    runtime_process = friday_install._source_runtime_module('runtime_process')
    runtime_containment = friday_install._source_runtime_module('runtime_containment')
    runtime_observers = friday_install._source_runtime_module('runtime_observers')
    for name in ('Refused', 'require', 'canonical', 'owned_file', 'unique', 'read_json', 'digest', 'pin'):
        assert getattr(friday_install, name) is getattr(runtime_primitives, name)
    for name in ('StopUnconfirmed', 'CommandFailed', 'safe_observation', 'clean_environment', 'run'):
        assert getattr(dsh_prepare, name) is getattr(runtime_process, name)
    for name in ('Budget', 'Containment', 'checked_binary', 'argv', 'namespace_exit'):
        assert getattr(install_containment, name) is getattr(runtime_containment, name)
    for name in ('a0_observe', 'dsh_observe', 'dsh_safety_observe', 'checked_dsh_safety'):
        assert getattr(worker_qualification, name) is getattr(runtime_observers, name)
    assert friday_install.safe_diagnostic(dsh_prepare.StopUnconfirmed(), 'qualification')['reason'] == 'stop_unconfirmed'
    error = runtime_primitives.Refused('observer_refused')
    assert friday_install.safe_diagnostic(error, 'qualification')['reason'] == 'observer_refused'


@pytest.mark.parametrize('alias', ['hermes_plugins.friday_rework', 'hermes_plugins.friday_rework__home_deadbeef'])
def test_native_alias_resolves_late_imports_with_local_class_identity(alias, monkeypatch, tmp_path):
    plugin = Path(__file__).resolve().parents[1] / 'plugins/friday_rework'
    module = _import_plugin({'path': str(plugin), 'module_name': alias, 'name': 'friday_rework'})
    assert module.__name__ == alias
    join = importlib.import_module(alias + '.user_worker_join')
    hr = importlib.import_module(alias + '.host_runtime')
    observers = importlib.import_module(alias + '.runtime_observers')
    process = importlib.import_module(alias + '.runtime_process')
    containment = importlib.import_module(alias + '.runtime_containment')
    dsh = importlib.import_module(alias + '.adapters.dsh')
    assert join.HostUnavailable is hr.HostUnavailable
    assert hr.DshHostConfig is dsh.DshHostConfig
    assert process.StopUnconfirmed.__module__ == alias + '.runtime_process'
    before = set(sys.modules)
    with pytest.raises(hr.HostUnavailable, match='both_worker_preparations_required'):
        join.qualify(tmp_path, {'runtime_profile': 'fixture'}, 1, {}, verify=lambda: pytest.fail('effect'))

    class BeforeEffect(Exception):
        pass

    def stop(*args, **kwargs):
        raise BeforeEffect()

    monkeypatch.setattr(hr, 'a0_deployment_contract', stop)
    with pytest.raises(BeforeEffect):
        observers.a0_observe({}, {}, None)
    monkeypatch.setattr(hr, '_dsh_web', stop)
    with pytest.raises(BeforeEffect):
        observers.dsh_observe({'dsh': {}}, tmp_path, tmp_path, None)
    # Both observers completed all late imports before the sentinels.
    assert not any(name.startswith(('scripts.', 'plugins.friday_rework.')) for name in set(sys.modules) - before)
    assert containment.Containment.__module__ == alias + '.runtime_containment'


def test_source_helpers_leave_native_packages_cold_and_keep_project_pins(tmp_path):
    root = Path(__file__).resolve().parents[1]
    native = tmp_path / 'native'
    for name in ('tools', 'plugins'):
        package = native / name
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('NATIVE_PACKAGE = True\n')
    code = textwrap.dedent("""
        import hashlib, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from scripts import friday_install as f, dsh_prepare as d, install_containment as c, worker_qualification as q
        assert 'plugins' not in sys.modules and 'tools' not in sys.modules
        assert f.Refused is f._source_runtime_module('runtime_primitives').Refused
        assert d.StopUnconfirmed is f._source_runtime_module('runtime_process').StopUnconfirmed
        assert c.Containment is f._source_runtime_module('runtime_containment').Containment
        assert q.a0_observe is f._source_runtime_module('runtime_observers').a0_observe
        assert f.safe_diagnostic(d.StopUnconfirmed(), 'qualification')['reason'] == 'stop_unconfirmed'
        files = {str(p.relative_to(f.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (f.ROOT / 'plugins/friday_rework').rglob('*.py')}
        value = {'project_files': files}
        f.project_plugin('runtime_observers', value)
        assert 'plugins' not in sys.modules and 'tools' not in sys.modules
        files['plugins/friday_rework/runtime_process.py'] = '0' * 64
        try:
            f.project_plugin('runtime_observers', value)
        except f.Refused as exc:
            assert exc.reason == 'project_source_changed'
        else:
            raise AssertionError('changed source accepted')
        f.native_packages(Path(sys.argv[2]))
        for name in ('plugins', 'tools'):
            module = sys.modules[name]
            assert module.NATIVE_PACKAGE
            assert module.__file__ == str(Path(sys.argv[2]) / name / '__init__.py')
    """)
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(root), str(native)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kind', ['package', 'module'])
def test_source_runtime_refuses_foreign_private_namespace(kind):
    root = Path(__file__).resolve().parents[1]
    code = textwrap.dedent("""
        import sys, types
        sys.path.insert(0, sys.argv[1])
        from scripts import friday_install as f
        alias = '_friday_install_validation_plugins'
        if sys.argv[2] == 'package':
            sys.modules[alias].__path__ = ['/foreign/plugins']
            expected = 'foreign_validator_package'
        else:
            foreign = types.ModuleType(alias + '.foreign')
            foreign.__file__ = '/foreign/module.py'
            sys.modules[foreign.__name__] = foreign
            expected = 'foreign_validator_module'
        try:
            f._source_runtime_module('runtime_process')
        except ValueError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError('foreign validator accepted')
    """)
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(root), kind],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
