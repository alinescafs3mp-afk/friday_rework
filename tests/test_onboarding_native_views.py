"""Prior independently reviewed current native profile joins; every external effect stays synthetic.

Reuse the producer's pinned setup of real admission/PluginManager/middleware;
assert on its actual retained rows, controller and result surfaces.
"""
import os, asyncio
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_user_implicit_profile import wired, users, offline_execution
from hermes_cli import friday_user_scope as scope

E = Path(os.environ.get("FRIDAY_FIXTURE_EVIDENCE", Path(__file__).parent))
ROUTES = [(profile, transport) for profile in (None, '', 'runtime')
          for transport in ('default', 'receiver-b')]


def record(name, value):
    with (E / 'observations.jsonl').open('a') as f:
        f.write(json.dumps({'case': name, **value}, sort_keys=True) + '\n')


def admitted(w):
    response = w.invoke('friday_work', w.args)
    assert response['accepted'], response
    row = w.host.store.snapshot()[response['reference']]
    return response, row


@pytest.mark.parametrize('wired', ROUTES, indirect=True)
def test_each_real_source_profile_keeps_both_owners(wired):
    w = wired
    response, row = admitted(w)
    cap = scope.current()
    binding = row['host']['binding']
    assert binding['ingress']['source_profile'] == (w.users.sources[0].profile or '')
    assert binding['ingress']['runtime_profile'] == cap.profile == row['owner']['profile']
    assert binding['ingress']['transport_profile'] == cap.principal[1]
    assert binding['ingress']['message']['bot_id'] == row['owner']['bot_id'] == cap.principal[2]
    assert binding['user_authority'] == {'principal_id': cap.key,
                                        'generation': cap.admission_generation}
    assert scope.check_retained_job(row) is None
    ambient = {**row['owner'], 'platform': cap.principal[0],
               'profile': binding['ingress']['source_profile']}
    assert cap.require_owner(ambient, binding['ingress']) is None
    assert w.invoke('friday_work', w.args) == response
    status = w.invoke('friday_result', {'action': 'status', 'reference': response['reference']})
    assert status['accepted'], status
    assert w.host.store.snapshot()[response['reference']] == row
    assert len(w.scheduled) == 1
    record('profile-owners', {'source': w.users.sources[0].profile,
           'runtime': cap.profile, 'transport': cap.principal[1],
           'authority': binding['user_authority'], 'row_unchanged': True})


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'receiver-b')], indirect=True)
def test_real_controller_notification_document_join(wired, monkeypatch):
    w = wired
    observations = offline_execution(w, monkeypatch)
    response, original = admitted(w)
    row = w.host._start(original)
    assert row['host']['terminal']['state'] == 'completed'
    assert row['host']['quiescence'] and len(observations.launches) == 1
    preserved = ('owner', 'created_at_unix', 'budget_seconds', 'deadline_unix', 'stop_intent')
    assert all(row[k] == original[k] for k in preserved)
    assert row['host']['binding'] == original['host']['binding']
    asyncio.run(w.result.notify_finished(w.host, row))
    asyncio.run(w.result.notify_finished(w.host, row))
    assert len(observations.notifications) == 1
    assert observations.notifications[0][1] == {
        'session_key': original['owner']['session_key'],
        'expected_session_id': original['owner']['session_id']}
    output = Path(row['workspace_reference']) / 'workspace/review.txt'
    output.write_text('useful owned offline answer\n')
    arguments = {'reference': response['reference']}
    listing = w.invoke('friday_result', {**arguments, 'action': 'list'})
    inspection = w.invoke('friday_result', {**arguments, 'action': 'inspect',
                                          'paths': ['review.txt']})
    assert listing['accepted'] and listing['files'][0]['path'] == 'review.txt'
    assert inspection['accepted'] and inspection['artifacts'][0]['preview'] == output.read_text()
    assert w.invoke('friday_result', {**arguments, 'action': 'deliver'})['delivery_requested']
    current = w.host.store.snapshot()[response['reference']]
    assert asyncio.run(w.result.ResultTool(w.host).deliver(current)) == 'DELIVERED'
    current = w.host.store.snapshot()[response['reference']]
    assert asyncio.run(w.result.ResultTool(w.host).deliver(current)) == 'DELIVERED'
    assert len(observations.sends) == 1
    assert observations.sends[0]['data'] == b'useful owned offline answer\n'
    assert observations.sends[0]['route'] == w.admission.delivery_route(original['host']['binding']['ingress'])
    final = w.host.store.snapshot()[response['reference']]
    assert all(final[k] == original[k] for k in preserved)
    assert final['host']['binding'] == original['host']['binding']
    assert final['notification']['state'] == 'OBSERVED'
    assert final['goal_verification'] == 'NOT_RUN'
    duplicate = w.invoke('friday_work', w.args)
    assert duplicate['accepted'] and duplicate['reference'] == response['reference']
    assert len(observations.launches) == 1
    assert len(w.scheduled) == 2  # Original work and explicit delivery only.
    record('end-to-end-offline', {'source': w.users.sources[0].profile,
           'transport': scope.current().principal[1], 'launches': 1,
           'notifications': 1, 'documents': 1, 'original_binding_preserved': True,
           'goal_verification': 'NOT_RUN', 'live': 'NOT_RUN'})


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'receiver-b')], indirect=True)
@pytest.mark.parametrize('field,value', [
    ('source_profile', None), ('source_profile', 'default'),
    ('source_profile', 'unknown'), ('runtime_profile', ''),
    ('runtime_profile', 'default'), ('transport_profile', 'unknown'),
    ('bot_id', 'foreign-account'), ('user_id', '2'),
    ('owner_profile', ''), ('owner_profile', 'default'),
    ('owner_account', 'foreign-account'), ('authority', None),
    ('generation', '1'), ('generation', 99), ('runtime_home', '/nonexistent/foreign')])
def test_retained_forgeries_cannot_replace_authoritative_worker_binding(wired, monkeypatch, field, value):
    w = wired
    observations = offline_execution(w, monkeypatch)
    response, original = admitted(w)
    forged = copy.deepcopy(original)
    binding = forged['host']['binding']
    if field == 'owner_profile': forged['owner']['profile'] = value
    elif field == 'owner_account': forged['owner']['bot_id'] = value
    elif field == 'authority': binding['user_authority'] = value
    elif field == 'generation': binding['user_authority']['generation'] = value
    elif field == 'runtime_home': binding['runtime']['runtime_home'] = value
    elif field in ('bot_id', 'user_id'): binding['ingress']['message'][field] = value
    else: binding['ingress'][field] = value
    with pytest.raises(scope.ScopeDenied): scope.check_retained_job(forged)
    with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.notify_finished(w.host, forged))
    assert not observations.launches and not observations.notifications and not observations.sends
    assert w.host.store.snapshot()[response['reference']] == original
    # _start selects task/owner then reloads the authoritative durable row;
    # mutable caller metadata cannot replace that row's binding or generation.
    association_error = __import__('importlib').import_module(w.package + '.associations').AssociationError
    if forged['owner'] != original['owner']:
        with pytest.raises((scope.ScopeDenied, association_error)): w.host._start(forged)
        assert not observations.launches
        assert w.host.store.snapshot()[response['reference']] == original
    else:
        started = w.host._start(forged)
        assert started['host']['binding'] == original['host']['binding']
        for key in ('owner', 'budget_seconds', 'deadline_unix', 'stop_intent'):
            assert started[key] == original[key]
        assert len(observations.launches) == 1
        assert scope.check_retained_job(started) is None
    assert not observations.notifications and not observations.sends
    assert w.invoke('friday_result', {'action': 'status', 'reference': response['reference']})['accepted']
    record('forgery', {'field': field, 'value': value,
           'transport': scope.current().principal[1], 'notification_refused_before_effects': True,
           'worker_binding': 'authoritative stored row only',
           'foreign_owner_refused': forged['owner'] != original['owner']})


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'receiver-b')], indirect=True)
@pytest.mark.parametrize('mutation', ['disable-enable', 'remove-recreate', 'role-cycle'])
def test_each_account_old_job_cannot_revive_and_owned_stop_survives(wired, monkeypatch, mutation):
    from friday_admin_controls.access import ProductAccess
    from hermes_cli.plugins_state import PluginState
    from hermes_cli.friday_product_access import KEY, current_access
    from hermes_cli.plugin_command_context import _command_context
    from gateway.session import SessionSource
    from gateway.run import GatewayRunner
    from agent import secret_scope
    w = wired
    # Real multiplexed ingress reads the receiving account's own allowlist.
    # Do not grant admission from the revoked worker's secret/profile context.
    monkeypatch.setattr(secret_scope, '_MULTIPLEX_ACTIVE', True)
    receiving = w.users.sources[0]._identity.authorization_home
    receiving_env = receiving / '.env'
    receiving_env.write_text('GATEWAY_ALLOWED_USERS=1\n')
    receiving_env.chmod(0o600)
    intake = object.__new__(GatewayRunner)  # No listener or gateway startup.
    observations = offline_execution(w, monkeypatch)
    response, original = admitted(w)
    old_cap = scope.current()
    old_source = w.users.sources[0]
    with scope.authority(old_cap.authorization_home):
        state = PluginState('friday_rework')
        access = ProductAccess(state)
        common = dict(platform=old_cap.principal[0], transport_profile=old_cap.principal[1],
                      account_id=old_cap.principal[2], user_id=old_cap.principal[3])
        if mutation == 'remove-recreate':
            doc = current_access(state); doc['users'].pop(old_cap.key); state.set(KEY, doc)
        else:
            access.set_user(**common, enabled=mutation == 'role-cycle',
                            role='admin' if mutation == 'role-cycle' else 'user')
        access.set_user(**common, enabled=True, role='user')
    new_source = SessionSource(old_source.platform, old_source.chat_id,
        user_id=old_source.user_id, chat_type=old_source.chat_type,
        thread_id=old_source.thread_id, profile=old_source.profile)
    new_source._identity = replace(old_source._identity)
    token = scope._CURRENT.set(None)
    try:
        # A new ingress is admitted outside the revoked task's retained scope.
        # Its fresh grant must not revive any old object or original job below.
        assert not w.users.gateway._principal_authorized(new_source, allow_adapter_delegation=True)
        assert intake._is_user_authorized_for_source(new_source, allow_adapter_delegation=True)
        with scope.scoped_source(new_source) as fresh:
            assert fresh.admission_generation > old_cap.admission_generation
            assert not w.invoke('friday_work', w.args)['accepted']
            assert not w.invoke('friday_result', {'action': 'status', 'reference': response['reference']})['accepted']
            with pytest.raises(scope.ScopeDenied): w.host._start(original)
            with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.notify_finished(w.host, original))
            retained = copy.deepcopy(original)
            retained['result'] = {'artifacts': [{'reference': 'synthetic-selection'}]}
            with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.ResultTool(w.host).deliver(retained))
            assert w.host.store.snapshot()[response['reference']] == original
            receipt = w.receipt('friday-stop')
            assert receipt['source']['profile'] == original['owner']['profile']
            assert receipt['admitted_ingress']['source_profile'] == (old_source.profile or '')
            with _command_context(w.host.ctx, receipt):
                stopped = json.loads(w.host.control('friday-stop', response['reference']))
            assert stopped['accepted'], stopped
            current = w.host.store.snapshot()[response['reference']]
            assert current['deadline_unix'] == original['deadline_unix']
            assert current['budget_seconds'] == original['budget_seconds']
            assert current['host']['binding'] == original['host']['binding']
            assert current['stop_intent'] == 'cancel'
            assert not observations.launches and not observations.notifications and not observations.sends
            record('no-revival-stop', {'mutation': mutation,
                   'transport': fresh.principal[1], 'old_generation': old_cap.admission_generation,
                   'new_generation': fresh.admission_generation, 'stop_intent': current['stop_intent'],
                   'deadline_unchanged': True})
    finally:
        scope._CURRENT.reset(token)


@pytest.mark.parametrize('wired', [(None, 'receiver-b'), ('runtime', 'receiver-b')], indirect=True)
def test_same_user_other_account_and_missing_scope_refuse_actual_consumers(wired, monkeypatch):
    w = wired
    observations = offline_execution(w, monkeypatch)
    response, row = admitted(w)
    own = scope.current()
    token = scope._CURRENT.set(None)
    association_error = __import__('importlib').import_module(w.package + '.associations').AssociationError
    try:
        with pytest.raises((scope.ScopeDenied, association_error)): w.host._start(row)
        with scope.authority(w.primary_home), scope.scoped_source(w.primary_source) as other:
            assert other.principal[3] == own.principal[3]
            assert other.key != own.key
            with pytest.raises((scope.ScopeDenied, association_error)): w.host._start(row)
            with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.notify_finished(w.host, row))
            retained = copy.deepcopy(row)
            retained['result'] = {'artifacts': [{'reference': 'synthetic-selection'}]}
            with pytest.raises((scope.ScopeDenied, association_error)): asyncio.run(w.result.ResultTool(w.host).deliver(retained))
        assert not observations.launches and not observations.notifications and not observations.sends
    finally:
        scope._CURRENT.reset(token)
    assert w.host.store.snapshot()[response['reference']] == row
    assert w.invoke('friday_result', {'action': 'status', 'reference': response['reference']})['accepted']
