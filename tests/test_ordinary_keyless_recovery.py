"""Source/fixture controls for explicit maintenance of one old keyless home.

Real private files, hashes, Git donors, onboarding admission, preparation and
publication run here. Source composition, stopped native endpoints and kernel
namespace observations are synthetic. These tests grant no runtime acceptance.
"""
import copy
import contextlib
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import friday_install as f, friday_worker_preparation as recovery
from scripts import friday_ordinary_install as ordinary, worker_install as workers
from scripts.install_containment import Budget
from test_ordinary_worker_preparation import installed, normal, service, install_input, doc, pin, configured_web_profile
from test_user_onboarding import env, complete, home as user_home, cas, ident, row, raw


def snapshot(root):
    """Bytes/modes/links, without following a foreign symlink."""
    result = {}
    for path in root.rglob('*'):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            result[str(path.relative_to(root))] = ('symlink', os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            result[str(path.relative_to(root))] = (path.read_bytes(), stat.S_IMODE(info.st_mode))
    return result


@pytest.fixture
def legacy(installed, env, monkeypatch):
    """Create an admitted worker-free user, then old helperless preparations."""
    s = installed
    configured_web_profile(s, 'exa-keyless')
    # Reuse the signed native onboarding fixture with this installed root.
    import hermes_constants
    monkeypatch.setenv('HERMES_HOME', str(s.home))
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(s.home))
    token = hermes_constants.set_hermes_home_override(str(s.home))
    env.home = s.home
    from hermes_cli.plugins_state import PluginState
    env.state = PluginState('friday_rework')
    from test_admin_foundation import Administration
    from friday_admin_controls.onboarding import Onboarding
    env.admin = Administration(); env.setup = Onboarding(env.admin)
    from tools.configure_product import compose_product
    config = compose_product(s.value['product'])['config']
    config['preserved-fixture'] = s.original_config['preserved-fixture']
    settings = recovery.configuration_settings(config)
    old_settings = env.cfg['plugins']['entries']['friday_rework']['settings']
    settings.update({k: copy.deepcopy(v) for k, v in old_settings.items() if k != 'onboarding'})
    config['gateway'] = copy.deepcopy(env.cfg['gateway'])
    ordinary_template = copy.deepcopy(settings['onboarding']['templates']['friday-local'])
    ordinary_template.pop('worker_inputs', None)
    ordinary_template['config']['plugins']['entries']['friday_rework']['settings'].pop('worker_requirements', None)
    settings['onboarding']['templates']['approved-local'] = ordinary_template
    env.template = ordinary_template
    doc(s.home / 'config.yaml', config)
    try:
        complete(env)
        # This is the real normal declaration compiler, before the missing
        # product-only extra was added to the historical installed generation.
        product, _ = workers.prepared_product(s.value, s.home, Budget(180), preparation=s.request['reports'])
        from scripts import a0_prepare
        native_sources = a0_prepare.service_sources(s.value['project_files'])
        for ref, source in ((product['runtime']['workers']['a0']['a0']['launcher'], 'scripts/rootless_docker_launch.py'),
                            (product['runtime']['workers']['a0']['a0']['daemon_unit'], a0_prepare.SERVICE_SOURCE)):
            path = Path(ref['path']); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(native_sources[source]); path.chmod(0o600)
        from plugins.friday_rework.user_worker_join import installation_inputs
        config = raw(env)
        recovery.configuration_settings(config)['onboarding']['templates']['friday-local']['worker_inputs'] = installation_inputs(product['runtime'])
        doc(s.home / 'config.yaml', config)
        # Derivation reads only these explicit synthetic namespace observations.
        from friday_admin_controls import user_worker_join as join
        namespace_stat = Path.stat
        def private_stat(path, *args, **kwargs):
            if str(path) == '/proc/self/ns/net': return SimpleNamespace(st_dev=1, st_ino=1)
            return namespace_stat(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'stat', private_stat)
        web_ref = s.value['worker_install']['dsh']['web']['egress_evidence']
        policy = f.read_json(Path(web_ref['path']))
        policy['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        s.value['worker_install']['dsh']['web']['egress_evidence'] = doc(Path(web_ref['path']), policy)
        # Update the compiled declaration to use the refreshed fixture policy.
        product, _ = workers.prepared_product(s.value, s.home, Budget(180), preparation=s.request['reports'])
        config = raw(env)
        recovery.configuration_settings(config)['onboarding']['templates']['friday-local']['worker_inputs'] = installation_inputs(product['runtime'])
        doc(s.home / 'config.yaml', config)
        env.setup.prepare_workers('default', session=env.operator,
            expected_config_sha256=cas(env), generation=row(env)['generation'],
            template='friday-local', **ident())
        s.user = user_home(env)
        from hermes_cli import friday_user_scope as scope
        from hermes_cli.friday_product_access import settings as access_settings
        with scope.authority(s.home):
            s.binding = copy.deepcopy(access_settings()['user_isolation']['bindings'][0])
        s.env = env
        s.old_tree = s.user / 'workers/qualification'
        failure = {'state': 'REFUSED_OR_UNCERTAIN', 'original_attempt': {
            'boot_id': 'closed-original-boot', 'started_mono': 1000.0,
            'deadline_mono': 1300.0, 'budget_seconds': 300},
            'retry_authorized': False, 'a0_probe_cleanup': 'OWN_INITIAL_PROBE_CUSTODY'}
        s.failure = doc(s.old_tree / 'failure.json', failure)
        for name in ('home', 'workspace'):
            (s.old_tree / 'dsh-safety' / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ('bootstrap.py', 'web-network.mjs', 'web-ca.pem'):
            path = s.old_tree / 'dsh-safety/inputs' / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(('SYNTHETIC CLOSED INPUT ' + name).encode()); path.chmod(0o400)
        s.closed = doc(s.deploy / 'closed-failure.json', {
            'failure': s.failure, 'server_original_attempt': failure['original_attempt']})
        marker = f.read_json(s.home / f.MARKER)
        marker['input_sha256'] = doc(s.deploy / 'installed-input.json', s.value)['sha256']
        marker['ordinary_gateway']['configuration_sha256'] = sys.modules['hermes_cli.friday_ordinary_gateway'].normalized_configuration(raw(env))
        doc(s.home / f.MARKER, marker)
        s.before = snapshot(s.home)
        yield s
    finally:
        hermes_constants.reset_hermes_home_override(token)


def execute(s):
    return recovery.recover_keyless(s.recovery_request, s.recovery_path, Budget(s.recovery_request['seconds']))


@pytest.fixture
def receiver(legacy):
    s = legacy
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.plugins_state import _plugin_data_namespace
    # Metadata inventories are explicit synthetic source-composition fixtures;
    # installed plugin/source pins, preparation consumers and every file write
    # remain production paths. No native checkout is loaded from an actual home.
    receipt = {'schema': 'friday.hermes-source.v1', 'base_tree': 'b' * 40,
        'files': {str(n): 'f' * 64 for n in range(17682)},
        'layers': ['synthetic-layer-' + str(n) for n in range(77)]}
    receipt_ref = doc(s.home / 'hermes-agent.source.json', receipt)
    stamp = doc(s.home / 'hermes-agent/install-stamp.json', {
        'schemaVersion': 2, 'distribution': 'friday-rework', 'payload': 'bootstrap',
        'fridaySource': {'baseTree': receipt['base_tree'], 'layers': receipt['layers']}})
    current = copy.deepcopy(s.value)
    for name in ('scripts/friday_install.py', 'scripts/friday_worker_preparation.py'):
        current['project_files'][name] = '0' * 64
    old_ref = doc(s.deploy / 'installed-input.json', current)
    new_ref = doc(s.deploy / 'recovery-input.json', s.value)
    marker = f.read_json(s.home / f.MARKER)
    marker['input_sha256'] = old_ref['sha256']
    marker['source_receipt_sha256'] = receipt_ref['sha256']
    marker['profile_files']['config.yaml'] = pin(s.home / 'config.yaml')['sha256']
    root_marker = doc(s.home / f.MARKER, marker)
    old_claim = f.read_json(Path(s.failure['path']))['original_attempt']
    s.closed = doc(s.deploy / 'closed-failure.json', {
        'state': 'CLOSED_FAILED_FIRST_ORIGINAL300_BEFORE_NATIVE_SCOPE_NO_RETRY',
        'failure': s.failure, 'server_original_attempt': old_claim, 'no_retry': True,
        'original_attempt_marker_retained': True, 'native_DSH_scope_created': False,
        'native_model_or_web_probe_started': False,
        'A0_bootstrap_or_keys_or_native_route_started': False,
        'workers': 'OFF', 'worker_runtime_acceptance': False})
    history = list(s.request['history'])
    history.extend(doc(s.home / 'preparation/history' / (str(n) + '.json'),
        {'fixture': n, 'accounting': 'CLOSED_NO_RETRY'}) for n in range(428 - len(history)))
    request = dict(schema=recovery.KEYLESS_RECOVERY_SCHEMA, recovery_id='source-only-recovery-1',
        seconds=180, home=str(s.home), profile=s.binding['runtime_profile'], binding=s.binding,
        generation=1, transition='NEW_PRODUCT_MAINTENANCE_NO_RUNTIME_AUTHORITY',
        installed_input=old_ref, recovery_input=new_ref, root_marker=root_marker,
        source_receipt=receipt_ref, stamp=stamp, root_configuration=pin(s.home / 'config.yaml'),
        root_profile=pin(s.home / 'FRIDAY-PROFILE.json'), native_unit=s.request['native_unit'],
        onboarding=pin(s.user / scope.ONBOARDING), user_marker=pin(s.user / scope.MARKER),
        configuration=pin(s.user / 'config.yaml'),
        access_state=pin(s.home / 'plugin-data' / _plugin_data_namespace('friday_rework', '') / 'state.json'),
        attachment=pin(s.user / 'workers/attachment.json'),
        preparations={kind: pin(s.user / 'workers' / kind / 'runtime-input.json') for kind in ('dsh', 'a0')},
        reports=s.request['reports'], history=history, failure=s.failure, closed_failure=s.closed,
        qualification_files={str(path.relative_to(s.old_tree)): pin(path)['sha256']
            for path in s.old_tree.rglob('*') if path.is_file()})
    s.recovery_request = request; s.recovery_path = s.deploy / 'recovery-request.json'
    doc(s.recovery_path, request)
    s.before = snapshot(s.home)
    s.tx = s.home / 'preparation' / ('ordinary-keyless-recovery-' + request['recovery_id'])
    return s


def test_explicit_new_maintenance_repairs_only_asset_template_attachment_and_preparations(receiver):
    s = receiver; old = s.before
    out = execute(s)
    assert out['state'] == 'REPAIRED_CONSUMERS_STOPPED_WORKERS_OFF_NEW_RUNTIME_NOT_AUTHORIZED'
    assert out['runtime_acceptance'] == out['new_runtime_authority'] == 'NOT_GRANTED'
    assert out['ready'] is out['consumers_started'] is out['workers_enabled'] is False
    assert out['old_attempt_retry_authorized'] is False and out['resume_allowed'] is False
    target = s.home / 'harness/friday-web-keyless.mjs'
    assert target.read_bytes() == (f.ROOT / 'plugins/friday_rework/adapters/dsh_keyless_web.mjs').read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o400
    mapping = out['archive_mapping']
    assert mapping == {str(s.old_tree): str(s.tx / 'failed-qualification')}
    assert not s.old_tree.exists()
    archive = s.tx / 'failed-qualification'
    assert snapshot(archive) == {name.removeprefix(str(s.old_tree.relative_to(s.home)) + '/'): value
        for name, value in old.items() if name.startswith(str(s.old_tree.relative_to(s.home)) + '/')}
    expected = {'config.yaml', f.MARKER,
        str((s.user / 'workers/attachment.json').relative_to(s.home)),
        *(str((s.user / 'workers' / k / 'runtime-input.json').relative_to(s.home)) for k in ('dsh', 'a0'))}
    after = snapshot(s.home)
    assert {name for name in old if name in after and old[name] != after[name]} == expected
    assert all(after[name] == value for name, value in old.items()
        if name not in expected and not name.startswith(str(s.old_tree.relative_to(s.home)) + '/'))
    attachment = f.read_json(s.user / 'workers/attachment.json')
    from plugins.friday_rework.worker_provision import preparation
    for kind in ('dsh', 'a0'):
        meta, runtime = preparation(s.user, s.binding['runtime_profile'], kind,
            pin(s.user / 'workers' / kind / 'runtime-input.json'))
        assert runtime == attachment['runtimes'][kind]
        assert meta['attachment'] == pin(s.user / 'workers/attachment.json')
        before = json.loads(old[str((s.user / 'workers' / kind / 'runtime-input.json').relative_to(s.home))][0])
        compare = copy.deepcopy(meta); compare['attachment'] = before['attachment']
        if kind == 'dsh':
            assert compare['runtime']['dsh']['native_files'].pop() == pin(target)
        assert compare == before
    assert not s.calls


def rewrite(s):
    doc(s.recovery_path, s.recovery_request)


@pytest.mark.parametrize('fault', ['clock300', 'transition', 'generation', 'extra',
    'settings', 'policy', 'source', 'native-count', 'layers', 'plugin-count', 'history-count'])
def test_explicit_shape_and_native_source_contract_refuse_before_writes(receiver, fault):
    s = receiver; r = s.recovery_request
    if fault == 'clock300': r['seconds'] = 300
    elif fault == 'transition': r['transition'] = 'RETRY_OLD_300'
    elif fault == 'generation': r['generation'] = 2
    elif fault == 'extra': r['retry_authorized'] = True
    elif fault in ('settings', 'policy', 'source'):
        value = f.read_json(Path(r['recovery_input']['path']))
        if fault == 'settings': value['product']['inference']['model'] = 'changed-model'
        elif fault == 'policy': value['worker_install']['a0']['policy']['sha256'] = 'a' * 64
        else: value['project_files']['scripts/a0_runtime.py'] = 'a' * 64
        r['recovery_input'] = doc(Path(r['recovery_input']['path']), value)
    elif fault in ('native-count', 'layers'):
        receipt = f.read_json(Path(r['source_receipt']['path']))
        if fault == 'native-count': receipt['files'].pop('0')
        else: receipt['layers'].pop()
        r['source_receipt'] = doc(Path(r['source_receipt']['path']), receipt)
    elif fault == 'plugin-count':
        marker = f.read_json(Path(r['root_marker']['path'])); marker['plugin_files'].pop(next(iter(marker['plugin_files'])))
        r['root_marker'] = doc(Path(r['root_marker']['path']), marker)
    else: r['history'].pop()
    rewrite(s); before = snapshot(s.home)
    with pytest.raises((ValueError, AssertionError)): execute(s)
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls


@pytest.mark.parametrize('field', ['root_configuration', 'configuration', 'root_marker',
    'onboarding', 'user_marker', 'access_state', 'attachment', 'preparation', 'history', 'request'])
def test_stale_pins_and_request_cas_refuse_before_writes(receiver, field):
    s = receiver; r = s.recovery_request
    ref = (r['preparations']['dsh'] if field == 'preparation' else r['history'][0]
        if field == 'history' else {'path': str(s.recovery_path)} if field == 'request' else r[field])
    path = Path(ref['path'])
    if field == 'request':
        changed = copy.deepcopy(r); changed['seconds'] = 30; doc(path, changed)
    else:
        path.write_bytes(path.read_bytes() + b' ')
    before = snapshot(s.home)
    with pytest.raises(ValueError): execute(s)
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls


@pytest.mark.parametrize('fault', ['extra-safety-file', 'safety-symlink', 'safety-writable',
    'qualification-original', 'qualification-observation', 'jobs', 'staging', 'cache',
    'a0-bootstrap', 'a0-plan', 'a0-receipt', 'dsh-receipt', 'closed-scope', 'retry', 'clock'])
def test_only_proven_closed_failure_before_native_can_be_archived(receiver, fault):
    s = receiver; r = s.recovery_request
    if fault in ('extra-safety-file', 'qualification-original', 'qualification-observation'):
        name = {'extra-safety-file': 'dsh-safety/inputs/foreign',
            'qualification-original': 'original.json', 'qualification-observation': 'observation.json'}[fault]
        doc(s.old_tree / name, {'must': 'survive'})
    elif fault == 'safety-symlink':
        path = s.old_tree / 'dsh-safety/inputs/bootstrap.py'
        original = path.with_name('outside-evidence'); original.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(original)
    elif fault == 'safety-writable': (s.old_tree / 'dsh-safety/inputs/bootstrap.py').chmod(0o600)
    elif fault in ('jobs', 'staging', 'cache'): doc(s.user / 'workers/dsh' / fault / 'owned-output', {'must': 'survive'})
    elif fault == 'a0-bootstrap': (s.user / 'workers/a0/bootstrap').mkdir(mode=0o700)
    elif fault in ('a0-plan', 'a0-receipt', 'dsh-receipt'):
        name = {'a0-plan': 'a0/probe-plan.json', 'a0-receipt': 'a0/runtime-receipt.json',
                'dsh-receipt': 'dsh/runtime-receipt.json'}[fault]
        doc(s.user / 'workers' / name, {'must': 'survive'})
    elif fault == 'closed-scope':
        closed = f.read_json(Path(r['closed_failure']['path'])); closed['native_DSH_scope_created'] = True
        r['closed_failure'] = doc(Path(r['closed_failure']['path']), closed)
    else:
        failure = f.read_json(Path(r['failure']['path']))
        if fault == 'retry': failure['retry_authorized'] = True
        else: failure['original_attempt']['deadline_mono'] += 1
        r['failure'] = doc(Path(r['failure']['path']), failure)
        r['qualification_files']['failure.json'] = r['failure']['sha256']
    rewrite(s); before = snapshot(s.home)
    with pytest.raises((ValueError, OSError)): execute(s)
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls


@pytest.mark.parametrize('fault', ['existing-asset', 'symlink-asset', 'active-consumer',
    'root-config-lock', 'user-config-lock', 'home-lock', 'root-held-lock',
    'user-held-lock', 'build-held-lock', 'foreign-inode'])
def test_maintenance_custody_gates_all_publication_and_helper(receiver, monkeypatch, fault):
    import fcntl
    s = receiver; target = s.home / 'harness/friday-web-keyless.mjs'; descriptor = None
    if fault == 'existing-asset': target.write_bytes(b'foreign asset'); target.chmod(0o400)
    elif fault == 'symlink-asset': target.symlink_to(s.deploy / 'outside-unowned')
    elif fault == 'active-consumer': s.hosts_live = True
    elif fault in ('root-config-lock', 'user-config-lock'):
        path = (s.home if fault == 'root-config-lock' else s.user) / 'config.yaml.lock'
        path.write_bytes(b'foreign lock evidence')
    elif fault == 'home-lock':
        descriptor = os.open(s.home, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault in ('root-held-lock', 'user-held-lock', 'build-held-lock'):
        path = (s.home if fault == 'root-held-lock' else s.user) / 'config.yaml.lock'
        if fault == 'build-held-lock':
            path = s.home / 'hermes-agent/.web_ui_build.lock'
            path.write_bytes(b''); path.chmod(0o600)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        real_stopped = ordinary.stopped_consumers
        @contextlib.contextmanager
        def replace_inode(*args, **kwargs):
            with real_stopped(*args, **kwargs) as prove:
                path = s.home / 'config.yaml'
                temporary = path.with_name('foreign-same-bytes')
                temporary.write_bytes(path.read_bytes()); temporary.chmod(0o600)
                os.replace(temporary, path)
                yield prove
        monkeypatch.setattr(ordinary, 'stopped_consumers', replace_inode)
    before = snapshot(s.home)
    try:
        with pytest.raises((ValueError, OSError)): execute(s)
    finally:
        if descriptor is not None: os.close(descriptor)
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls


def test_all_maintenance_writes_are_inside_native_and_both_config_locks(receiver, monkeypatch):
    s = receiver; held = set(); seen = []
    stopped = ordinary.stopped_consumers
    locked = ordinary.retained_first_contact_config_lock
    @contextlib.contextmanager
    def custody(*args, **kwargs):
        with stopped(*args, **kwargs) as prove:
            held.add('native')
            try: yield prove
            finally: held.remove('native')
    @contextlib.contextmanager
    def configuration(path):
        with locked(path):
            held.add(str(path))
            try: yield
            finally: held.remove(str(path))
    required = {'native', str(s.home / 'config.yaml'), str(s.user / 'config.yaml')}
    for name in ('write', 'publish_update_file'):
        real = getattr(ordinary, name)
        def guarded(path, *args, _real=real, **kwargs):
            assert held == required
            seen.append(str(path)); return _real(path, *args, **kwargs)
        monkeypatch.setattr(ordinary, name, guarded)
    real_rename = os.rename
    def archive(source, destination, *args, **kwargs):
        if Path(source) == s.old_tree: assert held == required
        return real_rename(source, destination, *args, **kwargs)
    monkeypatch.setattr(os, 'rename', archive)
    monkeypatch.setattr(ordinary, 'stopped_consumers', custody)
    monkeypatch.setattr(ordinary, 'retained_first_contact_config_lock', configuration)
    execute(s)
    assert str(s.home / 'harness/friday-web-keyless.mjs') in seen
    assert str(s.tx / 'intent.json') in seen and str(s.tx / 'committed.json') in seen
    assert not held and not s.calls


@pytest.mark.parametrize('publication', [1, 2, 3, 4, 5, 6])
def test_each_partial_publication_restores_owned_bytes_and_old_failure_once(receiver, monkeypatch, publication):
    s = receiver; real_publish = ordinary.publish_update_file; calls = []
    def fail_after(*args, **kwargs):
        real_publish(*args, **kwargs); calls.append(args[0])
        if len(calls) == publication: raise OSError('synthetic publication acknowledgement loss')
    monkeypatch.setattr(ordinary, 'publish_update_file', fail_after)
    with pytest.raises(OSError, match='acknowledgement'): execute(s)
    after = snapshot(s.home)
    assert all(after[name] == value for name, value in s.before.items())
    assert not (s.home / 'harness/friday-web-keyless.mjs').exists()
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert not (s.tx / 'committed.json').exists()
    with pytest.raises(ValueError, match='consumed_no_retry'): execute(s)
    s.recovery_request['recovery_id'] = 'cannot-reset-failure-with-new-id'; rewrite(s)
    with pytest.raises(ValueError, match='failure_already_consumed'): execute(s)
    assert not s.calls


def test_foreign_inode_during_partial_publication_is_preserved_stop_unconfirmed(receiver, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = receiver; real_publish = ordinary.publish_update_file
    target = s.home / 'harness/friday-web-keyless.mjs'; foreign = []
    def lose_ownership(path, *args, **kwargs):
        real_publish(path, *args, **kwargs)
        if path == s.home / 'config.yaml':
            tmp = target.with_name('foreign-same-bytes')
            tmp.write_bytes(target.read_bytes()); tmp.chmod(0o400); os.replace(tmp, target)
            foreign.append(ordinary.update_file_state(target))
            raise OSError('synthetic foreign inode after partial publication')
    monkeypatch.setattr(ordinary, 'publish_update_file', lose_ownership)
    with pytest.raises(StopUnconfirmed, match='ownership/rollback'): execute(s)
    assert ordinary.update_file_state(target) == foreign[0]
    assert not s.old_tree.exists() and (s.tx / 'failed-qualification/failure.json').is_file()
    assert (s.tx / 'intent.json').is_file() and not (s.tx / 'committed.json').exists()
    assert not (s.tx / 'failure.json').exists()
    assert (s.tx / 'before/config.yaml').read_bytes() == s.before['config.yaml'][0]
    with pytest.raises(ValueError): execute(s)
    assert ordinary.update_file_state(target) == foreign[0] and not s.calls


@pytest.mark.parametrize('fault', ['archive-fsync', 'commit-write'])
def test_archive_or_final_commit_failure_retains_consumed_evidence_and_restores_canonical_files(receiver, monkeypatch, fault):
    s = receiver
    if fault == 'archive-fsync':
        real = ordinary.sync_directory; failed = []
        def fail(path):
            if Path(path) == s.old_tree.parent and not s.old_tree.exists() and not failed:
                failed.append(True); raise OSError('synthetic archive fsync failure')
            return real(path)
        monkeypatch.setattr(ordinary, 'sync_directory', fail)
    else:
        real = ordinary.write
        def fail(path, *args, **kwargs):
            if Path(path) == s.tx / 'committed.json': raise OSError('synthetic final commit failure')
            return real(path, *args, **kwargs)
        monkeypatch.setattr(ordinary, 'write', fail)
    with pytest.raises(OSError, match='synthetic'): execute(s)
    after = snapshot(s.home)
    assert all(after[name] == value for name, value in s.before.items())
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert (s.tx / 'failed-before/failure.json').read_bytes() == Path(s.failure['path']).read_bytes()
    assert not (s.home / 'harness/friday-web-keyless.mjs').exists()
    with pytest.raises(ValueError, match='consumed_no_retry'): execute(s)
    assert not s.calls


def test_foreign_archived_inode_stops_tree_restoration_and_preserves_both_evidence_sets(receiver, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = receiver; real = ordinary.publish_update_file; foreign = []
    archived = s.tx / 'failed-qualification/dsh-safety/inputs/bootstrap.py'
    def fail(path, *args, **kwargs):
        real(path, *args, **kwargs)
        if Path(path) == s.home / 'harness/friday-web-keyless.mjs':
            temporary = archived.with_name('foreign-staged')
            temporary.write_bytes(archived.read_bytes()); temporary.chmod(0o400)
            os.replace(temporary, archived); foreign.append(ordinary.update_file_state(archived))
            raise OSError('synthetic archived evidence inode replaced')
    monkeypatch.setattr(ordinary, 'publish_update_file', fail)
    with pytest.raises(StopUnconfirmed, match='ownership/rollback'): execute(s)
    assert not s.old_tree.exists() and ordinary.update_file_state(archived) == foreign[0]
    assert (s.tx / 'failed-before/dsh-safety/inputs/bootstrap.py').read_bytes() == archived.read_bytes()
    assert (s.tx / 'intent.json').is_file() and (s.tx / 'before-mapping.json').is_file()
    assert not (s.tx / 'committed.json').exists() and not (s.tx / 'failure.json').exists()
    with pytest.raises((ValueError, OSError)): execute(s)
    assert ordinary.update_file_state(archived) == foreign[0] and not s.calls


def test_useful_clock_exhaustion_retains_original_cleanup_deadline_and_restores_owned_files(receiver, monkeypatch):
    s = receiver; original = Budget(180); expired = []; cleanup_proofs = []
    check = Budget.check; publish = ordinary.publish_update_file; stopped = ordinary.stopped_consumers
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
    with pytest.raises(ValueError, match='synthetic_original_useful'): recovery.recover_keyless(s.recovery_request, s.recovery_path, original)
    after = snapshot(s.home)
    assert all(after[name] == value for name, value in s.before.items())
    assert cleanup_proofs and not (s.home / 'harness/friday-web-keyless.mjs').exists()
    clock = f.read_json(s.tx / 'intent.json')['maintenance_clock']
    assert clock['deadline_mono'] == original.deadline and clock['cleanup_seconds'] == 10
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert not s.calls


def test_unconfirmed_native_custody_release_retains_committed_repair_without_reporting_success(receiver, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = receiver; stopped = ordinary.stopped_consumers
    @contextlib.contextmanager
    def release_failure(*args, **kwargs):
        with stopped(*args, **kwargs) as prove: yield prove
        raise f.Refused('ordinary_update_native_lock_release_unconfirmed')
    monkeypatch.setattr(ordinary, 'stopped_consumers', release_failure)
    with pytest.raises(StopUnconfirmed, match='native custody release'): execute(s)
    # Publication happened before the failed native lock release. Preserve its
    # transaction and originals; a cleanup error cannot pretend it rolled back.
    committed = f.read_json(s.tx / 'committed.json')
    assert committed['runtime_acceptance'] == committed['new_runtime_authority'] == 'NOT_GRANTED'
    assert committed['consumers_started'] is committed['workers_enabled'] is False
    assert (s.tx / 'failed-qualification/failure.json').is_file() and not s.old_tree.exists()
    target = s.home / 'harness/friday-web-keyless.mjs'
    retained = ordinary.update_file_state(target)
    assert retained is not None and retained['mode'] == 0o400
    assert (s.tx / 'before/config.yaml').read_bytes() == s.before['config.yaml'][0]
    with pytest.raises((ValueError, OSError)): execute(s)
    assert ordinary.update_file_state(target) == retained and not s.calls


def test_real_parser_dispatches_explicit_maintenance_with_one_budget(receiver, monkeypatch, capsys):
    s = receiver; seen = []
    def dispatch(request, path, budget):
        seen.append((copy.deepcopy(request), path, budget))
        return {'state': 'SOURCE_DISPATCH_ONLY_NO_RUNTIME'}
    monkeypatch.setattr(recovery, 'recover_keyless', dispatch)
    monkeypatch.setattr(sys, 'argv', ['friday_install.py', 'recover-ordinary-worker-keyless', '--input', str(s.recovery_path)])
    f.main()
    assert json.loads(capsys.readouterr().out)['state'] == 'SOURCE_DISPATCH_ONLY_NO_RUNTIME'
    assert len(seen) == 1 and seen[0][0] == s.recovery_request
    assert seen[0][1] == s.recovery_path and isinstance(seen[0][2], Budget)
    assert snapshot(s.home) == s.before and not s.calls


def test_fixture_is_old_helperless_user_with_no_runtime_authority(legacy):
    s = legacy
    assert not (s.home / 'harness/friday-web-keyless.mjs').exists()
    assert recovery.configuration_settings(raw(s.env))['runtime'] == {'enabled': False}
    assert row(s.env)['enabled'] is True and row(s.env)['generation'] == 1
    assert not s.calls
    for kind in ('dsh', 'a0'):
        meta = f.read_json(s.user / 'workers' / kind / 'runtime-input.json')
        assert meta['state'] == 'PREPARED_RUNTIME_UNOBSERVED'
        assert not (s.user / 'workers' / kind / 'runtime-receipt.json').exists()
        assert all(not list((s.user / 'workers' / kind / name).iterdir()) for name in ('jobs', 'staging', 'cache'))
