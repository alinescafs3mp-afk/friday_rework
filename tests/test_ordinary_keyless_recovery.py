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
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import friday_install as f, friday_worker_preparation as recovery
from scripts import friday_ordinary_install as ordinary, worker_install as workers
from scripts.install_containment import Budget
from test_ordinary_worker_preparation import installed, normal as base_normal, service, install_input, doc, pin, configured_web_profile
from test_user_onboarding import env, complete, home as user_home, cas, ident, row, raw
from scripts.a0_runtime import check_git_metadata as REAL_METADATA_CHECK
REAL_COMPOSITION_CHECK = f.composition_checked


def source79_inventory():
    """Public Source79 names and hashes; native receipt bytes stay synthetic."""
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
    assert len(names) == 231
    files = {name: f.digest(f.owned_file(f.ROOT / name)) for name in sorted(names)}
    layers = []
    for name in sorted(n for n in names if n.startswith('patches/hermes/') and n.endswith('.json')):
        body = json.loads(f.owned_file(f.ROOT / name))
        patch = body.get('patch') or 'patches/hermes/' + body['patch_file']
        assert files[patch] == body['patch_sha256']
        layers.append(dict(manifest=name, manifest_sha256=files[name], patch_sha256=files[patch]))
    assert len(layers) == 79
    lock_sha = files['sources.lock.json']
    value = dict(project_files=files, sources_lock=dict(sha256=lock_sha))
    receipt = dict(sources_lock_sha256=lock_sha, layers=layers,
        files={str(n): 'a' * 64 for n in range(17686)})
    return value, receipt


@pytest.fixture
def normal(service, monkeypatch):
    """Existing worker fixture plus authentic disposable A0 Git metadata.

    Native installed compositions and systemd remain synthetic. Metadata objects,
    detached/shallow identity, manifest hash and real pure checker execute here.
    """
    s = base_normal.__wrapped__(service, monkeypatch)
    from scripts import a0_runtime
    source = Path(s.value['worker_install']['a0']['git_metadata']['source'])
    repo = source.parent
    repo.mkdir(mode=0o700, parents=True)
    git_env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0'}
    def git(*args):
        return subprocess.run(['git', '--no-optional-locks', '-C', str(repo), *args],
            check=True, capture_output=True, text=True, timeout=5, env=git_env).stdout.strip()
    git('init', '--template=')
    (repo / 'fixture.txt').write_text('offline metadata identity, never mounted\n')
    git('add', 'fixture.txt')
    git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture')
    commit = git('rev-parse', 'HEAD'); tree = git('rev-parse', 'HEAD^{tree}')
    git('checkout', '--detach', commit)
    for name in git('for-each-ref', '--format=%(refname)').splitlines(): git('update-ref', '-d', name)
    (source / 'shallow').write_text(commit + '\n')
    for name, value in (('DONOR', commit), ('DONOR_TREE', tree), ('DONOR_DESCRIBE', commit[:7])):
        monkeypatch.setattr(a0_runtime, name, value)
    manifest = source.parent.parent / 'metadata.json'
    doc(manifest, a0_runtime.git_metadata_snapshot(source))
    s.value['worker_install']['a0']['git_metadata']['manifest_sha256'] = pin(manifest)['sha256']
    monkeypatch.setattr(a0_runtime, 'check_git_metadata', REAL_METADATA_CHECK)
    s.metadata_source = source; s.metadata_manifest = manifest
    return s


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


@pytest.fixture
def closed_receiver(receiver, monkeypatch):
    s = receiver
    # Produce the prior consumed repair using its unchanged production branch.
    execute(s)
    previous = s.tx
    old_manifest, _ = recovery._closed_tree_state(previous / 'failed-qualification', recovery.KEYLESS_FAILED_FILES, control=False)
    from hermes_cli import friday_user_scope as scope
    old_request = copy.deepcopy(s.recovery_request)
    request = copy.deepcopy(old_request)
    request.pop('qualification_files')
    request.update(schema=recovery.CLOSED_RECOVERY_SCHEMA, recovery_id='closed-source-only',
        transition='EXPLICIT_CLOSED_ARCHIVE_NO_RUNTIME_AUTHORITY')
    # The current retained failure has the demonstrated23-file footprint, and
    # remains old diagnostic format: recovery must not invent its missing cause.
    failure = {'state': 'REFUSED_OR_UNCERTAIN', 'original_attempt': {'boot_id': 'closed-original-boot',
        'started_mono': 2000.0, 'deadline_mono': 2300.0, 'budget_seconds': 300},
        'retry_authorized': False, 'a0_probe_cleanup': 'OWN_INITIAL_PROBE_CUSTODY'}
    for name in recovery.CLOSED_FAILED_FILES:
        path = s.old_tree / name
        if name == 'failure.json': doc(path, failure)
        else:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(('SYNTHETIC RETAINED ' + name).encode())
            path.chmod(0o664 if name.startswith('dsh-safety/workspace/') else 0o400)
    (s.old_tree / 'dsh-safety/home').mkdir(mode=0o700)
    request['failure'] = pin(s.old_tree / 'failure.json')
    manifest, _ = recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)
    request['qualification_tree'] = doc(s.deploy / 'tree.json', manifest)
    request['original_clock'] = doc(s.deploy / 'original-clock.json', dict(operation_id='closed-second', boot_id='closed-original-boot',
        physical_seconds=660, server_seconds=300, started_monotonic=1999.0, deadline_monotonic=2659.0,
        old_original300_reset=False, retry_authorized=False))
    unit = 'friday-qualify-dsh-' + f.digest(str(s.old_tree / 'dsh-safety').encode())[:24] + '-1.scope'
    units = {unit: {'returncode': 0, 'properties': dict(LoadState='not-found', ActiveState='inactive', SubState='dead', ControlGroup='', InvocationID='')},
        'friday-rework-docker.service': {'returncode': 0, 'properties': dict(LoadState='loaded', ActiveState='inactive', SubState='dead',
            ControlGroup='', InvocationID='', MainPID='0', ControlPID='0')}}
    cessation = dict(state='ROOT_NEW_NORMAL_SETUP_FAILED_NATIVE_SCOPE_COLLECTED_A0_UNSTARTED_DATA_PRESERVED',
        server_claim=failure['original_attempt'], server_failure=request['failure'], runtime_acceptance=False, workers='OFF',
        this_new_attempt_retry_authorized=False, A0='NO_BOOTSTRAP_ROUTE_OR_CONTAINER_STARTED', runtime_receipts='ABSENT',
        inside_original660=True, operation_id='closed-second', actual_units=units,
        absences={str(s.user / 'workers' / n): True for n in ('a0/bootstrap', 'a0/probe-plan.json', 'a0/runtime-receipt.json', 'dsh/runtime-receipt.json')})
    cessation['absences'].update({str(s.home.parent / 'rootless-docker/config/local-route.json'): True,
        str(Path('/run/user') / str(os.getuid()) / 'friday-rework-docker/rootlesskit/child_pid'): True,
        str(Path('/run/user') / str(os.getuid()) / 'friday-rework-docker/route-guard.json'): True})
    request['native_cessation'] = doc(s.deploy / 'cessation.json', cessation)
    request['closed_failure'] = doc(s.deploy / 'closed-second.json', dict(
        state='CONSUMED_CLOSED_FAILED_NEW_NORMAL_SETUP_AFTER_REPAIR_NO_RETRY', original_server300=failure['original_attempt'],
        no_retry=True, runtime_workers='OFF', runtime_acceptance=False, old_original300_closed_failure_preserved=True,
        old_physical660_not_reset=True, original_physical660_closed_within_budget=True,
        native_data_reconciliation=request['native_cessation'], clock=request['original_clock'], operation_id='closed-second'))
    history = list(request['history']) + [pin(previous / 'intent.json'), pin(previous / 'committed.json')]
    history += [doc(s.home / 'preparation/new-history' / (str(n) + '.json'), {'retained': n}) for n in range(465 - len(history))]
    # Preserve the original465 synthetic custody refs, then append29 generic members.
    s.pre79_history = copy.deepcopy(history)
    names = ['preparation/synthetic-source79-history/' + str(n) + '.json' for n in range(29)]
    assert len(history) == 465 and len(names) == 29
    history += [doc(s.home / n, {'synthetic_source79_history': n}) for n in names]
    request['history'] = history
    request['keyless_ancestry'] = dict(intent=pin(previous / 'intent.json'), committed=pin(previous / 'committed.json'),
        tree=doc(s.deploy / 'old-tree.json', old_manifest))
    receipt = f.read_json(Path(request['source_receipt']['path']))
    receipt['files'].update({str(n): 'a'*64 for n in range(17682, 17686)})
    # Exact production layer shape; native file bytes remain synthetic here.
    source_value, source_receipt = source79_inventory()
    receipt['layers'] = source_receipt['layers']
    request['source_receipt'] = doc(Path(request['source_receipt']['path']), receipt)
    request['stamp'] = doc(Path(request['stamp']['path']), dict(schemaVersion=2, distribution='friday-rework', payload='bootstrap',
        fridaySource=dict(baseTree=receipt['base_tree'], layers=receipt['layers'])))
    request['maintenance_source'] = pin(Path(recovery.__file__))
    current = copy.deepcopy(s.value)
    # Public Source79 names and current source bytes; no deployment input is loaded.
    future_paths = source_value['project_files']
    current['project_files'] = {n: sha for n, sha in current['project_files'].items() if n in future_paths}
    current['project_files']['sources.lock.json'] = f.digest(f.owned_file(f.ROOT / 'sources.lock.json'))
    assert set(current['project_files']) == set(future_paths) and len(future_paths) == 231
    # Historical helper/checker identity is synthetic and distinct from the
    # checked-out successor, so the real exact-two-source-delta guard executes
    # identically before and after these tests are publicly integrated.
    for name in ('scripts/friday_worker_preparation.py', 'scripts/dsh_prepare.py'):
        current['project_files'][name] = f.digest(('SYNTHETIC PRE-MAINTENANCE ' + name).encode())
    request['installed_input'] = doc(s.deploy / 'second-installed.json', current)
    successor = copy.deepcopy(current)
    successor['project_files']['scripts/friday_worker_preparation.py'] = request['maintenance_source']['sha256']
    successor['project_files']['scripts/dsh_prepare.py'] = pin(Path(recovery.__file__).with_name('dsh_prepare.py'))['sha256']
    request['recovery_input'] = doc(s.deploy / 'second-recovery.json', successor)
    marker = f.read_json(s.home / f.MARKER)
    marker['input_sha256'] = request['installed_input']['sha256']; marker['source_receipt_sha256'] = request['source_receipt']['sha256']
    request['root_marker'] = doc(s.home / f.MARKER, marker)
    request['root_configuration'] = pin(s.home / 'config.yaml'); request['attachment'] = pin(s.user / 'workers/attachment.json')
    request['preparations'] = {k: pin(s.user / 'workers' / k / 'runtime-input.json') for k in ('dsh', 'a0')}
    request['diagnostic_correction'] = pin(s.home / 'plugins/friday_rework/user_worker_join.py')
    request['source_acceptance'] = doc(s.deploy / 'source-acceptance.json', dict(state='ROOT_ACCEPTED_SOURCE_FAILURE_RECEIPT_ONLY_NOT_INSTALLED',
        source_sha256=request['diagnostic_correction']['sha256'], native_failure_cause='UNKNOWN'))
    s.native_calls = []; s.native_live = False
    from scripts import dsh_prepare
    previous_run = dsh_prepare.run
    def native(command, *args, **kw):
        if command[:3] != ['/usr/bin/systemctl', '--user', 'show']:
            assert command[0] == 'git', 'unexpected fixture command'
            return previous_run(command, *args, **kw)
        s.native_calls.append(command)
        properties = units[command[3]]['properties']
        if s.native_live: properties = {**properties, 'ActiveState': 'active'}
        return ('\n'.join(k + '=' + v for k, v in properties.items()), {})
    monkeypatch.setattr(dsh_prepare, 'run', native)
    s.recovery_request = request; s.recovery_path = s.deploy / 'closed-request.json'
    s.tx = s.home / 'preparation/ordinary-closed-reconciliation-closed-source-only'
    admit(s)
    s.before = snapshot(s.home)
    return s


def admit(s):
    r = s.recovery_request
    authority = {k: v for k, v in r.items() if k != 'admission'}
    r['admission'] = doc(s.deploy / 'archive-admission.json', dict(schema=recovery.CLOSED_RECOVERY_SCHEMA,
        state='ADMITTED_ARCHIVE_ONLY', request_binding_sha256=f.digest(ordinary.encoded(authority)),
        runtime_authority='NOT_GRANTED', old_attempt_retry_authorized=False))
    rewrite(s)


def reconcile(s):
    return recovery.reconcile_closed(s.recovery_request, s.recovery_path, Budget(180))


def test_closed_archive_preserves_all23_files_inodes_modes_both_attempts_and_off_state(closed_receiver):
    s = closed_receiver
    manifest, _ = recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)
    result = reconcile(s)
    assert result['runtime_authority'] == 'NOT_GRANTED' and result['resume_allowed'] is False
    assert not result['runtime_acceptance'] and not result['workers_enabled'] and not result['consumers_started']
    assert recovery._closed_tree_state(s.tx / 'failed-qualification', recovery.CLOSED_FAILED_FILES, control=True)[0] == manifest
    assert not s.old_tree.exists()
    marker = f.read_json(s.home / f.MARKER)
    assert marker['input_sha256'] == s.recovery_request['recovery_input']['sha256']
    after = snapshot(s.home)
    for name, state in s.before.items():
        if name == f.MARKER or name.startswith(str(s.old_tree.relative_to(s.home)) + '/'): continue
        assert after[name] == state
    assert (s.tx / 'failed-before/failure.json').read_bytes() == (s.tx / 'failed-qualification/failure.json').read_bytes()
    assert not s.calls and s.native_calls


@pytest.mark.parametrize('fault', ['missing-admission', 'wrong-admission', 'tree-extra', 'tree-mode', 'tree-inode',
    'clock', 'claim', 'source', 'settings', 'history', 'ancestry', 'diagnostic', 'active', 'unknown-native',
    'a0-bootstrap', 'a0-plan', 'a0-receipt', 'root-lock', 'user-lock', 'occupied', 'peer'])
def test_closed_recovery_refuses_changed_authority_custody_history_and_native_state(closed_receiver, fault):
    s = closed_receiver; r = s.recovery_request
    if fault == 'missing-admission': r.pop('admission'); rewrite(s)
    elif fault == 'wrong-admission':
        doc(Path(r['admission']['path']), {'state': 'NOT_ADMITTED'}); rewrite(s)
    elif fault == 'tree-extra': doc(s.old_tree / 'original.json', {'partial': 'A0 claim'})
    elif fault == 'tree-mode': (s.old_tree / 'dsh-safety/workspace/artifact').chmod(0o600)
    elif fault == 'tree-inode':
        p = s.old_tree / 'dsh-safety/workspace/artifact'; tmp = s.deploy / 'same-bytes'; tmp.write_bytes(p.read_bytes()); tmp.chmod(0o664); os.replace(tmp, p)
    elif fault in ('clock', 'claim', 'ancestry', 'diagnostic', 'history'):
        ref = r['original_clock'] if fault == 'clock' else r['failure'] if fault == 'claim' else r['keyless_ancestry']['intent'] if fault == 'ancestry' else r['diagnostic_correction'] if fault == 'diagnostic' else r['history'][0]
        p = Path(ref['path']); p.write_bytes(p.read_bytes() + b' ')
    elif fault in ('source', 'settings'):
        value = f.read_json(Path(r['recovery_input']['path']))
        if fault == 'source': value['project_files']['scripts/friday_install.py'] = 'a'*64
        else: value['product']['runtime']['enabled'] = True
        r['recovery_input'] = doc(Path(r['recovery_input']['path']), value); admit(s)
    elif fault == 'active': s.native_live = True
    elif fault == 'unknown-native':
        cessation = f.read_json(Path(r['native_cessation']['path'])); cessation['actual_units'] = {}
        r['native_cessation'] = doc(Path(r['native_cessation']['path']), cessation); admit(s)
    elif fault.startswith('a0-'):
        p = s.user / ('workers/a0/' + {'a0-bootstrap': 'bootstrap', 'a0-plan': 'probe-plan.json', 'a0-receipt': 'runtime-receipt.json'}[fault])
        if fault == 'a0-bootstrap': p.mkdir(mode=0o700)
        else: doc(p, {'partial': True})
    elif fault in ('root-lock', 'user-lock'): (s.home if fault == 'root-lock' else s.user).joinpath('config.yaml.lock').write_bytes(b'foreign')
    elif fault == 'occupied': s.tx.mkdir(mode=0o700)
    else: s.hosts_live = True
    before = snapshot(s.home)
    with pytest.raises((ValueError, OSError, KeyError)): reconcile(s)
    assert snapshot(s.home) == before and not s.calls


@pytest.mark.parametrize('fault', ['publish', 'archive-fsync', 'commit'])
def test_closed_partial_failure_restores_original_tree_and_marker_then_deduplicates_failure(closed_receiver, monkeypatch, fault):
    s = closed_receiver
    if fault == 'publish':
        publish = ordinary.publish_update_file
        fired = []
        def fail(*a, **kw):
            publish(*a, **kw)
            if not fired:
                fired.append(True); raise OSError('synthetic lost publication ACK')
        monkeypatch.setattr(ordinary, 'publish_update_file', fail)
    elif fault == 'archive-fsync':
        sync = ordinary.sync_directory; fired = []
        def fail(p):
            if p == s.old_tree.parent and not s.old_tree.exists() and not fired:
                fired.append(True); raise OSError('synthetic archive fsync failure')
            return sync(p)
        monkeypatch.setattr(ordinary, 'sync_directory', fail)
    else:
        write = ordinary.write
        def fail(p, *a, **kw):
            if p == s.tx / 'committed.json': raise OSError('synthetic commit failure')
            return write(p, *a, **kw)
        monkeypatch.setattr(ordinary, 'write', fail)
    with pytest.raises(OSError, match='synthetic'): reconcile(s)
    after = snapshot(s.home)
    assert all(after[n] == row for n, row in s.before.items())
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    with pytest.raises(ValueError): reconcile(s)
    s.recovery_request['recovery_id'] = 'different-id'; admit(s)
    with pytest.raises(ValueError, match='failure_already_consumed'): reconcile(s)
    assert not s.calls


def test_closed_foreign_archive_inode_preserved_with_stop_unconfirmed(closed_receiver, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = closed_receiver; publish = ordinary.publish_update_file
    path = s.tx / 'failed-qualification/dsh-safety/workspace/artifact'; foreign = []
    def fail(*a, **kw):
        publish(*a, **kw)
        if not foreign:
            p = s.deploy / 'foreign-inode'; p.write_bytes(path.read_bytes()); p.chmod(0o664); os.replace(p, path)
            foreign.append(ordinary.update_file_state(path)); raise OSError('synthetic foreign inode')
    monkeypatch.setattr(ordinary, 'publish_update_file', fail)
    with pytest.raises(StopUnconfirmed): reconcile(s)
    assert ordinary.update_file_state(path) == foreign[0] and not s.old_tree.exists()
    assert (s.tx / 'failed-before/dsh-safety/workspace/artifact').read_bytes() == path.read_bytes()
    assert not (s.tx / 'committed.json').exists() and not s.calls


def test_real_parser_dispatches_new_closed_schema_without_changing_old_mode(tmp_path, monkeypatch, capsys):
    request = {'schema': recovery.CLOSED_RECOVERY_SCHEMA, 'seconds': 30}
    path = tmp_path / 'closed.json'; doc(path, request); seen = []
    def admitted(value, request_path, budget):
        seen.append((value, request_path, budget)); return {'state': 'SOURCE_DISPATCH_ONLY'}
    monkeypatch.setattr(recovery, 'reconcile_closed', admitted)
    monkeypatch.setattr(sys, 'argv', ['friday_install.py', 'recover-ordinary-worker-keyless', '--input', str(path)])
    f.main()
    assert json.loads(capsys.readouterr().out) == {'state': 'SOURCE_DISPATCH_ONLY'}
    assert len(seen) == 1 and seen[0][0] == request and seen[0][1] == path and isinstance(seen[0][2], Budget)


def test_review_preimage_mode_under_private_umask(closed_receiver):
    s=closed_receiver
    assert os.umask(0o077)==0o077
    reconcile(s)
    path='dsh-safety/workspace/artifact'
    assert stat.S_IMODE((s.tx/'failed-qualification'/path).stat().st_mode)==0o664
    assert stat.S_IMODE((s.tx/'failed-before'/path).stat().st_mode)==0o600
    assert f.read_json(s.tx/'intent.json')['tree']['files'][path]['mode']==0o664



# Source-correction regression delta: installed composition/custody are synthetic
# fixture seams; all referenced Git objects, pins and filesystem changes are real.
def _change_fixture_source(path):
    path = Path(path)
    assert path.is_relative_to(Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']))
    before = path.read_bytes(); mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(0o600); path.write_bytes(before + b'\nUNREPINNED_PRIVATE_FIXTURE_SOURCE_DRIFT\n'); path.chmod(mode)
    return path, path.read_bytes()


@pytest.mark.parametrize('fault', ['dsh-source', 'dsh-cli', 'dsh-build-extra', 'node-bytes',
    'node-mode', 'node-link', 'dsh-native-helper', 'dsh-resolver', 'dsh-trust_bundle',
    'dsh-egress_evidence', 'dsh-research_policy', 'a0-source', 'a0-runtime', 'a0-launcher',
    'a0-docker', 'a0-daemon_unit', 'a0-policy', 'a0-metadata-manifest', 'a0-metadata-object'])
def test_closed_unrepinned_worker_source_drift_refuses_before_custody_or_archive(closed_receiver, monkeypatch, fault):
    s = closed_receiver
    attachment = f.read_json(s.user / 'workers/attachment.json')
    d = attachment['runtimes']['dsh']['dsh']; a = attachment['runtimes']['a0']['a0']
    changed = None
    if fault == 'dsh-source': changed = _change_fixture_source(s.home / 'harness/LICENSE')
    elif fault == 'dsh-cli': changed = _change_fixture_source(d['cli']['path'])
    elif fault == 'dsh-build-extra':
        p = s.home / 'harness/apps/cli/lib/unexpected.js'; p.write_bytes(b'UNREPINNED BUILD OUTPUT')
        changed = (p, p.read_bytes())
    elif fault == 'node-bytes': changed = _change_fixture_source(d['node']['path'])
    elif fault == 'node-mode': Path(d['node']['path']).chmod(0o720)
    elif fault == 'node-link':
        p = Path(d['node']['path']); p.rename(p.with_name('node-real')); p.symlink_to(p.with_name('node-real'))
    elif fault == 'dsh-native-helper': changed = _change_fixture_source(d['native_files'][-1]['path'])
    elif fault.startswith('dsh-'): changed = _change_fixture_source(d['web'][fault[4:]]['path'])
    elif fault == 'a0-source': changed = _change_fixture_source(Path(s.value['a0_donor']) / 'LICENSE')
    elif fault == 'a0-metadata-manifest': changed = _change_fixture_source(s.metadata_manifest)
    elif fault == 'a0-metadata-object': changed = _change_fixture_source(s.metadata_source / 'HEAD')
    else: changed = _change_fixture_source(a[fault[3:]]['path'])
    before = snapshot(s.home); tree = recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)[0]
    custody = []
    @contextlib.contextmanager
    def stopped(*args, **kwargs):
        custody.append(True)
        pytest.fail('source drift reached native custody')
        yield
    monkeypatch.setattr(ordinary, 'stopped_consumers', stopped)
    # Adapter/source/manifest validators retain their existing exception types.
    with pytest.raises((ValueError, OSError, RuntimeError)): reconcile(s)
    assert snapshot(s.home) == before and not s.tx.exists() and not custody
    assert recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)[0] == tree
    assert not s.calls and not s.native_calls
    if changed is not None: assert changed[0].read_bytes() == changed[1]


@pytest.mark.parametrize('fault', ['original-composition', 'successor-composition', 'native-provenance'])
def test_closed_native_provenance_refusal_precedes_installed_import_admission_and_custody(closed_receiver, monkeypatch, fault):
    import builtins
    s = closed_receiver; before = snapshot(s.home); events = []
    installed_import = builtins.__import__
    def importing(name, *args, **kwargs):
        if name.startswith(('hermes_cli', 'plugins.friday_rework')):
            events.append('installed-import')
        return installed_import(name, *args, **kwargs)
    def composition(value, *args, **kwargs):
        name = ('successor-composition' if value['project_files']['scripts/friday_worker_preparation.py'] ==
            s.recovery_request['maintenance_source']['sha256'] else 'original-composition')
        events.append(name)
        if fault == name: raise f.Refused('correction_control_' + name.replace('-', '_'))
    def packages(source):
        events.append('native-provenance')
        assert source == s.home / 'hermes-agent'
        raise f.Refused('correction_control_native_provenance')
    def admitted(*args, **kwargs):
        events.append('admission'); pytest.fail('unverified admission')
    @contextlib.contextmanager
    def stopped(*args, **kwargs):
        events.append('custody'); pytest.fail('unverified custody'); yield
    monkeypatch.setattr(builtins, '__import__', importing)
    monkeypatch.setattr(f, 'composition_checked', composition)
    monkeypatch.setattr(f, 'native_packages', packages)
    monkeypatch.setattr(recovery, '_keyless_admission', admitted)
    monkeypatch.setattr(ordinary, 'stopped_consumers', stopped)
    with pytest.raises(ValueError, match='correction_control_'): reconcile(s)
    expected = ['original-composition', 'successor-composition', 'native-provenance']
    assert events == expected[:expected.index(fault) + 1]
    assert snapshot(s.home) == before and not s.tx.exists() and not s.calls and not s.native_calls


def test_closed_both_compositions_and_native_provenance_precede_successful_admission_and_custody(closed_receiver, monkeypatch):
    import builtins
    s = closed_receiver; events = []; importing = builtins.__import__
    composition = f.composition_checked; packages = f.native_packages
    admitted = recovery._keyless_admission; stopped = ordinary.stopped_consumers
    def import_checked(name, *args, **kwargs):
        if name.startswith(('hermes_cli', 'plugins.friday_rework')): events.append('installed-import')
        return importing(name, *args, **kwargs)
    def compose(value, *args, **kwargs):
        events.append('successor-composition' if value['project_files']['scripts/friday_worker_preparation.py'] ==
            s.recovery_request['maintenance_source']['sha256'] else 'original-composition')
        return composition(value, *args, **kwargs)
    def provenance(*args, **kwargs): events.append('native-provenance'); return packages(*args, **kwargs)
    def admission(*args, **kwargs): events.append('admission'); return admitted(*args, **kwargs)
    @contextlib.contextmanager
    def custody(*args, **kwargs):
        events.append('custody')
        with stopped(*args, **kwargs) as prove: yield prove
    monkeypatch.setattr(builtins, '__import__', import_checked)
    monkeypatch.setattr(f, 'composition_checked', compose); monkeypatch.setattr(f, 'native_packages', provenance)
    monkeypatch.setattr(recovery, '_keyless_admission', admission); monkeypatch.setattr(ordinary, 'stopped_consumers', custody)
    result = reconcile(s)
    assert result['runtime_authority'] == 'NOT_GRANTED'
    assert events[:4] == ['original-composition', 'successor-composition', 'native-provenance', 'installed-import']
    assert events.index('native-provenance') < events.index('admission') < events.index('custody')
    assert events.count('original-composition') >= 4 and events.count('successor-composition') >= 4
    assert not s.calls


@pytest.mark.parametrize('moment', ['before-archive', 'after-publication'])
def test_closed_late_referenced_source_drift_revalidates_and_rolls_back_without_retry(closed_receiver, monkeypatch, moment):
    s = closed_receiver; tree = recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)[0]
    marker = (s.home / f.MARKER).read_bytes(); fired = []
    attachment = f.read_json(s.user / 'workers/attachment.json')
    path = Path(attachment['runtimes']['dsh']['dsh']['native_files'][-1]['path'])
    def drift():
        if not fired: fired.append(_change_fixture_source(path)[1])
    if moment == 'before-archive':
        sync = ordinary.sync_directory
        def before(p):
            value = sync(p)
            if p == s.tx: drift()
            return value
        monkeypatch.setattr(ordinary, 'sync_directory', before)
    else:
        publish = ordinary.publish_update_file
        def after(*args, **kwargs):
            value = publish(*args, **kwargs); drift(); return value
        monkeypatch.setattr(ordinary, 'publish_update_file', after)
    with pytest.raises((ValueError, RuntimeError)): reconcile(s)
    assert fired and path.read_bytes() == fired[0]
    assert (s.home / f.MARKER).read_bytes() == marker
    assert recovery._closed_tree_state(s.old_tree, recovery.CLOSED_FAILED_FILES, control=True)[0] == tree
    assert f.read_json(s.tx / 'failure.json')['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert not (s.tx / 'committed.json').exists() and not (s.tx / 'failed-qualification').exists()
    with pytest.raises((ValueError, RuntimeError)): reconcile(s)
    assert f.read_json(s.tx / 'intent.json')['state'] == 'CONSUMED_NO_RETRY'
    assert not s.calls


def _sanctioned_fixture_helper(s):
    from scripts import dsh_prepare
    donors = {r['id']: r for r in f.read_json(Path(s.value['sources_lock']['path']))['repositories']}
    identity = dsh_prepare.verify_source(s.home / 'harness', donors['dsh'])
    helper = s.home / 'harness/friday-web-keyless.mjs'
    helper.write_bytes(f.owned_file(f.ROOT / 'plugins/friday_rework/adapters/dsh_keyless_web.mjs'))
    helper.chmod(0o400)
    return dsh_prepare, donors['dsh'], identity, helper


def test_fixed_untracked_shipped_helper_is_explicit_only_and_keeps_base_donor_identity(normal):
    s = normal; checker, donor, identity, helper = _sanctioned_fixture_helper(s)
    with pytest.raises(ValueError, match='Unexpected untracked donor source'):
        checker.verify_source(s.home / 'harness', donor)
    assert checker.verify_source(s.home / 'harness', donor, keyless_helper=pin(helper)) == identity
    # Neither verifier edits Git excludes, source/index, file mode or metadata.
    assert not (s.home / 'harness/.git/info/exclude').exists()
    assert checker.run(['git', '--no-optional-locks', 'status', '--porcelain=v1', '--untracked-files=all'], s.home / 'harness')[0].strip() == '?? friday-web-keyless.mjs'
    assert stat.S_IMODE(helper.stat().st_mode) == 0o400 and not s.calls


@pytest.mark.parametrize('fault', ['wrong-bytes', 'wrong-mode', 'symlink', 'hardlink', 'foreign-extra',
    'wrong-pin', 'repinned-foreign-bytes', 'foreign-pin-path', 'missing-helper', 'tracked-source', 'helper-inode-drift'])
def test_fixed_keyless_extension_refuses_every_foreign_source_and_unsafe_helper(normal, monkeypatch, fault):
    s = normal; checker, donor, identity, helper = _sanctioned_fixture_helper(s)
    reference = pin(helper)
    if fault == 'wrong-bytes': _change_fixture_source(helper)
    elif fault == 'wrong-mode': helper.chmod(0o600)
    elif fault == 'symlink': helper.rename(helper.with_suffix('.real')); helper.symlink_to(helper.with_suffix('.real'))
    elif fault == 'hardlink': helper.with_suffix('.link').hardlink_to(helper)
    elif fault == 'foreign-extra': (s.home / 'harness/foreign.py').write_bytes(b'NEVER EXECUTED')
    elif fault == 'wrong-pin': reference['sha256'] = '0' * 64
    elif fault == 'repinned-foreign-bytes': _change_fixture_source(helper); reference = pin(helper)
    elif fault == 'foreign-pin-path': reference['path'] = str(s.home / 'harness/LICENSE')
    elif fault == 'missing-helper': helper.unlink()
    elif fault == 'tracked-source': _change_fixture_source(s.home / 'harness/LICENSE')
    else:
        run = checker.run; fired = []
        def changed(argv, *args, **kwargs):
            result = run(argv, *args, **kwargs)
            if '--others' in argv and not fired:
                alternate = s.deploy / 'same-helper-new-inode'
                alternate.write_bytes(helper.read_bytes()); alternate.chmod(0o400)
                os.replace(alternate, helper); fired.append(True)
            return result
        monkeypatch.setattr(checker, 'run', changed)
    before = snapshot(s.home)
    with pytest.raises((ValueError, OSError)):
        checker.verify_source(s.home / 'harness', donor, keyless_helper=reference)
    if fault != 'helper-inode-drift': assert snapshot(s.home) == before
    assert not s.calls


def test_closed_prepare_and_shipped_pin_proof_precede_explicit_helper_source_extension(closed_receiver, monkeypatch):
    s = closed_receiver
    from plugins.friday_rework import worker_provision
    from scripts import dsh_prepare
    prepare = worker_provision.prepare_inputs; verify = dsh_prepare.verify_source; events = []
    def prepared(home, profile, kind, *args, **kwargs):
        result = prepare(home, profile, kind, *args, **kwargs)
        events.append(kind)
        return result
    def source(donor, identity, **kwargs):
        assert events[-2:] == ['dsh', 'a0']
        assert kwargs == {'keyless_helper': pin(s.home / 'harness/friday-web-keyless.mjs')}
        events.append('explicit-source-extension')
        return verify(donor, identity, **kwargs)
    monkeypatch.setattr(worker_provision, 'prepare_inputs', prepared)
    monkeypatch.setattr(dsh_prepare, 'verify_source', source)
    reconcile(s)
    extension = f.read_json(s.tx / 'intent.json')['source_extension']
    assert extension == {'reference': pin(s.home / 'harness/friday-web-keyless.mjs'), 'mode': 0o400,
        'identity': list(ordinary.update_file_state(s.home / 'harness/friday-web-keyless.mjs')['identity'])}
    assert events == ['dsh', 'a0', 'explicit-source-extension'] * 4 and not s.calls


# After79 regression: this function reference is captured before fixture seams.
# Native bytes are excluded only after the unchanged production layer validator;
# these controls establish inventory consistency, never installed composition.
def test_old_impossible_candidate_fails_unchanged_production_composition(tmp_path):
    value, receipt = source79_inventory()
    receipt['layers'].pop()
    manifests = {n for n in value['project_files'] if n.startswith('patches/hermes/') and n.endswith('.json')}
    assert len(manifests) == 79 and len(receipt['layers']) == 78
    with pytest.raises(f.Refused, match='composition_overlay_set_changed'):
        REAL_COMPOSITION_CHECK(value, tmp_path / 'never-read-native', receipt, {})


@pytest.mark.parametrize('fault', ['none', 'layer-count78', 'duplicate-manifest', 'manifest-sha', 'patch-sha'])
def test_after79_real_production_layer_inventory_invariant(tmp_path, monkeypatch, fault):
    value, receipt = source79_inventory()
    called = []
    def boundary(source, row, donor, **kw):
        called.append((source, row, donor)); return row['files']
    monkeypatch.setattr(f, 'source_checked', boundary)
    if fault == 'layer-count78': receipt['layers'].pop()
    elif fault == 'duplicate-manifest': receipt['layers'][-1] = copy.deepcopy(receipt['layers'][0])
    elif fault == 'manifest-sha': receipt['layers'][-1]['manifest_sha256'] = '0' * 64
    elif fault == 'patch-sha': receipt['layers'][-1]['patch_sha256'] = '0' * 64
    if fault == 'none':
        assert len(receipt['layers']) == 79 and len(receipt['files']) == 17686
        assert REAL_COMPOSITION_CHECK(value, tmp_path / 'excluded-native', receipt, {}) == receipt['files']
        assert len(called) == 1
    else:
        with pytest.raises(f.Refused, match='composition_overlay_'):
            REAL_COMPOSITION_CHECK(value, tmp_path / 'excluded-native', receipt, {})
        assert not called


def test_after79_fixture_preserves465_plus29_history_and_closed_original_budgets(closed_receiver):
    s = closed_receiver; r = s.recovery_request
    assert len(r['history']) == 494 and r['history'][:465] == s.pre79_history
    assert len({ref['path'] for ref in r['history']}) == 494
    assert all(ref in r['history'][:465] for ref in (r['keyless_ancestry']['intent'], r['keyless_ancestry']['committed']))
    original = f.read_json(Path(r['original_clock']['path']))
    assert original['server_seconds'] == 300 and original['physical_seconds'] == 660
    assert original['old_original300_reset'] is original['retry_authorized'] is False
    receipt = f.read_json(Path(r['source_receipt']['path']))
    assert len(receipt['layers']) == 79 and len(receipt['files']) == 17686
    assert not s.calls


@pytest.mark.parametrize('fault', ['old-history465', 'history-duplicate', 'old-native78', 'old-files17683'])
def test_after79_exact_current_tuple_refuses_pre79_or_incomplete_custody(closed_receiver, fault):
    s = closed_receiver; r = s.recovery_request
    if fault == 'old-history465': r['history'] = r['history'][:465]
    elif fault == 'history-duplicate': r['history'][-1] = r['history'][0]
    else:
        receipt = f.read_json(Path(r['source_receipt']['path']))
        if fault == 'old-native78': receipt['layers'].pop()
        else:
            for n in range(17683, 17686): receipt['files'].pop(str(n))
        r['source_receipt'] = doc(Path(r['source_receipt']['path']), receipt)
        r['stamp'] = doc(Path(r['stamp']['path']), dict(schemaVersion=2, distribution='friday-rework', payload='bootstrap',
            fridaySource=dict(baseTree=receipt['base_tree'], layers=receipt['layers'])))
        marker = f.read_json(s.home / f.MARKER); marker['source_receipt_sha256'] = r['source_receipt']['sha256']
        r['root_marker'] = doc(s.home / f.MARKER, marker)
    admit(s); before = snapshot(s.home)
    with pytest.raises(f.Refused, match='ordinary_closed_(explicit_maintenance_request|complete_unique_pins|native79_project231)_required'):
        reconcile(s)
    assert snapshot(s.home) == before and not s.calls
