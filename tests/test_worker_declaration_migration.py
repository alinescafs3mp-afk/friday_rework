"""Future isolated SOURCE declaration controls; all execution is NOT_RUN.

Synthetic identities/configurations exercise the pure four-path planner. No
live identity, installed input, receipt, launcher, secret or private inventory is
copied. Proposed data and a successful pure plan confer no native authority.
Historical stage/proposal requests remain invalid at the stopped apply entry.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

# The existing fixture module establishes the supported source package alias;
# it does not register or execute a worker/plugin runtime.
import test_admin_foundation
from test_user_onboarding import env
from test_normal_user_worker_join import normal_env
from friday_admin_controls import worker_declarations as declaration
from scripts import friday_worker_declarations as native


ROOT_A0 = ('a0_deployment',)
TEMPLATE = ('plugins', 'entries', 'friday_rework', 'settings', 'onboarding',
            'templates', 'friday-local')
TEMPLATE_A0 = TEMPLATE + ('config', 'a0_deployment')
TEMPLATE_INPUTS = TEMPLATE + ('worker_inputs',)
FOUR = {('root_config', ROOT_A0), ('profile_config', ROOT_A0),
        ('root_config', TEMPLATE_A0), ('root_config', TEMPLATE_INPUTS)}
SOURCE_CANARY = 'SYNTHETIC_DECLARATION_PRESERVATION_31ae'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def ref(path, sha='a' * 64):
    return {'path': str(path), 'sha256': sha}


def get(document, path):
    for component in path:
        document = document[component]
    return document


def put(document, path, value):
    get(document, path[:-1])[path[-1]] = value


def old_deployment():
    return {'name': 'legacy-local-test', 'preset': 'Default',
        'chat': {'endpoint': 'http://192.168.1.78:8001/v1', 'model': 'dispatcher',
                 'context_length': 40960, 'max_output_tokens': 4096, 'timeout': 60},
        'utility': {'endpoint': 'http://192.168.1.78:8001/v1', 'model': 'dispatcher',
                    'context_length': 40960, 'max_output_tokens': 4096, 'timeout': 60},
        'embedding': {'endpoint': 'http://192.168.1.78:8002/v1', 'model': 'qwen3-embedding-0.6b',
                      'context_length': 0, 'timeout': 30}}


def current_deployment():
    value = old_deployment()
    value['name'] = 'current-spark-local'
    value['chat'] = {'endpoint': 'http://192.168.1.195:30000/v1',
        'model': 'qwen38-flash-next-abliterated', 'context_length': 262144,
        'max_output_tokens': 8192, 'timeout': 60}
    return value


@pytest.fixture
def data():
    root = Path('/synthetic-declaration-fixture/current-home')
    profile = root / 'profiles/synthetic-user'
    binding = dict(platform='telegram', transport_profile='default', account_id='synthetic-account',
                   user_id='synthetic-user', runtime_profile=profile.name,
                   tools=['browser_navigate', 'read_file', 'web_search', 'friday_work'])
    principal = hashlib.sha256(json.dumps([binding[k] for k in
        ('platform', 'transport_profile', 'account_id', 'user_id')],
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    model = {'provider': 'custom:friday-local', 'default': 'qwen38-flash-next-abliterated',
             'base_url': 'http://192.168.1.195:30000/v1', 'key_env': 'FRIDAY_LLM_API_KEY'}
    protected = {'default_model': 'Qwen3.5-27B', 'key_env': 'FRIDAY_COMPRESSOR_API_KEY',
                 'context_length': 40960, 'max_output_tokens': 4096}
    own = {'a0_deployment': old_deployment(), 'model': model,
        'providers': {'friday-local': {'models': {model['default']: {
            'context_length': 262144, 'bounded_context': {'main_max_output_tokens': 8192}}}},
            'friday-compression': protected},
        'web': {'profile': 'exa-keyless', 'canary': SOURCE_CANARY},
        'browser': {'preset': 'local-headless-basic', 'enabled': True},
        'auxiliary': {'compression': copy.deepcopy(protected)},
        'agent': {'request_budget_seconds': 120},
        'plugins': {'entries': {'friday_rework': {'settings': {'runtime': {'enabled': False}}}}}}
    old_inputs = {'required': ['dsh', 'a0'],
        'source_scope': {'home': str(root), 'profile': 'default'},
        'a0_network': {'name': 'friday-onboarding', 'endpoints': [
            'http://192.168.1.78:8001/v1', 'http://192.168.1.78:8002/v1'],
            'policy': ref(root / 'synthetic-inputs/network.nft')},
        'workers': {
            'dsh': {'budget_seconds': 900, 'max_file_bytes': 8388608, 'max_total_bytes': 16777216,
                'dsh': {'memory_bytes': 2147483648, 'cpu_percent': 200, 'tasks': 64,
                    'tmp_bytes': 67108864, 'shutdown_seconds': 2, 'key_name': 'FRIDAY_LLM_API_KEY',
                    'web': {'profile': 'exa-keyless', 'resolver': ref(root / 'synthetic-inputs/resolv.conf'),
                            'trust_bundle': ref(root / 'synthetic-inputs/ca.pem')},
                    'native_files': []}},
            'a0': {'budget_seconds': 600, 'max_file_bytes': 8388608, 'max_total_bytes': 16777216,
                'a0': {'deployment': old_deployment(), 'capability': None,
                    'launcher': ref(root.parent / 'rootless-docker/launch.py', 'b' * 64),
                    'policy': ref(root / 'synthetic-inputs/network.nft'),
                    'web': {'profile': 'searxng-google', 'image': 'sha256:' + 'c' * 64}}}}}
    incoming = copy.deepcopy(old_inputs)
    incoming['workers']['a0']['a0']['deployment'] = current_deployment()
    incoming['workers']['a0']['a0']['launcher']['sha256'] = 'd' * 64
    current_policy = ref(root / 'synthetic-inputs/current-network.nft', 'e' * 64)
    incoming['workers']['a0']['a0']['policy'] = copy.deepcopy(current_policy)
    incoming['a0_network']['policy'] = copy.deepcopy(current_policy)
    incoming['a0_network']['endpoints'] = ['http://192.168.1.195:30000/v1',
        'http://192.168.1.78:8001/v1', 'http://192.168.1.78:8002/v1']
    root_config = copy.deepcopy(own)
    settings = root_config['plugins']['entries']['friday_rework']['settings']
    settings.update(user_isolation={'enabled': True, 'bindings': [copy.deepcopy(binding)]},
        onboarding={'templates': {'friday-local': {'config': copy.deepcopy(own),
            'tools': binding['tools'], 'required_secrets': ['FRIDAY_LLM_API_KEY'],
            'worker_inputs': copy.deepcopy(old_inputs)}}})
    root_config['gateway'] = {'profile_routes': [{'profile': profile.name,
        'account': binding['account_id'], 'user': binding['user_id']}]}
    root_config['owner_history'] = {'canary': SOURCE_CANARY,
        'original_attempt': {'budget_seconds': 300, 'started_mono': 4000, 'deadline_mono': 4300},
        'physical_clock': {'physical_seconds': 420, 'started': 3999, 'deadline': 4419}}
    identity = {'schema': 'frw.current-dest-worker-identity.v1', 'binding': binding,
        'binding_sha256': fingerprint(binding), 'enabled': True, 'generation': 1,
        'principal': principal, 'profile': str(profile), 'profile_template': 'friday-ordinary-local',
        'worker_attach_template': 'friday-local', 'authority': 'STATIC_SOURCE_JOIN_ONLY',
        'source_refs': {'root_configuration': ref(root / 'config.yaml'),
            'configuration': ref(profile / 'config.yaml', 'b' * 64),
            'onboarding': ref(profile / '.friday-onboarding.json'),
            'user_marker': ref(profile / '.friday-user-scope.json'),
            'access_state': ref(root / 'plugin-data/synthetic-namespace/state.json'),
            'stale_attachment': ref(profile / 'workers/attachment.json')}}
    bundle = {'schema': 'frw.current-both-spark-declaration-change-data.v1',
        'state': 'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'root_before': copy.deepcopy(identity['source_refs']['root_configuration']),
        'profile_before': copy.deepcopy(identity['source_refs']['configuration']),
        'identity_reference': ref(root / 'synthetic-evidence/identity.json'),
        'preserve': 'All other config fields and native authority remain unchanged.',
        'required_native_transaction': 'Native stopped ownership, exact current lineage and operator entry required.',
        'changes': [
            {'document': document, 'path': list(path), 'before': old_deployment(),
             'after': current_deployment()} for document, path in
            (('root_config', ROOT_A0), ('profile_config', ROOT_A0), ('root_config', TEMPLATE_A0))] + [
            {'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
             'before_sha256': fingerprint(old_inputs),
             'after_reference': ref(root / 'synthetic-evidence/worker-inputs.json')}]}
    return SimpleNamespace(root=root_config, profile=own, incoming=incoming,
                           identity=identity, bundle=bundle)


def plan(d):
    return declaration.plan_declaration_delta(d.root, d.profile, d.incoming, d.identity, d.bundle)


def unchanged_except(before, after, paths):
    first, second = copy.deepcopy(before), copy.deepcopy(after)
    for path in paths:
        put(first, path, '<EXPLICIT_TYPED_CHANGE>')
        put(second, path, '<EXPLICIT_TYPED_CHANGE>')
    assert encoded(first) == encoded(second)


def test_exact_four_path_current_spark_delta_preserves_every_other_field_without_authority(data):
    d = data
    before = encoded(vars(d))
    result = plan(d)
    assert result['state'] == 'SOURCE_DECLARATION_DELTA_ONLY_NOT_NATIVE_AUTHORITY'
    assert result['ready'] is False
    assert result['native_authority'] is False and result['workers_enabled'] is False
    assert result['launcher']['installed'] is False
    assert result['launcher']['state'] == 'ALREADY_PROMOTED_LAUNCHER_REQUIRED_AT_NATIVE_APPLY'
    assert len(result['semantic_changes']) == 4
    assert get(result['root_config'], ROOT_A0) == current_deployment()
    assert get(result['root_config'], TEMPLATE_A0) == current_deployment()
    assert get(result['profile_config'], ROOT_A0) == current_deployment()
    assert get(result['root_config'], TEMPLATE_INPUTS) == d.incoming
    unchanged_except(d.root, result['root_config'], (ROOT_A0, TEMPLATE_A0, TEMPLATE_INPUTS))
    unchanged_except(d.profile, result['profile_config'], (ROOT_A0,))
    assert result['profile_config']['providers']['friday-compression'] == d.profile['providers']['friday-compression']
    assert result['root_config']['owner_history'] == d.root['owner_history']
    for value in (result['root_config'], result['profile_config']):
        settings = value['plugins']['entries']['friday_rework']['settings']
        assert settings['runtime'] == {'enabled': False} and 'worker_requirements' not in settings
    assert encoded(vars(d)) == before


def test_plan_output_is_detached_and_never_rewrites_inputs(data):
    original = encoded(vars(data))
    result = plan(data)
    result['root_config']['model']['default'] = 'FOREIGN_OUTPUT_MUTATION'
    result['profile_config']['browser']['enabled'] = False
    get(result['root_config'], TEMPLATE_INPUTS)['workers']['a0']['budget_seconds'] = 1
    assert encoded(vars(data)) == original


@pytest.mark.parametrize('damage', [
    'fifth-path', 'missing-path', 'duplicate-path', 'wrong-document',
    'old-root-subtree', 'old-profile-subtree', 'old-template-subtree', 'old-inputs-subtree',
    'incoming-deployment', 'binding-hash', 'principal', 'profile-path',
    'other-user-current-binding', 'disabled', 'boolean-generation',
    'foreign-source-scope', 'missing-worker', 'profile-runtime', 'profile-requirements',
    'invalid-incoming-ref', 'invalid-identity-ref', 'root-before-ref', 'profile-before-ref',
])
def test_exact_typed_delta_rejects_conflicts_or_foreign_source_without_mutating_inputs(data, damage):
    d = data
    if damage == 'fifth-path': d.bundle['changes'].append({'document': 'root_config', 'path': ['model'], 'before': {}, 'after': {}})
    elif damage == 'missing-path': d.bundle['changes'].pop()
    elif damage == 'duplicate-path': d.bundle['changes'][2] = copy.deepcopy(d.bundle['changes'][0])
    elif damage == 'wrong-document': d.bundle['changes'][1]['document'] = 'other_user_config'
    elif damage == 'old-root-subtree': d.root['a0_deployment']['chat']['context_length'] += 1
    elif damage == 'old-profile-subtree': d.profile['a0_deployment']['utility']['timeout'] += 1
    elif damage == 'old-template-subtree': get(d.root, TEMPLATE_A0)['embedding']['model'] = 'foreign-embedding'
    elif damage == 'old-inputs-subtree': get(d.root, TEMPLATE_INPUTS)['workers']['dsh']['budget_seconds'] -= 1
    elif damage == 'incoming-deployment': d.incoming['workers']['a0']['a0']['deployment']['utility']['context_length'] = 262144
    elif damage == 'binding-hash': d.identity['binding_sha256'] = 'f' * 64
    elif damage == 'principal': d.identity['principal'] = 'f' * 64
    elif damage == 'profile-path': d.identity['profile'] = str(Path(d.identity['profile']).with_name('other-user'))
    elif damage == 'other-user-current-binding':
        get(d.root, ('plugins', 'entries', 'friday_rework', 'settings', 'user_isolation', 'bindings'))[0]['user_id'] = 'other-user'
    elif damage == 'disabled': d.identity['enabled'] = False
    elif damage == 'boolean-generation': d.identity['generation'] = True
    elif damage == 'foreign-source-scope': d.incoming['source_scope']['home'] = '/synthetic-other-user-home'
    elif damage == 'missing-worker': d.incoming['workers'].pop('a0')
    elif damage == 'profile-runtime': d.profile['plugins']['entries']['friday_rework']['settings']['runtime']['enabled'] = True
    elif damage == 'profile-requirements': d.profile['plugins']['entries']['friday_rework']['settings']['worker_requirements'] = ['dsh', 'a0']
    elif damage == 'invalid-incoming-ref': d.bundle['changes'][3]['after_reference']['sha256'] = 'NOT_A_PIN'
    elif damage == 'invalid-identity-ref': d.bundle['identity_reference']['path'] = '../foreign-identity.json'
    elif damage == 'root-before-ref': d.bundle['root_before']['sha256'] = 'f' * 64
    else: d.bundle['profile_before']['sha256'] = 'f' * 64
    before = encoded(vars(d))
    with pytest.raises(declaration.DeclarationError):
        plan(d)
    assert encoded(vars(d)) == before


@pytest.mark.parametrize('spoof', [
    'lowered-context', 'lowered-output', 'wrong-endpoint', 'wrong-model',
    'protected-utility', 'protected-embedding', 'changed-timeout',
    'boolean-context', 'extra-chat-field',
])
def test_coherently_rebound_after_rows_cannot_override_current_inference_or_protected_routes(data, spoof):
    d = data
    after = current_deployment()
    if spoof == 'lowered-context': after['chat']['context_length'] = 40960
    elif spoof == 'lowered-output': after['chat']['max_output_tokens'] = 4096
    elif spoof == 'wrong-endpoint': after['chat']['endpoint'] = 'http://192.0.2.20:9000/v1'
    elif spoof == 'wrong-model': after['chat']['model'] = 'other-model'
    elif spoof == 'protected-utility': after['utility']['context_length'] = 262144
    elif spoof == 'protected-embedding': after['embedding']['model'] = 'other-embedding'
    elif spoof == 'changed-timeout': after['chat']['timeout'] = 30
    elif spoof == 'boolean-context': after['chat']['context_length'] = True
    else: after['chat']['unreviewed_provider_override'] = SOURCE_CANARY
    # All proposed afterimages agree and their owning Source pins could be
    # legitimately regenerated. Current root+profile inference and protected
    # utility/embedding remain independent authority for semantic validation.
    d.incoming['workers']['a0']['a0']['deployment'] = copy.deepcopy(after)
    for row in d.bundle['changes'][:3]: row['after'] = copy.deepcopy(after)
    before = encoded(vars(d))
    with pytest.raises(declaration.DeclarationError):
        plan(d)
    assert encoded(vars(d)) == before


@pytest.mark.parametrize('mutation', [
    'dsh-memory', 'dsh-cpu', 'dsh-tasks', 'dsh-tmp', 'dsh-stop', 'dsh-budget',
    'a0-budget', 'file-budget', 'native-ref', 'launcher-path', 'network-name',
    'policy-join', 'endpoint-order', 'endpoint-duplicate', 'boolean-budget', 'numeric-type',
])
def test_rebound_worker_input_proposal_preserves_resources_pins_and_typed_complement(data, mutation):
    d = data
    incoming = d.incoming
    dsh = incoming['workers']['dsh']
    a0 = incoming['workers']['a0']
    if mutation.startswith('dsh-') and mutation != 'dsh-budget':
        field = {'dsh-memory': 'memory_bytes', 'dsh-cpu': 'cpu_percent',
            'dsh-tasks': 'tasks', 'dsh-tmp': 'tmp_bytes', 'dsh-stop': 'shutdown_seconds'}[mutation]
        dsh['dsh'][field] -= 1
    elif mutation == 'dsh-budget': dsh['budget_seconds'] -= 1
    elif mutation == 'a0-budget': a0['budget_seconds'] -= 1
    elif mutation == 'file-budget': dsh['max_total_bytes'] -= 1
    elif mutation == 'native-ref': dsh['dsh']['web']['resolver']['sha256'] = 'f' * 64
    elif mutation == 'launcher-path': a0['a0']['launcher']['path'] += '.foreign'
    elif mutation == 'network-name': incoming['a0_network']['name'] = 'foreign-network'
    elif mutation == 'policy-join': a0['a0']['policy']['sha256'] = 'f' * 64
    elif mutation == 'endpoint-order': incoming['a0_network']['endpoints'].reverse()
    elif mutation == 'endpoint-duplicate': incoming['a0_network']['endpoints'].append(incoming['a0_network']['endpoints'][-1])
    elif mutation == 'boolean-budget': a0['budget_seconds'] = True
    else: dsh['budget_seconds'] = float(dsh['budget_seconds'])
    # The owner has rebound the proposed input reference to the new payload;
    # refusal must depend on its typed resource/pin complement or network join,
    # rather than a stale beforeimage/hash or disagreement among after rows.
    d.bundle['changes'][3]['after_reference']['sha256'] = fingerprint(incoming)
    assert d.bundle['changes'][3]['before_sha256'] == fingerprint(get(d.root, TEMPLATE_INPUTS))
    before = encoded(vars(d))
    with pytest.raises(declaration.DeclarationError):
        plan(d)
    assert encoded(vars(d)) == before


@pytest.mark.parametrize('claim', [
    'unissued-current-input', 'missing-operator-entry', 'normalized-marker-lineage-mismatch',
    'future-launcher-not-installed', 'foreign-generation', 'client-authorized', 'fake-native-callback',
])
def test_missing_native_migration_authority_cannot_be_replaced_by_source_plan_or_client_claim(
        data, tmp_path, claim):
    d = data
    proposed = plan(d)
    sentinel = tmp_path / 'untouched-current-config'
    sentinel.write_bytes(b'SYNTHETIC ORIGINAL CONFIG BYTES\n')
    sentinel.chmod(0o600)
    request = {'source_plan': proposed, 'current_input': ref(sentinel),
               'operator_entry': None, 'runtime_authority': 'NOT_GRANTED'}
    called = []
    if claim == 'unissued-current-input': request['current_input']['sha256'] = 'f' * 64
    elif claim == 'missing-operator-entry': request['operator_entry'] = None
    elif claim == 'normalized-marker-lineage-mismatch': request['root_marker'] = {'normalized_config_sha256': 'f' * 64}
    elif claim == 'future-launcher-not-installed': request['launcher_installed'] = False
    elif claim == 'foreign-generation': request['generation'] = d.identity['generation'] + 1
    elif claim == 'client-authorized': request.update(authorized=True, owner_approved=True, stopped_consumers=True)
    else: request['verify_native'] = lambda: called.append(True)
    before = (sentinel.read_bytes(), sentinel.stat().st_ino, sorted(p.name for p in tmp_path.iterdir()))
    with pytest.raises((declaration.DeclarationError, RuntimeError, ValueError), match='exact_apply_request_required'):
        native.apply_declarations(request)
    assert not called
    assert (sentinel.read_bytes(), sentinel.stat().st_ino, sorted(p.name for p in tmp_path.iterdir())) == before


def private_document(path, value):
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing): parent.mkdir(mode=0o700)
    path.write_bytes((json.dumps(value, sort_keys=True) + '\n').encode())
    path.chmod(0o600)
    return ref(path, hashlib.sha256(path.read_bytes()).hexdigest())


def file_snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_ino, p.stat().st_mode)
            for p in root.rglob('*') if p.is_file() and not p.name.endswith('.lock')}


@pytest.fixture
def source_files(data, tmp_path):
    d = data
    root = tmp_path / 'current-home'
    profile = root / 'profiles' / d.identity['binding']['runtime_profile']
    evidence = tmp_path / 'source-evidence'
    d.identity['profile'] = str(profile)
    d.incoming['source_scope']['home'] = str(root)
    get(d.root, TEMPLATE_INPUTS)['source_scope']['home'] = str(root)
    d.bundle['changes'][3]['before_sha256'] = fingerprint(get(d.root, TEMPLATE_INPUTS))
    root_ref = private_document(root / 'config.yaml', d.root)
    own_ref = private_document(profile / 'config.yaml', d.profile)
    sources = {'root_configuration': root_ref, 'configuration': own_ref,
        'onboarding': private_document(profile / '.friday-onboarding.json', {'SYNTHETIC_PROOF': SOURCE_CANARY}),
        'user_marker': private_document(profile / '.friday-user-scope.json', {'SYNTHETIC_MARKER': SOURCE_CANARY}),
        'access_state': private_document(root / 'plugin-data/synthetic-namespace/state.json', {'SYNTHETIC_STATE': SOURCE_CANARY}),
        'stale_attachment': private_document(profile / 'workers/attachment.json', {'SYNTHETIC_ATTACHMENT': SOURCE_CANARY})}
    d.identity['source_refs'] = sources
    d.bundle['root_before'] = root_ref
    d.bundle['profile_before'] = own_ref
    input_ref = private_document(evidence / 'worker-inputs.json', d.incoming)
    identity_ref = private_document(evidence / 'identity.json', d.identity)
    d.bundle['identity_reference'] = identity_ref
    d.bundle['changes'][3]['after_reference'] = input_ref
    bundle_ref = private_document(evidence / 'bundle.json', d.bundle)
    companion = {'bundle': bundle_ref, 'worker_inputs': input_ref, 'identity': identity_ref}
    output_parent = tmp_path / 'private-output'
    output_parent.mkdir(mode=0o700)
    return SimpleNamespace(data=d, root=root, profile=profile, evidence=evidence,
        companion=companion, output=output_parent / 'proposed',
        request={'schema': 'friday.worker-declarations.stage.v1', 'source': companion,
                 'root_configuration': root_ref, 'profile_configuration': own_ref},
        base=tmp_path)


def test_private_source_join_and_stage_produce_only_unapplied_candidate_files(source_files):
    s = source_files
    before = file_snapshot(s.root)
    joined = declaration.validate_declaration_source(s.companion, s.data.root, s.data.profile,
        root_home=s.root, profile_home=s.profile)
    assert joined['status'] == 'SOURCE_JOIN_ONLY_NOT_NATIVE_AUTHORITY'
    assert joined['native_apply_implemented'] is True and joined['ready'] is False
    assert 'root_config' not in joined and 'profile_config' not in joined
    result = native.stage(s.request, output=s.output)
    assert result['state'] == 'STAGED_ONLY_NOT_NATIVE_AUTHORITY'
    assert result['ready'] is False and result['workers_enabled'] is False
    assert s.output.stat().st_mode & 0o777 == 0o700
    assert {p.name for p in s.output.iterdir()} == {'root-config.proposed.json',
        'profile-config.proposed.json', 'declaration-source-join.json', 'request.json', 'stage.json'}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in s.output.iterdir())
    assert file_snapshot(s.root) == before
    staged = json.loads((s.output / 'profile-config.proposed.json').read_text())
    assert staged['a0_deployment'] == current_deployment()
    assert staged['providers']['friday-compression'] == s.data.profile['providers']['friday-compression']
    with pytest.raises(ValueError, match='exact_apply_request_required'):
        native.apply_declarations(s.request)
    assert file_snapshot(s.root) == before


@pytest.mark.parametrize('damage', [
    'bundle-pin', 'worker-input-pin', 'identity-pin', 'root-cas', 'profile-cas',
    'unjoined-worker-reference', 'unjoined-identity-reference', 'source-symlink',
    'source-hardlink', 'source-public', 'source-fifo', 'live-reference-fifo',
    'duplicate-json', 'client-callback',
    'output-in-current-home', 'output-collision',
])
def test_stage_refuses_cas_pin_alias_schema_or_output_conflicts_without_current_writes(source_files, damage):
    s = source_files
    if damage in ('bundle-pin', 'worker-input-pin', 'identity-pin'):
        key = {'bundle-pin': 'bundle', 'worker-input-pin': 'worker_inputs', 'identity-pin': 'identity'}[damage]
        p = Path(s.companion[key]['path']); p.write_bytes(p.read_bytes() + b'\n')
    elif damage in ('root-cas', 'profile-cas'):
        p = s.root / 'config.yaml' if damage == 'root-cas' else s.profile / 'config.yaml'
        p.write_bytes(p.read_bytes() + b'\n')
    elif damage in ('unjoined-worker-reference', 'unjoined-identity-reference'):
        if damage == 'unjoined-worker-reference':
            s.data.bundle['changes'][3]['after_reference'] = dict(s.companion['worker_inputs'], sha256='f' * 64)
        else:
            s.data.bundle['identity_reference'] = dict(s.companion['identity'], sha256='f' * 64)
        s.companion['bundle'] = private_document(Path(s.companion['bundle']['path']), s.data.bundle)
    elif damage.startswith('source-'):
        p = Path(s.companion['worker_inputs']['path'])
        if damage == 'source-public': p.chmod(0o644)
        elif damage == 'source-hardlink': os.link(p, p.with_name('hardlink-inputs.json'))
        elif damage == 'source-fifo':
            p.unlink(); os.mkfifo(p, 0o600)
        else:
            saved = p.with_name('retained-inputs.json'); p.rename(saved); p.symlink_to(saved)
    elif damage == 'live-reference-fifo':
        p = Path(s.data.identity['source_refs']['access_state']['path'])
        p.unlink(); os.mkfifo(p, 0o600)
    elif damage == 'duplicate-json':
        p = Path(s.companion['bundle']['path'])
        raw = p.read_bytes(); p.write_bytes(b'{"schema":"frw.current-both-spark-declaration-change-data.v1",' + raw[1:])
        s.companion['bundle'] = ref(p, hashlib.sha256(p.read_bytes()).hexdigest())
    elif damage == 'client-callback': s.companion['verify_native'] = True
    elif damage == 'output-in-current-home': s.output = s.root / 'staging-must-not-become-live'
    else: private_document(s.output / 'foreign.json', {'preserve': SOURCE_CANARY})
    before = file_snapshot(s.base)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        native.stage(s.request, output=s.output)
    assert file_snapshot(s.base) == before
    if damage in ('source-fifo', 'live-reference-fifo'):
        assert stat.S_ISFIFO(p.lstat().st_mode)


from test_worker_stale_archive import (
    stale as archive_stale, invoke as invoke_archive, rewrite as rewrite_archive,
    archive_directory, ordinary_unchanged, snapshot as archive_snapshot,
    reference as private_reference,
)
from test_user_onboarding import raw as native_raw, save as native_save
from hermes_cli import friday_user_scope as scope
from hermes_cli.config import require_readable_config_before_write
from friday_admin_controls import worker_archive


@pytest.fixture
def companion_archive(archive_stale):
    """Real synthetic ordinary admission plus pinned generic Source companion."""
    s = archive_stale
    own = require_readable_config_before_write(s.h / 'config.yaml')
    root = native_raw(s.e)
    root['a0_deployment'] = copy.deepcopy(own['a0_deployment'])
    root['model'] = copy.deepcopy(own['model'])
    root['providers'] = copy.deepcopy(own['providers'])
    settings = root['plugins']['entries']['friday_rework']['settings']
    settings['runtime'] = {'enabled': False}
    incoming = copy.deepcopy(get(root, TEMPLATE_INPUTS))
    # This existing archive fixture uses an admitted synthetic legacy main.
    # Derive its proposed deployment from that CURRENT config; the independent
    # pure fixture above exercises the exact public Spark262144/8192 values.
    after = copy.deepcopy(own['a0_deployment'])
    after['name'] = 'current-synthetic-source-fixture'
    capacity = own['providers']['friday-local']['models'][own['model']['default']]
    after['chat'].update(endpoint=own['model']['base_url'], model=own['model']['default'],
        context_length=capacity['context_length'],
        max_output_tokens=capacity['bounded_context']['main_max_output_tokens'])
    incoming['workers']['a0']['a0']['deployment'] = copy.deepcopy(after)
    incoming['workers']['a0']['a0']['launcher']['sha256'] = 'd' * 64
    incoming['a0_network']['endpoints'] = list(dict.fromkeys(
        after[role]['endpoint'] for role in ('chat', 'utility', 'embedding')))
    native_save(s.e, root)
    with scope.authority(s.e.home):
        state_path = s.e.state.data_dir / 'state.json'
    identity = {'schema': 'frw.current-dest-worker-identity.v1',
        'binding': copy.deepcopy(s.binding), 'binding_sha256': fingerprint(s.binding),
        'enabled': True, 'generation': 1, 'principal': hashlib.sha256(json.dumps(
            [s.binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')],
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
        'profile': str(s.h), 'profile_template': 'friday-ordinary-local',
        'worker_attach_template': 'friday-local', 'authority': 'STATIC_SOURCE_JOIN_ONLY',
        'source_refs': {'root_configuration': private_reference(s.e.home / 'config.yaml'),
            'configuration': private_reference(s.h / 'config.yaml'),
            'onboarding': private_reference(s.h / scope.ONBOARDING),
            'user_marker': private_reference(s.h / scope.MARKER),
            'access_state': private_reference(state_path),
            'stale_attachment': private_reference(s.h / 'workers/attachment.json')}}
    evidence = s.documents / 'declaration-companion'
    input_ref = private_document(evidence / 'worker-inputs.json', incoming)
    identity_ref = private_document(evidence / 'identity.json', identity)
    changes = []
    for name, path, document in (('root_config', ROOT_A0, root),
            ('profile_config', ROOT_A0, own), ('root_config', TEMPLATE_A0, root)):
        changes.append({'document': name, 'path': list(path),
                        'before': copy.deepcopy(get(document, path)), 'after': copy.deepcopy(after)})
    changes.append({'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
        'before_sha256': fingerprint(get(root, TEMPLATE_INPUTS)), 'after_reference': input_ref})
    bundle = {'schema': 'frw.current-both-spark-declaration-change-data.v1',
        'state': 'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'root_before': identity['source_refs']['root_configuration'],
        'profile_before': identity['source_refs']['configuration'],
        'identity_reference': identity_ref, 'changes': changes}
    companion = {'bundle': private_document(evidence / 'bundle.json', bundle),
                 'worker_inputs': input_ref, 'identity': identity_ref}
    s.request['current']['root_configuration'] = identity['source_refs']['root_configuration']
    s.request['declaration_source'] = companion
    rewrite_archive(s)
    s.declaration_identity, s.declaration_bundle = identity, bundle
    return s


def rebind_companion(s):
    companion = s.request['declaration_source']
    companion['identity'] = private_document(Path(companion['identity']['path']), s.declaration_identity)
    s.declaration_bundle['identity_reference'] = companion['identity']
    companion['bundle'] = private_document(Path(companion['bundle']['path']), s.declaration_bundle)
    rewrite_archive(s)


def test_pinned_source_companion_remains_valid_after_workers_move_and_public_result_is_redacted(companion_archive):
    s = companion_archive
    root_before = (s.e.home / 'config.yaml').read_bytes()
    result = invoke_archive(s.e, s.ref)
    assert result['state'] == 'ARCHIVED_STALE_WORKER_SETUP_NO_RUNTIME_AUTHORITY'
    assert result['declaration_source']['status'] == 'SOURCE_JOIN_ONLY_NOT_NATIVE_AUTHORITY'
    assert result['declaration_source']['native_apply_implemented'] is True
    assert set(result['declaration_source']) == {'status', 'bundle_sha256',
        'candidate_root_sha256', 'candidate_profile_sha256', 'native_apply_implemented'}
    assert worker_archive.snapshot_tree(archive_directory(s)) == s.tree
    assert not (s.h / 'workers').exists()
    assert (s.e.home / 'config.yaml').read_bytes() == root_before
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('damage', ['foreign-binding', 'foreign-generation', 'incoming-pin', 'historical-attachment-pin'])
def test_protected_archive_source_companion_refuses_foreign_authority_before_consumption(companion_archive, damage):
    s = companion_archive
    if damage == 'foreign-binding':
        identity = s.declaration_identity
        identity['binding']['user_id'] = 'other-user'
        identity['binding_sha256'] = fingerprint(identity['binding'])
        identity['principal'] = hashlib.sha256(json.dumps([identity['binding'][k] for k in
            ('platform', 'transport_profile', 'account_id', 'user_id')],
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        rebind_companion(s)
    elif damage == 'foreign-generation':
        s.declaration_identity['generation'] = 2
        rebind_companion(s)
    elif damage == 'historical-attachment-pin':
        s.declaration_identity['source_refs']['stale_attachment']['sha256'] = 'f' * 64
        rebind_companion(s)
    else:
        p = Path(s.request['declaration_source']['worker_inputs']['path'])
        p.write_bytes(p.read_bytes() + b'\n')
    before = archive_snapshot(s.e.home)
    with pytest.raises((PermissionError, ValueError, RuntimeError, OSError)):
        invoke_archive(s.e, s.ref)
    assert archive_snapshot(s.e.home) == before
    assert not s.native_calls and not (s.h / 'worker-setup-archive').exists()


@pytest.mark.parametrize('boundary', ['after-claim', 'after-rename'])
def test_declaration_pin_drift_after_claim_or_move_consumes_without_config_migration(
        companion_archive, monkeypatch, boundary):
    s = companion_archive
    from contextlib import contextmanager
    changed = []
    publish = worker_archive._write_at
    guard = worker_archive._native_guard

    def drift():
        if not changed:
            changed.append(True)
            p = Path(s.request['declaration_source']['worker_inputs']['path'])
            p.write_bytes(p.read_bytes() + b'\n')

    @contextmanager
    def after_claim_guard(home, request, budget):
        with guard(home, request, budget) as prove:
            if boundary == 'after-claim': drift()
            yield prove

    def after_rename_publication(parent, name, value):
        own_row = publish(parent, name, value)
        if name == 'committed.json' and boundary == 'after-rename': drift()
        return own_row

    monkeypatch.setattr(worker_archive, '_native_guard', after_claim_guard)
    monkeypatch.setattr(worker_archive, '_write_at', after_rename_publication)
    root_before = (s.e.home / 'config.yaml').read_bytes()
    with pytest.raises(worker_archive.StopUnconfirmed):
        invoke_archive(s.e, s.ref)
    assert changed == [True]
    assert (s.e.home / 'config.yaml').read_bytes() == root_before
    assert list((s.h / 'worker-setup-archive/consumed-attempts').iterdir())
    if boundary == 'after-claim': assert worker_archive.snapshot_tree(s.h / 'workers') == s.tree
    else: assert worker_archive.snapshot_tree(archive_directory(s)) == s.tree
    ordinary_unchanged(s.e, s.before)


@pytest.mark.parametrize('failure', ['nested-json-recursion', 'unexpected-stage-error'])
def test_staging_cli_internal_failures_are_constant_redacted_and_make_no_current_writes(
        source_files, monkeypatch, capsys, failure):
    s = source_files
    request_path = s.evidence / ('SYNTHETIC_PRIVATE_CLI_CANARY-' + failure + '.json')
    if failure == 'nested-json-recursion':
        # Real private pinned bytes reach the production JSON decoder. No
        # process or recursive Python object is constructed by this fixture.
        request_path.write_bytes(b'[' * 20000 + b'0' + b']' * 20000)
        request_path.chmod(0o600)
        request_ref = ref(request_path, hashlib.sha256(request_path.read_bytes()).hexdigest())
    else:
        request_ref = private_document(request_path, s.request)

        def unexpected_stage(*args, **kwargs):
            raise RuntimeError('SYNTHETIC_PRIVATE_CLI_CANARY:' + str(s.root))

        monkeypatch.setattr(native, 'stage', unexpected_stage)
    monkeypatch.setattr(sys, 'argv', ['friday_worker_declarations.py', 'stage',
        '--request', request_ref['path'], '--request-sha256', request_ref['sha256'],
        '--output', str(s.output)])
    before = file_snapshot(s.root)
    public_json_loads = json.loads

    def refused(error_code):
        assert native.main() == 2
        captured = capsys.readouterr()
        public = public_json_loads(captured.out)
        assert public == {'state': 'FAILED_CLOSED_RECONCILE_EXACT_JOURNAL', 'ready': False,
            'error': error_code, 'native_migration': 'NO_ACCEPTANCE_CLAIM'}
        assert not captured.err and len(captured.out) < 256
        assert str(s.root) not in captured.out and 'SYNTHETIC_PRIVATE_CLI_CANARY' not in captured.out
        assert file_snapshot(s.root) == before and not s.output.exists()

    if failure == 'nested-json-recursion':
        # The selected CPython C decoder accepts these real 20000-level bytes.
        # Their non-object shape must still be refused without current writes.
        refused('worker_declaration_stage_request_required')
        decoder_calls = []

        def recursive_decoder(raw, **kwargs):
            decoder_calls.append(raw)
            raise RecursionError('SYNTHETIC_PRIVATE_CLI_CANARY:' + str(s.root))

        # A deterministic unit negative control at the real pinned-file decoder
        # call; do not change global recursion limits or the ordinary decoder.
        with monkeypatch.context() as decoder_patch:
            decoder_patch.setattr(declaration.json, 'loads', recursive_decoder)
            refused('worker_declaration_request_failed_closed')
        assert decoder_calls == [request_path.read_bytes()]
        assert declaration.json.loads is public_json_loads
    else:
        refused('worker_declaration_request_failed_closed')
