"""Future isolated SOURCE regressions; NOT RUN and not native acceptance.

Synthetic homes, signed sessions, grants, ordinary admission, request pins and
filesystem transactions remain real.  Only the stopped native owner observation
is replaced by an explicitly OFFLINE fixture.  No service, model, process,
network, installed product or previous qualification is executed by this suite.
Collection/execution requires a separately reviewed native test installation.
"""
import asyncio
from contextlib import contextmanager
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import httpx
import pytest

from test_user_onboarding import (
    env, home, row, ident, cas, raw, save,
)
from test_normal_user_worker_join import normal_env, action
from test_same_user_worker_attach import ordinary, admitted
from test_admin_foundation import mounted_app
from test_operator_metadata_controls import snapshot as payload_snapshot
from hermes_cli import friday_user_scope as scope
from hermes_cli.config import require_readable_config_before_write
from friday_admin_controls import onboarding
from friday_admin_controls import worker_archive as archive
from friday_admin_controls.runtime_process import StopUnconfirmed

REAL_NATIVE_GUARD = archive._native_guard


REFUSALS = (PermissionError, ValueError, RuntimeError, OSError)
CANARY = 'SYNTHETIC_PRIVATE_ARCHIVE_CANARY_7c40'
URL = '/api/plugins/friday_rework/onboarding/workers/archive?profile=default'


def snapshot(root):
    """Keep native fixture exclusions while also detecting inode replacement."""
    result = payload_snapshot(root)
    for name, value in tuple(result.items()):
        info = (root / name).lstat()
        identity = (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
        if value[0] != 'directory':
            identity += (info.st_nlink,)
        result[name] = value + ('identity', identity)
    return result


def private_json(path, value):
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing):
        parent.mkdir(mode=0o700)
    # Synthetic paths only.  Do not widen existing directories or follow links.
    path.write_bytes((json.dumps(value, sort_keys=True) + '\n').encode())
    path.chmod(0o600)
    return reference(path)


def reference(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def payload(e, request, **changes):
    return dict(expected_config_sha256=cas(e), generation=row(e)['generation'],
                **ident(), request=request) | changes


def invoke(e, request, **changes):
    values = payload(e, request, **changes)
    session = values.pop('session', e.operator)
    return e.setup.archive_workers('default', session=session, **values)


def own_payload(e):
    """Product bytes that archival and reprepare must preserve exactly."""
    h = home(e)
    return {name: (h / name).read_bytes() for name in
            ('config.yaml', scope.ONBOARDING, scope.MARKER, '.env',
             'workspace/conversation-preserved.txt')}


def ordinary_unchanged(e, before):
    assert own_payload(e) == before
    assert row(e)['enabled'] and row(e)['generation'] == 1
    assert admitted(e)[0]
    config = require_readable_config_before_write(home(e) / 'config.yaml')
    settings = config['plugins']['entries']['friday_rework']['settings']
    assert settings['runtime'] == {'enabled': False}
    assert 'worker_requirements' not in settings


def only_archive_journal_added(e, before):
    """Post-admission refusals may consume the attempt, never alter payload.

    Auth/CAS/current-pin refusals still use exact whole-snapshot equality. Once
    admitted, the atomic no-replay claim can add only its own journal namespace.
    All preexisting bytes, modes and directories must remain unchanged.
    """
    after = snapshot(e.home)
    assert all(name in after and after[name] == value for name, value in before.items())
    allowed = 'profiles/user-1/worker-setup-archive'
    assert all(name == allowed or name.startswith(allowed + '/')
               for name in set(after) - set(before))


def signed_app(e):
    """Use the registered fixture provider and real native ASGI auth middleware."""
    from hermes_cli.dashboard_auth import middleware
    app = mounted_app(e)
    fixture_guard = getattr(e, 'offline_archive_guard', None)
    if fixture_guard is not None:
        # The dashboard loader can own a second supported package namespace.
        # Patch its trusted native boundary too; never let a disposable signed
        # API test accidentally inspect the host's actual service manager.
        route = next(r for r in app.routes if r.path.endswith('/onboarding/workers/archive'))
        admin = route.endpoint.__globals__['_admin']
        package = type(admin).__module__.rsplit('.', 1)[0]
        routed_engine = importlib.import_module(package + '.worker_archive')
        e.monkeypatch.setattr(routed_engine, '_native_guard', fixture_guard)

    @app.middleware('http')
    async def gate(request, next_call):
        return await middleware.gated_auth_middleware(request, next_call)

    return app


def post(e, body, token=None, *, url=URL):
    app = signed_app(e)
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://offline-fixture') as client:
            return await client.post(url, json=body, headers=headers)

    return asyncio.run(send())


@pytest.fixture
def stale(normal_env, monkeypatch):
    """Real ordinary admission and prepared workers; synthetic closed old claim.

    The current tree contains preparation only.  The failed native attempt was
    already moved by the previous explicit archive transaction.  Reconstruct
    those private documents from the public schema, never read a live home.
    """
    e = normal_env
    ordinary(e)
    h = home(e)
    path = h / 'workspace/conversation-preserved.txt'
    path.write_text(CANARY + ': existing user conversation\n')
    path.chmod(0o600)
    action(e, 'prepare', template='friday-local')
    # Reseal a current own configuration through the existing native managed
    # edit path. The inert synthetic nonce distinguishes it from the archived
    # template/configuration without changing a model, credential or budget.
    from hermes_cli.config import config_write_transaction, atomic_config_write
    with scope.authority(h), config_write_transaction(h / 'config.yaml'):
        current = require_readable_config_before_write(h / 'config.yaml')
        current['fixture_current_own_configuration'] = CANARY
        edit = onboarding.prepare_admin_config_edit(h, current)
        atomic_config_write(h / 'config.yaml', current)
        onboarding.finish_admin_config_edit(h, edit)
    # A current installation metadata update makes the attachment root pin
    # stale while the admitted ordinary profile remains independently valid.
    config = raw(e)
    config['owner_unrelated'] = 'CURRENT_CONFIGURATION_MUST_REMAIN_AUTHORITY'
    config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']['config']['fixture_current_template'] = CANARY
    save(e, config)
    with scope.authority(e.home):
        binding = next(b for b in scope.policy(e.home)['bindings']
                       if b['runtime_profile'] == h.name)
    claim = dict(boot_id='SYNTHETIC_CLOSED_BOOT', started_mono=4000.0,
                 deadline_mono=4300.0, budget_seconds=300)
    failure = dict(state='REFUSED_OR_UNCERTAIN', original_attempt=claim,
                   retry_authorized=False, a0_probe_cleanup='OWN_INITIAL_PROBE_CUSTODY',
                   error_kind='internal_error')
    documents = e.home / 'synthetic-archive-evidence'
    previous = e.home / 'preparation/previous-closed-worker-archive'
    failed = previous / 'failed-qualification'
    failure_ref = private_json(failed / 'failure.json', failure)
    failed_tree = archive.snapshot_tree(failed)
    mapping = {str(h / 'workers/qualification'): str(failed)}
    old_failure = dict(path=str(h / 'workers/qualification/failure.json'),
                       sha256=failure_ref['sha256'])
    old_intent = private_json(previous / 'intent.json', dict(
        schema='friday.ordinary-closed-worker-reconciliation.v2', state='CONSUMED_NO_RETRY',
        original_attempt=claim, old_attempt_retry_authorized=False,
        runtime_authority='NOT_GRANTED', tree=failed_tree, failure=old_failure,
        archive_mapping=mapping))
    old_commit = private_json(previous / 'committed.json', dict(
        state='ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY',
        original_attempt=claim, old_attempt_retry_authorized=False,
        runtime_authority='NOT_GRANTED', archive_mapping=mapping, ready=False,
        resume_allowed=False, workers_enabled=False, consumers_started=False,
        runtime_acceptance=False))
    clock = private_json(documents / 'original-clock.json', dict(
        operation='SYNTHETIC_SINGLE_CLOSED_ATTEMPT', boot_id=claim['boot_id'],
        physical_seconds=420, server_entry_seconds=300, POST_count=1,
        retry_authorized=False, started_monotonic=3999.0,
        deadline_monotonic=4419.0))
    native_unit = 'friday-qualify-dsh-' + hashlib.sha256(
        str(h / 'workers/qualification/dsh-safety').encode()).hexdigest()[:24] + '-1.scope'
    stopped = dict(ActiveState='inactive', SubState='dead', ControlGroup='',
                   InvocationID='', MainPID='0', ControlPID='0')
    cessation = private_json(documents / 'native-cessation.json', dict(
        operation='SYNTHETIC_SINGLE_CLOSED_ATTEMPT', failure=failure,
        response={'status': 503}, retry_authorized=False, bootstrap_state=None,
        bootstrap_cleanup_confirmed=True, all_observed_native_units_terminal=True,
        model_calls_by_this_operation=0, per_job_authority='NOT_GRANTED',
        native_after={native_unit: stopped,
                      'friday-rework-docker.service': copy.deepcopy(stopped)}))
    closed = private_json(documents / 'closed-custody.json', dict(
        schema='friday.exact-current-normal-diagnostic-closure.v1',
        state='CONSUMED_CLOSED_FAILED_503_INTERNAL_ERROR_WORKERS_OFF_NO_RETRY',
        original_server_attempt=claim, original_physical_deadline_preserved=True,
        retry_authorized=False, actual_HTTP_qualification_POSTs=1,
        A0='NOT_STARTED_NO_BOOTSTRAP_OR_PLAN', worker_runtime=False,
        all_actual_owned_finite_clients_reaped=True, original_physical_seconds=420,
        refs={'ROOT-DIAGNOSTIC-CLOCK.json': clock,
              'ROOT-DIAGNOSTIC-RESULT.json': cessation}))
    request = dict(
        schema='friday.worker-stale-archive.v1',
        intent='ARCHIVE_STALE_WORKER_SETUP_NO_RETRY', home=str(h), profile=h.name,
        binding_sha256=scope._fingerprint(binding), generation=row(e)['generation'],
        tree=archive.snapshot_tree(h / 'workers'), original_attempt=claim,
        original_failure=failure_ref, closed_custody=closed, original_clock=clock,
        native_cessation=cessation, native_unit=private_json(documents / 'gateway.service', {'OFFLINE_NATIVE_UNIT': True}),
        original_archive={'intent': old_intent, 'committed': old_commit},
        current={'root_configuration': reference(e.home / 'config.yaml'),
                 'configuration': reference(h / 'config.yaml'),
                 'onboarding': reference(h / scope.ONBOARDING),
                 'user_marker': reference(h / scope.MARKER)})
    request_path = documents / 'request.json'
    request_ref = private_json(request_path, request)
    native_calls = []

    @contextmanager
    def offline_stopped(home_path, requested, budget):
        """OFFLINE trusted native boundary; no authorization or payload bypass."""
        assert home_path == h and requested['native_unit'] == request['native_unit']
        budget.check()
        native_calls.append('STOPPED_OWNER_CHECK_ENTER')
        yield lambda **kwargs: budget.check()
        budget.check()
        native_calls.append('STOPPED_OWNER_CHECK_EXIT')

    monkeypatch.setattr(archive, '_native_guard', offline_stopped)
    e.offline_archive_guard = offline_stopped
    return SimpleNamespace(e=e, h=h, binding=binding, request=request,
        path=request_path, ref=request_ref, native_calls=native_calls,
        before=own_payload(e), tree=copy.deepcopy(request['tree']),
        claim=claim, failure=failure, previous=previous, documents=documents, native_unit=native_unit)


def rewrite(s):
    s.ref = private_json(s.path, s.request)
    return s.ref


def archive_direct(s, **changes):
    from friday_admin_controls.runtime_containment import Budget
    values = dict(verify=lambda: None, budget=Budget(180)) | changes
    with scope.authority(s.h):
        return archive.archive(s.h, s.binding, 1, s.request, **values)


def archive_directory(s):
    candidates = list((s.h / 'worker-setup-archive').glob('transactions/*/workers'))
    assert len(candidates) == 1
    return candidates[0]


def test_archive_preserves_bytes_then_explicit_reprepare_uses_current_home_and_template(stale, monkeypatch):
    s = stale
    old_root = (s.e.home / 'config.yaml').read_bytes()
    old_evidence = snapshot(s.previous)
    old_identities = copy.deepcopy(s.tree)
    forbidden = []

    def no_qualification(*args, **kwargs):
        forbidden.append(True)
        pytest.fail('archival/preparation must not qualify or grant native runtime')

    from friday_admin_controls import user_worker_join
    monkeypatch.setattr(user_worker_join, 'qualify', no_qualification)
    receipt = invoke(s.e, s.ref)
    target = archive_directory(s)
    assert archive.snapshot_tree(target) == old_identities
    assert not (s.h / 'workers').exists()
    assert receipt['runtime_authority'] == 'NOT_GRANTED'
    assert receipt['old_attempt_retry_authorized'] is False
    assert snapshot(s.previous) == old_evidence
    ordinary_unchanged(s.e, s.before)
    assert (s.e.home / 'config.yaml').read_bytes() == old_root
    # Archive alone creates no fresh tree or readiness. Preparation is an
    # independently explicit current API action with current CAS and template.
    from friday_admin_controls import worker_provision
    real_prepare = worker_provision.prepare_inputs
    current_configs = []

    def observe_current_config(home_path, profile, kind, runtime, config, **kwargs):
        # This spy leaves production validation/rendering intact and observes
        # an input that is deliberately absent from the old archived template.
        assert config['fixture_current_own_configuration'] == CANARY
        current_configs.append(kind)
        return real_prepare(home_path, profile, kind, runtime, config, **kwargs)

    monkeypatch.setattr(worker_provision, 'prepare_inputs', observe_current_config)
    prepared = action(s.e, 'prepare', template='friday-local')
    assert prepared['enabled'] and prepared['required_workers'] == ['dsh', 'a0']
    assert set(current_configs) == {'dsh', 'a0'}
    attachment = json.loads((s.h / onboarding.WORKER_ATTACHMENT).read_text())
    assert attachment['installation_config_sha256'] == cas(s.e)
    assert attachment['proof'] == reference(s.h / scope.ONBOARDING)
    current_template = raw(s.e)['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
    assert attachment['template_sha256'] == scope._fingerprint(current_template)
    own = require_readable_config_before_write(s.h / 'config.yaml')
    from friday_admin_controls.worker_provision import prepare_inputs
    c = attachment['runtimes']['dsh']
    # The real producer re-renders from current own config, independent of the
    # archived preparation; no patched renderer or stale template is consumed.
    _, _, expected_files, _, _ = prepare_inputs(
        s.h, s.h.name, 'dsh', c, own, tools=s.binding['tools'])
    patch = Path(c['dsh']['patch']['path'])
    assert patch.read_bytes() == expected_files[patch]
    assert patch.stat().st_ino != (target / 'dsh/inputs/dsh-local.json').stat().st_ino
    assert archive.snapshot_tree(target) == old_identities
    assert not (s.h / 'workers/qualification').exists()
    assert not any((s.h / 'workers' / kind / 'runtime-receipt.json').exists()
                   for kind in ('dsh', 'a0'))
    assert not forbidden
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('changed', [
    'root-configuration', 'configuration', 'onboarding', 'user-marker',
    'binding', 'generation', 'account', 'request-bytes', 'native-grant', 'revoked-user',
])
def test_current_authority_drift_refuses_without_archiving_or_resealing(stale, changed):
    s = stale
    options = {}
    keys = {'root-configuration': 'root_configuration', 'configuration': 'configuration',
            'onboarding': 'onboarding', 'user-marker': 'user_marker'}
    if changed in keys:
        path = Path(s.request['current'][keys[changed]]['path'])
        path.write_bytes(path.read_bytes() + b'\n')
    elif changed == 'binding':
        s.request['binding_sha256'] = 'b' * 64
        rewrite(s)
    elif changed == 'generation':
        s.request['generation'] += 1
        rewrite(s)
    elif changed == 'account': options['account_id'] = 'foreign-account'
    elif changed == 'request-bytes': s.path.write_bytes(s.path.read_bytes() + b' ')
    elif changed == 'native-grant':
        from gateway.pairing import PairingStore
        assert PairingStore().revoke('telegram', '1')
    else:
        s.e.admin.set_user('default', **ident(), enabled=False, role='user')
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref, **options)
    assert snapshot(s.e.home) == before
    assert not s.native_calls
    assert (s.h / 'workers').is_dir()


def test_direct_missing_operator_is_rejected_before_reading_protected_request(stale, monkeypatch):
    s = stale
    touched = []
    original = onboarding.digest

    def checked_digest(path):
        if Path(path) == s.path:
            touched.append(True)
            pytest.fail('unauthorized direct call read a protected request')
        return original(path)

    monkeypatch.setattr(onboarding, 'digest', checked_digest)
    original_read = archive.read_request

    def checked_read(value):
        if value == s.ref:
            touched.append(True)
            pytest.fail('unauthorized direct call inspected a protected request')
        return original_read(value)

    monkeypatch.setattr(archive, 'read_request', checked_read)
    before = snapshot(s.e.home)
    with pytest.raises(PermissionError):
        invoke(s.e, s.ref, session=None)
    assert not touched and snapshot(s.e.home) == before


@pytest.mark.parametrize('damage', [
    'workers-symlink', 'file-symlink', 'file-hardlink', 'file-public',
    'directory-public', 'missing-file', 'unknown-file', 'unknown-directory',
])
def test_exact_tree_refuses_unsafe_or_unknown_artifacts_without_adoption(stale, damage):
    s = stale
    p = s.h / 'workers/dsh/inputs/dsh-local.json'
    if damage == 'workers-symlink':
        (s.h / 'workers').rename(s.h / 'retained-unmoved-workers')
        (s.h / 'workers').symlink_to(s.h / 'retained-unmoved-workers', target_is_directory=True)
    elif damage == 'file-symlink':
        retained = s.documents / 'retained-patch.json'
        p.rename(retained)
        p.symlink_to(retained)
    elif damage == 'file-hardlink': os.link(p, s.documents / 'retained-hardlink')
    elif damage == 'file-public': p.chmod(0o644)
    elif damage == 'directory-public': p.parent.chmod(0o755)
    elif damage == 'missing-file': p.unlink()
    elif damage == 'unknown-file': private_json(s.h / 'workers/unknown.json', {'private': CANARY})
    else: (s.h / 'workers/unknown-directory').mkdir(mode=0o700)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    only_archive_journal_added(s.e, before)


def revise_provenance(s, key, mutate):
    path = Path(s.request[key]['path'])
    document = json.loads(path.read_text())
    mutate(document)
    s.request[key] = private_json(path, document)
    if key in ('original_clock', 'native_cessation'):
        closure_path = Path(s.request['closed_custody']['path'])
        closure = json.loads(closure_path.read_text())
        closure['refs'][{'original_clock': 'ROOT-DIAGNOSTIC-CLOCK.json',
                         'native_cessation': 'ROOT-DIAGNOSTIC-RESULT.json'}[key]] = s.request[key]
        s.request['closed_custody'] = private_json(closure_path, closure)
    rewrite(s)


@pytest.mark.parametrize('damage', [
    'closure-unreaped', 'closure-retry', 'closure-runtime', 'closure-wrong-attempt',
    'clock-new-boot', 'clock-new-budget', 'clock-second-post', 'clock-nan',
    'cessation-active', 'cessation-unknown-unit', 'cessation-uncertain-cleanup',
    'cessation-model-call', 'cessation-per-job-grant',
])
def test_closed_custody_and_original_attempt_cannot_be_replaced_by_new_claims(stale, damage):
    s = stale
    if damage.startswith('closure-'):
        key = 'closed_custody'
        def change(v):
            if damage == 'closure-unreaped': v['all_actual_owned_finite_clients_reaped'] = False
            elif damage == 'closure-retry': v['retry_authorized'] = True
            elif damage == 'closure-runtime': v['worker_runtime'] = True
            else: v['original_server_attempt']['started_mono'] += 1
    elif damage.startswith('clock-'):
        key = 'original_clock'
        def change(v):
            if damage == 'clock-new-boot': v['boot_id'] = 'FOREIGN_BOOT'
            elif damage == 'clock-new-budget': v['physical_seconds'] = 421
            elif damage == 'clock-second-post': v['POST_count'] = 2
            else: v['started_monotonic'] = float('nan')
    else:
        key = 'native_cessation'
        def change(v):
            if damage == 'cessation-active': v['native_after'][s.native_unit]['ActiveState'] = 'active'
            elif damage == 'cessation-unknown-unit': v['native_after'].pop(s.native_unit)
            elif damage == 'cessation-uncertain-cleanup': v['bootstrap_cleanup_confirmed'] = False
            elif damage == 'cessation-model-call': v['model_calls_by_this_operation'] = 1
            else: v['per_job_authority'] = 'GRANTED'
    revise_provenance(s, key, change)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    only_archive_journal_added(s.e, before)
    assert (s.h / 'workers').is_dir()


@pytest.mark.parametrize('custody', ['active', 'foreign', 'unknown', 'uncertain'])
def test_live_custody_refusal_precedes_archive_rename(stale, monkeypatch, custody):
    s = stale

    @contextmanager
    def refusing_guard(*args, **kwargs):
        # Explicit trusted native-boundary fixture, never an authorization
        # injection.  A real native owner refusal must leave payload in place.
        if custody == 'uncertain': raise StopUnconfirmed('OFFLINE uncertain native custody')
        raise PermissionError('OFFLINE ' + custody + ' native custody')
        yield  # Keep this a context manager; no native operation is performed.

    monkeypatch.setattr(archive, '_native_guard', refusing_guard)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    assert archive.snapshot_tree(s.h / 'workers') == s.tree
    ordinary_unchanged(s.e, s.before)
    # Consumed reconciliation records may be written, but no payload or prior
    # closed-attempt document can be rewritten by uncertain current custody.
    assert all(snapshot(s.e.home)[name] == value for name, value in before.items()
               if name.startswith('profiles/user-1/workers/') or name.startswith('preparation/'))


@pytest.mark.parametrize('foreign', ['whole-tree', 'original-failure', 'original-archive-mapping'])
def test_other_users_stale_tree_or_old_attempt_cannot_be_archived_at_same_generation(stale, foreign):
    s = stale
    # The other profile intentionally has the same numerical generation. A
    # generation comparison alone must never establish cross-user ownership.
    other = s.e.home / 'profiles/other-user'
    other.mkdir(mode=0o700)
    if foreign == 'whole-tree':
        (other / 'workers').mkdir(mode=0o700)
        private_json(other / 'workers/attachment.json', {'private': CANARY})
        s.request['tree'] = archive.snapshot_tree(other / 'workers')
    elif foreign == 'original-failure':
        s.request['original_failure'] = private_json(other / 'failure.json', s.failure)
    else:
        mapping = {str(other / 'workers/qualification'): str(s.previous / 'failed-qualification')}
        for field in ('intent', 'committed'):
            p = Path(s.request['original_archive'][field]['path'])
            doc = json.loads(p.read_text())
            doc['archive_mapping'] = mapping
            s.request['original_archive'][field] = private_json(p, doc)
    rewrite(s)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    only_archive_journal_added(s.e, before)
    assert archive.snapshot_tree(s.h / 'workers') == s.tree


@pytest.mark.parametrize('collision', ['foreign-child', 'foreign-transaction', 'archive-symlink'])
def test_archive_collision_preserves_foreign_destination_and_own_tree(stale, collision):
    s = stale
    root = s.h / 'worker-setup-archive'
    if collision == 'archive-symlink':
        root.symlink_to(s.documents, target_is_directory=True)
    else:
        root.mkdir(mode=0o700)
        if collision == 'foreign-child': private_json(root / 'foreign.json', {'private': CANARY})
        else:
            key = hashlib.sha256(archive.encoded(
                {'home': str(s.h), 'identity': s.tree['directories']['.']})).hexdigest()
            private_json(root / 'transactions' / key / 'workers/foreign.json', {'private': CANARY})
    before = snapshot(s.e.home)
    result = None
    try:
        result = invoke(s.e, s.ref)
    except REFUSALS:
        pass
    if result is not None:
        assert result['state'] == 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY'
        assert result['runtime_authority'] == 'NOT_GRANTED'
    after = snapshot(s.e.home)
    assert all(after[name] == value for name, value in before.items())
    assert archive.snapshot_tree(s.h / 'workers') == s.tree
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('repeat', ['same-request', 'new-reference', 'new-clock'])
def test_consumed_old_attempt_cannot_replay_with_new_request_or_clock(stale, repeat):
    s = stale
    first = invoke(s.e, s.ref)
    assert first['state'] == 'ARCHIVED_STALE_WORKER_SETUP_NO_RUNTIME_AUTHORITY'
    if repeat == 'new-reference':
        s.ref = private_json(s.documents / 'new-operation-id-request.json', s.request)
    elif repeat == 'new-clock':
        path = s.documents / 'new-operation-clock.json'
        s.request['original_clock'] = private_json(path, dict(
            operation='NEW_CLOCK_MUST_NOT_AUTHORIZE_RETRY', boot_id='NEW_BOOT',
            physical_seconds=420, server_entry_seconds=300, POST_count=1,
            retry_authorized=False, started_monotonic=9000.0, deadline_monotonic=9420.0))
        rewrite(s)
    before = snapshot(s.e.home)
    calls = list(s.native_calls)
    repeated = invoke(s.e, s.ref)
    assert repeated['state'] == 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY'
    assert repeated['runtime_authority'] == 'NOT_GRANTED'
    assert repeated['retry_authorized'] is False
    assert snapshot(s.e.home) == before and s.native_calls == calls
    assert not (s.h / 'workers').exists()
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('boundary', ['before-rename', 'after-rename', 'before-commit', 'after-commit'])
def test_interrupted_archive_rolls_back_owned_bytes_and_permanently_consumes_attempt(stale, monkeypatch, boundary):
    s = stale
    from scripts import friday_ordinary_install as atomic
    rename = atomic.rename_directory_noreplace
    publish = archive._write_at
    primary = OSError('SYNTHETIC one-shot archive boundary failure')
    fired = []

    def rename_fault(source_fd, source, target_fd, target):
        first = source == 'workers' and target == 'workers' and not fired
        if first and boundary == 'before-rename':
            fired.append(True)
            raise primary
        result = rename(source_fd, source, target_fd, target)
        if first and boundary == 'after-rename':
            fired.append(True)
            raise primary
        return result

    def publish_fault(parent, name, value):
        if name == 'committed.json' and not fired and boundary == 'before-commit':
            fired.append(True)
            raise primary
        result = publish(parent, name, value)
        if name == 'committed.json' and not fired and boundary == 'after-commit':
            fired.append(True)
            raise primary
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(atomic, 'rename_directory_noreplace', rename_fault)
        scoped.setattr(archive, '_write_at', publish_fault)
        with pytest.raises(OSError) as caught:
            invoke(s.e, s.ref)
    assert caught.value is primary and fired == [True]
    assert archive.snapshot_tree(s.h / 'workers') == s.tree
    tx = next((s.h / 'worker-setup-archive/transactions').iterdir())
    assert not (tx / 'workers').exists() and not (tx / 'released.json').exists()
    failure = json.loads((tx / 'failure.json').read_text())
    assert failure['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert failure['retry_authorized'] is False
    assert json.loads((tx / 'intent.json').read_text())['original_attempt'] == s.claim
    # An immutable possibly-published commit alone never means success after
    # rollback. Disposition excludes that interpretation without deleting proof.
    if (tx / 'committed.json').exists():
        assert json.loads((tx / 'disposition.json').read_text())['runtime_authority'] == 'NOT_GRANTED'
    before = snapshot(s.e.home)
    repeated = invoke(s.e, s.ref)
    assert repeated['state'] == 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY'
    assert snapshot(s.e.home) == before
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('foreign', ['new-source', 'replaced-archive', 'modified-archive', 'failed-rollback'])
def test_rollback_requires_owned_identity_and_retains_stop_unconfirmed_evidence(stale, monkeypatch, foreign):
    s = stale
    from scripts import friday_ordinary_install as atomic
    rename = atomic.rename_directory_noreplace
    publish = archive._write_at
    injected = []
    retained = {}

    def guarded_rename(source_fd, source, target_fd, target):
        if injected and foreign == 'failed-rollback':
            raise OSError('OFFLINE rollback persistence failure')
        return rename(source_fd, source, target_fd, target)

    def break_after_move(parent, name, value):
        if name == 'committed.json' and not injected:
            injected.append(True)
            target = archive_directory(s)
            if foreign == 'new-source':
                (s.h / 'workers').mkdir(mode=0o700)
                private_json(s.h / 'workers/foreign.json', {'private': CANARY})
            elif foreign == 'replaced-archive':
                target.rename(target.with_name('foreign-retained-original'))
                target.mkdir(mode=0o700)
                private_json(target / 'foreign.json', {'private': CANARY})
            elif foreign == 'modified-archive':
                p = target / 'dsh/inputs/dsh-local.json'
                p.write_bytes(p.read_bytes() + b'\nFOREIGN_MUTATION\n')
            retained['before-refusal'] = snapshot(s.e.home)
            raise OSError('OFFLINE uncertain failure after rename')
        return publish(parent, name, value)

    monkeypatch.setattr(atomic, 'rename_directory_noreplace', guarded_rename)
    monkeypatch.setattr(archive, '_write_at', break_after_move)
    with pytest.raises(archive.StopUnconfirmed):
        invoke(s.e, s.ref)
    assert injected == [True]
    tx = next((s.h / 'worker-setup-archive/transactions').iterdir())
    assert json.loads((tx / 'stop-unconfirmed.json').read_text())['state'] == 'STOP_UNCONFIRMED'
    assert not (tx / 'released.json').exists()
    after = snapshot(s.e.home)
    assert all(after[name] == value for name, value in retained['before-refusal'].items())
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('artifact', [
    'request-symlink', 'request-hardlink', 'request-public', 'failure-symlink',
    'failure-hardlink', 'closure-public', 'commit-hardlink',
])
def test_protected_request_and_provenance_cannot_follow_aliases_or_public_files(stale, artifact):
    s = stale
    if artifact.startswith('request-'): p = s.path
    elif artifact.startswith('failure-'): p = Path(s.request['original_failure']['path'])
    elif artifact == 'closure-public': p = Path(s.request['closed_custody']['path'])
    else: p = Path(s.request['original_archive']['committed']['path'])
    if artifact.endswith('-public'): p.chmod(0o644)
    elif artifact.endswith('-hardlink'): os.link(p, s.documents / ('alias-' + p.name))
    else:
        alias = s.documents / ('retained-' + p.name)
        p.rename(alias)
        p.symlink_to(alias)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    only_archive_journal_added(s.e, before)
    assert archive.snapshot_tree(s.h / 'workers') == s.tree


@pytest.mark.parametrize('revocation', ['current-configuration', 'native-grant', 'request-identity'])
def test_authority_revoked_after_rename_cannot_be_used_for_rollback(stale, monkeypatch, revocation):
    s = stale
    publish = archive._write_at
    changed = []

    def revoke_before_commit(parent, name, value):
        if name == 'committed.json' and not changed:
            changed.append(True)
            if revocation == 'current-configuration':
                p = s.e.home / 'config.yaml'
                p.write_bytes(p.read_bytes() + b'\n')
            elif revocation == 'native-grant':
                from gateway.pairing import PairingStore
                assert PairingStore().revoke('telegram', '1')
            else:
                replacement = s.path.with_name('new-inode-same-request.json')
                replacement.write_bytes(s.path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, s.path)
        return publish(parent, name, value)

    monkeypatch.setattr(archive, '_write_at', revoke_before_commit)
    with pytest.raises(archive.StopUnconfirmed):
        invoke(s.e, s.ref)
    assert changed == [True]
    target = archive_directory(s)
    assert archive.snapshot_tree(target) == s.tree
    assert not (s.h / 'workers').exists()
    assert own_payload(s.e) == s.before
    assert (target.parent / 'stop-unconfirmed.json').is_file()
    assert not (target.parent / 'released.json').exists()


@pytest.mark.parametrize('malformed', ['duplicate-key', 'nonfinite', 'trailing-json'])
def test_private_request_strict_json_rejects_ambiguous_or_nonfinite_authority(stale, malformed):
    s = stale
    raw = s.path.read_bytes()
    if malformed == 'duplicate-key':
        raw = b'{"schema":"friday.worker-stale-archive.v1",' + raw[1:]
    elif malformed == 'nonfinite':
        raw = raw.replace(b'"generation": 1', b'"generation": NaN', 1)
        assert b'NaN' in raw
    else:
        raw += b'{"unexpected_second_authority": true}'
    s.path.write_bytes(raw)
    s.ref = reference(s.path)
    before = snapshot(s.e.home)
    with pytest.raises(REFUSALS):
        invoke(s.e, s.ref)
    assert snapshot(s.e.home) == before and not s.native_calls


@pytest.mark.parametrize('boundary', ['native-release', 'release-receipt'])
def test_archive_commit_is_not_success_until_custody_release_is_confirmed(stale, monkeypatch, boundary):
    s = stale
    publish = archive._write_at

    @contextmanager
    def release_unconfirmed(home_path, requested, budget):
        yield lambda **kwargs: budget.check()
        raise archive.StopUnconfirmed('OFFLINE native custody release unconfirmed')

    def failed_release(parent, name, value):
        if name == 'released.json':
            raise OSError('OFFLINE final release receipt persistence failed')
        return publish(parent, name, value)

    if boundary == 'native-release': monkeypatch.setattr(archive, '_native_guard', release_unconfirmed)
    else: monkeypatch.setattr(archive, '_write_at', failed_release)
    with pytest.raises(archive.StopUnconfirmed):
        invoke(s.e, s.ref)
    target = archive_directory(s)
    assert archive.snapshot_tree(target) == s.tree
    assert (target.parent / 'committed.json').is_file()
    assert (target.parent / 'stop-unconfirmed.json').is_file()
    assert not (target.parent / 'released.json').exists()
    ordinary_unchanged(s.e, s.before)


def test_actual_signed_operator_can_archive_without_preparation_or_qualification(stale):
    s = stale
    response = post(s.e, payload(s.e, s.ref), s.e.operator.access_token)
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'ARCHIVED_STALE_WORKER_SETUP_NO_RUNTIME_AUTHORITY'
    assert response.json()['runtime_authority'] == 'NOT_GRANTED'
    assert not (s.h / 'workers').exists()
    assert archive.snapshot_tree(archive_directory(s)) == s.tree
    ordinary_unchanged(s.e, s.before)



@pytest.mark.parametrize('actor', ['absent', 'forged', 'ordinary', 'foreign-profile'])
def test_real_signed_archive_ingress_refuses_before_private_request_read(normal_env, actor):
    e = normal_env
    ordinary(e)
    request = {'path': str(e.home / (CANARY + '.json')), 'sha256': 'a' * 64}
    before = snapshot(e.home)
    token = {'absent': None, 'forged': 'unsigned-' + CANARY,
             'ordinary': e.provider._mint_session('ordinary').access_token,
             'foreign-profile': e.operator.access_token}[actor]
    url = URL.replace('profile=default', 'profile=foreign') if actor == 'foreign-profile' else URL
    response = post(e, payload(e, request), token, url=url)
    assert response.status_code in (401, 403), response.text
    assert CANARY not in response.text and str(e.home) not in response.text
    assert snapshot(e.home) == before


@pytest.mark.parametrize('malformed', [
    'extra-root', 'extra-ref', 'missing-ref', 'missing-sha', 'wrong-sha',
    'upper-sha', 'oversized-path', 'boolean-generation', 'generation-zero',
])
def test_signed_archive_schema_errors_are_bounded_and_redacted(normal_env, malformed):
    e = normal_env
    ordinary(e)
    body = payload(e, {'path': str(e.home / (CANARY + '.json')), 'sha256': 'a' * 64})
    if malformed == 'extra-root': body['secret'] = CANARY
    elif malformed == 'extra-ref': body['request']['secret'] = CANARY
    elif malformed == 'missing-ref': body.pop('request')
    elif malformed == 'missing-sha': body['request'].pop('sha256')
    elif malformed == 'wrong-sha': body['request']['sha256'] = CANARY
    elif malformed == 'upper-sha': body['request']['sha256'] = 'A' * 64
    elif malformed == 'oversized-path': body['request']['path'] = CANARY * 200
    elif malformed == 'boolean-generation': body['generation'] = True
    else: body['generation'] = 0
    before = snapshot(e.home)
    response = post(e, body, e.operator.access_token)
    assert response.status_code == 422, response.text
    assert response.json() == {'detail': 'invalid_product_request'}
    assert len(response.content) < 256 and CANARY not in response.text
    assert snapshot(e.home) == before


@pytest.mark.parametrize('error', [PermissionError, ValueError, OSError, StopUnconfirmed])
def test_valid_signed_archive_masks_internal_failure_metadata(normal_env, monkeypatch, error):
    """Only the failing delegate is synthetic; signed middleware/schema are real."""
    e = normal_env
    ordinary(e)
    request = private_json(e.home / 'synthetic-archive-request.json', {'private': CANARY})
    app = signed_app(e)
    route = next(r for r in app.routes if r.path.endswith('/onboarding/workers/archive'))
    api_admin = route.endpoint.__globals__['_admin']

    def failed(*args, **kwargs):
        raise error(CANARY + ':' + str(e.home))

    monkeypatch.setattr(api_admin, 'onboarding_workers_archive', failed)

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://offline-fixture') as client:
            return await client.post(URL, json=payload(e, request),
                                     headers={'Authorization': 'Bearer ' + e.operator.access_token})

    before = snapshot(e.home)
    response = asyncio.run(send())
    assert response.status_code == (403 if error is PermissionError else 400 if error is ValueError else 503)
    assert len(response.content) < 256
    assert CANARY not in response.text and str(e.home) not in response.text
    assert snapshot(e.home) == before


def fd_directory(fd):
    """Inspect only a fixture-owned retained descriptor, never native state."""
    return Path(os.readlink('/proc/self/fd/' + str(fd)))


def new_tree_inode_and_request(s):
    """A fresh exact root inode cannot erase the SAME failed-attempt claim."""
    source = s.h / 'workers'
    retained = s.h / 'fixture-retained-workers-root'
    previous = archive.snapshot_tree(source)
    source.rename(retained)
    source.mkdir(mode=0o700)
    for child in list(retained.iterdir()):
        child.rename(source / child.name)
    retained.rmdir()
    current = archive.snapshot_tree(source)
    assert current['directories']['.'] != previous['directories']['.']
    assert current['files'] == previous['files']
    assert all(current['directories'][name] == identity
               for name, identity in previous['directories'].items() if name != '.')
    s.request['tree'] = current
    # A syntactically valid rebound clock remains about the same original
    # 300-second failed attempt. It must never create another archival chance.
    old_clock = json.loads(Path(s.request['original_clock']['path']).read_text())
    old_clock['started_monotonic'] -= 1
    old_clock['deadline_monotonic'] -= 1
    s.request['original_clock'] = private_json(s.documents / 'fresh-clock-reference.json', old_clock)
    closed = json.loads(Path(s.request['closed_custody']['path']).read_text())
    closed['refs']['ROOT-DIAGNOSTIC-CLOCK.json'] = s.request['original_clock']
    s.request['closed_custody'] = private_json(s.documents / 'fresh-closed-reference.json', closed)
    s.path = s.documents / 'fresh-operation-request.json'
    rewrite(s)
    assert s.request['original_attempt'] == s.claim
    return current


def assert_same_attempt_consumed_after_new_inode(s, monkeypatch):
    current = new_tree_inode_and_request(s)
    before = snapshot(s.e.home)
    calls = []

    @contextmanager
    def never_native_again(*args, **kwargs):
        calls.append('native-reacquired')
        pytest.fail('a consumed failed attempt reached native custody again')
        yield

    monkeypatch.setattr(archive, '_native_guard', never_native_again)
    consumed = invoke(s.e, s.ref)
    assert consumed['state'] == 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY'
    assert consumed['runtime_authority'] == 'NOT_GRANTED'
    assert consumed['retry_authorized'] is False
    assert not calls and snapshot(s.e.home) == before
    assert archive.snapshot_tree(s.h / 'workers') == current
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('exception', [OSError, KeyboardInterrupt])
@pytest.mark.parametrize('boundary', [
    'attempt-directory-created', 'attempt-claim-before', 'attempt-claim-after',
    'transaction-directory-created', 'intent-before', 'intent-after',
    'tree-claim-before', 'tree-claim-after',
])
def test_claim_phase_interruption_permanently_consumes_same_attempt_across_new_tree_inode(
        stale, monkeypatch, exception, boundary):
    s = stale
    mkdir = os.mkdir
    publish = archive._write_at
    fired = []
    primary = exception('OFFLINE single claim publication interruption')

    def mkdir_fault(path, mode=0o777, *, dir_fd=None):
        result = mkdir(path, mode, dir_fd=dir_fd)
        if dir_fd is not None and not fired:
            parent = fd_directory(dir_fd)
            matched = (boundary == 'attempt-directory-created' and parent.name == 'consumed-attempts'
                       or boundary == 'transaction-directory-created' and parent.name == 'transactions')
            if matched:
                fired.append(True)
                raise primary
        return result

    def publication_fault(parent, name, value):
        directory = fd_directory(parent)
        stage = ('attempt-claim' if name == 'claim.json' and directory.parent.name == 'consumed-attempts'
                 else 'intent' if name == 'intent.json'
                 else 'tree-claim' if directory.name == 'consumed-trees' else None)
        matched = stage is not None and boundary.startswith(stage + '-') and not fired
        if matched and boundary.endswith('-before'):
            fired.append(True)
            raise primary
        result = publish(parent, name, value)
        if matched and boundary.endswith('-after'):
            fired.append(True)
            raise primary
        return result

    original_tree = archive.snapshot_tree(s.h / 'workers')
    with monkeypatch.context() as faults:
        faults.setattr(os, 'mkdir', mkdir_fault)
        faults.setattr(archive, '_write_at', publication_fault)
        with pytest.raises((OSError, KeyboardInterrupt, archive.StopUnconfirmed)):
            invoke(s.e, s.ref)
    assert fired == [True]
    assert archive.snapshot_tree(s.h / 'workers') == original_tree
    assert_same_attempt_consumed_after_new_inode(s, monkeypatch)


@pytest.mark.parametrize('exception', [OSError, KeyboardInterrupt])
@pytest.mark.parametrize('boundary', [
    'attempt-claim-before', 'attempt-claim-after', 'stop-before', 'stop-after',
])
def test_uncertain_native_custody_stop_retention_cannot_lose_attempt_replay_guard(
        stale, monkeypatch, exception, boundary):
    s = stale
    publish = archive._write_at
    retain = archive._retain_stop
    claim = archive._claim_attempt
    fired = []
    retaining = []

    @contextmanager
    def uncertain_native(*args, **kwargs):
        raise archive.StopUnconfirmed('OFFLINE uncertain native custody before transaction')
        yield

    def retaining_stop(*args, **kwargs):
        retaining.append(True)
        return retain(*args, **kwargs)

    def retained_claim_fault(*args, **kwargs):
        matched = retaining and boundary.startswith('attempt-claim-') and not fired
        if matched and boundary.endswith('-before'):
            fired.append(True)
            raise exception('OFFLINE retained claim acknowledgement failure')
        result = claim(*args, **kwargs)
        if matched and boundary.endswith('-after'):
            # The actual helper returned an open descriptor. Close this owned
            # fixture handle before simulating a lost return acknowledgement.
            os.close(result)
            fired.append(True)
            raise exception('OFFLINE retained claim lost acknowledgement')
        return result

    def stop_publication_fault(parent, name, value):
        directory = fd_directory(parent)
        stage = 'stop' if name == 'stop-unconfirmed.json' else None
        matched = retaining and stage is not None and boundary.startswith(stage + '-') and not fired
        if matched and boundary.endswith('-before'):
            fired.append(True)
            raise exception('OFFLINE stop-retention interruption')
        result = publish(parent, name, value)
        if matched and boundary.endswith('-after'):
            fired.append(True)
            raise exception('OFFLINE stop-retention lost acknowledgement')
        return result

    monkeypatch.setattr(archive, '_native_guard', uncertain_native)
    with monkeypatch.context() as faults:
        faults.setattr(archive, '_retain_stop', retaining_stop)
        faults.setattr(archive, '_claim_attempt', retained_claim_fault)
        faults.setattr(archive, '_write_at', stop_publication_fault)
        with pytest.raises(archive.StopUnconfirmed):
            invoke(s.e, s.ref)
    assert retaining
    assert fired == [True]
    assert archive.snapshot_tree(s.h / 'workers') == s.tree
    assert_same_attempt_consumed_after_new_inode(s, monkeypatch)


@pytest.mark.parametrize('boundary', ['native-release-return', 'release-receipt-published'])
@pytest.mark.parametrize('mutation', [
    'current-configuration', 'protected-request-identity',
    'transaction-path', 'archived-workers-path',
])
def test_successful_native_release_then_current_or_archive_drift_never_returns_success(
        stale, monkeypatch, boundary, mutation):
    s = stale
    from scripts import friday_ordinary_install as atomic
    rename = atomic.rename_directory_noreplace
    publish = archive._write_at
    released = []
    entered = []
    changed = []
    postrelease_native = []
    postrelease_rename = []
    retained = {}

    def mutate_owned_boundary():
        assert released and not changed
        changed.append(True)
        target = archive_directory(s)
        tx = target.parent
        retained['original-transaction'] = tx
        if mutation == 'current-configuration':
            p = s.e.home / 'config.yaml'
            p.write_bytes(p.read_bytes() + b'\n')
        elif mutation == 'protected-request-identity':
            replacement = s.path.with_name('same-bytes-new-inode-after-release.json')
            replacement.write_bytes(s.path.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, s.path)
        elif mutation == 'transaction-path':
            moved = tx.with_name('fixture-retained-original-transaction')
            tx.rename(moved)
            tx.mkdir(mode=0o700)
            private_json(tx / 'foreign.json', {'private': CANARY})
            retained['original-transaction'] = moved
        else:
            target.rename(tx / 'fixture-retained-original-workers')
            target.mkdir(mode=0o700)
            private_json(target / 'foreign.json', {'private': CANARY})
        retained['after-mutation'] = snapshot(s.e.home)

    @contextmanager
    def offline_release_success(home_path, request, budget):
        assert not entered
        entered.append(True)

        def native_prove(**kwargs):
            if released:
                postrelease_native.append(True)
                pytest.fail('archive reacquired native ownership after successful release')
            budget.check()

        yield native_prove
        released.append(True)
        if boundary == 'native-release-return':
            mutate_owned_boundary()

    def no_rollback_after_release(source_fd, source, target_fd, target):
        if released:
            postrelease_rename.append(True)
            pytest.fail('archive attempted rollback after native ownership release')
        return rename(source_fd, source, target_fd, target)

    def mutate_after_release_publication(parent, name, value):
        result = publish(parent, name, value)
        if name == 'released.json' and boundary == 'release-receipt-published' and not changed:
            assert released
            mutate_owned_boundary()
        return result

    monkeypatch.setattr(archive, '_native_guard', offline_release_success)
    monkeypatch.setattr(atomic, 'rename_directory_noreplace', no_rollback_after_release)
    monkeypatch.setattr(archive, '_write_at', mutate_after_release_publication)
    with pytest.raises(archive.StopUnconfirmed):
        invoke(s.e, s.ref)
    assert entered == [True] and released == [True] and changed == [True]
    assert not postrelease_native and not postrelease_rename
    assert not (s.h / 'workers').exists()
    tx = retained['original-transaction']
    assert (tx / 'intent.json').is_file()
    assert json.loads((tx / 'stop-unconfirmed.json').read_text())['state'] == 'STOP_UNCONFIRMED'
    # The durable consumed-attempt directory outlives a replaced tx/tree name.
    claims = list((s.h / 'worker-setup-archive/consumed-attempts').iterdir())
    assert len(claims) == 1 and claims[0].is_dir()
    after = snapshot(s.e.home)
    assert all(after[name] == value for name, value in retained['after-mutation'].items())
    # Only STOP reconciliation evidence may be added after the boundary.
    assert set(after) - set(retained['after-mutation']) == {
        str((tx / 'stop-unconfirmed.json').relative_to(s.e.home))}
    assert own_payload(s.e) == s.before


@pytest.fixture
def native_guard_adapter(stale, monkeypatch):
    """Run the real native guard against explicit OFFLINE adapter responses.

    Real protected files, descriptor retention, unit-output parsing, gateway
    role claim/release sequencing and proof checks remain production code.
    Native command execution/PID/rendezvous APIs and the user-bus socket stat
    are synthetic. No actual socket, process or service is created or queried.
    """
    s = stale
    from gateway import host_rendezvous as hr, status
    from hermes_cli import gateway as gw
    from scripts import dsh_prepare
    from friday_admin_controls.runtime_containment import Budget
    runtime_base = s.documents / 'fake-run/user'
    runtime = runtime_base / str(os.getuid())
    private_json(runtime / 'fixture-only.json', {'OFFLINE': True})
    bus = runtime / 'bus'
    state = s.documents / 'fake-host-state'
    private_json(state / 'fixture-only.json', {'OFFLINE': True})
    lock = state / 'gateway.lock'
    lock.write_bytes(b'')
    lock.chmod(0o600)
    record = state / 'gateway-record.json'
    unit = Path(s.request['native_unit']['path'])
    service = 'friday-native-fixture.service'
    daemon = 'friday-rework-docker.service'
    fixture = SimpleNamespace(s=s, fault=None, held=False, entered=False,
        role_calls=[], commands=[], lock=lock, unit=unit, bus=bus, runtime=runtime,
        budget=Budget(180), foreign_unit='friday-qualify-dsh-' + 'f' * 24 + '-1.scope')
    fixture.unit_rows = {
        service: dict(LoadState='loaded', ActiveState='inactive', SubState='dead', MainPID='0', ControlPID='0'),
        daemon: dict(LoadState='loaded', ActiveState='inactive', SubState='dead', MainPID='0', ControlPID='0', ControlGroup='', InvocationID=''),
        s.native_unit: dict(LoadState='not-found', ActiveState='inactive', SubState='dead', ControlGroup='', InvocationID=''),
    }
    native_path_type = type(Path())

    class OfflineRuntimePath(native_path_type):
        def lstat(self):
            if str(self) == str(bus):
                return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600,
                    st_uid=os.getuid() + (1 if fixture.fault == 'foreign-bus' else 0), st_nlink=1)
            return super().lstat()

    def mapped_path(value):
        if str(value) == '/run/user':
            return OfflineRuntimePath(runtime_base)
        return Path(value)

    monkeypatch.setattr(archive, 'Path', mapped_path)
    monkeypatch.setattr(gw, 'get_systemd_unit_path', lambda *, system:
        s.documents / 'absent-system-native.service' if system else
        s.documents / 'foreign-user-native.service' if fixture.fault == 'foreign-unit' else unit)
    monkeypatch.setattr(gw, 'get_service_name', lambda: service.removesuffix('.service'))

    def gateway_only(operation, role):
        assert role == hr.ROLE_GATEWAY, 'dashboard/serve role must never be probed or claimed'
        fixture.role_calls.append((operation, role))

    def owns(role):
        gateway_only('owns', role)
        return fixture.held

    def claim(role):
        gateway_only('claim', role)
        fixture.entered = True
        fixture.held = fixture.fault != 'claim-exception-unowned'
        if fixture.fault in ('claim-exception', 'claim-exception-unowned'):
            raise OSError('OFFLINE synthetic native gateway claim failure')
        return hr.HostLockOutcome.ACQUIRED, None

    def release(role):
        gateway_only('release', role)
        fixture.held = False
        if fixture.fault == 'release-exception':
            raise OSError('OFFLINE synthetic native gateway release failure')

    def read_record(role, *, include_stale):
        gateway_only('read-record', role)
        assert include_stale is True
        return {'OFFLINE_PRESENT_RENDEZVOUS': True} if fixture.fault == 'rendezvous-present' else None

    monkeypatch.setattr(hr, 'host_state_dir', lambda: state)
    monkeypatch.setattr(hr, 'lock_path', lambda role: (gateway_only('lock-path', role), lock)[1])
    monkeypatch.setattr(hr, 'record_path', lambda role: (gateway_only('record-path', role), record)[1])
    monkeypatch.setattr(hr, 'owns_host_lock', owns)
    monkeypatch.setattr(hr, 'claim_host_lock', claim)
    monkeypatch.setattr(hr, 'release_host_lock', release)
    monkeypatch.setattr(hr, 'read_record', read_record)
    monkeypatch.setattr(status, 'get_running_pid_identity_strict', lambda path:
        {'OFFLINE_PID_PRESENT': True} if fixture.fault == 'pid-active' else None)

    def unit_show(argv, cwd, *, timeout, deadline):
        # Interpret the production command request; never spawn or call native
        # systemd. Extra/foreign names must not reach this adapter at all.
        assert cwd == s.e.home
        assert argv[0] == '/usr/bin/env'
        assert argv[4:7] == ['/usr/bin/systemctl', '--user', 'show']
        name = argv[7]
        assert name in fixture.unit_rows and name != fixture.foreign_unit
        assert argv[1] == 'XDG_RUNTIME_DIR=' + str(runtime)
        assert argv[2] == 'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(bus)
        assert argv[3] == 'SYSTEMCTL_FORCE_BUS=1'
        assert 0 < timeout <= 5 and deadline <= fixture.budget.deadline
        properties = argv[8].removeprefix('--property=').split(',')
        row = fixture.unit_rows[name].copy()
        fixture.commands.append(name)
        if fixture.fault == 'gateway-active' and name == service: row['ActiveState'] = 'active'
        elif fixture.fault == 'daemon-active' and name == daemon: row['ActiveState'] = 'active'
        elif fixture.fault == 'scope-loaded' and name == s.native_unit: row['LoadState'] = 'loaded'
        elif fixture.fault == 'scope-unknown' and name == s.native_unit: row['LoadState'] = 'unknown'
        text = '\n'.join(key + '=' + row[key] for key in properties) + '\n'
        if fixture.fault == 'malformed-properties': text = 'ActiveState\n'
        elif fixture.fault == 'duplicate-properties': text += 'ActiveState=inactive\n'
        return text, '', 0

    monkeypatch.setattr(dsh_prepare, 'run', unit_show)
    return fixture


@pytest.mark.parametrize('fault', [
    'none', 'foreign-history-unqueried', 'gateway-active', 'daemon-active',
    'scope-loaded', 'scope-unknown', 'malformed-properties', 'duplicate-properties',
    'foreign-unit', 'changed-unit-pin', 'changed-lock', 'pid-active',
    'rendezvous-present', 'claim-exception', 'claim-exception-unowned',
    'release-exception', 'ownership-lost', 'foreign-bus', 'nonempty-lock',
])
def test_real_native_guard_parser_retained_gateway_role_and_release_controls(native_guard_adapter, fault):
    f = native_guard_adapter
    s = f.s
    f.fault = fault
    if fault == 'foreign-history-unqueried':
        revise_provenance(s, 'native_cessation', lambda v:
            v['native_after'].update({f.foreign_unit: dict(
                ActiveState='inactive', SubState='dead', ControlGroup='', InvocationID='')}))
    elif fault == 'nonempty-lock': f.lock.write_bytes(b'FOREIGN_LOCK_CONTENT')
    positive = fault in ('none', 'foreign-history-unqueried')
    accepted = []

    def exercise():
        with REAL_NATIVE_GUARD(s.h, s.request, f.budget) as prove:
            accepted.append(True)
            if fault == 'changed-unit-pin': f.unit.write_bytes(f.unit.read_bytes() + b'\n')
            elif fault == 'changed-lock':
                replacement = f.lock.with_name('replacement-gateway.lock')
                replacement.write_bytes(b'')
                replacement.chmod(0o600)
                os.replace(replacement, f.lock)
            elif fault == 'ownership-lost': f.held = False
            prove()

    if positive:
        exercise()
        assert accepted == [True]
        assert set(f.commands) == set(f.unit_rows)
    else:
        with pytest.raises(REFUSALS):
            exercise()
    assert not f.held
    assert all(role == __import__('gateway.host_rendezvous', fromlist=['ROLE_GATEWAY']).ROLE_GATEWAY
               for operation, role in f.role_calls)
    if f.entered:
        assert [operation for operation, role in f.role_calls].count('claim') == 1
        assert [operation for operation, role in f.role_calls].count('release') == 1
    assert f.foreign_unit not in f.commands


@pytest.mark.parametrize('receipt_name', ['committed.json', 'released.json'])
@pytest.mark.parametrize('substitution', ['stop-content', 'same-bytes-new-inode'])
def test_successful_receipt_writer_cannot_adopt_substituted_content_or_identity(
        stale, monkeypatch, receipt_name, substitution):
    s = stale
    from scripts import friday_ordinary_install as atomic
    publish = archive._write_at
    rename = atomic.rename_directory_noreplace
    entered = []
    released = []
    changed = []
    postrelease_native = []
    postrelease_rename = []
    retained = {}

    @contextmanager
    def offline_custody(home_path, request, budget):
        assert not entered
        entered.append(True)

        def prove(**kwargs):
            if released:
                postrelease_native.append(True)
                pytest.fail('receipt substitution reacquired native ownership after release')
            budget.check()

        try:
            yield prove
        finally:
            released.append(True)

    def only_owned_rollback(source_fd, source, target_fd, target):
        if released:
            postrelease_rename.append(True)
            pytest.fail('receipt substitution rolled back without native ownership')
        return rename(source_fd, source, target_fd, target)

    def substitute_after_successful_writer(parent, name, value):
        # Production publication, byte checks, fsync and own-row capture finish
        # first. The callback then races the pathname before returning that
        # original verified row; callers must never adopt a second read as own.
        own_row = publish(parent, name, value)
        if name == receipt_name and not changed:
            changed.append(True)
            path = fd_directory(parent) / name
            before = path.lstat()
            raw = path.read_bytes()
            if substitution == 'stop-content':
                document = json.loads(raw)
                document['state'] = 'STOP_UNCONFIRMED'
                document['foreign_receipt_canary'] = CANARY
                path.write_bytes((json.dumps(document, sort_keys=True) + '\n').encode())
                assert path.lstat().st_ino == before.st_ino
            else:
                replacement = path.with_name('fixture-replacement-' + name)
                replacement.write_bytes(raw)
                replacement.chmod(0o600)
                os.replace(replacement, path)
                assert path.read_bytes() == raw and path.lstat().st_ino != before.st_ino
            retained['path'] = path
            retained['snapshot'] = snapshot(s.e.home)[str(path.relative_to(s.e.home))]
        return own_row

    monkeypatch.setattr(archive, '_native_guard', offline_custody)
    monkeypatch.setattr(atomic, 'rename_directory_noreplace', only_owned_rollback)
    monkeypatch.setattr(archive, '_write_at', substitute_after_successful_writer)
    with pytest.raises((archive.ArchiveRefused, archive.StopUnconfirmed)):
        invoke(s.e, s.ref)
    assert changed == [True] and entered == [True] and released == [True]
    assert not postrelease_native and not postrelease_rename
    foreign_path = retained['path']
    assert snapshot(s.e.home)[str(foreign_path.relative_to(s.e.home))] == retained['snapshot']
    tx = foreign_path.parent
    if (s.h / 'workers').exists():
        # A pre-release committed-receipt race may be rolled back only if the
        # original native owner and all worker identities remained proven.
        assert receipt_name == 'committed.json'
        assert archive.snapshot_tree(s.h / 'workers') == s.tree
        assert not (tx / 'workers').exists() and not (tx / 'released.json').exists()
        disposition = json.loads((tx / 'disposition.json').read_text())
        assert disposition['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    else:
        assert archive.snapshot_tree(tx / 'workers') == s.tree
        assert json.loads((tx / 'stop-unconfirmed.json').read_text())['state'] == 'STOP_UNCONFIRMED'
    # A changed release receipt is evidence of uncertainty even when its
    # pathname exists; it grants neither archive acceptance nor replay.
    if receipt_name == 'released.json':
        assert not (s.h / 'workers').exists()
    before_repeat = snapshot(s.e.home)
    repeated = invoke(s.e, s.ref)
    assert repeated['state'] == 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY'
    assert repeated['runtime_authority'] == 'NOT_GRANTED'
    assert repeated['retry_authorized'] is False
    assert snapshot(s.e.home) == before_repeat and entered == [True]
    ordinary_unchanged(s.e, s.before)
