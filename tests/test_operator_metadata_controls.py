"""Independent finite Source controls for verified administrative metadata.

Native onboarding, provider signing, pairing and capability checks remain real.
All identities, homes, secrets, stores and adapters are private test fixtures.
No worker, process, service, model, socket client or remote call is exercised.
"""
import asyncio
import base64
from contextlib import contextmanager
import contextvars
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import httpx
import pytest

from hermes_cli import config as native, friday_product_access as policy
from hermes_cli import friday_user_scope as scope
from hermes_cli.dashboard_auth import registry as providers
from hermes_cli.plugins_state import PluginState
from test_user_onboarding import env as env
from test_user_onboarding import (
    complete, admitted, prepare, home, cas, ident, activate, secrets, grant,
    row, raw, save,
)
from test_ordinary_skills import entered
from test_admin_foundation import mounted_app


REFUSALS = (PermissionError, RuntimeError, ValueError)


def snapshot(root):
    """Compare actual private configuration/state/payload, including directories.

    Native lock files, rejection audit and native last-good config backups are
    metadata rather than product payload. Their paths are the only exclusions.
    """
    result = {}
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root).as_posix()
        if (p.name.endswith('.lock') or rel == 'logs/dashboard-auth.log'
                or rel.startswith('backups/config/')):
            continue
        st = p.lstat()
        if p.is_symlink():
            result[rel] = ('link', st.st_mode & 0o777, os.readlink(p))
        elif p.is_file():
            result[rel] = ('file', st.st_mode & 0o777, p.read_bytes())
        elif p.is_dir():
            result[rel] = ('directory', st.st_mode & 0o777)
        else:
            result[rel] = ('other', st.st_mode)
    return result


def engaged(env):
    complete(env, '1')
    ok, source = admitted(env, '1')
    assert ok and source._friday_user_scope is not None
    assert scope._ENGAGED and scope._CURRENT.get() is None
    return source


def request_prepare(env, actor=None, profile='default'):
    return env.setup.prepare(profile, session=env.operator if actor is None else actor,
        expected_config_sha256=cas(env), template='approved-local',
        runtime_profile='user-2', **ident('2'))


def expire(monkeypatch):
    old = policy.time
    monkeypatch.setattr(policy, 'time', SimpleNamespace(
        time=lambda: old.time() + 86400, monotonic=old.monotonic))


def revoke(env):
    config = raw(env)
    config['plugins']['entries']['friday_rework']['settings']['admin']['operators'][0]['user_id'] = 'revoked-owner'
    save(env, config)


def assert_private_no_second_user(env, before):
    assert snapshot(env.home) == before
    assert not home(env, '2').exists()
    with scope.authority(env.home):
        assert len(policy.current_access(env.state)['users']) == 1


def native_toggle(env, enabled):
    """A separate native writer changes real access generation, not predicates."""
    with scope.authority(env.home):
        document = policy.current_access(env.state)
        document['users'][policy.principal_id(**ident('1'))]['enabled'] = enabled
        env.state.set(policy.KEY, document)


def test_real_first_user_admission_then_complete_real_second_user(env):
    engaged(env)
    with pytest.raises(scope.ScopeDenied):
        scope.current()
    result = complete(env, '2')
    assert result['generation'] == 1 and row(env, '2')['enabled'] is True
    assert home(env, '1') != home(env, '2')
    for uid in ('1', '2'):
        accepted, source = admitted(env, uid)
        assert accepted
        with scope.authority(home(env, uid)), scope.scoped_source(source) as cap:
            assert cap.principal == ('telegram', 'default', 'bot-A', uid)
            assert cap.profile == 'user-' + uid
            assert (cap.home / scope.MARKER).is_file()
            assert ('synthetic-' + uid + '-LOCAL_KEY') in (cap.home / '.env').read_text()
            assert ('synthetic-' + ('2' if uid == '1' else '1') + '-LOCAL_KEY') not in (cap.home / '.env').read_text()


def test_unengaged_real_operator_keeps_existing_prepare_secret_grant_activation(env):
    assert not scope._ENGAGED and scope._CURRENT.get() is None
    complete(env, '1')
    complete(env, '2')
    assert all(admitted(env, uid)[0] for uid in ('1', '2'))


def test_actual_native_login_minted_session_with_refresh_token_is_accepted(env):
    engaged(env)
    minted = env.provider._mint_session('owner')
    assert minted.refresh_token and env.provider.verify_session(access_token=minted.access_token).refresh_token == ''
    result = request_prepare(env, actor=minted)
    assert result['enabled'] is False and result['generation'] == 1
    assert home(env, '2').is_dir() and not (home(env, '2') / scope.MARKER).exists()


@pytest.mark.parametrize('kind', [
    'missing', 'forged_shape', 'forged_exact_session', 'invalid_signature',
    'token_subject_mismatch', 'foreign_provider', 'foreign_org', 'foreign_user', 'expired',
])
def test_invalid_native_operator_after_engagement_refuses_without_payload_effect(env, kind):
    engaged(env)
    actor = env.operator
    def invalid_signature():
        encoded = actor.access_token
        decoded = bytearray(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        decoded[-1] ^= 1
        return replace(actor, access_token=base64.urlsafe_b64encode(decoded).decode().rstrip('='))
    actors = {
        'missing': lambda: None,
        'forged_shape': lambda: SimpleNamespace(**vars(actor)),
        'forged_exact_session': lambda: replace(actor, access_token='unsigned-canary'),
        'invalid_signature': invalid_signature,
        'token_subject_mismatch': lambda: replace(actor, access_token=env.provider._mint_session('ordinary').access_token),
        'foreign_provider': lambda: replace(actor, provider='foreign'),
        'foreign_org': lambda: replace(actor, org_id='foreign'),
        'foreign_user': lambda: env.provider.verify_session(access_token=env.provider._mint_session('ordinary').access_token),
        'expired': lambda: replace(actor, expires_at=1),
    }
    actor = actors[kind]()
    before = snapshot(env.home)
    with pytest.raises(REFUSALS):
        env.setup.prepare('default', session=actor, expected_config_sha256=cas(env),
            template='approved-local', runtime_profile='user-2', **ident('2'))
    assert_private_no_second_user(env, before)


@pytest.mark.parametrize('kind', ['absent', 'foreign_secret', 'replaced_same_secret'])
def test_missing_foreign_or_replaced_native_provider_refuses_before_target_write(env, kind):
    engaged(env)
    assert providers.restore_registration('basic', env.provider, None, scope=str(env.home))
    replacement = None
    if kind != 'absent':
        replacement = type(env.provider)(username='owner', password_hash='unused-synthetic-only',
            secret=(b'foreign-provider-key-at-least-32bytes' if kind == 'foreign_secret'
                else env.provider._secret))
        providers.register_provider(replacement, scope=str(env.home))
    before = snapshot(env.home)
    try:
        if kind == 'replaced_same_secret':
            # A new request can authenticate a currently configured provider.
            # Replacement DURING an existing transaction must revoke its lease.
            with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
                assert providers.restore_registration('basic', replacement, None, scope=str(env.home))
                providers.register_provider(env.provider, scope=str(env.home))
                unchanged = snapshot(env.home)
                with pytest.raises(REFUSALS):
                    access.store.state_set('operator_control_canary', {'must': 'not_write'})
                assert snapshot(env.home) == unchanged
        else:
            with pytest.raises(REFUSALS):
                request_prepare(env)
            assert_private_no_second_user(env, before)
    finally:
        current = providers.snapshot_registration('basic', scope=str(env.home))
        if current is not None:
            assert providers.restore_registration('basic', current, None, scope=str(env.home))
        providers.register_provider(env.provider, scope=str(env.home))


def test_config_operator_revocation_refuses_after_engagement(env):
    engaged(env)
    revoke(env)
    before = snapshot(env.home)
    with pytest.raises(REFUSALS):
        request_prepare(env)
    assert_private_no_second_user(env, before)


@pytest.mark.parametrize('state', ['active', 'revoked', 'reenabled'])
def test_retained_ordinary_scope_never_promotes_even_with_real_operator(env, state):
    complete(env, '1')
    with entered(env, '1') as cap:
        if state != 'active':
            native_toggle(env, False)
            if state == 'reenabled':
                native_toggle(env, True)
        before = snapshot(env.home)
        with pytest.raises(PermissionError, match='operator_source_scope_required'):
            request_prepare(env)
        assert_private_no_second_user(env, before)
        if state != 'active':
            with pytest.raises(scope.ScopeDenied):
                cap.check()


def test_metadata_authority_does_not_supply_user_or_cli_capability(env):
    engaged(env)
    from friday_admin_controls.associations import Associations
    from hermes_cli.friday_cli_principal import current_cli, initialize_cli
    from hermes_cli.friday_cli_work import is_cli, check_store
    before = snapshot(env.home)
    for operation in (scope.current, is_cli, lambda: Associations(env.state),
            lambda: check_store(None, env.state), lambda: current_cli(required=True), initialize_cli):
        with pytest.raises(scope.ScopeDenied):
            operation()
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        for operation in (scope.current, is_cli, lambda: Associations(env.state),
                lambda: current_cli(required=True)):
            with pytest.raises(scope.ScopeDenied):
                operation()
        assert isinstance(access.store.state_get(policy.KEY), dict)
    assert snapshot(env.home) == before


@pytest.mark.parametrize('operation', ['get', 'set', 'lock'])
@pytest.mark.parametrize('mutation', ['object', 'fake', 'plugin_id', 'namespace', 'data_dir', 'directory', 'home'])
def test_exact_state_namespace_directory_home_custody_refuses_no_effect(env, monkeypatch, operation, mutation):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        store = access.store
        original = store.state
        saved_directory = None
        calls = []
        with monkeypatch.context() as local:
            alternate = env.home / 'profiles' / 'operator-alternate'
            def fake_state():
                def unexpected(*args, **kwargs):
                    calls.append('fake_state_touched')
                    pytest.fail('foreign state adapter reached before authority refusal')
                fake = SimpleNamespace(_plugin_id='friday_rework', _data_namespace=original._data_namespace,
                    data_dir=original.data_dir, get=unexpected, set=unexpected)
                local.setattr(store, 'state', fake)
            def data_directory():
                directory_property = PluginState.data_dir
                alternate_directory = env.home / 'foreign-state-directory'
                alternate_directory.mkdir(mode=0o700)
                local.setattr(PluginState, 'data_dir', property(lambda state:
                    alternate_directory if state is original else directory_property.fget(state)))
            def replace_directory():
                nonlocal saved_directory, directory
                directory = original.data_dir
                saved_directory = directory.with_name(directory.name + '-saved')
                directory.rename(saved_directory)
                directory.mkdir(mode=0o700)
            directory = None
            mutations = {
                'object': lambda: local.setattr(store, 'state', PluginState('friday_rework')),
                'fake': fake_state,
                'plugin_id': lambda: local.setattr(original, '_plugin_id', 'foreign_plugin'),
                'namespace': lambda: local.setattr(original, '_data_namespace', 'foreign_namespace'),
                'data_dir': data_directory,
                'directory': replace_directory,
                'home': lambda: alternate.mkdir(mode=0o700),
            }
            mutations[mutation]()
            def invoke():
                if operation == 'get':
                    return store.state_get(policy.KEY)
                if operation == 'set':
                    return store.state_set('operator_control_canary', {'must': 'not_write'})
                with store._locked():
                    pytest.fail('changed authority reached association body')
            before = snapshot(env.home)
            try:
                with pytest.raises(REFUSALS):
                    if mutation == 'home':
                        with scope.authority(alternate):
                            invoke()
                    else:
                        invoke()
                assert snapshot(env.home) == before and not calls
            finally:
                if saved_directory is not None:
                    assert list(directory.iterdir()) == []
                    directory.rmdir()
                    saved_directory.rename(directory)


@pytest.mark.parametrize('mutation', ['session', 'session_token', 'administration', 'launch_home'])
def test_original_session_and_administration_authority_are_bound(env, monkeypatch, mutation):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        before = snapshot(env.home)
        original_session_values = dict(vars(env.operator))
        try:
            with monkeypatch.context() as local:
                if mutation == 'session':
                    object.__setattr__(env.operator, 'user_id', 'another-operator')
                elif mutation == 'session_token':
                    object.__setattr__(env.operator, 'access_token', 'forged-after-lock')
                elif mutation == 'administration':
                    local.setattr(env.setup, 'admin', type(env.setup.admin)())
                else:
                    local.setattr(env.setup.admin, 'launch_home', env.home / 'foreign-launch')
                with pytest.raises(REFUSALS):
                    access.store.state_set('operator_control_canary', {'must': 'not_write'})
                assert snapshot(env.home) == before
        finally:
            for key, value in original_session_values.items():
                object.__setattr__(env.operator, key, value)


def test_replaced_root_home_is_refused_without_creating_state_or_repairing_it(env):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        saved = env.home.with_name('saved-authority-home')
        env.home.rename(saved)
        env.home.mkdir(mode=0o700)
        created_identity = env.home.stat().st_dev, env.home.stat().st_ino
        (env.home / 'config.yaml').write_bytes((saved / 'config.yaml').read_bytes())
        (env.home / 'config.yaml').chmod(0o600)
        before = snapshot(env.home.parent)
        try:
            with pytest.raises(REFUSALS):
                access.store.state_get(policy.KEY)
            assert snapshot(env.home.parent) == before
        finally:
            # Only this test-created replacement root is disposable. Retain the
            # failed no-effects assertion even when product code made backups;
            # cleanup must not mask that observation with a nonempty-rmdir error.
            info = env.home.lstat()
            assert not env.home.is_symlink() and (info.st_dev, info.st_ino) == created_identity
            shutil.rmtree(env.home)
            saved.rename(env.home)


@pytest.mark.parametrize('context_kind', ['empty', 'copied'])
def test_active_operator_metadata_cannot_cross_original_context(env, context_kind):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        context = contextvars.Context() if context_kind == 'empty' else contextvars.copy_context()
        before = snapshot(env.home)
        with pytest.raises(REFUSALS):
            context.run(access.store.state_get, policy.KEY)
        assert snapshot(env.home) == before
        # A foreign-context attempt must not poison the rightful context.
        assert access.store.state_get(policy.KEY)['users']


@pytest.mark.parametrize('exceptional', [False, True])
def test_retained_operator_metadata_expires_on_transaction_exit_and_exception(env, exceptional):
    engaged(env)
    retained = None
    copied = None
    class DeliberateExit(Exception):
        pass
    try:
        with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
            retained = access.store
            copied = contextvars.copy_context()
            if exceptional:
                raise DeliberateExit()
    except DeliberateExit:
        assert exceptional
    before = snapshot(env.home)
    for operation in (lambda: retained.state_get(policy.KEY),
            lambda: retained.state_set('operator_control_canary', {'must': 'not_write'}),
            lambda: copied.run(retained.state_get, policy.KEY)):
        with pytest.raises(REFUSALS):
            operation()
        assert snapshot(env.home) == before


@pytest.mark.parametrize('lock_kind', ['association', 'native_state', 'root_config'])
@pytest.mark.parametrize('change', ['expire', 'revoke'])
def test_revalidation_after_actual_locks_prevents_target_effect(env, monkeypatch, lock_kind, change):
    engaged(env)
    injected = []
    after_injection = []
    def invalidate():
        if injected:
            return
        injected.append(lock_kind)
        if change == 'expire':
            expire(monkeypatch)
        else:
            revoke(env)
        after_injection.append(snapshot(env.home))
    if lock_kind == 'root_config':
        original = native.config_write_transaction
        @contextmanager
        def locked(path, *args, **kwargs):
            with original(path, *args, **kwargs) as value:
                if Path(path) == env.home / 'config.yaml':
                    invalidate()
                yield value
        monkeypatch.setattr(native, 'config_write_transaction', locked)
    else:
        import fcntl
        original = fcntl.flock
        target = env.state.data_dir / ('admission.lock' if lock_kind == 'association' else '.state.json.lock')
        inode = target.stat()
        expected = inode.st_dev, inode.st_ino
        def locked(fd, operation):
            result = original(fd, operation)
            info = os.fstat(fd)
            if (operation & fcntl.LOCK_EX and (info.st_dev, info.st_ino) == expected):
                invalidate()
            return result
        monkeypatch.setattr(fcntl, 'flock', locked)
    with pytest.raises(REFUSALS):
        request_prepare(env)
    assert injected == [lock_kind]
    assert_private_no_second_user(env, after_injection[0])


@pytest.mark.parametrize('operation', ['get', 'set'])
def test_native_state_lock_revalidation_precedes_read_disclosure_or_durable_write(env, monkeypatch, operation):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        store = access.store
        import fcntl
        original = fcntl.flock
        lock = store.state.data_dir / '.state.json.lock'
        info = lock.stat(); expected = info.st_dev, info.st_ino
        injected = []
        def locked(fd, mode):
            value = original(fd, mode)
            current = os.fstat(fd)
            if mode & fcntl.LOCK_EX and (current.st_dev, current.st_ino) == expected and not injected:
                injected.append(True)
                expire(monkeypatch)
            return value
        before = snapshot(env.home)
        monkeypatch.setattr(fcntl, 'flock', locked)
        with pytest.raises(REFUSALS):
            if operation == 'get':
                store.state_get(policy.KEY)
            else:
                store.state_set('operator_control_canary', {'must': 'not_write'})
        assert injected and snapshot(env.home) == before


def test_operator_transaction_keeps_root_config_cas_after_first_user_engagement(env):
    engaged(env)
    stale = cas(env)
    config = raw(env); config['owner_unrelated'] = 'EXTERNAL_CAS_CANARY'; save(env, config)
    before = snapshot(env.home)
    with pytest.raises(ValueError, match='config_conflict'):
        env.setup.prepare('default', session=env.operator, expected_config_sha256=stale,
            template='approved-local', runtime_profile='user-2', **ident('2'))
    assert_private_no_second_user(env, before)


def test_operator_association_native_compare_refuses_intervening_native_writer(env):
    engaged(env)
    from friday_admin_controls.associations import KEY
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        store = access.store
        expected = copy.deepcopy(store.state_get(KEY))
        changed = copy.deepcopy(expected)
        changed['external_corruption_canary'] = True
        # An independent native writer changes the same already-locked metadata.
        # The operator's retained compare token must not overwrite those bytes.
        store.state.set(KEY, changed)
        before = snapshot(env.home)
        with pytest.raises(RuntimeError):
            store._save(expected)
        assert snapshot(env.home) == before
        assert store.state.get(KEY) == changed


def test_replaced_native_state_lock_inode_refuses_before_payload_effect(env):
    engaged(env)
    with env.setup.transaction('default', cas(env), env.operator) as (_, access, _):
        path = access.state.data_dir / '.state.json.lock'
        saved = path.with_name('saved-native-state-lock')
        path.rename(saved)
        path.write_bytes(saved.read_bytes()); path.chmod(0o600)
        before = snapshot(env.home)
        try:
            with pytest.raises(REFUSALS):
                access.store.state_set('operator_control_canary', {'must': 'not_write'})
            assert snapshot(env.home) == before
        finally:
            path.unlink()
            saved.rename(path)


def test_native_generation_revocation_never_revives_retained_ordinary_source(env):
    source = engaged(env)
    old_generation = row(env, '1')['generation']
    native_toggle(env, False)
    native_toggle(env, True)
    assert row(env, '1')['generation'] > old_generation
    with scope.authority(home(env, '1')):
        with pytest.raises(scope.ScopeDenied):
            source._friday_user_scope.check()
    # A freshly admitted event stays independent of the revoked retained object.
    assert admitted(env, '1')[0]


def test_modern_full_worker_requirements_remain_disabled_after_engagement(env):
    engaged(env)
    from test_product_profile import inputs, template
    from tools.configure_product import compose_product
    spec = inputs(); spec['inference']['key_env'] = 'LOCAL_KEY'
    env.template = template(compose_product(spec))
    assert env.template['worker_inputs'] == {'required': ['dsh', 'a0'], 'workers': {}}
    config = raw(env)
    config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local'] = env.template
    # This control deliberately replaces the whole template. The native merge
    # writer preserves old nested keys, which would create a hybrid template.
    native.atomic_config_replace(env.home / 'config.yaml', config)
    prepare(env, '2'); secrets(env, '2'); grant(env, '2')
    result = activate(env, '2')
    assert result == {'state': 'DISABLED_REQUIRED_WORKERS_PENDING', 'enabled': False,
                      'worker_execution': 'BOTH_REQUIRED_WORKERS_UNQUALIFIED'}
    assert not row(env, '2')['enabled']
    assert not (home(env, '2') / scope.MARKER).exists()
    assert not admitted(env, '2')[0]


@pytest.mark.parametrize('kind', ['invalid_signature', 'ordinary', 'foreign_profile'])
def test_actual_native_signed_dashboard_ingress_refuses_before_second_user_effect(env, kind):
    engaged(env)
    app = mounted_app(env)
    from hermes_cli.dashboard_auth import middleware
    @app.middleware('http')
    async def gate(request, next_call):
        return await middleware.gated_auth_middleware(request, next_call)
    token = env.operator.access_token
    if kind == 'invalid_signature':
        token = 'invalid-signature-canary'
    elif kind == 'ordinary':
        token = env.provider._mint_session('ordinary').access_token
    profile = 'foreign' if kind == 'foreign_profile' else 'default'
    before = snapshot(env.home)
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
            return await client.post('/api/plugins/friday_rework/onboarding/prepare?profile=' + profile,
                headers={'Authorization': 'Bearer ' + token},
                json=dict(expected_config_sha256=cas(env), template='approved-local',
                    runtime_profile='user-2', **ident('2')))
    response = asyncio.run(send())
    assert response.status_code in (401, 403), response.text
    assert_private_no_second_user(env, before)


@pytest.mark.parametrize('kind', ['fake', 'foreign_plugin', 'namespace'])
def test_initial_metadata_mint_rejects_foreign_factory_before_state_property_effect(env, monkeypatch, kind):
    engaged(env)
    touches = []
    if kind == 'fake':
        class FakeState:
            _plugin_id = 'friday_rework'
            _data_namespace = env.state._data_namespace
            @property
            def data_dir(self):
                touches.append('foreign_data_dir')
                pytest.fail('initial mint evaluated foreign state data_dir')
        selected = FakeState()
    else:
        selected = PluginState('foreign_plugin' if kind == 'foreign_plugin' else 'friday_rework')
        if kind == 'namespace':
            selected._data_namespace = 'foreign_namespace_canary'
    monkeypatch.setattr(env.setup.admin, '_state', lambda: selected)
    # Include nested backups: a refusal after a config reader created a new
    # known-good backup is an actual effect, not a permitted ignored artifact.
    before = snapshot(env.home.parent)
    with pytest.raises(REFUSALS):
        request_prepare(env)
    assert snapshot(env.home.parent) == before and not touches
    assert not home(env, '2').exists()


@pytest.mark.parametrize('part', ['parent', 'directory', 'lock'])
def test_initial_metadata_mint_refuses_private_mode_drift_without_native_repair(env, part):
    engaged(env)
    directory = env.state.data_dir
    path = (directory.parent if part == 'parent' else directory if part == 'directory'
        else directory / '.state.json.lock')
    original_mode = path.stat().st_mode & 0o777
    wrong_mode = 0o750 if part != 'lock' else 0o640
    path.chmod(wrong_mode)
    before = snapshot(env.home.parent)
    try:
        with pytest.raises(REFUSALS):
            request_prepare(env)
        assert snapshot(env.home.parent) == before
        assert path.stat().st_mode & 0o777 == wrong_mode
        assert not home(env, '2').exists()
    finally:
        path.chmod(original_mode)


def test_initial_metadata_mint_refuses_root_alias_before_native_config_read(env, monkeypatch):
    engaged(env)
    import hermes_constants
    alias = env.home.with_name('operator-root-alias')
    alias.symlink_to(env.home, target_is_directory=True)
    try:
        with monkeypatch.context() as local:
            # A coherent private declaration still cannot turn a path alias
            # into the exact primary authority home. No UID/predicate changes.
            local.setenv('HERMES_HOME', str(alias))
            local.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(alias))
            local.setattr(env.setup.admin, 'launch_home', alias)
            with scope.authority(alias):
                before = snapshot(env.home.parent)
                with pytest.raises(REFUSALS):
                    request_prepare(env)
                assert snapshot(env.home.parent) == before
                assert not home(env, '2').exists()
    finally:
        assert alias.is_symlink()
        alias.unlink()

