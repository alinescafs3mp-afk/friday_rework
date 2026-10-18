"""Actual signed native Dashboard reads after ordinary admission, offline only.

No authentication bypass, route substitute, socket, provider API or worker run.
The ephemeral read lease must never become a write or user/CLI capability.
"""
import asyncio
from contextlib import contextmanager
import contextvars
from dataclasses import replace
import json
import os
import stat

import httpx
import pytest

from hermes_cli import friday_product_access as policy
from hermes_cli import friday_user_scope as scope
from hermes_cli.dashboard_auth import registry as providers
from hermes_cli.plugins_state import PluginState
from test_admin_foundation import mounted_app
from test_operator_metadata_controls import REFUSALS, engaged, native_toggle, request_prepare, revoke, snapshot
from test_ordinary_skills import entered
from test_user_onboarding import env as env
from test_user_onboarding import admitted, cas, grant, home, ident, raw, row, save
from friday_admin_controls.associations import AssociationError, Associations


READS = ('users', 'onboarding', 'pairing', 'tasks')


def signed_app(env):
    """Use the real registered native provider and unmodified require_admin."""
    from hermes_cli.dashboard_auth import middleware
    app = mounted_app(env)

    @app.middleware('http')
    async def gate(request, next_call):
        return await middleware.gated_auth_middleware(request, next_call)
    return app


async def get(client, env, surface, *, token=None, profile='default'):
    return await client.get('/api/plugins/friday_rework/' + surface,
        params={'profile': profile}, headers={'Authorization': 'Bearer ' +
            (env.operator.access_token if token is None else token)})


async def assert_reads(client, env, count):
    before = snapshot(env.home)
    replies = {name: await get(client, env, name) for name in READS}
    assert all(reply.status_code == 200 for reply in replies.values()), {
        name: (reply.status_code, reply.text) for name, reply in replies.items()}
    users = replies['users'].json()['users']
    assert {item['user_id'] for item in users} == {str(i) for i in range(1, count + 1)}
    assert replies['onboarding'].json()['templates'] == ['approved-local']
    assert isinstance(replies['pairing'].json()['approved'], list)
    assert replies['tasks'].json() == []
    public = '\n'.join(reply.text for reply in replies.values())
    assert 'synthetic-1-LOCAL_KEY' not in public and 'synthetic-2-LOCAL_KEY' not in public
    assert snapshot(env.home) == before


def test_actual_signed_reads_then_full_http_second_user_and_separate_native_content(env):
    engaged(env)
    assert scope._CURRENT.get() is None
    app = signed_app(env)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url='http://synthetic') as client:
            await assert_reads(client, env, 1)
            headers = {'Authorization': 'Bearer ' + env.operator.access_token}
            response = await client.post('/api/plugins/friday_rework/onboarding/prepare',
                params={'profile': 'default'}, headers=headers,
                json=dict(expected_config_sha256=cas(env), template='approved-local',
                    runtime_profile='user-2', **ident('2')))
            assert response.status_code == 200, response.text
            prepared = response.json()
            assert not prepared['enabled'] and not admitted(env, '2')[0]
            args = dict(expected_config_sha256=cas(env), generation=prepared['generation'], **ident('2'))
            for name in ('LOCAL_KEY', 'EXA_API_KEY'):
                response = await client.put('/api/plugins/friday_rework/onboarding/credentials',
                    params={'profile': 'default'}, headers=headers,
                    json=args | {'name': name, 'value': 'synthetic-2-' + name})
                assert response.status_code == 200, response.text
                assert 'synthetic-2-' not in response.text
            assert not admitted(env, '2')[0]
            grant(env, '2')
            response = await client.post('/api/plugins/friday_rework/onboarding/activate',
                params={'profile': 'default'}, headers=headers, json=args)
            assert response.status_code == 200 and response.json()['enabled'], response.text
            await assert_reads(client, env, 2)
    asyncio.run(scenario())
    assert row(env, '2')['enabled']
    from tools.file_tools import read_file_tool, write_file_tool
    from tools.memory_tool import MemoryStore, memory_tool
    for uid in ('1', '2'):
        with entered(env, uid):
            memory = MemoryStore(); memory.load_from_disk()
            assert json.loads(memory_tool(action='add', content='READ_FLOW_PRIVATE_' + uid, store=memory))['success']
            assert json.loads(write_file_tool('own.txt', 'READ_FLOW_FILE_' + uid))['success']
            assert 'READ_FLOW_FILE_' + uid in read_file_tool('own.txt')
    for uid, other in (('1', '2'), ('2', '1')):
        with entered(env, uid):
            memory = MemoryStore(); memory.load_from_disk()
            content = json.dumps(memory._entries_for('memory'))
            assert 'READ_FLOW_PRIVATE_' + uid in content and 'READ_FLOW_PRIVATE_' + other not in content
            refused = read_file_tool(str(home(env, other) / 'workspace/own.txt'))
            assert 'READ_FLOW_FILE_' + other not in refused
            assert 'product_user_scope_refused' in refused


@pytest.mark.parametrize('surface', READS)
@pytest.mark.parametrize('kind', ('invalid_signature', 'ordinary', 'foreign_profile', 'config_revoked'))
def test_actual_signed_read_ingress_denies_no_metadata_disclosure_or_payload_effect(env, surface, kind):
    engaged(env)
    app = signed_app(env)
    token, profile = env.operator.access_token, 'default'
    if kind == 'invalid_signature':
        token = 'invalid-native-signature-canary'
    elif kind == 'ordinary':
        token = env.provider._mint_session('ordinary').access_token
    elif kind == 'foreign_profile':
        profile = 'foreign'
    else:
        revoke(env)
    before = snapshot(env.home)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url='http://synthetic') as client:
            return await get(client, env, surface, token=token, profile=profile)
    response = asyncio.run(scenario())
    assert response.status_code == (401 if kind == 'invalid_signature' else 403), response.text
    assert all(value not in response.text for value in ('bot-A', 'approved-local', 'synthetic-1-LOCAL_KEY'))
    assert snapshot(env.home) == before and not home(env, '2').exists()


@pytest.mark.parametrize('kind', ('missing', 'expired', 'invalid_signature', 'foreign_user', 'foreign_org'))
def test_direct_read_requires_current_verified_native_operator_session(env, kind):
    engaged(env)
    actors = {
        'missing': None,
        'expired': replace(env.operator, expires_at=0),
        'invalid_signature': replace(env.operator, access_token='unsigned-canary'),
        'foreign_user': env.provider.verify_session(access_token=env.provider._mint_session('ordinary').access_token),
        'foreign_org': replace(env.operator, org_id='foreign-org'),
    }
    before = snapshot(env.home)
    with pytest.raises(REFUSALS):
        env.admin.users('default', session=actors[kind])
    assert snapshot(env.home) == before


@pytest.mark.parametrize('exceptional', (False, True))
def test_read_authority_expires_after_normal_or_exception_exit(env, exceptional):
    engaged(env)
    class DeliberateExit(Exception):
        pass
    try:
        with env.admin.metadata_read('default', session=env.operator) as (_, state, operator):
            store = Associations(state, _operator=operator)
            assert store.state_get(policy.KEY)['users']
            copied = contextvars.copy_context()
            if exceptional:
                raise DeliberateExit()
    except DeliberateExit:
        assert exceptional
    before = snapshot(env.home)
    for invoke in (lambda: store.state_get(policy.KEY),
            lambda: copied.run(store.state_get, policy.KEY)):
        with pytest.raises(REFUSALS):
            invoke()
        assert snapshot(env.home) == before


@pytest.mark.parametrize('context_kind', ('empty', 'copied'))
def test_read_authority_is_bound_to_original_context(env, context_kind):
    engaged(env)
    with env.admin.metadata_read('default', session=env.operator) as (_, state, operator):
        store = Associations(state, _operator=operator)
        foreign = contextvars.Context() if context_kind == 'empty' else contextvars.copy_context()
        before = snapshot(env.home)
        with pytest.raises(REFUSALS):
            foreign.run(store.state_get, policy.KEY)
        assert snapshot(env.home) == before
        assert store.state_get(policy.KEY)['users']


@contextmanager
def replaced_read_provider(env):
    replacement = type(env.provider)(username='owner', password_hash='synthetic-unused', secret=env.provider._secret)
    assert providers.restore_registration('basic', env.provider, None, scope=str(env.home))
    providers.register_provider(replacement, scope=str(env.home))
    try:
        yield
    finally:
        assert providers.restore_registration('basic', replacement, None, scope=str(env.home))
        providers.register_provider(env.provider, scope=str(env.home))


@contextmanager
def revoked_read_operator(env):
    original = raw(env)
    revoke(env)
    try:
        yield
    finally:
        save(env, original)


@contextmanager
def changed_read_attribute(target, name, value):
    original = getattr(target, name)
    object.__setattr__(target, name, value)
    try:
        yield
    finally:
        object.__setattr__(target, name, original)


@contextmanager
def replaced_read_directory(state):
    directory = state.data_dir
    saved = directory.with_name(directory.name + '-saved')
    directory.rename(saved); directory.mkdir(mode=0o700)
    try:
        yield
    finally:
        assert list(directory.iterdir()) == []
        directory.rmdir(); saved.rename(directory)


@contextmanager
def foreign_read_home(env):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    alternate = env.home / 'profiles/foreign-operator-home'; alternate.mkdir(mode=0o700)
    token = set_hermes_home_override(str(alternate))
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def read_authority_mutation(env, store, state, mutation):
    mutations = {
        'provider_replaced': lambda: replaced_read_provider(env),
        'config_revoked': lambda: revoked_read_operator(env),
        'expired_session': lambda: changed_read_attribute(env.operator, 'expires_at', 0),
        'state_object': lambda: changed_read_attribute(store, 'state', PluginState('friday_rework')),
        'namespace': lambda: changed_read_attribute(state, '_data_namespace', 'foreign_namespace_canary'),
        'plugin_id': lambda: changed_read_attribute(state, '_plugin_id', 'foreign_plugin'),
        'state_directory': lambda: replaced_read_directory(state),
        'home_override': lambda: foreign_read_home(env),
    }
    return mutations[mutation]()


@pytest.mark.parametrize('mutation', ('provider_replaced', 'config_revoked', 'expired_session',
    'state_object', 'namespace', 'plugin_id', 'state_directory', 'home_override'))
def test_retained_read_authority_revalidates_bound_provider_state_path_and_session(env, mutation):
    engaged(env)
    with env.admin.metadata_read('default', session=env.operator) as (_, state, operator):
        store = Associations(state, _operator=operator)
        assert store.state_get(policy.KEY)['users']
        with read_authority_mutation(env, store, state, mutation):
            before = snapshot(env.home)
            with pytest.raises(REFUSALS):
                store.state_get(policy.KEY)
            assert snapshot(env.home) == before


def test_read_authority_never_promotes_current_user_cli_or_unscoped_store(env):
    from hermes_cli.friday_cli_principal import current_cli
    from hermes_cli.friday_cli_work import is_cli
    engaged(env)
    with env.admin.metadata_read('default', session=env.operator) as (_, state, operator):
        before = snapshot(env.home)
        for invoke in (scope.current, is_cli, lambda: current_cli(required=True), lambda: Associations(state)):
            with pytest.raises(scope.ScopeDenied):
                invoke()
        assert Associations(state, _operator=operator).state_get(policy.KEY)['users']
        assert snapshot(env.home) == before


@pytest.mark.parametrize('state', ('active', 'revoked', 'reenabled'))
def test_retained_current_ordinary_cap_never_promotes_to_read_operator(env, state):
    engaged(env)
    with entered(env) as cap:
        if state != 'active':
            native_toggle(env, False)
            if state == 'reenabled':
                native_toggle(env, True)
        before = snapshot(env.home)
        with pytest.raises(REFUSALS):
            env.admin.users('default', session=env.operator)
        assert snapshot(env.home) == before
        if state != 'active':
            with pytest.raises(scope.ScopeDenied):
                cap.check()


def attempt_read_authority_write(env, store, state, operator, request_id, operation):
    from hermes_cli.plugins_state import LockAcquisitionBudget

    def association_lock():
        with store._locked():
            pytest.fail('read authority reached a mutating association body')

    def native_write(kind):
        mutations = {
            'native_replace': lambda native: native.replace('read_authority_forbidden', {'effect': True}),
            'native_journal': lambda native: native.journal('forbidden', b'forbidden'),
            'native_write': lambda native: native.write_all(-1, b'forbidden'),
        }
        with operator.transaction(state, LockAcquisitionBudget(.25)) as native:
            mutations[kind](native)

    operations = {
        'state_set': lambda: store.state_set('read_authority_forbidden', {'effect': True}),
        'association_lock': association_lock,
        'onboarding_prepare': lambda: request_prepare(env),
        'product_user_write': lambda: env.admin.set_user('default', **ident('1'), enabled=False, role='user'),
        'pairing_approval': lambda: env.admin.approve('default', platform='telegram', transport_profile='default',
            account_id='bot-A', request_id=request_id),
        'settings_write': lambda: env.admin.write_settings('default', {'expected_sha256': cas(env), 'kind': 'model',
            'values': {'model': 'forbidden-read-lease-model'}}, env.operator),
        'native_replace': lambda: native_write('native_replace'),
        'native_journal': lambda: native_write('native_journal'),
        'native_write': lambda: native_write('native_write'),
    }
    operations[operation]()


@pytest.mark.parametrize('operation', ('state_set', 'association_lock', 'native_replace', 'native_journal',
    'native_write', 'onboarding_prepare', 'product_user_write', 'pairing_approval', 'settings_write'))
def test_read_authority_cannot_write_metadata_or_mutate_native_transaction(env, operation):
    from gateway.pairing import PairingStore
    engaged(env)
    pairing = PairingStore()
    pairing.generate_code('telegram', '2', 'synthetic second user')
    request_id = next(item['request_id'] for item in pairing.list_pending() if item['user_id'] == '2')
    with env.admin.metadata_read('default', session=env.operator) as (_, state, operator):
        store = Associations(state, _operator=operator)
        before = snapshot(env.home)
        with pytest.raises(REFUSALS):
            attempt_read_authority_write(env, store, state, operator, request_id, operation)
        assert snapshot(env.home) == before
        assert not pairing.is_approved('telegram', '2')


@pytest.mark.parametrize('change', ('provider_replaced', 'config_revoked'))
def test_admin_read_revalidates_after_actual_projection_before_return(env, monkeypatch, change):
    from friday_admin_controls.access import ProductAccess
    engaged(env)
    injected, after = [], []
    original = ProductAccess.users
    replacement = None

    def interrupted(access):
        nonlocal replacement
        result = original(access)
        if not injected:
            injected.append(change)
            if change == 'config_revoked':
                revoke(env)
            else:
                replacement = type(env.provider)(username='owner', password_hash='synthetic-unused',
                    secret=env.provider._secret)
                assert providers.restore_registration('basic', env.provider, None, scope=str(env.home))
                providers.register_provider(replacement, scope=str(env.home))
            after.append(snapshot(env.home))
        return result
    monkeypatch.setattr(ProductAccess, 'users', interrupted)
    try:
        with pytest.raises(REFUSALS):
            env.admin.users('default', session=env.operator)
        assert injected == [change] and snapshot(env.home) == after[0]
    finally:
        if replacement is not None:
            assert providers.restore_registration('basic', replacement, None, scope=str(env.home))
            providers.register_provider(env.provider, scope=str(env.home))


@pytest.mark.parametrize('change', ('expire', 'revoke'))
def test_read_revalidates_after_actual_native_state_lock_before_disclosure(env, monkeypatch, change):
    import fcntl
    from test_operator_metadata_controls import expire
    engaged(env)
    injected = []
    after = []
    original = fcntl.flock
    lock = env.state.data_dir / '.state.json.lock'
    info = lock.stat(); expected = info.st_dev, info.st_ino

    def locked(fd, mode):
        value = original(fd, mode)
        current = os.fstat(fd)
        if mode & fcntl.LOCK_EX and (current.st_dev, current.st_ino) == expected and not injected:
            injected.append(change)
            expire(monkeypatch) if change == 'expire' else revoke(env)
            after.append(snapshot(env.home))
        return value
    monkeypatch.setattr(fcntl, 'flock', locked)
    with pytest.raises(REFUSALS):
        env.admin.users('default', session=env.operator)
    assert injected == [change] and snapshot(env.home) == after[0]


@pytest.mark.parametrize('damage', ('lost_store', 'invalid_marker', 'aliased_marker'))
def test_metadata_read_preserves_association_loss_and_marker_refusal_without_repair(env, damage):
    from friday_admin_controls.associations import KEY
    engaged(env)
    directory = env.state.data_dir
    if damage == 'lost_store':
        path = directory / 'state.json'
        value = json.loads(path.read_text())
        assert KEY in value
        del value[KEY]
        path.write_text(json.dumps(value)); path.chmod(0o600)
        reason = 'association_store_lost'
    elif damage == 'invalid_marker':
        (directory / 'admission.lock').write_bytes(b'invalid-marker')
        reason = 'invalid_admission_marker'
    else:
        marker = directory / 'admission.lock'
        saved = directory / 'original-admission-marker'
        marker.rename(saved); marker.symlink_to(saved)
        reason = 'unsafe_admission_lock'
    marker = directory / 'admission.lock'
    info = marker.lstat()
    marker_before = (info.st_dev, info.st_ino, info.st_mode, marker.read_bytes())
    before = snapshot(env.home)
    if damage == 'aliased_marker':
        # The final pre-open private regular-file guard refuses the alias.
        with pytest.raises(AssociationError, match='unsafe_admission_lock'):
            env.admin.tasks('default', session=env.operator)
    else:
        with pytest.raises(REFUSALS, match=reason):
            env.admin.tasks('default', session=env.operator)
    assert snapshot(env.home) == before
    info = marker.lstat()
    assert (info.st_dev, info.st_ino, info.st_mode, marker.read_bytes()) == marker_before


def test_fifo_admission_marker_read_refuses_before_wait_or_payload_effect(env):
    engaged(env)
    marker = env.state.data_dir / 'admission.lock'
    marker.unlink(); os.mkfifo(marker, 0o600)
    info = marker.lstat()
    assert stat.S_ISFIFO(info.st_mode)
    marker_before = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size)
    before = snapshot(env.home)
    with pytest.raises(AssociationError, match='unsafe_admission_lock'):
        env.admin.tasks('default', session=env.operator)
    assert snapshot(env.home) == before
    info = marker.lstat()
    assert (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size) == marker_before
    assert stat.S_ISFIFO(info.st_mode)


@pytest.mark.parametrize('change', ('mode', 'nlink'))
def test_admission_marker_custody_rechecked_after_actual_flock_before_disclosure(env, monkeypatch, change):
    import fcntl
    engaged(env)
    marker = env.state.data_dir / 'admission.lock'
    info = marker.stat(); expected = info.st_dev, info.st_ino
    original = fcntl.flock
    injected, after, marker_after = [], [], []
    mutations = {
        'mode': lambda: marker.chmod(0o640),
        'nlink': lambda: os.link(marker, marker.with_name('read-marker-hardlink')),
    }

    def locked(fd, mode):
        value = original(fd, mode)
        current = os.fstat(fd)
        if mode & fcntl.LOCK_SH and (current.st_dev, current.st_ino) == expected and not injected:
            mutations[change]()
            injected.append(change)
            info = marker.lstat()
            marker_after.append((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
                marker.read_bytes()))
            after.append(snapshot(env.home))
        return value
    monkeypatch.setattr(fcntl, 'flock', locked)
    with pytest.raises(AssociationError, match='unsafe_admission_lock'):
        env.admin.tasks('default', session=env.operator)
    assert injected == [change] and snapshot(env.home) == after[0]
    info = marker.lstat()
    assert (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
        marker.read_bytes()) == marker_after[0]


@pytest.mark.parametrize('part', ('namespace', 'native_lock'))
def test_initial_read_mint_missing_storage_refuses_before_native_config_reader(env, monkeypatch, part):
    from hermes_cli import config as native
    import utils
    engaged(env)
    directory = env.state.data_dir
    selected = {'namespace': directory, 'native_lock': directory / '.state.json.lock'}[part]
    saved = selected.with_name(selected.name + '-missing-read-control')
    selected.rename(saved)
    touches = []

    def forbidden_reader(*args, **kwargs):
        touches.append('native_config_reader')
        pytest.fail('missing read store reached a native config reader before refusing')
    try:
        before = snapshot(env.home.parent)
        with monkeypatch.context() as local:
            local.setattr(native, 'load_config_readonly', forbidden_reader)
            local.setattr(utils, 'load_yaml_file_readonly', forbidden_reader)
            with pytest.raises(PermissionError, match='operator_metadata_read_store_missing'):
                env.admin.users('default', session=env.operator)
        assert not touches and snapshot(env.home.parent) == before
        assert not selected.exists()
    finally:
        assert not selected.exists()
        saved.rename(selected)
