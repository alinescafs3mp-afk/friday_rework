"""Source-only controls for the explicit current closed archive path.

Native build bytes and stopped service observations are synthetic. Production
source/layer validators, admission, preparation consumers, archive custody and
rollback run against disposable private files; these tests grant no runtime
acceptance and never import the installed product.
"""
import copy
import contextlib
import json
import os
import sys
from pathlib import Path

import pytest

from scripts import friday_install as f, friday_worker_preparation as recovery
from scripts import friday_ordinary_install as ordinary
from scripts.install_containment import Budget
import test_ordinary_keyless_recovery as old
from test_ordinary_keyless_recovery import (
    normal, installed, env, legacy, receiver, closed_receiver, service,
    install_input, closed_user_bus, doc, pin, snapshot, admit, reconcile,
)


POST79_FILES = {
    'patches/hermes/' + stem + suffix
    for stem in ('ordinary-file-tool-contract', 'ordinary-web-delivery-privacy',
                 'spark-request-budget', 'ordinary-file-reply-context-caption',
                 'ordinary-web-runtime-history')
    for suffix in ('-manifest.json', '.patch')
}


def source_inventory(*, legacy79=False):
    """Exact public project names; native payload hashes remain synthetic."""
    names = set("""
        config/RESEARCH.md config/SOUL.md config/apparmor/friday-dsh-native-v1
        scripts/a0_prepare.py scripts/a0_runtime.py scripts/check_dsh_local.py
        scripts/check_upstream.py scripts/check_upstream_system.py scripts/dsh_native_probe.mjs
        scripts/dsh_prepare.py scripts/friday-rework-docker.service scripts/friday_install.py
        scripts/friday_native.py scripts/friday_ordinary_a0_registration.py
        scripts/friday_ordinary_install.py scripts/friday_start.py
        scripts/friday_worker_preparation.py scripts/hermes_prepare.py
        scripts/install_containment.py scripts/install_credentials.py
        scripts/rootless_docker_launch.py scripts/worker_install.py scripts/worker_qualification.py
        sources.lock.json tools/configure_local_test.py tools/configure_product.py
        tools/render_dsh_local.py tools/web_profile.py
    """.split())
    names.update(str(path.relative_to(f.ROOT))
        for area in ('plugins/friday_rework', 'patches/hermes')
        for path in (f.ROOT / area).rglob('*')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    if legacy79:
        assert POST79_FILES <= names
        names -= POST79_FILES
    assert len(names) == (231 if legacy79 else 241)
    files = {name: f.digest(f.owned_file(f.ROOT / name)) for name in sorted(names)}
    layers = []
    for name in sorted(n for n in names if n.startswith('patches/hermes/') and n.endswith('.json')):
        body = json.loads(f.owned_file(f.ROOT / name))
        patch = body.get('patch') or 'patches/hermes/' + body['patch_file']
        assert files[patch] == body['patch_sha256']
        layers.append(dict(manifest=name, manifest_sha256=files[name], patch_sha256=files[patch]))
    assert len(layers) == (79 if legacy79 else 84)
    lock_sha = files['sources.lock.json']
    value = dict(project_files=files, sources_lock=dict(sha256=lock_sha))
    receipt = dict(sources_lock_sha256=lock_sha, layers=layers,
        files={str(n): 'a' * 64 for n in range(17686 if legacy79 else 17693)})
    return value, receipt


@pytest.fixture(autouse=True)
def keep_historical_fixture_at79(monkeypatch, tmp_path):
    """Old fixture stays historical while its checked-out source has84 layers."""
    monkeypatch.setattr(old, 'source79_inventory', lambda: source_inventory(legacy79=True))
    monkeypatch.setattr(old, 'admit', admit)
    monkeypatch.setenv('FRIDAY_FIXTURE_EVIDENCE', str(tmp_path))


def admit(s):
    r = s.recovery_request
    authority = {k: v for k, v in r.items() if k != 'admission'}
    r['admission'] = doc(s.deploy / 'archive-admission.json', dict(schema=r['schema'],
        state='ADMITTED_ARCHIVE_ONLY', request_binding_sha256=f.digest(ordinary.encoded(authority)),
        runtime_authority='NOT_GRANTED', old_attempt_retry_authorized=False))
    old.rewrite(s)


@pytest.mark.parametrize('legacy79', [False, True])
def test_real_overlay_composition_accepts_exact_current_and_historical_sets(tmp_path, monkeypatch, legacy79):
    value, receipt = source_inventory(legacy79=legacy79)
    called = []
    def native_boundary(source, row, donor, **kwargs):
        called.append((source, row, donor))
        return row['files']
    monkeypatch.setattr(f, 'source_checked', native_boundary)
    result = old.REAL_COMPOSITION_CHECK(value, tmp_path / 'synthetic-native', receipt, {})
    assert result == receipt['files'] and len(called) == 1


@pytest.mark.parametrize('fault', ['missing-layer', 'duplicate-layer', 'manifest-sha', 'patch-sha'])
def test_real_current_overlay_validator_refuses_before_native_payload(tmp_path, monkeypatch, fault):
    value, receipt = source_inventory()
    called = []
    monkeypatch.setattr(f, 'source_checked', lambda *args, **kwargs: called.append(True))
    if fault == 'missing-layer': receipt['layers'].pop()
    elif fault == 'duplicate-layer': receipt['layers'][-1] = copy.deepcopy(receipt['layers'][0])
    elif fault == 'manifest-sha': receipt['layers'][-1]['manifest_sha256'] = '0' * 64
    else: receipt['layers'][-1]['patch_sha256'] = '0' * 64
    with pytest.raises(f.Refused, match='composition_overlay_'):
        old.REAL_COMPOSITION_CHECK(value, tmp_path / 'never-read-native', receipt, {})
    assert not called


def current_failure():
    return dict(state='REFUSED_OR_UNCERTAIN', original_attempt=dict(
        boot_id='private-closed-current-boot', started_mono=4000.0,
        deadline_mono=4300.0, budget_seconds=300), retry_authorized=False,
        a0_probe_cleanup='OWN_INITIAL_PROBE_CUSTODY', error_kind='internal_error')


def current_tree(s, folder=None):
    return recovery._closed_tree_state(s.old_tree if folder is None else folder,
        recovery.CLOSED_FAILED_FILES, control=True, current=True)


def test_current_claim_accepts_retained_internal_error_without_inventing_cause():
    failure = current_failure(); before = copy.deepcopy(failure)
    assert recovery._closed_claim(failure, current=True) == failure['original_attempt']
    assert failure == before
    with pytest.raises(f.Refused): recovery._closed_claim(failure)
    old_failure = copy.deepcopy(failure); old_failure.pop('error_kind')
    assert recovery._closed_claim(old_failure) == failure['original_attempt']
    with pytest.raises(f.Refused): recovery._closed_claim(old_failure, current=True)


@pytest.mark.parametrize('fault', ['retry', 'budget', 'duration', 'nonfinite',
    'boolean-clock', 'error-kind', 'extra-key', 'state', 'cleanup'])
def test_current_claim_rejects_retry_reset_unknown_diagnostic_and_schema_growth(fault):
    failure = current_failure()
    if fault == 'retry': failure['retry_authorized'] = True
    elif fault == 'budget': failure['original_attempt']['budget_seconds'] = 420
    elif fault == 'duration': failure['original_attempt']['deadline_mono'] += 1
    elif fault == 'nonfinite': failure['original_attempt']['deadline_mono'] = float('inf')
    elif fault == 'boolean-clock':
        failure['original_attempt']['started_mono'] = True
        failure['original_attempt']['deadline_mono'] = 301.0
    elif fault == 'error-kind': failure['error_kind'] = 'guessed_DSH_JSONDecodeError'
    elif fault == 'extra-key': failure['retry_new_generation'] = False
    elif fault == 'state': failure['state'] = 'SUCCESS'
    else: failure['a0_probe_cleanup'] = 'UNCONFIRMED'
    with pytest.raises(f.Refused, match='ordinary_closed_original_claim_required'):
        recovery._closed_claim(failure, current=True)


@pytest.fixture
def committed_update_chain(tmp_path):
    """Real recursive history validator, with two private committed updates."""
    home = tmp_path / 'update-home'; home.mkdir(mode=0o700)
    deploy = tmp_path / 'update-documents'
    first = doc(deploy / 'first.json', {'synthetic': 'first installed input'})
    second = doc(deploy / 'second.json', {'synthetic': 'second installed input'})
    third = doc(deploy / 'third.json', {'synthetic': 'third installed input'})
    doc(home / 'preparation/ordinary-gateway/committed.json',
        {'state': 'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'})
    doc(home / 'preparation/ordinary-gateway-archive/old.json',
        {'state': 'OLD_ATTEMPT_RETAINED_NO_RETRY', 'seconds': 300})
    def mapping():
        return {str(p.relative_to(home)): pin(p)['sha256']
            for p in (home / 'preparation').rglob('*') if p.is_file()}
    def committed(request):
        body = f.read_json(Path(request['path']))
        tx = home / ('preparation/ordinary-source-update-' + body['previous_input']['sha256'])
        doc(tx / 'intent.json', dict(schema='friday.ordinary-telegram-source-update-transaction.v1',
            state='SOURCE_UPDATE_CONSUMED_NO_RETRY', request_sha256=request['sha256']))
        doc(tx / 'committed.json', dict(state='SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
            previous_input=body['previous_input'], current_input=body['current_input'],
            gateway_started=False, workers_enabled=False))
        return tx
    earlier = doc(deploy / 'earlier-update.json', dict(
        schema='friday.ordinary-telegram-source-update.v1', previous_input=first, current_input=second))
    committed(earlier)
    current = doc(deploy / 'current-update.json', dict(
        schema='friday.ordinary-telegram-source-update.v39', previous_input=second, current_input=third,
        predecessor_update=earlier, transaction_history=mapping()))
    tx = committed(current)
    return dict(home=home, current=current, expected=mapping(), tx=tx)


def test_real_recursive_history_preserves_committed_predecessor_and_old_closed_receipts(committed_update_chain):
    s = committed_update_chain
    actual = ordinary.update_history(s['home'], s['expected'], predecessor=s['current'])
    assert actual == s['expected'] and len(actual) == 6
    assert not (s['tx'] / 'rolled-back.json').exists()


@pytest.mark.parametrize('fault', ['missing-ref', 'wrong-sha', 'new-file', 'rollback', 'current-request-drift'])
def test_real_recursive_history_refuses_missing_drift_or_rolled_back_chain(committed_update_chain, fault):
    s = committed_update_chain; before = snapshot(s['home'])
    expected = copy.deepcopy(s['expected'])
    if fault == 'missing-ref': expected.pop(next(iter(expected)))
    elif fault == 'wrong-sha': expected[next(iter(expected))] = '0' * 64
    elif fault == 'new-file': doc(s['tx'] / 'foreign.json', {'unowned': 'must survive'})
    elif fault == 'rollback': doc(s['tx'] / 'rolled-back.json', {'state': 'ROLLED_BACK'})
    else:
        path = Path(s['current']['path']); path.write_bytes(path.read_bytes() + b' ')
    mutation = snapshot(s['home'])
    with pytest.raises((f.Refused, ValueError)):
        ordinary.update_history(s['home'], expected, predecessor=s['current'])
    assert snapshot(s['home']) == mutation
    if fault in ('missing-ref', 'wrong-sha', 'current-request-drift'):
        assert mutation == before


@pytest.fixture
def current_archive(closed_receiver, monkeypatch):
    """Source85 archive I/O with synthetic bounded historical chain identity.

    All703 ref pins and the actual update-history mechanism are tested; this
    integration fixture replaces only the extensive specific deployment chain
    with an exact private mapping. The real current admission helper has its own
    controls below. The installed fixture's unchanged historical config permits
    the existing real admission validator at this boundary.
    """
    s = closed_receiver; r = s.recovery_request
    value = f.read_json(Path(r['installed_input']['path']))
    inventory, receipt = source_inventory()
    value['project_files'] = inventory['project_files']
    helper = 'scripts/friday_worker_preparation.py'
    value['project_files'][helper] = f.digest(b'SYNTHETIC INSTALLED PRE-MAINTENANCE HELPER')
    r['installed_input'] = doc(s.deploy / 'current-installed.json', value)
    successor = copy.deepcopy(value)
    successor['project_files'][helper] = r['maintenance_source']['sha256']
    r['recovery_input'] = doc(s.deploy / 'current-recovery.json', successor)
    previous_receipt = f.read_json(Path(r['source_receipt']['path']))
    previous_receipt.update(receipt)
    previous_receipt['sources_lock_sha256'] = value['sources_lock']['sha256']
    r['source_receipt'] = doc(Path(r['source_receipt']['path']), previous_receipt)
    r['stamp'] = doc(Path(r['stamp']['path']), dict(schemaVersion=2,
        distribution='friday-rework', payload='bootstrap', fridaySource=dict(
            baseTree=previous_receipt['base_tree'], layers=previous_receipt['layers'])))
    marker = f.read_json(s.home / f.MARKER)
    marker['input_sha256'] = r['installed_input']['sha256']
    marker['source_receipt_sha256'] = r['source_receipt']['sha256']
    r['root_marker'] = doc(s.home / f.MARKER, marker)
    legacy_tree, _ = recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)
    s.legacy_workspace_modes = {row['mode'] for name, row in legacy_tree['files'].items()
        if name.startswith('dsh-safety/workspace/')}
    assert s.legacy_workspace_modes == {0o664}
    failure = current_failure()
    r['failure'] = doc(s.old_tree / 'failure.json', failure)
    for path in (s.old_tree / 'dsh-safety/workspace').rglob('*'):
        if path.is_file(): path.chmod(0o600)
    tree, _ = current_tree(s)
    r['qualification_tree'] = doc(Path(r['qualification_tree']['path']), tree)
    normalized = f.read_json(Path(r['native_cessation']['path']))
    normalized['server_claim'] = failure['original_attempt']; normalized['server_failure'] = r['failure']
    s.retained660 = copy.deepcopy(r['original_clock'])
    s.retained660_bytes = Path(s.retained660['path']).read_bytes()
    operation = 'SYNTHETIC_CURRENT_WORKER_FAILURE_DIAGNOSTIC'
    clock = dict(operation=operation, boot_id=failure['original_attempt']['boot_id'],
        accepted_unix=1700000000.0, started_monotonic=3999.0, physical_seconds=420,
        deadline_monotonic=4419.0, server_entry_seconds=300, POST_count=1,
        retry_authorized=False, outcome='UNCONFIRMED_BEFORE_SEND')
    r['original_clock'] = doc(s.deploy / 'current-clock.json', clock)
    diagnostic = dict(operation=operation,
        response=dict(status=503, body=dict(detail='native_state_unavailable_or_write_unconfirmed')),
        error_class=None, native_after={k: v['properties'] for k, v in normalized['actual_units'].items()},
        failure=failure, retry_authorized=False, bootstrap_state=None, bootstrap_cleanup_confirmed=True,
        same_gateway=True, elapsed_seconds=6.5, all_observed_native_units_terminal=True,
        model_calls_by_this_operation=0, per_job_authority='NOT_GRANTED',
        state='RETURNED_NATIVE_TERMINAL_WITH_RETAINED_BOOTSTRAP_CLEANUP')
    r['native_cessation'] = doc(s.deploy / 'current-diagnostic-result.json', diagnostic)
    post = doc(s.deploy / 'current-post-preservation.json', dict(
        schema='friday.current-diagnostic-post-preservation.v1',
        within_original_physical420=True, all_admission_pins_unchanged=True,
        all_prior_12_persistent_and_1_session_files_unchanged=True,
        old_claims_preserved=True, new_attempt_retry_authorized=False, per_job_grant=False))
    closed = dict(schema='friday.exact-current-normal-diagnostic-closure.v1',
        state='CONSUMED_CLOSED_FAILED_503_INTERNAL_ERROR_WORKERS_OFF_NO_RETRY',
        closed_moscow='2000-01-01T00:00:00+03:00', elapsed_physical_seconds=244.0,
        original_physical_seconds=420, original_server_attempt=failure['original_attempt'],
        original_physical_deadline_preserved=True, retry_authorized=False,
        actual_HTTP_qualification_POSTs=1, A0='NOT_STARTED_NO_BOOTSTRAP_OR_PLAN', worker_runtime=False,
        same_ordinary_gateway_and_authenticated_UI=True,
        full_two_DB_and_12_persistent_1_session_preserved=True,
        heavy_slot_same_inode_available_released=True, all_actual_owned_finite_clients_reaped=True,
        no_model_calls_or_Spark_traffic_by_qualification=True,
        refs={'ROOT-DIAGNOSTIC-CLOCK.json': r['original_clock'],
              'ROOT-DIAGNOSTIC-RESULT.json': r['native_cessation'],
              'ROOT-POST-PRESERVATION.json': post})
    r['closed_failure'] = doc(s.deploy / 'current-closed.json', closed)
    previous_input = doc(s.deploy / 'source85-previous.json', {'synthetic_previous_input': True})
    r['history'].append(doc(s.home / 'preparation' / ('ordinary-source-update-' +
        previous_input['sha256']) / 'committed.json', dict(
            state='SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED', current_input=r['installed_input'],
            source_receipt_sha256=r['source_receipt']['sha256'])))
    r['history'] += [doc(s.home / 'preparation/current-synthetic-history' / (str(n) + '.json'),
        {'synthetic_current_chain': n, 'retry_authorized': False}) for n in range(703 - len(r['history']))]
    history = {str(Path(ref['path']).relative_to(s.home)): ref['sha256'] for ref in r['history']}
    r['current_update'] = doc(s.deploy / 'current-update.json', dict(
        schema='friday.ordinary-telegram-source-update.v39', current_input=r['installed_input'],
        transaction_history=history, home=str(s.home), configuration=r['root_configuration'],
        profile=r['root_profile'], native_unit=r['native_unit'], previous_input=previous_input))
    monkeypatch.setattr(recovery, 'CLOSED_CURRENT_UPDATE_SHA', r['current_update']['sha256'])
    monkeypatch.setattr(recovery, 'CLOSED_CURRENT_INPUT_SHA', r['installed_input']['sha256'])
    monkeypatch.setattr(recovery, 'CLOSED_DIAGNOSTIC_SOURCE_SHA', r['diagnostic_correction']['sha256'])
    r['schema'] = recovery.CLOSED_CURRENT_SCHEMA
    s.history_calls = []; s.composition_calls = []
    def synthetic_chain(home, expected, predecessor=None, *args, **kwargs):
        assert home == s.home and predecessor == r['current_update']
        f.require(expected == history, 'ordinary_update_transaction_history_changed')
        s.history_calls.append(copy.deepcopy(expected))
        return copy.deepcopy(history)
    monkeypatch.setattr(ordinary, 'update_history', synthetic_chain)
    def retained_boundary(home, update):
        assert home == s.home and update['current_input'] == r['installed_input']
        for name in ('root_configuration', 'root_profile', 'onboarding', 'user_marker', 'configuration'):
            f.pin(r[name])
    monkeypatch.setattr(ordinary, 'checked_source82_retained', retained_boundary)
    def native_boundary(source, row, donor, **kwargs):
        s.composition_calls.append(copy.deepcopy(row['layers']))
        return row['files']
    monkeypatch.setattr(f, 'source_checked', native_boundary)
    monkeypatch.setattr(f, 'composition_checked', old.REAL_COMPOSITION_CHECK)
    def unchanged_config_admission(request, home, profile, config, attachment, history):
        assert len(s.composition_calls) >= 2
        return recovery._keyless_admission(request, home, profile, config, attachment)
    monkeypatch.setattr(recovery, '_closed_current_admission', unchanged_config_admission)
    s.normalized = normalized
    admit(s); s.before = snapshot(s.home)
    return s


def test_current_archive_preserves23_inodes_original300_420_660_and_all703_history(current_archive):
    s = current_archive; before = snapshot(s.home)
    tree, _ = current_tree(s)
    old_intent = f.read_json(Path(s.recovery_request['keyless_ancestry']['intent']['path']))
    result = reconcile(s)
    assert result['state'] == 'ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY'
    assert result['runtime_authority'] == 'NOT_GRANTED'
    for key in ('ready', 'runtime_acceptance', 'consumers_started', 'workers_enabled',
                'resume_allowed', 'old_attempt_retry_authorized'):
        assert result[key] is False
    assert result['original_attempt'] == current_failure()['original_attempt']
    archived, _ = current_tree(s, s.tx / 'failed-qualification')
    assert archived == tree and len(archived['files']) == 23 and not s.old_tree.exists()
    workspace = [row for name, row in archived['files'].items() if name.startswith('dsh-safety/workspace/')]
    assert len(workspace) == 15 and {row['mode'] for row in workspace} == {0o600}
    assert s.legacy_workspace_modes == {0o664}
    assert f.read_json(Path(s.recovery_request['keyless_ancestry']['intent']['path'])) == old_intent
    assert old_intent['original_attempt']['budget_seconds'] == 300
    assert f.read_json(Path(s.recovery_request['original_clock']['path']))['physical_seconds'] == 420
    retained_clock = f.read_json(f.pin(s.retained660))
    assert retained_clock['physical_seconds'] == 660 and retained_clock['server_seconds'] == 300
    assert retained_clock['old_original300_reset'] is retained_clock['retry_authorized'] is False
    assert Path(s.retained660['path']).read_bytes() == s.retained660_bytes
    for ref in s.recovery_request['history']:
        assert f.pin(ref) == Path(ref['path'])
    after = snapshot(s.home)
    for name, state in before.items():
        if name == f.MARKER or name.startswith(str(s.old_tree.relative_to(s.home)) + '/'): continue
        assert after[name] == state
    assert s.history_calls and len(s.history_calls[0]) == 703
    assert len(s.composition_calls) >= 2 and not s.calls and s.native_calls
    assert f.read_json(s.tx / 'intent.json')['schema'] == s.recovery_request['schema']


def test_existing_operator_cli_dispatches_current_schema_and_archives_only_closed_tree(current_archive, monkeypatch, capsys):
    s = current_archive
    tree, _ = current_tree(s)
    monkeypatch.setattr(sys, 'argv', ['friday_install.py', 'recover-ordinary-worker-keyless',
        '--input', str(s.recovery_path)])
    f.main()
    result = json.loads(capsys.readouterr().out)
    assert result == f.read_json(s.tx / 'committed.json')
    assert result['state'] == 'ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY'
    assert result['runtime_authority'] == 'NOT_GRANTED'
    assert result['old_attempt_retry_authorized'] is result['resume_allowed'] is False
    assert current_tree(s, s.tx / 'failed-qualification')[0] == tree
    assert not s.old_tree.exists() and not s.calls


def test_current_useful_budget_expiry_uses_original_cleanup_deadline_and_restores_owned_tree(current_archive, monkeypatch):
    s = current_archive; original = Budget(180); expired = []; cleanup_proofs = []
    check = Budget.check; publish = ordinary.publish_update_file; stopped = ordinary.stopped_consumers
    tree, _ = current_tree(s)
    def bounded_check(budget, *args, **kwargs):
        if expired and budget.deadline == original.deadline - 10:
            raise f.Refused('synthetic_original_useful_budget_exhausted')
        return check(budget, *args, **kwargs)
    @contextlib.contextmanager
    def custody(home, unit, budget):
        assert budget is original
        with stopped(home, unit, budget) as prove:
            def checked():
                assert budget.deadline == original.deadline
                budget.check(); prove()
                if expired: cleanup_proofs.append(True)
            yield checked
    def first_publication(*args, **kwargs):
        publish(*args, **kwargs); expired.append(True)
    monkeypatch.setattr(Budget, 'check', bounded_check)
    monkeypatch.setattr(ordinary, 'stopped_consumers', custody)
    monkeypatch.setattr(ordinary, 'publish_update_file', first_publication)
    with pytest.raises(ValueError, match='synthetic_original_useful'):
        recovery.reconcile_closed(s.recovery_request, s.recovery_path, original)
    after = snapshot(s.home)
    assert all(after[name] == value for name, value in s.before.items())
    assert cleanup_proofs and current_tree(s)[0] == tree
    clock = f.read_json(s.tx / 'intent.json')['maintenance_clock']
    assert clock['deadline_mono'] == original.deadline
    assert clock['useful_deadline_mono'] == original.deadline - 10
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert not s.calls


@pytest.mark.parametrize('fault', ['history-count', 'history-duplicate', 'history-repinned',
    'current-update-stale', 'current-update-replaced', 'checker-delta', 'product-delta',
    'native-count', 'native-layers', 'current-retry', 'current-budget', 'current-error',
    'clock420-reset', 'closure-retry', 'closure-posts', 'diagnostic-active', 'diagnostic-missing-unit',
    'diagnostic-model-call', 'post-stale', 'post-declines', 'tree-extra', 'tree-mode', 'tree-inode', 'current-native-active'])
def test_current_archive_rejects_drift_resets_or_activity_before_any_write(current_archive, fault):
    s = current_archive; r = s.recovery_request
    if fault == 'history-count': r['history'].pop()
    elif fault == 'history-duplicate': r['history'][-1] = r['history'][0]
    elif fault == 'history-repinned':
        ref = r['history'][-1]
        r['history'][-1] = doc(Path(ref['path']), {'changed_after_chain_acceptance': True})
    elif fault == 'current-update-stale':
        path = Path(r['current_update']['path']); path.write_bytes(path.read_bytes() + b' ')
    elif fault == 'current-update-replaced':
        body = f.read_json(Path(r['current_update']['path'])); body['current_input'] = r['recovery_input']
        r['current_update'] = doc(Path(r['current_update']['path']), body)
    elif fault in ('checker-delta', 'product-delta'):
        body = f.read_json(Path(r['recovery_input']['path']))
        if fault == 'checker-delta': body['project_files']['scripts/dsh_prepare.py'] = '0' * 64
        else: body['product']['runtime']['enabled'] = True
        r['recovery_input'] = doc(Path(r['recovery_input']['path']), body)
    elif fault in ('native-count', 'native-layers'):
        body = f.read_json(Path(r['source_receipt']['path']))
        if fault == 'native-count': body['files'].pop(next(iter(body['files'])))
        else: body['layers'].pop()
        r['source_receipt'] = doc(Path(r['source_receipt']['path']), body)
        marker = f.read_json(s.home / f.MARKER); marker['source_receipt_sha256'] = r['source_receipt']['sha256']
        r['root_marker'] = doc(s.home / f.MARKER, marker)
    elif fault in ('current-retry', 'current-budget', 'current-error'):
        failure = f.read_json(Path(r['failure']['path']))
        if fault == 'current-retry': failure['retry_authorized'] = True
        elif fault == 'current-budget': failure['original_attempt']['budget_seconds'] = 420
        else: failure['error_kind'] = 'guessed_subsystem_cause'
        r['failure'] = doc(Path(r['failure']['path']), failure)
        tree, _ = current_tree(s)
        r['qualification_tree'] = doc(Path(r['qualification_tree']['path']), tree)
    elif fault == 'clock420-reset':
        clock = f.read_json(Path(r['original_clock']['path'])); clock['physical_seconds'] = 660
        r['original_clock'] = doc(Path(r['original_clock']['path']), clock)
        closed = f.read_json(Path(r['closed_failure']['path']))
        closed['refs']['ROOT-DIAGNOSTIC-CLOCK.json'] = r['original_clock']
        r['closed_failure'] = doc(Path(r['closed_failure']['path']), closed)
    elif fault in ('closure-retry', 'closure-posts'):
        body = f.read_json(Path(r['closed_failure']['path']))
        body['retry_authorized' if fault == 'closure-retry' else 'actual_HTTP_qualification_POSTs'] = True if fault == 'closure-retry' else 2
        r['closed_failure'] = doc(Path(r['closed_failure']['path']), body)
    elif fault in ('diagnostic-active', 'diagnostic-missing-unit', 'diagnostic-model-call'):
        body = f.read_json(Path(r['native_cessation']['path']))
        if fault == 'diagnostic-active':
            body['native_after']['friday-rework-docker.service']['ActiveState'] = 'active'
        elif fault == 'diagnostic-missing-unit':
            body['native_after'].pop(next(k for k in body['native_after'] if k != 'friday-rework-docker.service'))
        else: body['model_calls_by_this_operation'] = 1
        r['native_cessation'] = doc(Path(r['native_cessation']['path']), body)
        closed = f.read_json(Path(r['closed_failure']['path']))
        closed['refs']['ROOT-DIAGNOSTIC-RESULT.json'] = r['native_cessation']
        r['closed_failure'] = doc(Path(r['closed_failure']['path']), closed)
    elif fault in ('post-stale', 'post-declines'):
        body = f.read_json(Path(r['closed_failure']['path']))
        post_ref = body['refs']['ROOT-POST-PRESERVATION.json']
        if fault == 'post-stale':
            path = Path(post_ref['path']); path.write_bytes(path.read_bytes() + b' ')
        else:
            post = f.read_json(Path(post_ref['path'])); post['old_claims_preserved'] = False
            body['refs']['ROOT-POST-PRESERVATION.json'] = doc(Path(post_ref['path']), post)
            r['closed_failure'] = doc(Path(r['closed_failure']['path']), body)
    elif fault == 'tree-extra': doc(s.old_tree / 'foreign.json', {'owned': 'must survive'})
    elif fault == 'tree-mode':
        (s.old_tree / 'dsh-safety/workspace/artifact').chmod(0o664)
        # Reject the format itself, before comparing its manifest with the pin.
        with pytest.raises(f.Refused, match='ordinary_closed_tree_mode_changed'):
            current_tree(s)
    elif fault == 'tree-inode':
        path = s.old_tree / 'dsh-safety/workspace/artifact'
        other = s.deploy / 'foreign-same-bytes'; other.write_bytes(path.read_bytes()); other.chmod(0o600)
        os.replace(other, path)
    else: s.native_live = True
    admit(s); before = snapshot(s.home)
    with pytest.raises((ValueError, OSError, KeyError, AssertionError)):
        reconcile(s)
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls


@pytest.mark.parametrize('fault', ['publish', 'archive-fsync', 'commit'])
def test_current_partial_failure_restores_marker_tree_and_consumes_original_failure(current_archive, monkeypatch, fault):
    # Same production rollback body must retain its behavior for the v2 entry.
    old.test_closed_partial_failure_restores_original_tree_and_marker_then_deduplicates_failure(
        current_archive, monkeypatch, fault)


def test_current_foreign_archive_inode_preserves_evidence_and_reports_stop_unconfirmed(current_archive, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = current_archive; publish = ordinary.publish_update_file
    path = s.tx / 'failed-qualification/dsh-safety/workspace/artifact'; foreign = []
    def fail(*args, **kwargs):
        publish(*args, **kwargs)
        if not foreign:
            other = s.deploy / 'foreign-inode'; other.write_bytes(path.read_bytes()); other.chmod(0o600)
            os.replace(other, path); foreign.append(ordinary.update_file_state(path))
            raise OSError('synthetic foreign inode with unchanged current mode')
    monkeypatch.setattr(ordinary, 'publish_update_file', fail)
    with pytest.raises(StopUnconfirmed): reconcile(s)
    assert ordinary.update_file_state(path) == foreign[0] and not s.old_tree.exists()
    assert (s.tx / 'failed-before/dsh-safety/workspace/artifact').read_bytes() == path.read_bytes()
    assert not (s.tx / 'committed.json').exists() and not s.calls

