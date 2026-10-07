"""Native actor/transaction boundaries with real signed sessions and stores.

Synthetic keys and ASGI only: no worker, model, socket, service or installation.
The original readiness/CAS/generation controls remain in onboarding/worker tests.
"""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from hermes_cli import config as native, friday_product_access as policy
from test_user_onboarding import env, complete, prepare, secrets, grant, home, row, ident, cas, raw, save, admitted
from test_user_worker_provision import worker_prepare, inputs, reviewed
from test_admin_repair import basic_app
from hermes_cli import friday_user_scope as scope

ACTIONS = ('prepare', 'credentials', 'activate', 'worker_prepare', 'worker_configure')


def case(env, action, uid='2'):
    # Initialize the existing association store before measuring target effects.
    env.admin.users('default')
    from friday_admin_controls.access import ProductAccess
    with ProductAccess(env.state).store._locked():
        pass
    if action != 'prepare':
        prepare(env, uid)
    body = dict(expected_config_sha256=cas(env), **ident(uid))
    if action == 'prepare':
        body.update(template='approved-local', runtime_profile='user-' + uid)
    else:
        body['generation'] = row(env, uid)['generation']
    if action == 'credentials':
        body.update(name='LOCAL_KEY', value='synthetic-new-local-key')
    elif action == 'activate':
        secrets(env, uid); grant(env, uid)
    elif action == 'worker_prepare':
        runtime, _ = inputs(env, uid)
        body.update(worker='dsh', runtime=runtime)
    elif action == 'worker_configure':
        prepared = worker_prepare(env, uid); secrets(env, uid); grant(env, uid)
        body.update(worker='dsh', preparation=prepared['preparation'], runtime_receipt=reviewed(env, prepared))
    method = {'worker_prepare': 'prepare_worker', 'worker_configure': 'configure_worker'}.get(action, action)
    return body, getattr(env.setup, method), getattr(env.admin, 'onboarding_' + action)


def snapshot(env):
    # Native locks, rejection audit events and read-time last-good config
    # backups are metadata; compare all actual configuration, stores and user
    # payload including credentials, proofs, markers and worker inputs.
    return {str(p.relative_to(env.home)): p.read_bytes() for p in env.home.rglob('*')
            if p.is_file() and not p.name.endswith('.lock')
            and p.relative_to(env.home).as_posix() != 'logs/dashboard-auth.log'
            and not (p.parent.name == 'config' and p.parent.parent.name == 'backups')}


def expire(monkeypatch):
    clock = policy.time
    monkeypatch.setattr(policy, 'time', SimpleNamespace(time=lambda: clock.time() + 86400,
                                                       monotonic=clock.monotonic))


def request(env, action, body, app, token):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
            return await client.request('PUT' if action == 'credentials' else 'POST',
                '/api/plugins/friday_rework/onboarding/' + action.replace('_', '/') + '?profile=default',
                json=body, headers={'Authorization': 'Bearer ' + token})
    return asyncio.run(run())


@pytest.mark.parametrize('action', ACTIONS)
@pytest.mark.parametrize('actor_kind', ('missing', 'ordinary', 'expired', 'foreign_provider', 'foreign_org'))
def test_direct_and_administration_require_current_operator(env, action, actor_kind):
    body, direct, admin = case(env, action)
    actor = env.operator
    if actor_kind == 'ordinary':
        actor = env.provider.verify_session(access_token=env.provider._mint_session('ordinary').access_token)
    elif actor_kind == 'expired':
        actor = replace(actor, expires_at=1)
    elif actor_kind == 'foreign_provider':
        actor = replace(actor, provider='foreign')
    elif actor_kind == 'foreign_org':
        actor = replace(actor, org_id='foreign')
    args = {} if actor_kind == 'missing' else dict(session=actor)
    before = snapshot(env)
    for call in (direct, admin):
        with pytest.raises(PermissionError, match='verified_admin_required'):
            call('default', **body, **args)
        assert snapshot(env) == before


@pytest.mark.parametrize('action', ACTIONS)
@pytest.mark.parametrize('source_state', ('active', 'revoked', 'reenabled'))
def test_ordinary_source_refuses_even_valid_operator_before_home_override(env, monkeypatch, action, source_state):
    complete(env, '1')
    body, direct, admin = case(env, action)
    accepted, source = admitted(env, '1'); assert accepted
    with scope.authority(home(env, '1')), scope.scoped_source(source) as cap:
        if source_state != 'active':
            with scope.authority(env.home):
                env.admin.set_user('default', **ident('1'), enabled=False, role='user')
                if source_state == 'reenabled':
                    env.admin.set_user('default', **ident('1'), enabled=True, role='user')
            if source_state == 'revoked':
                with pytest.raises(scope.ScopeDenied): cap.check()
                assert cap.revoked
        before = snapshot(env)
        # This fails if onboarding enters operator authority to inspect policy
        # before rejecting the actual retained ordinary native context.
        from friday_admin_controls import admin_controls
        @contextmanager
        def no_authority_override(*args):
            pytest.fail('ordinary caller reached operator authority override')
            yield
        with monkeypatch.context() as local:
            local.setattr(admin_controls, 'authority_home', no_authority_override)
            for call in (direct, admin):
                with pytest.raises(PermissionError, match='operator_source_scope_required'):
                    call('default', session=env.operator, **body)
                assert snapshot(env) == before


@pytest.mark.parametrize('action', ACTIONS)
def test_signed_expiry_after_real_root_lock_refuses_all_mutations(env, monkeypatch, action):
    body, _, _ = case(env, action)
    app, token = basic_app(env); before = snapshot(env)
    original = native.config_write_transaction; entered = []
    @contextmanager
    def locked(path):
        with original(path):
            if Path(path) == env.home / 'config.yaml':
                entered.append(str(path)); expire(monkeypatch)
            yield
    monkeypatch.setattr(native, 'config_write_transaction', locked)
    response = request(env, action, body, app, token)
    assert entered and response.status_code == 403, response.text
    assert snapshot(env) == before


@pytest.mark.parametrize('action', ACTIONS[1:])
def test_signed_expiry_after_real_target_lock_refuses_all_mutations(env, monkeypatch, action):
    body, _, _ = case(env, action)
    app, token = basic_app(env); before = snapshot(env)
    original = native.config_write_transaction; entered = []
    @contextmanager
    def locked(path):
        with original(path):
            if Path(path) == home(env, '2') / 'config.yaml':
                entered.append(str(path)); expire(monkeypatch)
            yield
    monkeypatch.setattr(native, 'config_write_transaction', locked)
    response = request(env, action, body, app, token)
    assert entered and response.status_code == 403, response.text
    assert snapshot(env) == before


def test_signed_credential_expiry_after_real_env_lock_refuses_native_secret_write(env, monkeypatch):
    body, _, _ = case(env, 'credentials')
    app, token = basic_app(env); before = snapshot(env)
    original = native._env_write_lock; entered = []
    @contextmanager
    def locked(path):
        with original(path):
            entered.append(str(path)); expire(monkeypatch)
            yield
    monkeypatch.setattr(native, '_env_write_lock', locked)
    response = request(env, 'credentials', body, app, token)
    assert entered and response.status_code == 403, response.text
    assert snapshot(env) == before


@pytest.mark.parametrize('action', ACTIONS)
@pytest.mark.parametrize('change', ('remove_operator', 'foreign_org'))
def test_signed_policy_revocation_inside_lock_is_403_before_target_write(env, monkeypatch, action, change):
    body, _, _ = case(env, action)
    app, token = basic_app(env); before = snapshot(env)
    original = native.config_write_transaction; entered = []
    @contextmanager
    def locked(path):
        with original(path):
            if Path(path) == env.home / 'config.yaml' and not entered:
                entered.append(str(path))
                cfg = raw(env); operators = cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']
                if change == 'remove_operator': operators[0]['user_id'] = 'another-operator'
                else: operators[0]['org_id'] = 'another-org'
                save(env, cfg)
            yield
    monkeypatch.setattr(native, 'config_write_transaction', locked)
    response = request(env, action, body, app, token)
    assert entered and response.status_code == 403, response.text
    after = snapshot(env)
    assert {k: v for k, v in after.items() if k != 'config.yaml'} == {k: v for k, v in before.items() if k != 'config.yaml'}


@pytest.mark.parametrize('action', ACTIONS)
def test_signed_invalid_ordinary_and_expired_ingress_never_changes_target(env, monkeypatch, action):
    body, _, _ = case(env, action)
    app, token = basic_app(env); before = snapshot(env)
    from hermes_cli.dashboard_auth import request_utils
    provider = request_utils.list_session_providers()[0]
    ordinary = provider._mint_session('ordinary').access_token
    for bad in ('invalid-signature', ordinary):
        response = request(env, action, body, app, bad)
        assert response.status_code in (401, 403), response.text
        assert snapshot(env) == before
    expire(monkeypatch)
    response = request(env, action, body, app, token)
    assert response.status_code == 403, response.text
    assert snapshot(env) == before


@pytest.mark.parametrize('action', ACTIONS)
def test_actor_expiry_during_validation_is_rechecked_before_effect(env, monkeypatch, action):
    body, _, admin = case(env, action)
    before = snapshot(env); entered = []
    if action == 'prepare':
        from friday_admin_controls import onboarding as module
        name = 'validate_template'
    elif action == 'credentials':
        from agent import secret_scope as module
        name = 'load_env_file'
    elif action == 'activate':
        from gateway.pairing import PairingStore as module
        name = 'is_approved'
    elif action == 'worker_prepare':
        from friday_admin_controls import worker_provision as module
        name = 'prepare_inputs'
    else:
        from friday_admin_controls import host_runtime as module
        name = 'check_runtime'
    original = getattr(module, name)
    def validated(*args, **kwargs):
        value = original(*args, **kwargs)
        if not entered:
            entered.append(True); expire(monkeypatch)
        return value
    monkeypatch.setattr(module, name, validated)
    with pytest.raises(PermissionError, match='verified_admin_required'):
        admin('default', session=env.operator, **body)
    assert entered and snapshot(env) == before


def test_engaged_process_operator_without_user_context_keeps_legitimate_workflow(env, monkeypatch):
    monkeypatch.setattr(scope, '_ENGAGED', True)
    assert scope._CURRENT.get() is None
    result = complete(env)
    assert result['generation'] == 1 and row(env)['enabled'] and admitted(env)[0]


@pytest.mark.parametrize('action', ACTIONS)
def test_expiry_after_actual_association_lock_refuses_native_mutation(env, monkeypatch, action):
    from friday_admin_controls.associations import Associations
    body, _, admin = case(env, action)
    before = snapshot(env); original = Associations._locked; entered = []
    @contextmanager
    def locked(store):
        with original(store) as data:
            if not entered:
                entered.append(True); expire(monkeypatch)
            yield data
    monkeypatch.setattr(Associations, '_locked', locked)
    with pytest.raises(PermissionError, match='verified_admin_required'):
        admin('default', session=env.operator, **body)
    assert entered and snapshot(env) == before


def test_prepare_expiry_at_new_home_lock_leaves_disabled_partial_without_adoption(env, monkeypatch):
    body, _, admin = case(env, 'prepare')
    original = native.config_write_transaction; entered = []
    with monkeypatch.context() as local:
        # Restore the eligibility clock together with the lock injection.
        clock = policy.time
        def advance():
            local.setattr(policy, 'time', SimpleNamespace(time=lambda: clock.time() + 86400,
                                                        monotonic=clock.monotonic))
        @contextmanager
        def expiry_lock(path):
            with original(path):
                if Path(path) == home(env, '2') / 'config.yaml':
                    entered.append(True); advance()
                yield
        local.setattr(native, 'config_write_transaction', expiry_lock)
        with pytest.raises(PermissionError):
            admin('default', session=env.operator, **body)
    assert entered and row(env, '2')['enabled'] is False
    assert row(env, '2')['generation'] == 1
    assert not (home(env, '2') / scope.MARKER).exists()
    assert not (home(env, '2') / scope.ONBOARDING).exists()
    assert not (home(env, '2') / 'config.yaml').exists()
    with pytest.raises(ValueError, match='existing_principal_not_adopted'):
        admin('default', session=env.operator, **dict(body, expected_config_sha256=cas(env)))


def test_expiry_after_config_commit_does_not_reseal_or_activate_partial_worker(env, monkeypatch):
    body, _, admin = case(env, 'worker_configure')
    h = home(env, '2'); before_config = (h / 'config.yaml').read_bytes()
    before_proof = (h / scope.ONBOARDING).read_bytes(); generation = row(env, '2')['generation']
    original = native.atomic_config_write; committed = []
    with monkeypatch.context() as local:
        clock = policy.time
        def write(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if Path(path) == h / 'config.yaml':
                committed.append(True)
                local.setattr(policy, 'time', SimpleNamespace(time=lambda: clock.time() + 86400,
                                                            monotonic=clock.monotonic))
            return result
        local.setattr(native, 'atomic_config_write', write)
        with pytest.raises(PermissionError, match='verified_admin_required'):
            admin('default', session=env.operator, **body)
    assert committed and (h / 'config.yaml').read_bytes() != before_config
    assert (h / scope.ONBOARDING).read_bytes() == before_proof
    assert row(env, '2')['enabled'] is False and row(env, '2')['generation'] == generation
    assert not (h / scope.MARKER).exists()
    with pytest.raises(PermissionError, match='prepared_home_changed'):
        admin('default', session=env.operator, **body)
