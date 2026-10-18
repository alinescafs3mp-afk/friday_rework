"""Native CLI principal/store controls with the process's actual numeric UID.

No UID, admission, current_cli, users.current or is_cli predicate is mocked.
The real operator creates one private CLI binding; no CLI process is started.
"""
import contextvars

import pytest

from hermes_cli import config as native, friday_product_access as policy
from hermes_cli import friday_cli_principal as cli
from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_cli_work import is_cli
from hermes_cli.plugins_state import PluginState
from test_user_onboarding import env as env
from test_user_onboarding import cas, home, raw
from test_operator_metadata_controls import engaged, snapshot, request_prepare
from friday_admin_controls.associations import Associations, AssociationError


def configure_cli_account(env):
    config = raw(env)
    account = dict(platform='cli', transport_profile='default', account_id='local-os',
        runtime_profiles=['default'])
    config['plugins']['entries']['friday_rework']['settings']['product_access']['accounts'].append(account)
    native.atomic_config_replace(env.home / 'config.yaml', config)


def cli_identity():
    return dict(platform='cli', transport_profile='default', account_id='local-os', user_id='local-current')


def prepare_cli(env, uid):
    return env.setup.prepare('default', session=env.operator,
        expected_config_sha256=cas(env), template='approved-local',
        runtime_profile='cli-current', uid=uid, **cli_identity())


@pytest.fixture
def local_cli(env):
    engaged(env)
    configure_cli_account(env)
    actual_uid = cli.numeric_os_uid()
    result = prepare_cli(env, actual_uid)
    generation = result['generation']
    assert result['uid'] == actual_uid and result['enabled'] is False
    for name in env.template['required_secrets']:
        env.setup.credentials('default', session=env.operator,
            expected_config_sha256=cas(env), generation=generation,
            name=name, value='synthetic-cli-' + name, **cli_identity())
    activated = env.setup.activate('default', session=env.operator,
        expected_config_sha256=cas(env), generation=generation, **cli_identity())
    assert activated['enabled'] is True
    directory = env.home / 'profiles' / 'cli-current'
    assert (directory / scope.MARKER).is_file()
    yield env, directory, actual_uid


def run_in_real_cli(fixture, operation):
    env, directory, actual_uid = fixture
    # Native initialize_cli owns capability minting. A temporary copied Context
    # limits its native ContextVar setters' lifetime without resetting guards,
    # forging a capability or affecting the parent ordinary context.
    def run():
        with scope.authority(directory):
            cap = cli.initialize_cli()
            assert cap is cli.current_cli(required=True)
            assert cap.os_uid == actual_uid == cli.numeric_os_uid()
            assert cap.principal == ('cli', 'default', 'local-os', 'local-current')
            assert cap.home == directory and cap.authorization_home == env.home
            return operation(env, cap)
    return contextvars.copy_context().run(run)


def test_real_numeric_uid_native_cli_capability_and_store_remain_usable(local_cli):
    def operation(env, cap):
        assert is_cli() is True and scope.current() is cap
        state = PluginState('friday_rework')
        store = Associations(state)
        store.state_set('cli_control_canary', {'owner': 'CURRENT_CLI_ONLY'})
        assert store.state_get('cli_control_canary') == {'owner': 'CURRENT_CLI_ONLY'}
        assert state.data_dir == cap.home / 'plugin-data' / state._data_namespace
        with scope.authority(env.home):
            assert env.state.get('cli_control_canary') is None
        assert cli.current_cli(required=True) is cap
        before = snapshot(env.home)
        with pytest.raises(PermissionError, match='operator_source_scope_required'):
            request_prepare(env)
        assert snapshot(env.home) == before
        assert cli.current_cli(required=True) is cap
    run_in_real_cli(local_cli, operation)


def test_actual_foreign_numeric_uid_operator_provisioning_refuses_before_target_write(env):
    engaged(env)
    configure_cli_account(env)
    before = snapshot(env.home)
    actual_uid = cli.numeric_os_uid()
    with pytest.raises(PermissionError, match='foreign_cli_uid_owner_contract_unsupported'):
        prepare_cli(env, actual_uid + 1)
    assert snapshot(env.home) == before
    assert not (env.home / 'profiles' / 'cli-current').exists()
    assert len(policy.current_access(env.state)['users']) == 1


def test_actual_foreign_numeric_uid_policy_does_not_admit_current_process(local_cli):
    env, directory, actual_uid = local_cli
    config = raw(env)
    mapping = config['plugins']['entries']['friday_rework']['settings']['cli_admission']['principals']
    assert len(mapping) == 1 and mapping[0]['uid'] == actual_uid
    mapping[0]['uid'] = actual_uid + 1
    native.atomic_config_replace(env.home / 'config.yaml', config)
    before = snapshot(env.home)
    def run():
        with scope.authority(directory), pytest.raises(scope.ScopeDenied):
            cli.initialize_cli()
    contextvars.copy_context().run(run)
    assert snapshot(env.home) == before


@pytest.mark.parametrize('mutation', ['uid_mapping', 'home', 'state_object', 'foreign_plugin'])
def test_retained_native_cli_refuses_foreign_authority_without_payload_effect(local_cli, mutation):
    def operation(env, cap):
        state = PluginState('friday_rework')
        store = Associations(state)
        store.state_set('cli_control_canary', {'owner': 'CURRENT_CLI_ONLY'})
        if mutation == 'uid_mapping':
            with scope.authority(env.home):
                config = raw(env)
                config['plugins']['entries']['friday_rework']['settings']['cli_admission']['principals'][0]['uid'] = cap.os_uid + 1
                native.atomic_config_replace(env.home / 'config.yaml', config)
        elif mutation == 'state_object':
            store.state = PluginState('friday_rework')
        elif mutation == 'foreign_plugin':
            store.state = PluginState('foreign_plugin')
        before = snapshot(env.home)
        expected_error = AssociationError if mutation == 'state_object' else scope.ScopeDenied
        expected_message = '^foreign_cli_state$' if mutation == 'state_object' else None
        with pytest.raises(expected_error, match=expected_message) as refused:
            if mutation == 'home':
                with scope.authority(home(env, '1')):
                    cli.current_cli(required=True)
            elif mutation == 'uid_mapping':
                cli.current_cli(required=True)
            else:
                store.state_set('cli_control_canary', {'must': 'not_overwrite'})
        if mutation == 'state_object':
            assert type(refused.value) is AssociationError
        assert snapshot(env.home) == before
        with scope.authority(cap.home):
            assert state.get('cli_control_canary') == {'owner': 'CURRENT_CLI_ONLY'}
    run_in_real_cli(local_cli, operation)


def test_gateway_user_cannot_acquire_native_cli_principal_by_selecting_cli_home(local_cli):
    env, directory, actual_uid = local_cli
    from test_ordinary_skills import entered
    with entered(env, '1'):
        before = snapshot(env.home)
        with scope.authority(directory), pytest.raises(scope.ScopeDenied):
            cli.initialize_cli()
        assert snapshot(env.home) == before
