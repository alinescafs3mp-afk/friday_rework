"""Read-only policy and onboarding regressions.

These tests compare complete retained file inventories before and after native
policy reads, real afterimage preparation and refused foreign bindings. Run
against a coherent native source composition that includes the read-only policy
change; these definitions do not grant installation or runtime authority.
"""
import json
import os
import stat

import pytest

from hermes_yaml import safe_load
from hermes_cli import friday_user_scope as users
from hermes_cli.config_effective import read_user_config_effective_readonly
from hermes_cli.friday_product_access import settings
import test_stopped_worker_declarations as stopped
from test_stopped_worker_declarations import afterimage_case, normal_env, env
from test_user_onboarding import raw, save


def inventory(root):
    """Exact byte/mode/type inventory: no backup/lock exclusion or content dump."""
    result = {'.': ('directory', stat.S_IMODE(root.lstat().st_mode))}
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        name = str(path.relative_to(root))
        if stat.S_ISREG(info.st_mode):
            result[name] = ('file', mode, path.read_bytes())
        elif stat.S_ISDIR(info.st_mode):
            result[name] = ('directory', mode)
        elif stat.S_ISLNK(info.st_mode):
            result[name] = ('symlink', mode, os.readlink(path))
        else:
            result[name] = ('other', mode, stat.S_IFMT(info.st_mode), info.st_rdev)
    return result


def document(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)


def test_native_policy_reads_current_changed_file_without_retained_effects(tmp_path, monkeypatch):
    root = tmp_path / 'home'; root.mkdir(mode=0o700)
    monkeypatch.delenv('HERMES_MANAGED_DIR', raising=False)
    path = root / 'config.yaml'
    for canary in ('original', 'changed-current-file'):
        document(path, {'plugins': {'entries': {'friday_rework': {
            'settings': {'read_only_canary': canary}}}}})
        before = inventory(root)
        with users.authority(root):
            assert settings() == {'read_only_canary': canary}
            assert settings() == {'read_only_canary': canary}
        assert inventory(root) == before


@pytest.mark.parametrize('body', ['plugins: [', '[]', 'false'])
def test_native_policy_refuses_current_malformed_or_nonmapping_without_backup(tmp_path, monkeypatch, body):
    root = tmp_path / 'home'; root.mkdir(mode=0o700)
    monkeypatch.delenv('HERMES_MANAGED_DIR', raising=False)
    path = root / 'config.yaml'; path.write_text(body); path.chmod(0o600)
    before = inventory(root)
    with users.authority(root), pytest.raises(ValueError, match='product_configuration_unreadable'):
        settings()
    assert inventory(root) == before


@pytest.mark.parametrize('body', [None, '', 'null'])
def test_native_policy_first_run_keeps_managed_precedence_and_strict_diagnostic_contract(tmp_path, monkeypatch, body):
    root = tmp_path / 'home'; root.mkdir(mode=0o700)
    managed = tmp_path / 'managed'; managed.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_MANAGED_DIR', str(managed))
    monkeypatch.setenv('FRW_READONLY_SYNTHETIC_CANARY', 'managed-expanded')
    document(managed / 'config.yaml', {'plugins': {'entries': {'friday_rework': {
        'settings': {'read_only_canary': '${FRW_READONLY_SYNTHETIC_CANARY}'}}}}})
    path = root / 'config.yaml'
    if body is not None:
        path.write_text(body); path.chmod(0o600)
    before, managed_before = inventory(root), inventory(managed)
    with users.authority(root):
        assert settings() == {'read_only_canary': 'managed-expanded'}
    with pytest.raises((FileNotFoundError, ValueError)):
        read_user_config_effective_readonly(path)
    assert inventory(root) == before
    assert inventory(managed) == managed_before


def test_valid_changed_root_builds_real_five_afterimages_without_retained_effects(afterimage_case):
    case = afterimage_case
    root = raw(case.e)
    root['read_only_afterimage_canary'] = stopped.CANARY
    save(case.e, root)
    case.plan['root_config']['read_only_afterimage_canary'] = stopped.CANARY
    case.view.before['config.yaml'] = stopped.native_update.update_file_state(case.e.home / 'config.yaml')
    before = inventory(case.e.home)
    outputs = stopped.build(case)
    assert set(outputs) == case.names
    assert all(state['mode'] == 0o600 for state in outputs.values())
    assert inventory(case.e.home) == before
    assert safe_load(outputs['config.yaml']['data'])['read_only_afterimage_canary'] == stopped.CANARY


def test_foreign_binding_refusal_keeps_every_retained_byte_mode_and_member(afterimage_case):
    case = afterimage_case
    root = raw(case.e)
    stopped.get(root, ('plugins', 'entries', 'friday_rework', 'settings',
        'user_isolation', 'bindings'))[0]['user_id'] = 'foreign-user'
    save(case.e, root)
    before = inventory(case.e.home)
    with pytest.raises(PermissionError, match='managed_setup_access_missing'):
        stopped.build(case)
    assert inventory(case.e.home) == before


@pytest.mark.parametrize('gateway_damage', ['native-default', 'multiplex-disabled', 'route-missing'])
def test_real_native_onboarding_gateway_reads_keep_defaults_refusals_and_retained_inventory(afterimage_case, gateway_damage):
    case = afterimage_case
    root = raw(case.e)
    root['gateway'].pop('multiplex_profiles', None)
    if gateway_damage == 'multiplex-disabled':
        root['gateway']['multiplex_profiles'] = False
    elif gateway_damage == 'route-missing':
        root['gateway']['profile_routes'] = []
    save(case.e, root)
    before = inventory(case.e.home)
    with users.authority(case.e.home):
        if gateway_damage == 'native-default':
            users.check_onboarding_home(case.e.home, case.view.profile_home, case.view.binding)
            assert users.onboarding_profile_routes([])
        else:
            with pytest.raises(users.ScopeDenied):
                users.check_onboarding_home(case.e.home, case.view.profile_home, case.view.binding)
            if gateway_damage == 'multiplex-disabled':
                with pytest.raises(users.ScopeDenied):
                    users.onboarding_profile_routes([])
    assert inventory(case.e.home) == before
