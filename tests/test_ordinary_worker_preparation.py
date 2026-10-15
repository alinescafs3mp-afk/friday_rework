"""Isolated declaration continuation; synthetic native gate/build/service reports.

Real local Git donors, current inventories, production compiler/projection,
native config lock and publication/rollback are exercised. No native build,
namespace, network, model, service or actual installed home is used.
"""
import copy
import contextlib
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from scripts import friday_worker_preparation as prep, friday_install as entry
from scripts import friday_ordinary_install as ordinary, worker_install as workers
from scripts.install_containment import Budget
from scripts import install_containment
from test_normal_worker_install import normal, doc, pin, service, install_input

REAL_NATIVE_PREPARATION = prep.native_preparation
BUILD = {'memory_bytes': 6*1024**3, 'swap_bytes': 0, 'cpu_percent': 200, 'tasks': 128,
         'affinity': [0, 1], 'fsize_bytes': 256*1024**2, 'core_bytes': 0, 'seconds': 900, 'cleanup_seconds': 60}


@pytest.fixture
def installed(normal, monkeypatch):
    s = normal
    (s.home / 'plugins/friday_rework').chmod(0o700)
    for path in (s.home / 'plugins/friday_rework').rglob('__pycache__'):
        shutil.rmtree(path)
    from tools.configure_product import compose_product
    config = compose_product(s.value['product'])['config']
    settings = prep.configuration_settings(config)
    templates = settings['onboarding']['templates']
    templates['friday-ordinary-local'] = copy.deepcopy(templates['friday-local'])
    templates['friday-ordinary-local'].pop('worker_inputs')
    config['preserved-fixture'] = {'goal': 'never reset', 'accounting': [1, 2, 3]}
    doc(s.home / 'config.yaml', config)
    doc(s.home / 'FRIDAY-PROFILE.json', {'fixture': 'ordinary'})
    doc(s.home / 'hermes-agent.source.json', {'fixture': 'native56'})
    (s.home / 'hermes-agent').mkdir(mode=0o700)
    old = copy.deepcopy(s.value)
    old['project_files'].pop('scripts/friday_worker_preparation.py', None)
    old_ref = doc(s.deploy / 'current-input.json', old)
    new_ref = doc(s.deploy / 'new-input.json', s.value)
    gateway = ModuleType('hermes_cli.friday_ordinary_gateway')
    def normalized(cfg):
        return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    def check(home, role=False):
        cfg = yaml.safe_load((home / 'config.yaml').read_text())
        marker = entry.read_json(home / entry.MARKER)
        assert marker['ordinary_gateway']['configuration_sha256'] == normalized(cfg)
        assert prep.configuration_settings(cfg)['runtime'] == {'enabled': False}
    gateway.check = check; gateway.normalized_configuration = normalized
    gateway.configuration_identity = lambda home: (check(home), entry.read_json(home / entry.MARKER)['ordinary_gateway']['configuration_sha256'])[1]
    monkeypatch.setitem(sys.modules, gateway.__name__, gateway)
    marker = {'schema': entry.SCHEMA, 'home': str(s.home), 'source': str(s.home / 'hermes-agent'),
              'state': 'INSTALLED_TEMPLATE_INCOMPLETE', 'completion_stage': 'TELEGRAM_ORDINARY',
              'worker_state': 'BOTH_WORKERS_PREPARATION_PENDING', 'runtime_ready': False,
              'input_sha256': old_ref['sha256'], 'source_receipt_sha256': pin(s.home / 'hermes-agent.source.json')['sha256'],
              'ordinary_gateway': {'configuration_sha256': normalized(config), 'credential_files': {'.env': None}},
              'original_attempt': {'fixture': 'EXPIRED_PRESERVE'},
              'profile_files': {'config.yaml': pin(s.home / 'config.yaml')['sha256']},
              'plugin_files': {n: sha for n, sha in s.value['project_files'].items() if n.startswith('plugins/friday_rework/')}}
    doc(s.home / entry.MARKER, marker)
    # Synthetic installed native source identity only; current Git/source and
    # policy/deployment consumers below are production code, not fixtures.
    def spec(value, **kwargs):
        workers.settings(value)
        for n, sha in value['project_files'].items():
            assert entry.digest(entry.owned_file(entry.ROOT / n)) == sha
        donors = {r['id']: r for r in entry.read_json(Path(value['sources_lock']['path']))['repositories']}
        return s.home, donors
    monkeypatch.setattr(entry, 'spec_checked', spec)
    monkeypatch.setattr(entry, 'composition_checked', lambda value, source, receipt, donor: None)
    monkeypatch.setattr(entry, 'native_packages', lambda source: None)
    history = doc(s.home / 'preparation/old-build-failure.json',
                  {'returncode': -15, 'reaped': True, 'timeout': False, 'resume_allowed': False})
    reports = {k: pin(s.home / ('preparation/a0.json' if k == 'a0' else 'preparation/harness/' + n))
               for k, n in prep.NAMES.items()}
    request = {'schema': prep.SCHEMA, 'request_id': 'isolated-request-1', 'seconds': 300, 'home': str(s.home),
               'current_input': old_ref, 'preparation_input': new_ref,
               'marker': pin(s.home / entry.MARKER), 'source_receipt': pin(s.home / 'hermes-agent.source.json'),
               'configuration': pin(s.home / 'config.yaml'), 'profile': pin(s.home / 'FRIDAY-PROFILE.json'),
               'reports': reports, 'history': [history], 'native_unit': doc(s.deploy / 'native.service', {'fixture': 'unit'}),
               'build_resources': copy.deepcopy(BUILD)}
    s.request = request; s.request_path = s.deploy / 'request.json'; doc(s.request_path, request)
    s.original_config = copy.deepcopy(config); s.original_marker = copy.deepcopy(marker)
    s.profile_refs = [doc(s.home / 'profiles/existing/config.yaml', {'runtime': {'enabled': False}}),
                      doc(s.home / 'profiles/existing/.friday-onboarding.json', {'generation': 1, 'proof': 'preserved'})]
    s.history_bytes = Path(history['path']).read_bytes()
    def no_native(*args, **kwargs): pytest.fail('complete declarations executed a native preparer')
    monkeypatch.setattr(prep, 'native_preparation', lambda value, home, tx, reports, donors, budget, verify, **kw: reports)
    s.no_native = no_native
    s.hosts_live = False
    @contextlib.contextmanager
    def stopped(home, unit, budget):
        if s.hosts_live: raise entry.Refused('ordinary_update_native_stop_required')
        yield lambda: entry.require(not s.hosts_live, 'ordinary_update_no_native_consumer_required')
    monkeypatch.setattr(ordinary, 'stopped_consumers', stopped)
    return s


def execute(s):
    return ordinary.prepare_workers(s.request, s.request_path, Budget(300))


def test_complete_publication_preserves_ordinary_runtime_users_and_failed_history(installed):
    s = installed; result = execute(s)
    assert result['ready'] is False and result['runtime_enabled'] is False
    assert result['a0_service'] == 'UNREGISTERED' and result['missing_a0_service_paths']
    after = yaml.safe_load((s.home / 'config.yaml').read_text())
    declarations = prep.configuration_settings(after)['onboarding']['templates']['friday-local'].pop('worker_inputs')
    assert set(declarations['workers']) == {'dsh', 'a0'}
    expected = copy.deepcopy(s.original_config)
    prep.configuration_settings(expected)['onboarding']['templates']['friday-local'].pop('worker_inputs')
    assert after == expected
    assert Path(s.request['history'][0]['path']).read_bytes() == s.history_bytes
    marker = entry.read_json(s.home / entry.MARKER)
    assert marker['original_attempt'] == s.original_marker['original_attempt']
    assert marker['input_sha256'] == s.request['preparation_input']['sha256']
    assert marker['ordinary_gateway']['operator_entry']['input'] == s.request['preparation_input']
    assert marker['worker_state'] == 'BOTH_WORKERS_PREPARATION_PENDING'
    assert not (s.home / 'workers').exists() and not s.calls
    for ref in s.profile_refs: assert pin(Path(ref['path'])) == ref


@pytest.mark.parametrize('field', ['marker', 'configuration', 'source_receipt', 'current_input', 'preparation_input', 'profile'])
def test_changed_binding_refuses_before_attempt(installed, field):
    s = installed; path = Path(s.request[field]['path']); path.write_bytes(path.read_bytes() + b' ')
    before = (s.home / 'config.yaml').read_bytes()
    with pytest.raises(ValueError): execute(s)
    assert (s.home / 'config.yaml').read_bytes() == before
    assert not list((s.home / 'preparation').glob('ordinary-workers-*'))


@pytest.mark.parametrize('case', ['failed-build', 'missing-smoke', 'foreign-report', 'inventory-drift', 'source-drift', 'toolchain-drift'])
def test_incomplete_foreign_or_changed_native_reports_refuse(installed, case):
    s = installed
    before = (s.home / 'config.yaml').read_bytes()
    if case == 'failed-build':
        s.request['reports']['build'] = doc(Path(s.request['reports']['build']['path']),
            dict(entry.read_json(Path(s.request['reports']['build']['path'])), build={'returncode': -15, 'timeout': False, 'reaped': True}))
    elif case == 'missing-smoke':
        row = entry.read_json(Path(s.request['reports']['smoke']['path'])); row['smoke'].pop()
        s.request['reports']['smoke'] = doc(Path(s.request['reports']['smoke']['path']), row)
    elif case == 'foreign-report':
        s.request['reports']['build'] = doc(s.deploy / 'dsh-build.json', {})
    elif case == 'inventory-drift':
        (s.home / 'harness/apps/cli/lib/bin.js').write_bytes(b'changed output')
    elif case == 'source-drift':
        (s.home / 'harness/LICENSE').write_bytes(b'changed tracked source')
    else:
        (s.deploy / 'toolchain/bin/node').write_bytes(b'changed executable')
    doc(s.request_path, s.request)
    with pytest.raises((ValueError, RuntimeError, KeyError)): execute(s)
    assert (s.home / 'config.yaml').read_bytes() == before
    assert not (s.home / 'workers').exists() and not s.calls


@pytest.mark.parametrize('case', ['expired', 'foreign-home', 'foreign-profile', 'changed-resources', 'changed-runtime'])
def test_unapproved_policy_or_operational_change_fails_before_native(installed, case):
    s = installed; value = copy.deepcopy(s.value)
    if case in ('expired', 'foreign-home', 'foreign-profile'):
        ref = value['worker_install']['dsh']['web']['egress_evidence']; row = entry.read_json(Path(ref['path']))
        if case == 'expired': row['expires_unix'] = time.time() - 1
        elif case == 'foreign-home': row['runtime_home'] = str(s.deploy / 'foreign')
        else: row['runtime_profile'] = 'foreign'
        value['worker_install']['dsh']['web']['egress_evidence'] = doc(s.deploy / 'new-policy.json', row)
    elif case == 'changed-resources': value['worker_install']['dsh']['resources']['memory_bytes'] //= 2
    else: value['product']['runtime'] = {'enabled': True}
    s.request['preparation_input'] = doc(s.deploy / 'new-input.json', value); doc(s.request_path, s.request)
    with pytest.raises(ValueError): execute(s)
    assert not list((s.home / 'preparation').glob('ordinary-workers-*')) and not s.calls


def test_concurrent_configuration_change_preserved_without_publication(installed, monkeypatch):
    s = installed
    def concurrent(value, home, tx, reports, donors, budget, verify, **kw):
        cfg = copy.deepcopy(s.original_config); cfg['new-owner-pairing'] = 'preserve'
        doc(home / 'config.yaml', cfg)
        return reports
    monkeypatch.setattr(prep, 'native_preparation', concurrent)
    with pytest.raises(ValueError): execute(s)
    assert yaml.safe_load((s.home / 'config.yaml').read_text())['new-owner-pairing'] == 'preserve'
    tx = next((s.home / 'preparation').glob('ordinary-workers-*'))
    assert entry.read_json(tx / 'failure.json')['resume_allowed'] is False


def test_interrupted_request_cannot_repeat(installed, monkeypatch):
    s = installed
    def failure(*args, **kwargs): raise RuntimeError('synthetic interruption before native effects')
    monkeypatch.setattr(prep, 'native_preparation', failure)
    with pytest.raises(RuntimeError): execute(s)
    with pytest.raises(ValueError, match='consumed_no_retry'): execute(s)
    assert not s.calls and not (s.home / 'workers').exists()


@pytest.mark.parametrize('change', ['whitespace', 'seconds'])
def test_consumed_logical_request_cannot_acquire_new_clock_from_changed_json(installed, monkeypatch, change):
    s = installed
    def failure(*args, **kwargs): raise RuntimeError('synthetic interrupted attempt')
    monkeypatch.setattr(prep, 'native_preparation', failure)
    with pytest.raises(RuntimeError): execute(s)
    if change == 'whitespace': s.request_path.write_text(json.dumps(s.request, separators=(',', ':')))
    else:
        s.request['seconds'] = 301; doc(s.request_path, s.request)
    with pytest.raises(ValueError, match='consumed_no_retry'): execute(s)
    assert len(list((s.home / 'preparation').glob('ordinary-workers-*'))) == 1


def test_real_parser_dispatch_uses_one_original_budget(installed, monkeypatch, capsys):
    s = installed; calls = []
    def dispatch(request, path, budget):
        calls.append((request, path, budget.deadline)); return {'state': 'SYNTHETIC_DISPATCH_ONLY'}
    monkeypatch.setattr(ordinary, 'prepare_workers', dispatch)
    monkeypatch.setattr(sys, 'argv', ['friday_install.py', 'prepare-ordinary-workers', '--input', str(s.request_path)])
    before = time.monotonic(); entry.main(); after = time.monotonic()
    assert len(calls) == 1 and calls[0][:2] == (s.request, s.request_path)
    assert before + 300 <= calls[0][2] <= after + 300
    assert json.loads(capsys.readouterr().out)['state'] == 'SYNTHETIC_DISPATCH_ONLY'


def test_remaining_dispatch_reuses_completed_phases_and_keeps_fresh_evidence(installed, monkeypatch):
    s = installed; calls = []; checks = []; resources = []
    reports = {k: copy.deepcopy(s.request['reports'][k]) for k in ('source', 'toolchain')}
    old_reports = {k: Path(v['path']).read_bytes() for k, v in s.request['reports'].items()}
    tx = s.home / 'preparation/isolated-dispatch'; tx.mkdir(mode=0o700)
    monkeypatch.setattr(prep, 'native_resources', lambda value: resources.append(value))
    class FakeCustody:
        def __init__(self, containment, budget, env):
            assert containment == s.value['containment'] and budget.deadline > time.monotonic()
            assert env['PATH'].startswith(s.value['worker_install']['dsh']['toolchain_root'] + '/bin:')
        def probe(self, python, cwd): calls.append('namespace-probe')
        def run(self, argv, cwd, **kwargs):
            assert cwd == entry.ROOT and 0 < kwargs['timeout'] <= 840
            phase = argv[3]; calls.append(('a0-' if argv[2].endswith('a0_prepare.py') else 'dsh-') + phase)
            if argv[2].endswith('a0_prepare.py'):
                assert phase == 'check'
                doc(Path(argv[argv.index('--output') + 1]), json.loads(old_reports['a0']))
            else:
                evidence = Path(argv[argv.index('--evidence') + 1]); assert evidence == tx / 'harness'
                row = json.loads(old_reports['source'] if phase == 'check' else old_reports[phase])
                doc(evidence / ('dsh-' + phase + '.json'), row)
                if phase in ('build', 'smoke'): doc(evidence / prep.NAMES['inventory'], json.loads(old_reports['inventory']))
            return '', {'returncode': 0, 'reaped': True, 'namespace_init_exit_verified': True}
    monkeypatch.setattr(install_containment, 'Containment', FakeCustody)
    result = REAL_NATIVE_PREPARATION(s.value, s.home, tx, reports, {}, Budget(900), lambda: checks.append(True), build_resources=BUILD)
    assert calls == ['namespace-probe', 'dsh-check', 'dsh-build', 'dsh-smoke', 'a0-check']
    assert len(resources) == 5 and len(checks) == 10
    assert set(result) == set(prep.NAMES)
    assert result['source'] == s.request['reports']['source'] and result['toolchain'] == s.request['reports']['toolchain']
    for k, ref in s.request['reports'].items(): assert Path(ref['path']).read_bytes() == old_reports[k]
    assert not s.calls and not (s.home / 'workers').exists()


@pytest.mark.parametrize('case', ['memory', 'cpu', 'tasks', 'swap', 'affinity', 'fsize', 'core', 'root', 'parent-escape'])
def test_existing_native_resource_prerequisites_cannot_be_relaxed(installed, tmp_path, monkeypatch, case):
    s = installed; root = tmp_path / 'cgroups'; root.mkdir(mode=0o700)
    group = root / 'bounded'; group.mkdir(mode=0o700)
    r = BUILD
    values = {'memory.max': str(r['memory_bytes']), 'memory.swap.max': '0', 'pids.max': str(r['tasks']), 'cpu.max': '200000 100000'}
    monkeypatch.setattr(prep.resource, 'getrlimit', lambda which: (0, 0) if which == prep.resource.RLIMIT_CORE else (256*1024**2,)*2)
    for name, text in values.items(): (group / name).write_text(text)
    membership = tmp_path / 'membership'; membership.write_text('0::/bounded\n')
    prep.native_resources(r, membership=membership, root=root)
    if case == 'memory': (group / 'memory.max').write_text(str(4 * 1024**3))
    elif case == 'tasks': (group / 'pids.max').write_text('256')
    elif case == 'swap': (group / 'memory.swap.max').write_text('max')
    elif case == 'affinity': monkeypatch.setattr(prep.os, 'sched_getaffinity', lambda pid: {0})
    elif case in ('fsize', 'core'):
        wanted = prep.resource.RLIMIT_FSIZE if case == 'fsize' else prep.resource.RLIMIT_CORE
        monkeypatch.setattr(prep.resource, 'getrlimit', lambda which: (-1, -1) if which == wanted else ((0, 0) if which == prep.resource.RLIMIT_CORE else (256*1024**2,)*2))
    elif case == 'cpu': (group / 'cpu.max').write_text('400000 100000')
    elif case == 'root': membership.write_text('0::/\n')
    else: membership.write_text('0::/../bounded\n')
    with pytest.raises(ValueError): prep.native_resources(r, membership=membership, root=root)


def test_missing_resource_scope_stops_before_any_native_custody(installed, monkeypatch):
    s = installed; tx = s.home / 'preparation/isolated-refusal'; tx.mkdir(mode=0o700)
    def missing(value): raise entry.Refused('ordinary_worker_native_resource_scope_required')
    monkeypatch.setattr(prep, 'native_resources', missing)
    monkeypatch.setattr(install_containment, 'Containment', s.no_native)
    with pytest.raises(ValueError, match='native_resource_scope_required'):
        REAL_NATIVE_PREPARATION(s.value, s.home, tx, {}, {}, Budget(900), s.no_native, build_resources=BUILD)
    assert list(tx.iterdir()) == []


def test_marker_failure_restores_exact_own_config_and_keeps_history(installed, monkeypatch):
    s = installed; real_publish = ordinary.publish_update_file
    before = {n: (s.home / n).read_bytes() for n in ('config.yaml', entry.MARKER)}
    calls = []
    def publication(path, data, mode, saved, owned, name):
        calls.append(name)
        if name == entry.MARKER: raise RuntimeError('synthetic failed marker write')
        return real_publish(path, data, mode, saved, owned, name)
    monkeypatch.setattr(ordinary, 'publish_update_file', publication)
    with pytest.raises(RuntimeError): execute(s)
    assert calls == ['config.yaml', entry.MARKER, 'config.yaml']
    assert all((s.home / n).read_bytes() == data for n, data in before.items())
    assert Path(s.request['history'][0]['path']).read_bytes() == s.history_bytes


def real_identify(s, monkeypatch):
    # Exercise the actual native immutable boot-generation consumer. Source/
    # credential ownership is synthetic; its HMAC/equality logic is unmodified.
    from hermes_cli import friday_gateway_owner as owner
    monkeypatch.setattr(owner.owner, 'enabled', lambda: True)
    monkeypatch.setattr(owner.owner, 'expected', lambda: {'home': str(s.home), 'source': str(s.home / 'hermes-agent'), 'operator': 'fixture'})
    monkeypatch.setattr(owner.owner, 'read_owned', lambda path, private=True: entry.owned_file(path, private=private))
    monkeypatch.setattr(owner.owner, 'credentials', lambda home, operator: (None, {'secret': b'fixture-only-key'}, None, None))
    return lambda: owner.bind_identify(s.home, lambda: {'native': True})


def test_live_boot_identity_stays_valid_when_publication_is_pending(installed, monkeypatch):
    s = installed; make_identify = real_identify(s, monkeypatch)
    identify = make_identify(); boot = identify(); s.hosts_live = True
    before = {name: (s.home / name).read_bytes() for name in ('config.yaml', entry.MARKER)}
    result = execute(s)
    assert result['state'] == 'PENDING_NATIVE_HOST_MAINTENANCE_REQUIRED'
    assert result['reports'] == s.request['reports']
    assert identify() == boot
    assert all((s.home / name).read_bytes() == raw for name, raw in before.items())
    assert not (s.home / 'workers').exists() and not s.calls


def test_quiescent_publication_requires_fresh_native_boot_identity(installed, monkeypatch):
    s = installed; make_identify = real_identify(s, monkeypatch)
    old_identify = make_identify(); original = old_identify()
    result = execute(s)
    assert result['state'] == 'BOTH_WORKER_DECLARATIONS_PUBLISHED_QUALIFICATION_PENDING'
    with pytest.raises((ValueError, RuntimeError, PermissionError)): old_identify()
    fresh = make_identify()()
    assert fresh['native'] is True and fresh['friday_owner'] != original['friday_owner']


def test_staged_source_change_during_preparation_refuses_before_publication(installed, monkeypatch):
    s = installed; before = (s.home / 'config.yaml').read_bytes()
    def changed(value, home, tx, reports, donors, budget, verify, **kw):
        path = home / 'worker-runtime-source/scripts/a0_runtime.py'
        path.chmod(0o600); path.write_bytes(b'changed staged source, never executed')
        return reports
    monkeypatch.setattr(prep, 'native_preparation', changed)
    with pytest.raises(ValueError, match='staged_source_changed'): execute(s)
    assert (s.home / 'config.yaml').read_bytes() == before


@pytest.mark.parametrize('case', ['absent', 'partial', 'extra', 'unbounded-memory', 'unbounded-clock', 'missing-cleanup', 'boolean-affinity'])
def test_explicit_build_scope_never_changes_worker_job_resources(installed, case):
    s = installed; value = copy.deepcopy(BUILD)
    if case == 'absent': value = None
    elif case == 'partial': value.pop('tasks')
    elif case == 'extra': value['override'] = True
    elif case == 'unbounded-memory': value['memory_bytes'] = -1
    elif case == 'unbounded-clock': value['seconds'] = 86400
    elif case == 'missing-cleanup': value['cleanup_seconds'] = 0
    else: value['affinity'] = [False, True]
    before = copy.deepcopy(s.value['worker_install'])
    s.request['build_resources'] = value; doc(s.request_path, s.request)
    with pytest.raises(ValueError, match='explicit_build_resources_required'): execute(s)
    assert s.value['worker_install'] == before
    assert before['dsh']['resources']['memory_bytes'] == 2*1024**3 and before['dsh']['resources']['tasks'] == 64
    assert not list((s.home / 'preparation').glob('ordinary-workers-*'))
