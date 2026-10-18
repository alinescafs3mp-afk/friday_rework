"""Unexecuted SOURCE controls for stopped declaration maintenance.

The afterimage tests call the writer's non-authorizing construction seam with
real native config, onboarding proof and normalization consumers. They do not
fake a StoppedOperator, f.inspect, source identity or native stopped authority.
Publication controls use the same descriptor/CAS/owned-inode helpers as apply.
Full stopped apply/source/build/PM/native/live gates remain separately required.
No fixture in this module is permission to operate on an installed home.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from types import SimpleNamespace

import pytest

import test_admin_foundation
from test_user_onboarding import env, home, raw, save, row, ident, cas, grant, activate
from test_normal_user_worker_join import normal_env
from test_product_profile import split_inputs
from test_native_installer import install_input
from test_normal_worker_install import normal, service
from test_worker_declaration_migration import (
    data as declaration_data, plan as typed_plan, get, put, fingerprint,
    private_document, unchanged_except, ROOT_A0, TEMPLATE_A0, TEMPLATE_INPUTS,
)
from friday_admin_controls import worker_declarations as declaration
from friday_admin_controls import worker_declaration_writer as writer
from friday_admin_controls.stopped_operator import StoppedOperator
from friday_admin_controls import onboarding
from hermes_cli import friday_user_scope as users
from hermes_cli import friday_ordinary_gateway as ordinary
from hermes_cli.config import require_readable_config_before_write
from hermes_cli.config_effective import _effective
from scripts import friday_install as native_install
from scripts import friday_ordinary_install as native_update
from scripts import friday_worker_declarations as native_entry
from scripts import a0_runtime as native_a0
from scripts.dsh_prepare import StopUnconfirmed
from scripts.install_containment import Budget
from tools.configure_product import compose_product
from plugins.friday_rework.adapters.a0_profile import legacy_profile


CANARY = 'SYNTHETIC_STOPPED_DECLARATION_PRESERVATION_a91b'
REFUSED = (ValueError, PermissionError, RuntimeError, OSError)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False) + '\n').encode()


def pinned(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def retained_bytes(root):
    return {str(path.relative_to(root)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in root.rglob('*') if path.is_file()
        and not path.name.endswith('.lock') and not path.name.endswith('.backup')}


def installation_pair(plan):
    inputs = get(plan['root_config'], TEMPLATE_INPUTS)
    legacy_policy = {'path': '/synthetic-stopped-home/legacy-policy', 'sha256': 'b' * 64}
    before = {'home': '/synthetic-stopped-home', 'seconds': 660,
        'product': {'a0_deployment': legacy_profile(), 'runtime': {'enabled': False},
            'inference': {'preserve': CANARY}, 'compression_inference': {'preserve': CANARY}},
        'project_files': {'scripts/rootless_docker_launch.py': 'a' * 64},
        'worker_install': {'dsh': {'budget_seconds': 300,
                'resources': {'memory_bytes': 2147483648, 'cpu_percent': 200, 'tasks': 64}},
            'a0': {'budget_seconds': 300, 'policy': copy.deepcopy(legacy_policy),
                'network': {'name': inputs['a0_network']['name'],
                    'policy': copy.deepcopy(legacy_policy),
                    'endpoints': ['http://192.168.1.78:8001/v1', 'http://192.168.1.78:8002/v1']},
                'history': {'consumed_no_retry': True}}},
        'source': {'receipt': 'b' * 64, 'build': 'c' * 64, 'pm': 'd' * 64}}
    after = copy.deepcopy(before)
    after['product']['a0_deployment'] = copy.deepcopy(plan['root_config']['a0_deployment'])
    after['worker_install']['a0']['policy'] = copy.deepcopy(inputs['workers']['a0']['a0']['policy'])
    after['worker_install']['a0']['network']['policy'] = copy.deepcopy(inputs['a0_network']['policy'])
    after['worker_install']['a0']['network']['endpoints'] = copy.deepcopy(inputs['a0_network']['endpoints'])
    return before, after


def test_installation_successor_accepts_planned_deployment_and_joined_network_counterparts(declaration_data):
    plan = typed_plan(declaration_data)
    previous, current = installation_pair(plan)
    original = encoded([previous, current, plan])
    writer.validate_installation_delta(previous, current, plan)
    assert encoded([previous, current, plan]) == original


@pytest.mark.parametrize('damage', [
    'main-route', 'compression-route', 'worker-enable', 'worker-budget', 'memory-cap',
    'source-inventory', 'source-receipt', 'build', 'pm', 'original-seconds',
    'foreign-home', 'wrong-deployment', 'type-alias', 'extra-root-field',
    'a0-policy-join', 'network-policy-join', 'network-endpoint-join', 'network-name',
])
def test_installation_successor_rejects_coherently_rebound_unapproved_delta(declaration_data, damage):
    plan = typed_plan(declaration_data)
    previous, current = installation_pair(plan)
    if damage == 'main-route': current['product']['inference']['preserve'] = 'foreign'
    elif damage == 'compression-route': current['product']['compression_inference']['preserve'] = 'foreign'
    elif damage == 'worker-enable': current['product']['runtime']['enabled'] = True
    elif damage == 'worker-budget': current['worker_install']['a0']['budget_seconds'] -= 1
    elif damage == 'memory-cap': current['worker_install']['dsh']['resources']['memory_bytes'] -= 1
    elif damage == 'source-inventory': current['project_files']['scripts/rootless_docker_launch.py'] = 'f' * 64
    elif damage in ('source-receipt', 'build', 'pm'):
        current['source'][{'source-receipt': 'receipt', 'build': 'build', 'pm': 'pm'}[damage]] = 'f' * 64
    elif damage == 'original-seconds': current['seconds'] += 1
    elif damage == 'foreign-home': current['home'] += '-foreign'
    elif damage == 'wrong-deployment': current['product']['a0_deployment']['chat']['max_output_tokens'] -= 1
    elif damage == 'type-alias': current['worker_install']['a0']['budget_seconds'] = float(current['worker_install']['a0']['budget_seconds'])
    elif damage == 'a0-policy-join': current['worker_install']['a0']['policy']['sha256'] = 'f' * 64
    elif damage == 'network-policy-join': current['worker_install']['a0']['network']['policy']['sha256'] = 'f' * 64
    elif damage == 'network-endpoint-join': current['worker_install']['a0']['network']['endpoints'].reverse()
    elif damage == 'network-name': current['worker_install']['a0']['network']['name'] += '-foreign'
    else: current['client_authorized'] = True
    before = encoded([previous, current, plan])
    with pytest.raises(REFUSED): writer.validate_installation_delta(previous, current, plan)
    assert encoded([previous, current, plan]) == before


@pytest.fixture
def afterimage_case(normal_env, tmp_path):
    """Real admitted synthetic profile; a structural view is NO native authority."""
    e = normal_env
    ordinary_template = copy.deepcopy(e.template)
    ordinary_template.pop('worker_inputs')
    ordinary_template['required_secrets'] = [name for name in ordinary_template['required_secrets']
        if name != 'SEARXNG_SECRET']
    root = raw(e)
    templates = get(root, ('plugins', 'entries', 'friday_rework', 'settings', 'onboarding', 'templates'))
    templates['friday-ordinary-local'] = ordinary_template
    save(e, root)
    e.setup.prepare('default', session=e.operator, expected_config_sha256=cas(e),
        template='friday-ordinary-local', runtime_profile='user-1', **ident())
    for name in ordinary_template['required_secrets']:
        e.setup.credentials('default', session=e.operator, expected_config_sha256=cas(e),
            generation=row(e)['generation'], **ident(), name=name, value='SYNTHETIC_' + name)
    grant(e)
    assert activate(e)['enabled']
    own_home = home(e)
    own = require_readable_config_before_write(own_home / 'config.yaml')
    root = raw(e)
    # Complete native product surfaces are real composer output. Preserve the
    # signed fixture's committed admin policy, bindings and actual user routes.
    for name, value in e.bundle['config'].items():
        if name not in ('plugins', 'gateway'):
            root[name] = copy.deepcopy(value)
    for name in ('a0_deployment', 'model', 'providers', 'auxiliary', 'delegation'):
        root[name] = copy.deepcopy(own[name])
    for name, value in e.bundle['config']['gateway'].items():
        root['gateway'].setdefault(name, copy.deepcopy(value))
    root['dashboard']['basic_auth']['username'] = e.operator.user_id
    get(root, ('plugins', 'entries', 'friday_rework', 'settings'))['runtime'] = {'enabled': False}
    root['preserved_original_clocks'] = {'attempt300': {'deadline_mono': 4300, 'retry_authorized': False},
        'physical420': {'deadline_mono': 4419}, 'prior660': {'deadline_mono': 4660}}
    save(e, root)
    with users.authority(e.home):
        binding = copy.deepcopy(next(b for b in users.policy(e.home)['bindings']
            if b['runtime_profile'] == own_home.name))
        state_path = e.state.data_dir / 'state.json'
    # Historical attachment data is deliberately outside the current profile's
    # absent workers tree. This synthetic member supplies no archive authority.
    archived_attachment = private_document(e.home / 'preparation/synthetic-closed-source/attachment.json',
        {'state': 'SYNTHETIC_HISTORICAL_MEMBER_ONLY', 'canary': CANARY})
    private_document(own_home / 'workspace/continued-conversation.json', {'preserve': CANARY})
    private_document(e.home / 'profiles/non-target/config.yaml', {'preserve': CANARY})
    incoming = copy.deepcopy(get(root, TEMPLATE_INPUTS))
    after = copy.deepcopy(own['a0_deployment'])
    after['name'] = 'current-stopped-synthetic'
    model = own['model']
    capacity = own['providers']['friday-local']['models'][model['default']]
    after['chat'].update(endpoint=model['base_url'], model=model['default'],
        context_length=capacity['context_length'],
        max_output_tokens=capacity['bounded_context']['main_max_output_tokens'])
    incoming['workers']['a0']['a0']['deployment'] = copy.deepcopy(after)
    incoming['workers']['a0']['a0']['launcher']['sha256'] = 'd' * 64
    incoming['a0_network']['endpoints'] = list(dict.fromkeys(
        after[role]['endpoint'] for role in ('chat', 'utility', 'embedding')))
    evidence = tmp_path / 'afterimage-evidence'
    evidence.mkdir(mode=0o700)
    input_ref = private_document(evidence / 'worker-inputs.json', incoming)
    identity = {'schema': 'frw.current-dest-worker-identity.v1', 'binding': binding,
        'binding_sha256': fingerprint(binding), 'enabled': True, 'generation': row(e)['generation'],
        'principal': hashlib.sha256(json.dumps([binding[k] for k in declaration.IDENTITY_FIELDS],
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
        'profile': str(own_home), 'profile_template': 'friday-ordinary-local',
        'worker_attach_template': 'friday-local', 'authority': 'STATIC_SOURCE_JOIN_ONLY',
        'source_refs': {'root_configuration': pinned(e.home / 'config.yaml'),
            'configuration': pinned(own_home / 'config.yaml'),
            'onboarding': pinned(own_home / users.ONBOARDING),
            'user_marker': pinned(own_home / users.MARKER),
            'access_state': pinned(state_path),
            'stale_attachment': {'path': str(own_home / 'workers/attachment.json'),
                'sha256': archived_attachment['sha256']}}}
    identity_ref = private_document(evidence / 'identity.json', identity)
    changes = [{'document': name, 'path': list(path),
        'before': copy.deepcopy(get(document, path)), 'after': copy.deepcopy(after)}
        for name, path, document in (('root_config', ROOT_A0, root),
            ('profile_config', ROOT_A0, own), ('root_config', TEMPLATE_A0, root))]
    changes.append({'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
        'before_sha256': fingerprint(get(root, TEMPLATE_INPUTS)), 'after_reference': input_ref})
    bundle = {'schema': 'frw.current-both-spark-declaration-change-data.v1',
        'state': 'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'root_before': identity['source_refs']['root_configuration'],
        'profile_before': identity['source_refs']['configuration'],
        'identity_reference': identity_ref, 'changes': changes}
    plan = declaration.plan_declaration_delta(root, own, incoming, identity, bundle)
    previous, current = installation_pair(plan)
    for value in (previous, current):
        value['home'] = str(e.home)
        value['project_files']['scripts/friday_native.py'] = 'a' * 64
    previous['product']['a0_deployment'] = copy.deepcopy(own['a0_deployment'])
    previous_ref = private_document(evidence / 'previous-input.json', previous)
    current_ref = private_document(evidence / 'current-input.json', current)
    profile_contract = copy.deepcopy(e.bundle['contract'])
    profile_contract['native_dashboard']['operator'] = {
        'provider': e.operator.provider, 'user_id': e.operator.user_id, 'org_id': e.operator.org_id}
    profile_ref = private_document(e.home / 'FRIDAY-PROFILE.json', profile_contract)
    marker = {'schema': native_install.SCHEMA, 'home': str(e.home),
        'state': 'INSTALLED_TEMPLATE_INCOMPLETE', 'completion_stage': 'TELEGRAM_ORDINARY',
        'runtime_ready': False, 'worker_state': 'BOTH_WORKERS_PREPARATION_PENDING',
        'input_sha256': previous_ref['sha256'], 'original_attempt': root['preserved_original_clocks'],
        'profile_files': {'config.yaml': pinned(e.home / 'config.yaml')['sha256'],
            'FRIDAY-PROFILE.json': profile_ref['sha256']},
        'ordinary_gateway': {'configuration_sha256': ordinary.normalized_configuration(_effective(root)),
            'operator_entry': {'input': previous_ref,
                'script': {'path': str(evidence / 'native-not-executed.py'), 'sha256': 'a' * 64}},
            'history': {'closed_original_attempt': CANARY}, 'credential_files': {'preserved': CANARY}}}
    private_document(e.home / native_install.MARKER, marker)
    prefix = str(own_home.relative_to(e.home)) + '/'
    names = ['config.yaml', native_install.MARKER, prefix + 'config.yaml',
        prefix + users.ONBOARDING, prefix + users.MARKER]
    view = SimpleNamespace(home=e.home, profile_home=own_home, marker=marker,
        previous=previous, current=current, request={'current_input': current_ref},
        before={name: native_update.update_file_state(e.home / name) for name in names},
        binding=binding, row=copy.deepcopy(row(e)), proof=read(own_home / users.ONBOARDING))
    stage = evidence / 'stage'
    stage.mkdir(mode=0o700)
    return SimpleNamespace(e=e, view=view, plan=plan, stage=stage, prefix=prefix,
        root_before=root, own_before=own, before=retained_bytes(e.home), names=set(names))


def build(s):
    return writer.prepare_afterimages(s.view, s.plan, s.stage)


def publication_order(s):
    return ['config.yaml', s.prefix + 'config.yaml', s.prefix + users.ONBOARDING,
        s.prefix + users.MARKER, native_install.MARKER]


def test_real_afterimage_builder_publishes_exact_five_with_native_profile_and_marker_lineage(afterimage_case):
    s = afterimage_case
    outputs = build(s)
    assert set(outputs) == s.names
    assert retained_bytes(s.e.home) == s.before
    owned = {}
    with native_update.SourceUpdateDirectories(s.e.home, list(outputs), []) as directories:
        for name in publication_order(s):
            state = outputs[name]
            directories.prove()
            native_update.publish_update_file(s.e.home / name, state['data'], state['mode'],
                s.view.before[name], owned, name, parent_fd=directories.parent_fd(name))
        directories.prove()
    root = require_readable_config_before_write(s.e.home / 'config.yaml')
    own = require_readable_config_before_write(s.view.profile_home / 'config.yaml')
    unchanged_except(s.root_before, root, (ROOT_A0, TEMPLATE_A0, TEMPLATE_INPUTS))
    unchanged_except(s.own_before, own, (ROOT_A0,))
    marker = read(s.e.home / native_install.MARKER)
    assert marker['input_sha256'] == s.view.request['current_input']['sha256']
    assert marker['ordinary_gateway']['operator_entry']['input'] == s.view.request['current_input']
    assert marker['ordinary_gateway']['operator_entry']['script'] == s.view.marker['ordinary_gateway']['operator_entry']['script']
    assert marker['ordinary_gateway']['configuration_sha256'] == ordinary.normalized_configuration(_effective(root))
    assert marker['original_attempt'] == s.view.marker['original_attempt']
    assert marker['ordinary_gateway']['history'] == s.view.marker['ordinary_gateway']['history']
    assert marker['ordinary_gateway']['credential_files'] == s.view.marker['ordinary_gateway']['credential_files']
    proof = read(s.view.profile_home / users.ONBOARDING)
    assert proof['config_sha256'] == pinned(s.view.profile_home / 'config.yaml')['sha256']
    assert {k: v for k, v in proof.items() if k != 'config_sha256'} == {
        k: v for k, v in s.view.proof.items() if k != 'config_sha256'}
    user_marker = read(s.view.profile_home / users.MARKER)
    assert user_marker['onboarding_sha256'] == pinned(s.view.profile_home / users.ONBOARDING)['sha256']
    with users.authority(s.e.home): users.check_onboarding_home(s.e.home, s.view.profile_home, s.view.binding)
    assert row(s.e)['enabled'] and row(s.e)['generation'] == s.view.row['generation']
    current = retained_bytes(s.e.home)
    assert {n: v for n, v in current.items() if n not in s.names} == {
        n: v for n, v in s.before.items() if n not in s.names}
    assert all(state['mode'] == 0o600 for state in outputs.values())
    assert get(root, ('plugins', 'entries', 'friday_rework', 'settings', 'runtime')) == {'enabled': False}
    assert get(own, ('plugins', 'entries', 'friday_rework', 'settings', 'runtime')) == {'enabled': False}
    assert not (s.view.profile_home / 'workers').exists()


@pytest.mark.parametrize('damage', ['config-proof', 'soul-proof', 'user-marker', 'missing-key', 'binding', 'required-keys-proof'])
def test_afterimage_builder_uses_real_native_onboarding_validation_not_copied_hashes(afterimage_case, damage):
    s = afterimage_case
    if damage == 'config-proof':
        proof = read(s.view.profile_home / users.ONBOARDING); proof['config_sha256'] = 'f' * 64
        private_document(s.view.profile_home / users.ONBOARDING, proof)
    elif damage == 'soul-proof':
        path = s.view.profile_home / 'SOUL.md'; path.write_bytes(path.read_bytes() + b'\nFOREIGN_SOUL')
    elif damage == 'user-marker':
        marker = read(s.view.profile_home / users.MARKER); marker['binding_sha256'] = 'f' * 64
        private_document(s.view.profile_home / users.MARKER, marker)
    elif damage == 'missing-key': (s.view.profile_home / '.env').write_bytes(b'UNRELATED=SYNTHETIC\n')
    elif damage == 'binding':
        root = raw(s.e); get(root, ('plugins', 'entries', 'friday_rework', 'settings', 'user_isolation', 'bindings'))[0]['user_id'] = 'foreign-user'; save(s.e, root)
    else:
        proof = read(s.view.profile_home / users.ONBOARDING)
        proof['required_secrets'].append('SYNTHETIC_UNDECLARED_OWNER_KEY')
        private_document(s.view.profile_home / users.ONBOARDING, proof)
    before = retained_bytes(s.e.home)
    with pytest.raises(REFUSED): build(s)
    assert retained_bytes(s.e.home) == before


@pytest.mark.parametrize('published', [0, 1, 2, 3, 4])
def test_real_owned_publication_can_restore_each_partial_five_file_prefix(afterimage_case, published):
    s = afterimage_case
    outputs = build(s)
    owned = {}
    with native_update.SourceUpdateDirectories(s.e.home, list(outputs), []) as directories:
        for index, name in enumerate(publication_order(s)):
            if index > published: break
            state = outputs[name]
            native_update.publish_update_file(s.e.home / name, state['data'], state['mode'],
                s.view.before[name], owned, name, parent_fd=directories.parent_fd(name))
        native_update.restore_update_files(s.e.home, s.view.before, owned, directories)
        directories.prove()
    assert retained_bytes(s.e.home) == s.before
    with users.authority(s.e.home): users.check_onboarding_home(s.e.home, s.view.profile_home, s.view.binding)


@pytest.mark.parametrize('damage', ['foreign-inode-same-bytes', 'changed-bytes', 'changed-mode', 'symlink'])
def test_real_rollback_proves_whole_affected_set_before_restoring_any_path(afterimage_case, damage):
    s = afterimage_case
    outputs = build(s)
    owned = {}
    with native_update.SourceUpdateDirectories(s.e.home, list(outputs), []) as directories:
        for name in publication_order(s):
            state = outputs[name]
            native_update.publish_update_file(s.e.home / name, state['data'], state['mode'],
                s.view.before[name], owned, name, parent_fd=directories.parent_fd(name))
        foreign = s.e.home / 'config.yaml'
        if damage == 'foreign-inode-same-bytes':
            temporary = s.e.home / 'foreign-replacement'; temporary.write_bytes(foreign.read_bytes()); temporary.chmod(0o600); os.replace(temporary, foreign)
        elif damage == 'changed-bytes': foreign.write_bytes(foreign.read_bytes() + b'\nFOREIGN')
        elif damage == 'changed-mode': foreign.chmod(0o400)
        else:
            saved = s.e.home / 'foreign-target'; foreign.rename(saved); foreign.symlink_to(saved)
        expected = {name: (s.e.home / name).read_bytes() for name in outputs}
        with pytest.raises(REFUSED): native_update.restore_update_files(s.e.home, s.view.before, owned, directories)
        assert {name: (s.e.home / name).read_bytes() for name in outputs} == expected


@pytest.mark.parametrize('damage', ['same-body-foreign-inode', 'changed-bytes', 'changed-mode'])
def test_real_publication_cas_refuses_foreign_current_state_and_cleans_only_own_stage(afterimage_case, damage):
    s = afterimage_case
    outputs = build(s)
    path = s.e.home / 'config.yaml'
    if damage == 'same-body-foreign-inode':
        foreign = s.e.home / 'foreign-current-config'; foreign.write_bytes(path.read_bytes()); foreign.chmod(0o600); os.replace(foreign, path)
    elif damage == 'changed-bytes': path.write_bytes(path.read_bytes() + b'\nFOREIGN\n')
    else: path.chmod(0o400)
    before = native_update.update_file_state(path)
    owned = {}
    with native_update.SourceUpdateDirectories(s.e.home, list(outputs), []) as directories:
        with pytest.raises(REFUSED):
            native_update.publish_update_file(path, outputs['config.yaml']['data'], 0o600,
                s.view.before['config.yaml'], owned, 'config.yaml', parent_fd=directories.parent_fd('config.yaml'))
        assert native_update.update_file_state(path) == before
        assert owned == {}
        assert not path.with_name(path.name + '.ordinary-staged').exists()


def clock_document(tmp_path, **changes):
    started = time.monotonic() - 1
    body = {'schema': 'friday.worker-declarations.clock.v1',
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'started_mono': started, 'deadline_mono': started + 180, 'seconds': 180}
    body.update(changes)
    return private_document(tmp_path / 'original-clock.json', body), body


def test_clock_uses_original_deadline_without_reset_or_extension(tmp_path):
    reference, original = clock_document(tmp_path)
    before = Path(reference['path']).read_bytes()
    result = writer.validated_clock(reference, 180)
    assert Path(reference['path']).read_bytes() == before
    # The helper returns the authenticated finite body or its native Budget;
    # both representations must retain exactly the original deadline.
    deadline = result['deadline_mono'] if type(result) is dict else result.deadline
    assert deadline == original['deadline_mono']


@pytest.mark.parametrize('damage', ['expired', 'foreign-boot', 'extended', 'boolean-seconds',
    'nonfinite', 'future-start', 'extra-field', 'pin-drift', 'public', 'symlink', 'hardlink'])
def test_clock_rejects_stale_unbounded_or_unproved_original_claim(tmp_path, damage):
    reference, body = clock_document(tmp_path)
    if damage == 'expired':
        started = time.monotonic() - 181
        body.update(started_mono=started, deadline_mono=started + 180)
    elif damage == 'foreign-boot': body['boot_id'] = 'FOREIGN_BOOT'
    elif damage == 'extended': body['deadline_mono'] += 1
    elif damage == 'boolean-seconds': body['seconds'] = True
    elif damage == 'nonfinite': body['deadline_mono'] = float('inf')
    elif damage == 'future-start':
        body['started_mono'] = time.monotonic() + 30; body['deadline_mono'] = body['started_mono'] + 180
    elif damage == 'extra-field': body['owner_approved'] = True
    if damage not in ('pin-drift', 'public', 'symlink', 'hardlink'):
        path = Path(reference['path']); path.write_text(json.dumps(body)); path.chmod(0o600); reference = pinned(path)
    elif damage == 'pin-drift': Path(reference['path']).write_bytes(Path(reference['path']).read_bytes() + b'\n')
    elif damage == 'public': Path(reference['path']).chmod(0o644)
    elif damage == 'symlink':
        path = Path(reference['path']); saved = path.with_name('saved-clock'); path.rename(saved); path.symlink_to(saved)
    else: os.link(reference['path'], tmp_path / 'foreign-clock-alias')
    with pytest.raises(REFUSED): writer.validated_clock(reference, 180)


def test_new_commit_journal_returns_only_its_created_private_descriptor_identity(tmp_path):
    path = tmp_path / 'committed.json'
    data = encoded({'state': 'SYNTHETIC_COMMIT_ONLY', 'runtime_acceptance': 'NOT_GRANTED'})
    created = writer._new_journal(path, data)
    assert created == native_update.update_file_state(path)
    assert created['data'] == data and created['mode'] == 0o600
    assert path.stat().st_nlink == 1
    with pytest.raises(REFUSED): writer._new_journal(path, data)
    assert native_update.update_file_state(path) == created


@pytest.mark.parametrize('occupied', ['same-body', 'foreign-body', 'symlink', 'hardlink', 'directory'])
def test_commit_journal_collision_never_adopts_overwrites_or_unlinks_existing_entry(tmp_path, occupied):
    path = tmp_path / 'committed.json'
    foreign = tmp_path / 'foreign-retained'
    foreign.write_bytes(b'FOREIGN JOURNAL PRESERVE\n'); foreign.chmod(0o600)
    if occupied == 'symlink': path.symlink_to(foreign)
    elif occupied == 'hardlink': os.link(foreign, path)
    elif occupied == 'directory': path.mkdir(mode=0o700)
    else:
        path.write_bytes(b'PROPOSED\n' if occupied == 'same-body' else b'FOREIGN\n'); path.chmod(0o600)
    info = path.lstat()
    expected = (info.st_dev, info.st_ino, info.st_mode, info.st_nlink)
    before = foreign.read_bytes()
    with pytest.raises(REFUSED): writer._new_journal(path, b'PROPOSED\n')
    info = path.lstat()
    assert (info.st_dev, info.st_ino, info.st_mode, info.st_nlink) == expected
    assert foreign.read_bytes() == before
    if path.is_file():
        assert path.read_bytes() == (b'PROPOSED\n' if occupied == 'same-body' else
            before if occupied in ('symlink', 'hardlink') else b'FOREIGN\n')


@pytest.mark.parametrize('replacement', ['same-body-foreign-inode', 'changed-body-same-inode'])
def test_commit_journal_replacement_after_write_cannot_become_owned_by_rereading(tmp_path, monkeypatch, replacement):
    path = tmp_path / 'committed.json'
    original = os.fsync
    fired = []
    def interfere(fd):
        result = original(fd)
        if not fired and path.exists() and stat.S_ISREG(os.fstat(fd).st_mode):
            fired.append(True)
            if replacement == 'same-body-foreign-inode':
                foreign = tmp_path / 'foreign-created'; foreign.write_bytes(path.read_bytes()); foreign.chmod(0o600); os.replace(foreign, path)
            else: path.write_bytes(b'FOREIGN CONCURRENT BODY\n')
        return result
    monkeypatch.setattr(os, 'fsync', interfere)
    with pytest.raises(REFUSED): writer._new_journal(path, b'PROPOSED\n')
    assert fired == [True]
    assert path.read_bytes() == (b'PROPOSED\n' if replacement == 'same-body-foreign-inode'
        else b'FOREIGN CONCURRENT BODY\n')


@pytest.mark.parametrize('transition', ['consume', 'enter', 'prove', 'pins'])
def test_real_native_authority_cannot_claim_or_prove_without_required_preflight(env, tmp_path, transition):
    original = retained_bytes(tmp_path)
    authority = StoppedOperator({}, Budget(180))
    operation = {'consume': authority.consume, 'enter': authority.__enter__,
        'prove': authority.prove, 'pins': authority.pins_unchanged}[transition]
    with pytest.raises(REFUSED): operation()
    assert not authority.active and not authority.consumed and not authority.entered
    assert retained_bytes(tmp_path) == original


@pytest.mark.parametrize('claim', ['empty', 'stage-request', 'client-authorized', 'callback', 'injected-authority'])
def test_apply_rejects_request_shape_before_any_client_claim_can_be_authority(tmp_path, claim):
    sentinel = tmp_path / 'current-config'; sentinel.write_bytes(CANARY.encode()); sentinel.chmod(0o600)
    calls = []
    request = {}
    if claim == 'stage-request': request = {'schema': 'friday.worker-declarations.stage.v1', 'source': {}}
    elif claim == 'client-authorized': request = {'authorized': True, 'owner_approved': True, 'stopped_consumers': True}
    elif claim == 'callback': request = {'verify_native': lambda: calls.append(True)}
    elif claim == 'injected-authority': request = {'authority': object(), 'source_plan': {'native_authority': True}}
    request_path = tmp_path / 'request.json'
    request_path.write_bytes(encoded({})); request_path.chmod(0o600)
    before = retained_bytes(tmp_path)
    with pytest.raises(REFUSED):
        native_entry.apply_declarations(request, request_path=request_path,
            request_sha256=pinned(request_path)['sha256'])
    assert not calls and retained_bytes(tmp_path) == before


def test_request_snapshot_keeps_original_owned_descriptor_and_exact_bytes(tmp_path):
    reference = private_document(tmp_path / 'request.json', {'preserve': CANARY})
    before = native_update.update_file_state(Path(reference['path']))
    assert writer._request_snapshot(reference) == before
    assert native_update.update_file_state(Path(reference['path'])) == before


@pytest.mark.parametrize('interference', ['same-body-foreign-inode', 'changed-body-same-inode'])
def test_request_snapshot_refuses_replacement_during_initial_read_without_adopting_it(tmp_path, monkeypatch, interference):
    reference = private_document(tmp_path / 'request.json', {'preserve': CANARY})
    path = Path(reference['path'])
    original_bytes = path.read_bytes()
    original_inode = path.stat().st_ino
    original_fdopen = os.fdopen
    fired = []
    @contextmanager
    def interfering_reader(fd, *args, **kwargs):
        with original_fdopen(fd, *args, **kwargs) as stream:
            class Reader:
                def read(self, *read_args, **read_kwargs):
                    value = stream.read(*read_args, **read_kwargs)
                    if not fired:
                        fired.append(True)
                        if interference == 'same-body-foreign-inode':
                            foreign = path.with_name('foreign-request'); foreign.write_bytes(original_bytes); foreign.chmod(0o600); os.replace(foreign, path)
                        else: path.write_bytes(encoded({'foreign': CANARY}))
                    return value
            yield Reader()
    monkeypatch.setattr(os, 'fdopen', interfering_reader)
    with pytest.raises(REFUSED): writer._request_snapshot(reference)
    assert fired == [True]
    assert path.read_bytes() == (original_bytes if interference == 'same-body-foreign-inode'
        else encoded({'foreign': CANARY}))
    assert (path.stat().st_ino != original_inode) is (interference == 'same-body-foreign-inode')
    assert {entry.name for entry in tmp_path.iterdir()} == {'request.json'}


@pytest.mark.parametrize('kind', ['stop-unconfirmed', 'unexpected'])
def test_apply_cli_preserves_uncertain_outcome_and_redacts_private_primary(tmp_path, monkeypatch, capsys, kind):
    """Error-boundary injection grants no stopped/native execution authority."""
    request = private_document(tmp_path / 'request.json', {})
    private_primary = CANARY + ':' + str(tmp_path)
    def failed(*args, **kwargs):
        assert kwargs == {'request_path': request['path'], 'request_sha256': request['sha256']}
        error = StopUnconfirmed(private_primary) if kind == 'stop-unconfirmed' else RuntimeError(private_primary)
        raise error
    monkeypatch.setattr(native_entry, 'apply_declarations', failed)
    monkeypatch.setattr(sys, 'argv', ['friday_worker_declarations.py', 'apply',
        '--request', request['path'], '--request-sha256', request['sha256']])
    before = retained_bytes(tmp_path)
    result = native_entry.main()
    captured = capsys.readouterr()
    public = json.loads(captured.out)
    assert result == (3 if kind == 'stop-unconfirmed' else 2)
    assert public['state'] == ('STOP_UNCONFIRMED' if kind == 'stop-unconfirmed'
        else 'FAILED_CLOSED_RECONCILE_EXACT_JOURNAL')
    assert public['ready'] is False and public['native_migration'] == 'NO_ACCEPTANCE_CLAIM'
    assert CANARY not in captured.out and str(tmp_path) not in captured.out
    assert not captured.err and retained_bytes(tmp_path) == before


def test_supported_native_phase_refuses_bytecode_before_product_api_or_request_read(tmp_path, monkeypatch, capsys):
    calls = []
    def forbidden_api():
        calls.append(True)
        pytest.fail('native product API reached before no-bytecode admission')
    monkeypatch.setattr(native_update, 'api', forbidden_api)
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    monkeypatch.setattr(sys, 'argv', ['friday_ordinary_install.py', 'rebind-worker-declarations',
        '--request', str(tmp_path / 'PRIVATE_UNREAD_REQUEST'), '--request-sha256', 'a' * 64])
    before = retained_bytes(tmp_path)
    with pytest.raises(SystemExit) as stopped: native_update.recovery_main()
    captured = capsys.readouterr()
    assert stopped.value.code == 2 and not calls and not captured.out
    assert json.loads(captured.err) == {'state': 'NOT_STARTED', 'ready': False,
        'error': 'worker_declaration_native_no_bytecode_required'}
    assert 'PRIVATE_UNREAD_REQUEST' not in captured.err
    assert retained_bytes(tmp_path) == before


def pm_snapshot(root):
    """No metadata repair; retain link identities without following aliases."""
    result = {}
    for path in root.rglob('*'):
        info = path.lstat()
        identity = (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if stat.S_ISREG(info.st_mode):
            with path.open('rb') as stream: content = hashlib.file_digest(stream, 'sha256').hexdigest()
            result[str(path.relative_to(root))] = (identity, content)
        elif stat.S_ISLNK(info.st_mode):
            result[str(path.relative_to(root))] = (identity, os.readlink(path))
    return result


@pytest.fixture
def pm_components(tmp_path):
    """Actual native PM data readers; NO selected/native operator authority.

    No tool ensure/installed_package/env_for/verification command is invoked.
    All records and the non-executed synthetic binary live in this temp tree.
    """
    from pm.lock import Facts, Lockfile
    from pm.registry import get_package
    from pm.store import Store, current_target
    root = tmp_path / 'pm-component'
    root.mkdir(mode=0o700)
    store = root / 'tools'
    store.mkdir(mode=0o700)
    target = current_target()
    package = get_package('node')
    node = package.binary(Store(store).entry('node-synthetic-source'), target)
    assert node is not None
    node.parent.mkdir(mode=0o700, parents=True)
    for directory in (node.parent, node.parent.parent): directory.chmod(0o700)
    node.write_bytes(b'SYNTHETIC NODE BYTES - NEVER EXECUTED\n'); node.chmod(0o700)
    lock_ref = private_document(root / 'lock.json', {'schema': 1, 'packages': {
        'node': {'version': '0.0.0-source-fixture', 'artifacts': {target: {
            'url': 'https://example.invalid/source-only-not-fetched', 'sha256': 'a' * 64}}}}})
    tool_facts = private_document(store / 'facts.json', {'schema': 1, 'packages': {
        'node': {'entry': 'node-synthetic-source', 'version': '0.0.0-source-fixture',
            'target': target, 'artifacts': ['a' * 64], 'env': {'PATH': ['{{store}}/node-synthetic-source/bin']}}}})
    selected = root / 'installs/synthetic-generation/venv'
    runtime_facts = private_document(root / 'installs/facts.json', {'schema': 1, 'packages': {
        'venv': {'environment': str(selected)}}})
    pyvenv = private_document(selected / 'pyvenv.cfg', {'SYNTHETIC_NOT_SELECTED_NOT_EXECUTED': True})
    references = {'runtime_facts': runtime_facts, 'tool_facts': tool_facts,
        'pyvenv_cfg': pyvenv, 'node': pinned(node)}
    authority = StoppedOperator({'native_pm': copy.deepcopy(references)}, Budget(180))
    authority.f, authority.ordinary = native_install, native_update
    return SimpleNamespace(root=root, node=node, store=store, target=target,
        package=package, lock=Lockfile(Path(lock_ref['path'])),
        facts=Facts(Path(tool_facts['path']), strict=True), references=references,
        authority=authority)


def test_actual_native_pm_fact_lock_store_selector_and_authority_binary_reader_are_read_only(pm_components):
    s = pm_components
    before = pm_snapshot(s.root)
    artifacts = s.lock.artifacts('node', s.target)
    identity = (s.target, tuple(artifact['sha256'] for artifact in artifacts))
    assert s.facts.installed('node', s.lock.version('node'), s.store, identity)
    from pm.store import Store
    selected = s.package.binary(Store(s.store).entry(s.facts.get('node')['entry']), s.target)
    assert selected == s.node
    state = s.authority._binary_state(selected, full=True)
    assert set(state) == {'identity', 'sha256'} and state['sha256'] == s.references['node']['sha256']
    assert s.authority._binary_state(selected, full=False) == state
    assert pm_snapshot(s.root) == before
    assert not s.authority.active and not s.authority.consumed


@pytest.mark.parametrize('size', [1024, 65 * 1024**2])
def test_native_pm_binary_stream_reader_keeps_document_limit_and_returns_no_binary_copy(tmp_path, size):
    node = tmp_path / 'node-never-executed'
    node.write_bytes(b'SYNTHETIC_EXECUTABLE_NOT_EXECUTED\n')
    with node.open('r+b') as stream: stream.truncate(size)
    node.chmod(0o700)
    before = pm_snapshot(tmp_path)
    authority = StoppedOperator({}, Budget(180))
    state = authority._binary_state(node, full=True)
    assert set(state) == {'identity', 'sha256'}
    assert state['identity'][5] == size
    with node.open('rb') as stream: assert state['sha256'] == hashlib.file_digest(stream, 'sha256').hexdigest()
    assert pm_snapshot(tmp_path) == before


@pytest.mark.parametrize('damage', ['missing-node', 'extra-field', 'boolean-map', 'node-digest',
    'non-executable', 'doc-hardlink', 'doc-symlink', 'doc-pin-drift'])
def test_real_pm_reference_preflight_denies_before_selection_and_never_heals(pm_components, damage):
    s = pm_components
    references = s.authority.request['native_pm']
    if damage == 'missing-node': references.pop('node')
    elif damage == 'extra-field': references['client_installed'] = True
    elif damage == 'boolean-map': s.authority.request['native_pm'] = True
    elif damage == 'node-digest': references['node']['sha256'] = 'f' * 64
    elif damage == 'non-executable':
        s.node.chmod(0o600)
        # Native Facts marks a matching existing store entry installed without
        # repairing it. The stopped reader must additionally refuse its mode.
        identity = (s.target, tuple(artifact['sha256'] for artifact in s.lock.artifacts('node', s.target)))
        assert s.facts.installed('node', s.lock.version('node'), s.store, identity)
    else:
        path = Path(references['tool_facts']['path'])
        if damage == 'doc-hardlink': os.link(path, s.root / 'foreign-facts-alias')
        elif damage == 'doc-symlink':
            retained = path.with_name('retained-facts.json'); path.rename(retained); path.symlink_to(retained)
        else: path.write_bytes(path.read_bytes() + b'\n')
    before = pm_snapshot(s.root)
    with pytest.raises(REFUSED): s.authority._pm_preflight()
    assert pm_snapshot(s.root) == before
    assert not hasattr(s.authority, '_pm_state') and not s.authority.active and not s.authority.consumed
    if damage == 'non-executable': assert stat.S_IMODE(s.node.stat().st_mode) == 0o600


@pytest.mark.parametrize('damage', ['non-executable', 'empty', 'over-limit', 'hardlink', 'symlink', 'directory'])
def test_pm_binary_reader_refuses_unsafe_existing_entry_without_chmod_or_repair(pm_components, damage):
    s = pm_components
    if damage == 'non-executable': s.node.chmod(0o600)
    elif damage == 'empty': s.node.write_bytes(b'')
    elif damage == 'over-limit':
        with s.node.open('r+b') as stream: stream.truncate(512 * 1024**2 + 1)
    elif damage == 'hardlink': os.link(s.node, s.root / 'foreign-node-alias')
    elif damage == 'symlink':
        retained = s.node.with_name('retained-node'); s.node.rename(retained); s.node.symlink_to(retained)
    else: s.node.unlink(); s.node.mkdir(mode=0o700)
    # For the sparse over-limit case capture metadata only: rejection must
    # occur before reading the file; no 512MiB hash is needed for this control.
    info = s.node.lstat()
    expected = (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size)
    with pytest.raises(REFUSED): s.authority._binary_state(s.node, full=True)
    info = s.node.lstat()
    assert (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size) == expected


@pytest.mark.parametrize('damage', ['same-body-foreign-inode', 'changed-body', 'non-executable-mode'])
def test_retained_pm_binary_reader_rejects_cached_selection_drift_without_adopting_or_healing(pm_components, damage):
    s = pm_components
    s.authority._binary_state(s.node, full=True)
    if damage == 'same-body-foreign-inode':
        foreign = s.node.with_name('foreign-node'); foreign.write_bytes(s.node.read_bytes()); foreign.chmod(0o700); os.replace(foreign, s.node)
    elif damage == 'changed-body': s.node.write_bytes(b'FOREIGN NODE BYTES - NEVER EXECUTED\n')
    else: s.node.chmod(0o600)
    before = pm_snapshot(s.root)
    with pytest.raises(REFUSED): s.authority._binary_state(s.node, full=False)
    assert pm_snapshot(s.root) == before


def private_tree_snapshot(root):
    result = pm_snapshot(root)
    for path in root.rglob('*'):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            result['DIRECTORY:' + str(path.relative_to(root))] = (
                info.st_dev, info.st_ino, info.st_uid, info.st_mode)
    return result


@pytest.fixture
def pairing_grant(env):
    """Actual native synthetic grant; initialize=False is NOT write authority."""
    from gateway import pairing
    env.monkeypatch.setattr(pairing, 'PAIRING_DIR', None)
    PairingStore = pairing.PairingStore
    grant(env)
    store = PairingStore()
    # Preparation may use the process umask; the observer requires the actual
    # private custody contract. Tighten only this disposable fixture's dirs.
    current = store._dir
    while current != env.home:
        assert env.home in current.parents
        current.chmod(0o700)
        current = current.parent
    assert store.is_approved('telegram', '1')
    return SimpleNamespace(e=env, store=store, active=store._dir)


def test_native_noninitializing_pairing_constructor_reads_existing_grant_without_mkdir_or_migration(pairing_grant, monkeypatch):
    from gateway import pairing
    s = pairing_grant
    before = private_tree_snapshot(s.e.home)
    def forbidden(*args, **kwargs): pytest.fail('noninitializing pairing constructor attempted initialization')
    with monkeypatch.context() as boundary:
        boundary.setattr(pairing, '_migrate_split_pairing_dirs', forbidden)
        boundary.setattr(Path, 'mkdir', forbidden)
        observed = pairing.PairingStore(initialize=False)
        assert observed.is_approved('telegram', '1')
        assert not observed.is_approved('telegram', 'foreign-unapproved')
    assert private_tree_snapshot(s.e.home) == before


def test_native_noninitializing_pairing_constructor_refuses_missing_directory_without_creating_it(env):
    from gateway import pairing
    env.monkeypatch.setattr(pairing, 'PAIRING_DIR', None)
    PairingStore = pairing.PairingStore
    before = private_tree_snapshot(env.home)
    with pytest.raises(REFUSED): PairingStore(initialize=False)
    assert private_tree_snapshot(env.home) == before


@pytest.mark.parametrize('initialize', [None, 0, 1, 'false', {}, []])
def test_native_pairing_initialization_option_requires_exact_boolean_before_effects(env, initialize):
    from gateway import pairing
    env.monkeypatch.setattr(pairing, 'PAIRING_DIR', None)
    PairingStore = pairing.PairingStore
    before = private_tree_snapshot(env.home)
    with pytest.raises((ValueError, TypeError)): PairingStore(initialize=initialize)
    assert private_tree_snapshot(env.home) == before


@pytest.mark.parametrize('unsafe', ['public-directory', 'symlink-directory'])
def test_native_noninitializing_pairing_constructor_refuses_unproved_directory_custody(pairing_grant, unsafe):
    from gateway.pairing import PairingStore
    s = pairing_grant
    if unsafe == 'public-directory': s.active.chmod(0o755)
    else:
        retained = s.active.with_name('foreign-retained-pairing'); s.active.rename(retained); s.active.symlink_to(retained, target_is_directory=True)
    before = private_tree_snapshot(s.e.home)
    with pytest.raises(REFUSED): PairingStore(initialize=False)
    assert private_tree_snapshot(s.e.home) == before


def test_native_pairing_alternate_layout_creation_race_is_never_migrated_by_observer(pairing_grant, monkeypatch):
    from gateway import pairing
    s = pairing_grant
    alternate = (s.e.home / 'pairing' if s.active == s.e.home / 'platforms/pairing'
        else s.e.home / 'platforms/pairing')
    assert not alternate.exists()
    original = pairing._default_pairing_dir
    expected = []
    def alternate_after_layout_selection():
        selected = original()
        assert selected == s.active
        private_document(alternate / 'telegram-approved.json', {
            'race-foreign': {'approved_at': 1, 'user_name': CANARY}})
        expected.append(private_tree_snapshot(s.e.home))
        return selected
    monkeypatch.setattr(pairing, '_default_pairing_dir', alternate_after_layout_selection)
    observed = pairing.PairingStore(initialize=False)
    assert len(expected) == 1 and observed._dir == s.active
    assert observed.is_approved('telegram', '1') and not observed.is_approved('telegram', 'race-foreign')
    assert private_tree_snapshot(s.e.home) == expected[0]
    assert read(alternate / 'telegram-approved.json')['race-foreign']['user_name'] == CANARY


def test_native_pairing_default_initialization_and_ordinary_grant_writer_still_work(env):
    from gateway import pairing
    env.monkeypatch.setattr(pairing, 'PAIRING_DIR', None)
    PairingStore = pairing.PairingStore
    store = PairingStore()
    assert store._dir.is_dir()
    assert store.generate_code('telegram', 'ordinary-default-fixture', 'Synthetic fixture')
    pending = next(item for item in store.list_pending() if item['user_id'] == 'ordinary-default-fixture')
    assert store.approve_request('telegram', pending['request_id'])
    assert store.is_approved('telegram', 'ordinary-default-fixture')


@pytest.fixture
def a0_runtime_lock_case(tmp_path, monkeypatch):
    root = tmp_path / 'isolated-native-a0-runtime'
    root.mkdir(mode=0o700)
    lock = root / 'runtime.lock'
    lock.write_bytes(b''); lock.chmod(0o600)
    # Patch only the native runtime data root. The two real lock consumers,
    # flock implementation and exact existing file remain production code.
    monkeypatch.setattr(native_a0, 'RUNTIME', root)
    return SimpleNamespace(root=root, lock=lock)


def test_retained_stopped_runtime_lock_excludes_actual_native_runtime_lock_consumer(a0_runtime_lock_case):
    s = a0_runtime_lock_case
    before = private_tree_snapshot(s.root)
    with native_update.retained_build_lock(s.root, lock_path=s.lock, required=True) as prove:
        prove()
        with pytest.raises(BlockingIOError):
            # This real context manager uses only the pinned global data root;
            # no Runtime plan, constructor, route or execution is authorized.
            with native_a0.Runtime.locked(None): pytest.fail('native runtime lock entered under stopped custody')
        prove()
    # Both consumers release their own descriptor on refusal/success.
    with native_a0.Runtime.locked(None): pass
    assert private_tree_snapshot(s.root) == before


def test_actual_native_runtime_lock_excludes_retained_stopped_custody(a0_runtime_lock_case):
    s = a0_runtime_lock_case
    before = private_tree_snapshot(s.root)
    with native_a0.Runtime.locked(None):
        with pytest.raises(BlockingIOError):
            with native_update.retained_build_lock(s.root, lock_path=s.lock, required=True):
                pytest.fail('stopped custody entered under actual native runtime lock')
    with native_update.retained_build_lock(s.root, lock_path=s.lock, required=True) as prove: prove()
    assert private_tree_snapshot(s.root) == before


@pytest.mark.parametrize('damage', ['missing', 'nonempty'])
def test_stopped_runtime_custody_requires_existing_empty_lock_without_creation_or_overwrite(a0_runtime_lock_case, damage):
    s = a0_runtime_lock_case
    if damage == 'missing': s.lock.unlink()
    else: s.lock.write_bytes(CANARY.encode())
    before = private_tree_snapshot(s.root)
    with pytest.raises(REFUSED):
        with native_update.retained_build_lock(s.root, lock_path=s.lock, required=True):
            pytest.fail('unproved runtime lock was adopted')
    assert private_tree_snapshot(s.root) == before
    if damage == 'missing': assert not s.lock.exists()
    else: assert s.lock.read_bytes() == CANARY.encode()


def main_deployment(spec):
    deployment = legacy_profile()
    primary = spec['inference']
    deployment['name'] = 'current-spark-stopped'
    deployment['chat'].update(endpoint=primary['base_url'], model=primary['model'],
        context_length=primary['context'], max_output_tokens=primary['main_output'])
    return deployment


@pytest.mark.parametrize('role', ['current-main', 'preserved-compression'])
def test_both_real_product_consumers_allow_exact_inactive_current_or_legacy_role(install_input, role):
    spec = split_inputs()
    spec['a0_deployment'] = main_deployment(spec) if role == 'current-main' else legacy_profile()
    before = encoded(spec)
    bundle = compose_product(spec)
    assert bundle['config']['a0_deployment'] == spec['a0_deployment']
    assert bundle['config']['auxiliary']['compression']['context_length'] == 40960
    value = copy.deepcopy(install_input); value['product'] = spec
    native_install.spec_checked(value, cli_only=True)
    assert encoded(spec) == before
    assert not Path(value['home']).exists()


@pytest.mark.parametrize('mixed', ['endpoint', 'model', 'context', 'output', 'main-key', 'compression-key'])
def test_both_real_product_consumers_refuse_mixed_or_credential_alias_a0_roles(install_input, mixed):
    spec = split_inputs(); spec['a0_deployment'] = main_deployment(spec)
    fields = {'endpoint': ('endpoint', 'base_url'), 'model': ('model', 'model'),
        'context': ('context_length', 'context'), 'output': ('max_output_tokens', 'main_output')}
    if mixed in fields:
        dest, source = fields[mixed]; spec['a0_deployment']['chat'][dest] = spec['compression_inference'][source]
    elif mixed == 'main-key': spec['inference']['key_env'] = 'FRIDAY_COMPRESSION_API_KEY'
    else: spec['compression_inference']['key_env'] = 'FRIDAY_LLM_API_KEY'
    before = encoded(spec)
    with pytest.raises(REFUSED): compose_product(spec)
    value = copy.deepcopy(install_input); value['product'] = spec
    with pytest.raises(REFUSED): native_install.spec_checked(value, cli_only=True)
    assert encoded(spec) == before
    assert not Path(value['home']).exists()


def test_active_workers_cannot_take_preserved_compressor_as_main(normal_env, install_input):
    spec = split_inputs()
    spec['a0_deployment'] = legacy_profile()
    spec['runtime'] = copy.deepcopy(normal_env.operator_runtime)
    with pytest.raises(ValueError, match='a0_product_inference_profile_mismatch'):
        compose_product(spec)
    value = copy.deepcopy(install_input); value['product'] = spec
    with pytest.raises(ValueError, match='a0_product_inference_profile_mismatch'):
        native_install.spec_checked(value, cli_only=True)


@pytest.fixture
def native_worker_input_pair(normal):
    """Real worker_install/settings/LocalNetwork consumers, synthetic temp pins.

    Existing normal fixture uses isolated local Git donors and explicit fake
    native manager/build reports. No service/build/network/model is executed;
    this fixture supplies no native source-install or stopped authority.
    """
    s = normal
    previous = copy.deepcopy(s.value)
    previous['product'] = split_inputs()
    previous['product']['a0_deployment'] = legacy_profile()
    current = copy.deepcopy(previous)
    current['product']['a0_deployment'] = main_deployment(current['product'])
    policy = private_document(s.deploy / 'current-declaration-policy.json', {
        'state': 'SYNTHETIC_SOURCE_POLICY_ONLY_NOT_FIREWALL_ACCEPTANCE', 'preserve': CANARY})
    current['worker_install']['a0']['policy'] = copy.deepcopy(policy)
    network = current['worker_install']['a0']['network']
    network['policy'] = copy.deepcopy(policy)
    network['endpoints'] = list(dict.fromkeys(current['product']['a0_deployment'][role]['endpoint']
        for role in ('chat', 'utility', 'embedding')))
    return SimpleNamespace(s=s, previous=previous, current=current)


def test_native_installation_validator_consumes_joined_current_main_and_three_worker_network_leaves(native_worker_input_pair):
    s = native_worker_input_pair
    before = retained_bytes(s.s.home)
    original = encoded([s.previous, s.current])
    native_install.spec_checked(s.previous, cli_only=True)
    native_install.spec_checked(s.current, cli_only=True)
    assert len(s.current['worker_install']['a0']['network']['endpoints']) == 3
    assert encoded([s.previous, s.current]) == original
    assert retained_bytes(s.s.home) == before


@pytest.mark.parametrize('damage', ['stale-old-endpoints', 'unjoined-policy', 'policy-pin-drift',
    'missing-embedding', 'extra-endpoint', 'duplicate-endpoint'])
def test_native_worker_network_consumer_refuses_partial_or_unproved_successor(native_worker_input_pair, damage):
    s = native_worker_input_pair
    network = s.current['worker_install']['a0']['network']
    if damage == 'stale-old-endpoints': network['endpoints'] = copy.deepcopy(s.previous['worker_install']['a0']['network']['endpoints'])
    elif damage == 'unjoined-policy': network['policy'] = copy.deepcopy(s.previous['worker_install']['a0']['network']['policy'])
    elif damage == 'policy-pin-drift':
        path = Path(network['policy']['path']); path.write_bytes(path.read_bytes() + b'\n')
    elif damage == 'missing-embedding': network['endpoints'].pop()
    elif damage == 'extra-endpoint': network['endpoints'].append('http://192.168.1.90:9999/v1')
    else: network['endpoints'].append(network['endpoints'][-1])
    before = retained_bytes(s.s.home)
    with pytest.raises(REFUSED): native_install.spec_checked(s.current, cli_only=True)
    assert retained_bytes(s.s.home) == before
