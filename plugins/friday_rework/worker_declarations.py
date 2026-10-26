"""Typed worker declaration proposals; no admission or deployment authority.

The caller must authenticate the source references and own the native operator
transaction.  These functions deliberately do not edit config, reseal a home,
archive a worker, run a probe, or treat a declaration as an observation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat


ROOT_A0 = ('a0_deployment',)
SETTINGS = ('plugins', 'entries', 'friday_rework', 'settings')
TEMPLATE = SETTINGS + ('onboarding', 'templates', 'friday-local')
TEMPLATE_A0 = TEMPLATE + ('config', 'a0_deployment')
TEMPLATE_INPUTS = TEMPLATE + ('worker_inputs',)
IDENTITY_FIELDS = ('platform', 'transport_profile', 'account_id', 'user_id')
CHANGE_PATHS = frozenset({('root_config', ROOT_A0),
    ('profile_config', ROOT_A0), ('root_config', TEMPLATE_A0),
    ('root_config', TEMPLATE_INPUTS)})
WORKER_INPUT_CHANGE_PATHS = (
    ('workers', 'a0', 'a0', 'deployment'),
    ('workers', 'a0', 'a0', 'launcher', 'sha256'),
    ('workers', 'a0', 'a0', 'policy'),
    ('a0_network', 'policy'),
    ('a0_network', 'endpoints'),
)
NATIVE_GAPS = (
    'reviewed_current_root_input_and_source_build_pm_inventory_required',
    'native_stopped_consumer_and_operator_admission_handoff_required',
    'exact_config_marker_lineage_and_profile_reseal_cas_required',
    'reviewed_launcher_promotion_and_all_input_pin_propagation_required',
)
MAX_SOURCE_BYTES = 32 * 1024 * 1024

# These are public source bytes, not an installed worker/service receipt.  The
# guarded-six operational predecessor has additional private history and is not
# interchangeable with this five-file public predecessor.
SERVICE_SCHEMA = 'friday.worker-web-service-source-declaration.v1'
SERVICE_FILES = frozenset({
    'scripts/a0_runtime.py', 'scripts/rootless_docker_launch.py',
    'plugins/friday_rework/adapters/a0_profile.py',
    'plugins/friday_rework/adapters/a0_web.py',
    'scripts/friday-rework-docker.service',
})
SERVICE_ANCHOR = {
    'scripts/a0_runtime.py': 'd46880a70ac70dadefb56281d21137e1aa12e1042f71e47ba455956e2477cc32',
    'scripts/rootless_docker_launch.py': 'b6825c510a7b50be20419fc0f57fee042dc9beef6d10a58b10fef1592da2fd77',
    'plugins/friday_rework/adapters/a0_profile.py': 'a0ebc0925111dfb06c99e381c20a8cea079761e9ddea8ef2ef2af7a68cc57bc9',
    'plugins/friday_rework/adapters/a0_web.py': '1daf09d50e2443d0984b26d40356478c7a3d210ccd373d92e0781ec5e78d7bf0',
    'scripts/friday-rework-docker.service': '53e6d86ff912f4ad0761362bc5e7937d2131e48892469236be09db6b49bcd0ba',
}
WEB_PROBE_RUNTIME_SHA256 = 'f02f471dc6546999e8d33d004768650ab51f3eefe5d1ab36b1ab0eee928f59b8'
WEB_PROBE_SOURCE_SHA256 = 'ba8c7a73ef8452184d1b832fc207f1d954a8efe15ac0b8ab799b5b1986a34d76'
WEB_PROBE_TARGET = dict(SERVICE_ANCHOR, **{
    'scripts/a0_runtime.py': WEB_PROBE_RUNTIME_SHA256,
    'plugins/friday_rework/adapters/a0_web.py': WEB_PROBE_SOURCE_SHA256,
})
WEB_PROBE_SERVICE_DISCRIMINATOR = 'PUBLIC_A0_WEB_OVERLAY_XMLRPC_EXACT'
WEB_HTTP_RUNTIME_SHA256 = '943b399247db9636dbf6aaf96f79ae988852f4366f3f7ef3893e77433425d11a'
WEB_HTTP_SOURCE_SHA256 = 'b16fb6681372223c4c6c04e6e7021eb53993cea56136bfe28419ac566976d5b6'
WEB_HTTP_TARGET = dict(WEB_PROBE_TARGET, **{
    'scripts/a0_runtime.py': WEB_HTTP_RUNTIME_SHA256,
    'plugins/friday_rework/adapters/a0_web.py': WEB_HTTP_SOURCE_SHA256,
})
WEB_HTTP_SERVICE_DISCRIMINATOR = 'PUBLIC_A0_WEB_HTTP_CONFIG_GIT_EXACT'
SERVICE_INPUT_PATHS = (
    ('workers', 'a0', 'a0', 'runtime', 'sha256'),
    ('workers', 'a0', 'a0', 'launcher', 'sha256'),
)


def web_probe_service_transition(old, new):
    """Recognize only the reviewed public two-file web/runtime source edge."""
    return (type(old) is dict and type(new) is dict
        and old == SERVICE_ANCHOR and new == WEB_PROBE_TARGET)


def web_http_service_transition(old, new):
    """The exact public first web tuple to its HTTP/Git repair."""
    return (type(old) is dict and type(new) is dict
        and old == WEB_PROBE_TARGET and new == WEB_HTTP_TARGET)


def service_transition_pair(discriminator):
    """Resolve only published public source edges, never installed history."""
    if discriminator == WEB_PROBE_SERVICE_DISCRIMINATOR:
        return copy.deepcopy(SERVICE_ANCHOR), copy.deepcopy(WEB_PROBE_TARGET)
    require(discriminator == WEB_HTTP_SERVICE_DISCRIMINATOR,
        'worker_declaration_exact_public_web_service_transition_required')
    return copy.deepcopy(WEB_PROBE_TARGET), copy.deepcopy(WEB_HTTP_TARGET)


def service_installed_discriminator(project):
    target = service_project_sources(project)
    if target == WEB_PROBE_TARGET:
        return WEB_PROBE_SERVICE_DISCRIMINATOR
    require(target == WEB_HTTP_TARGET,
        'worker_declaration_installed_service_target_required')
    return WEB_HTTP_SERVICE_DISCRIMINATOR


def service_source_transition(old, new):
    require(web_probe_service_transition(old, new) or web_http_service_transition(old, new),
        'worker_declaration_exact_public_web_service_transition_required')
    return ('plugins/friday_rework/adapters/a0_web.py', 'scripts/a0_runtime.py')


def service_transition_discriminator(old, new):
    service_source_transition(old, new)
    return (WEB_HTTP_SERVICE_DISCRIMINATOR if web_http_service_transition(old, new)
        else WEB_PROBE_SERVICE_DISCRIMINATOR)


def service_project_sources(project):
    require(type(project) is dict,
        'worker_declaration_service_project_inventory_required')
    return {name: project.get(name) for name in SERVICE_FILES}


def service_source_edge(previous, current, anchor, *, target=None):
    """Distinguish pending publication from unchanged source observations."""
    if target is None:
        target = WEB_HTTP_TARGET if anchor == WEB_PROBE_TARGET else WEB_PROBE_TARGET
    service_source_transition(anchor, target)
    left = service_project_sources(previous)
    right = service_project_sources(current)
    require(any(left == a and right == b for a, b in (
        (anchor, anchor), (anchor, target), (target, target))),
        'worker_declaration_exact_public_web_service_edge_changed')
    return left == anchor and right == target


def pending_service_project(previous, current):
    require(type(previous) is dict and type(current) is dict
        and type(previous.get('project_files')) is dict
        and type(current.get('project_files')) is dict,
        'worker_declaration_service_project_inventory_required')
    old = service_project_sources(previous['project_files'])
    new = service_project_sources(current['project_files'])
    if old == new:
        return None
    service_source_transition(old, new)
    require(_same({k: v for k, v in previous.items() if k != 'project_files'},
        {k: v for k, v in current.items() if k != 'project_files'}),
        'worker_declaration_service_project_operational_delta_refused')
    return copy.deepcopy(current['project_files'])


def service_pending_target(anchor, current, future):
    service_source_transition(anchor, future)
    require(type(current) is dict and current in (anchor, future),
        'worker_declaration_exact_public_web_pending_required')


def service_publication_sources(before, after, old, new, home):
    """Join both existing source mirrors; never publish or grant authority."""
    changed = service_source_transition(old, new)
    require(type(before) is dict and type(after) is dict and set(before) == set(after),
        'worker_declaration_service_publication_inventory_required')
    root = _absolute(str(home))
    for staged, ref in before.items():
        require(type(staged) is str and staged.startswith('worker-runtime-source/')
            and _reference(ref) == root / staged,
            'worker_declaration_service_publication_plan_join_changed')
        if staged not in {'worker-runtime-source/' + name for name in changed}:
            require(after[staged] == ref['sha256'],
                'worker_declaration_service_unrelated_publication_delta')
    for name in changed:
        staged = 'worker-runtime-source/' + name
        require(staged in before and _reference(before[staged]) == root / staged
            and before[staged]['sha256'] == old[name]
            and after.get(staged) == new[name],
            'worker_declaration_service_publication_plan_join_changed')


def service_worker_discriminator(after):
    runtime_after = _at(after, SERVICE_INPUT_PATHS[0])
    require(runtime_after in (WEB_PROBE_RUNTIME_SHA256, WEB_HTTP_RUNTIME_SHA256),
        'worker_declaration_exact_service_input_pin_required')
    return (WEB_HTTP_SERVICE_DISCRIMINATOR
        if runtime_after == WEB_HTTP_RUNTIME_SHA256 else WEB_PROBE_SERVICE_DISCRIMINATOR)


def service_worker_inputs(before, after, home):
    """Update the public runtime donor hash, retaining every other input."""
    require(type(before) is dict and type(after) is dict,
        'worker_declaration_service_worker_inputs_required')
    anchor, target = service_transition_pair(service_worker_discriminator(after))
    restored = copy.deepcopy(after)
    root = _absolute(str(home))
    for path, name in zip(SERVICE_INPUT_PATHS,
            ('scripts/a0_runtime.py', 'scripts/rootless_docker_launch.py')):
        require(_at(before, path) == anchor[name]
            and _at(after, path) == target[name],
            'worker_declaration_exact_service_input_pin_required')
        old_ref, new_ref = _at(before, path[:-1]), _at(after, path[:-1])
        require(_reference(old_ref) == _reference(new_ref)
            and (name != 'scripts/a0_runtime.py'
                or old_ref['path'] == str(root / 'worker-runtime-source' / name)),
            'worker_declaration_service_input_path_changed')
        _replace(restored, path, anchor[name])
    require(_same(before, restored),
        'worker_declaration_service_unrelated_worker_input_delta')


def service_installation_delta(previous, current, plan):
    """Maintain two worker mirrors only after canonical source installation.

    This writer never installs project/native code. Both installation tuples
    describe the same already-installed public target; only the separate
    declaration and the two existing worker mirrors may change.
    """
    require(type(plan) is dict, 'worker_declaration_exact_service_plan_required')
    _, target = service_transition_pair(plan.get('service_source_transition'))
    require(type(previous) is dict and type(current) is dict
        and _same(previous, current)
        and type(current.get('project_files')) is dict
        and service_project_sources(current['project_files']) == target,
        'worker_declaration_installed_service_target_required')
    require(_same(_at(current, ('product', 'runtime')), {'enabled': False}),
        'worker_declaration_runtime_must_remain_disabled')


def service_declaration_plan(root_config, profile_config, worker_inputs, identity, bundle):
    """Plan the exact public mirror edge; native custody is still required."""
    require(type(root_config) is dict and type(profile_config) is dict
        and type(worker_inputs) is dict and type(bundle) is dict,
        'worker_declaration_documents_required')
    require(bundle.get('schema') == SERVICE_SCHEMA and bundle.get('state') ==
        'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'worker_declaration_service_schema_required')
    _reference(bundle.get('identity_reference'))
    home, profile_home = _identity_join(root_config, profile_config, identity, bundle)
    require(worker_inputs.get('required') == ['dsh', 'a0']
        and type(worker_inputs.get('workers')) is dict
        and set(worker_inputs['workers']) == {'dsh', 'a0'}
        and all(type(worker_inputs['workers'][name]) is dict for name in ('dsh', 'a0'))
        and _same(worker_inputs.get('source_scope'),
            {'home': str(home), 'profile': identity['binding']['transport_profile']}),
        'worker_declaration_service_scope_changed')
    before = _at(root_config, TEMPLATE_INPUTS)
    service_worker_inputs(before, worker_inputs, home)
    discriminator = service_worker_discriminator(worker_inputs)
    deployment = _at(worker_inputs, ('workers', 'a0', 'a0', 'deployment'))
    require(type(deployment) is dict and type(deployment.get('chat')) is dict
        and type(deployment.get('utility')) is dict
        and type(deployment.get('embedding')) is dict
        and all(_same(deployment, _at(cfg, path)) for cfg, path in (
            (root_config, ROOT_A0), (profile_config, ROOT_A0),
            (root_config, TEMPLATE_A0))),
        'worker_declaration_service_deployment_must_remain_unchanged')
    rows = bundle.get('changes')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict
        and set(rows[0]) == {'document', 'path', 'before_sha256', 'after_reference'}
        and rows[0]['document'] == 'root_config'
        and rows[0]['path'] == list(TEMPLATE_INPUTS)
        and rows[0]['before_sha256'] == fingerprint(before),
        'worker_declaration_service_exact_input_change_required')
    _reference(rows[0]['after_reference'])
    result = copy.deepcopy(root_config)
    _replace(result, TEMPLATE_INPUTS, worker_inputs)
    return {'schema': 'friday.worker-declaration-delta.v1',
        'state': 'SOURCE_DECLARATION_DELTA_ONLY_NOT_NATIVE_AUTHORITY',
        'ready': False, 'native_authority': False,
        'native_apply_implemented': True, 'workers_enabled': False,
        'service_source_transition': discriminator,
        'root_config': result, 'profile_config': copy.deepcopy(profile_config),
        'semantic_changes': [{'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
            'before_sha256': fingerprint(before), 'after_sha256': fingerprint(worker_inputs)}],
        'principal': identity['principal'], 'generation': identity['generation'],
        'profile': str(profile_home),
        'launcher': {'reference': copy.deepcopy(_at(worker_inputs,
            ('workers', 'a0', 'a0', 'launcher'))),
            'state': 'UNCHANGED_PUBLIC_LAUNCHER_SOURCE_ONLY', 'installed': False},
        'missing_native_prerequisites': list(NATIVE_GAPS)}


class DeclarationError(ValueError):
    """Bounded public code; never interpolate a path or private document."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise DeclarationError(code)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _typed(value):
    """Canonical JSON equality distinguishes bool/int and absent/null."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False)


def _same(left, right):
    return _typed(left) == _typed(right)


def _at(value, path):
    for part in path:
        require(type(value) is dict and part in value,
            'worker_declaration_path_missing')
        value = value[part]
    return value


def _replace(value, path, replacement):
    parent = _at(value, path[:-1])
    require(type(parent) is dict and path[-1] in parent,
        'worker_declaration_path_missing')
    parent[path[-1]] = copy.deepcopy(replacement)


def _absolute(value):
    require(type(value) is str and value.startswith('/')
        and not any(ord(char) < 32 for char in value),
        'worker_declaration_absolute_path_required')
    path = Path(value)
    require(str(path) == value and '..' not in path.parts,
        'worker_declaration_canonical_path_required')
    return path


def _reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'},
        'worker_declaration_exact_reference_required')
    path = _absolute(value['path'])
    sha = value['sha256']
    require(type(sha) is str and len(sha) == 64
        and all(c in '0123456789abcdef' for c in sha) and sha != '0' * 64,
        'worker_declaration_exact_digest_required')
    return path


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'worker_declaration_duplicate_json_key')
        result[key] = value
    return result


def _read_reference(ref, *, json_document=True):
    """Read a pinned owned private regular file, retaining exact fd identity.

    Open each directory without following links. Native mutation locks remain
    the caller's responsibility; an unchanged hash alone grants no authority.
    """
    path = _reference(ref)
    # Reject a FIFO/device at fstat instead of blocking in open beforehand.
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    parent_fd = os.open('/', flags | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
            and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_size <= MAX_SOURCE_BYTES,
            'worker_declaration_private_source_required')
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_SOURCE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            require(size <= MAX_SOURCE_BYTES, 'worker_declaration_source_too_large')
        after = os.fstat(fd)
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
            s.st_ctime_ns, s.st_mode, s.st_uid, s.st_nlink)
        require(identity(before) == identity(after) == identity(current),
            'worker_declaration_source_changed')
        raw = b''.join(chunks)
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'],
            'worker_declaration_source_digest_changed')
        if not json_document:
            return raw
        return json.loads(raw, object_pairs_hook=_no_duplicates,
            parse_constant=lambda _: (_ for _ in ()).throw(
                DeclarationError('worker_declaration_nonfinite_json')))
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def _identity_join(root_config, profile_config, identity, bundle):
    require(type(identity) is dict and identity.get('schema') ==
        'frw.current-dest-worker-identity.v1', 'worker_declaration_identity_schema')
    binding = identity.get('binding')
    require(type(binding) is dict and all(type(binding.get(k)) is str
        and binding[k] and len(binding[k].encode()) <= 512
        and binding[k].strip() == binding[k]
        and not any(ord(char) < 32 for char in binding[k]) for k in IDENTITY_FIELDS)
        and all(type(binding.get(k)) is str and re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', binding[k])
            for k in ('runtime_profile', 'transport_profile')),
        'worker_declaration_identity_invalid')
    principal = hashlib.sha256(json.dumps([binding[k] for k in IDENTITY_FIELDS],
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    require(identity.get('principal') == principal
        and identity.get('binding_sha256') == fingerprint(binding),
        'worker_declaration_identity_fingerprint_changed')
    require(type(identity.get('generation')) is int and identity['generation'] > 0
        and identity.get('enabled') is True,
        'worker_declaration_current_generation_required')
    require(identity.get('profile_template') == 'friday-ordinary-local'
        and identity.get('worker_attach_template') == 'friday-local',
        'worker_declaration_template_identity_changed')
    profile_home = _absolute(identity.get('profile'))
    require(profile_home.name == binding['runtime_profile']
        and profile_home.parent.name == 'profiles',
        'worker_declaration_profile_identity_changed')
    home = profile_home.parent.parent
    rows = _at(root_config, SETTINGS + ('user_isolation', 'bindings'))
    require(type(rows) is list, 'worker_declaration_bindings_required')
    matches = [row for row in rows if type(row) is dict
        and row.get('runtime_profile') == binding['runtime_profile']]
    require(len(matches) == 1 and _same(matches[0], binding),
        'worker_declaration_current_binding_changed')
    for document in (root_config, profile_config):
        settings = _at(document, SETTINGS)
        require(type(settings) is dict and _same(settings.get('runtime'), {'enabled': False})
            and 'worker_requirements' not in settings,
            'worker_declaration_ordinary_profile_required')
    refs = identity.get('source_refs')
    require(type(refs) is dict and set(refs) == {'access_state', 'configuration',
        'onboarding', 'root_configuration', 'stale_attachment', 'user_marker'},
        'worker_declaration_identity_sources_required')
    paths = {name: _reference(ref) for name, ref in refs.items()}
    expected = {'configuration': profile_home / 'config.yaml',
        'root_configuration': home / 'config.yaml',
        'onboarding': profile_home / '.friday-onboarding.json',
        'user_marker': profile_home / '.friday-user-scope.json',
        'stale_attachment': profile_home / 'workers' / 'attachment.json'}
    require(all(paths[name] == path for name, path in expected.items())
        and paths['access_state'].name == 'state.json'
        and paths['access_state'].parent.parent == home / 'plugin-data',
        'worker_declaration_identity_source_path_changed')
    require(_same(refs['root_configuration'], bundle.get('root_before'))
        and _same(refs['configuration'], bundle.get('profile_before')),
        'worker_declaration_current_raw_cas_changed')
    return home, profile_home


def _deployment_join(root_config, profile_config, deployment):
    """Join A0 chat to both current native main declarations, keeping auxiliaries.

    An authenticated proposal still cannot choose a different model/capacity
    merely because its four container subtrees were explicitly named.
    """
    chat_fields = {'endpoint', 'model', 'context_length', 'max_output_tokens'}
    require(type(deployment) is dict and type(deployment.get('chat')) is dict,
        'worker_declaration_deployment_required')
    after_chat = deployment['chat']
    for document in (root_config, profile_config):
        model = _at(document, ('model',))
        require(type(model) is dict and type(model.get('default')) is str
            and type(model.get('base_url')) is str,
            'worker_declaration_current_main_metadata_required')
        capacity = _at(document, ('providers', 'friday-local', 'models', model['default']))
        require(type(capacity) is dict and type(capacity.get('context_length')) is int
            and capacity['context_length'] > 0
            and type(capacity.get('bounded_context')) is dict
            and type(capacity['bounded_context'].get('main_max_output_tokens')) is int
            and 0 < capacity['bounded_context']['main_max_output_tokens'] <=
                capacity['context_length'],
            'worker_declaration_current_main_capacity_required')
        expected = {'endpoint': model['base_url'], 'model': model['default'],
            'context_length': capacity['context_length'],
            'max_output_tokens': capacity['bounded_context']['main_max_output_tokens']}
        require(all(field in after_chat and _same(after_chat[field], value)
            for field, value in expected.items()),
            'worker_declaration_current_main_join_changed')
    for before in (_at(root_config, ROOT_A0), _at(profile_config, ROOT_A0),
            _at(root_config, TEMPLATE_A0)):
        require(type(before) is dict and type(before.get('chat')) is dict
            and all(field in before and field in deployment
                and _same(before[field], deployment[field]) for field in ('utility', 'embedding')),
            'worker_declaration_auxiliary_deployment_changed')
        # Preserve timeout and all unrequested chat/deployment metadata. The
        # declared descriptive name and the four current-main leaves may move.
        require('timeout' in before['chat'] and 'timeout' in after_chat
            and _same(before['chat']['timeout'], after_chat['timeout'])
            and _same({k: v for k, v in before['chat'].items() if k not in chat_fields},
                {k: v for k, v in after_chat.items() if k not in chat_fields})
            and _same({k: v for k, v in before.items() if k not in ('name', 'chat')},
                {k: v for k, v in deployment.items() if k not in ('name', 'chat')}),
            'worker_declaration_deployment_metadata_changed')


def _worker_inputs_join(root_config, worker_inputs, deployment):
    """Retain every resource budget/native pin outside five reviewed leaves."""
    before = _at(root_config, TEMPLATE_INPUTS)
    require(type(before) is dict, 'worker_declaration_current_worker_inputs_required')
    _reference(_at(before, ('workers', 'a0', 'a0', 'launcher')))
    policy = _at(worker_inputs, ('workers', 'a0', 'a0', 'policy'))
    network_policy = _at(worker_inputs, ('a0_network', 'policy'))
    _reference(policy)
    _reference(network_policy)
    require(_same(policy, network_policy), 'worker_declaration_network_policy_join_changed')
    endpoints = []
    for role in ('chat', 'utility', 'embedding'):
        value = deployment[role].get('endpoint')
        require(type(value) is str and value,
            'worker_declaration_deployment_endpoint_required')
        if value not in endpoints:
            endpoints.append(value)
    require(_same(_at(worker_inputs, ('a0_network', 'endpoints')), endpoints),
        'worker_declaration_network_endpoints_join_changed')
    restored = copy.deepcopy(worker_inputs)
    for path in WORKER_INPUT_CHANGE_PATHS:
        # Both sides must actually contain each admitted leaf. No implicit
        # defaults or guessed native declarations may enter the proposal.
        _at(restored, path)
        _replace(restored, path, _at(before, path))
    require(_same(before, restored), 'worker_declaration_unrelated_worker_input_delta')


def plan_declaration_delta(root_config, profile_config, worker_inputs, identity, bundle):
    """Return exactly four typed CAS replacements on current document copies.

    This pure function checks a static identity join, not native pairing,
    current_access, a signed operator session, or current source installation.
    Authenticate all input pins in the owning native transaction before use.
    """
    require(type(root_config) is dict and type(profile_config) is dict
        and type(worker_inputs) is dict and type(bundle) is dict,
        'worker_declaration_documents_required')
    if bundle.get('schema') == SERVICE_SCHEMA:
        return service_declaration_plan(root_config, profile_config, worker_inputs, identity, bundle)
    require(bundle.get('schema') == 'frw.current-both-spark-declaration-change-data.v1'
        and bundle.get('state') ==
            'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'worker_declaration_bundle_schema')
    _reference(bundle.get('identity_reference'))
    home, profile_home = _identity_join(root_config, profile_config, identity, bundle)
    require(worker_inputs.get('required') == ['dsh', 'a0']
        and type(worker_inputs.get('workers')) is dict
        and set(worker_inputs['workers']) == {'dsh', 'a0'}
        and _same(worker_inputs.get('source_scope'), {'home': str(home),
            'profile': identity['binding']['transport_profile']}),
        'worker_declaration_worker_input_scope_changed')
    try:
        deployment = worker_inputs['workers']['a0']['a0']['deployment']
        launcher = worker_inputs['workers']['a0']['a0']['launcher']
    except (KeyError, TypeError):
        raise DeclarationError('worker_declaration_a0_inputs_required') from None
    _reference(launcher)
    require(type(deployment) is dict and type(deployment.get('chat')) is dict
        and type(deployment.get('utility')) is dict
        and type(deployment.get('embedding')) is dict,
        'worker_declaration_deployment_required')
    _deployment_join(root_config, profile_config, deployment)
    _worker_inputs_join(root_config, worker_inputs, deployment)
    changes = bundle.get('changes')
    require(type(changes) is list and len(changes) == 4,
        'worker_declaration_exact_four_changes_required')
    indexed = {}
    for row in changes:
        require(type(row) is dict and type(row.get('document')) is str
            and type(row.get('path')) is list
            and all(type(part) is str for part in row['path']),
            'worker_declaration_change_shape_invalid')
        key = (row['document'], tuple(row['path']))
        require(key in CHANGE_PATHS and key not in indexed,
            'worker_declaration_change_path_forbidden')
        indexed[key] = row
    require(set(indexed) == CHANGE_PATHS, 'worker_declaration_exact_four_changes_required')
    documents = {'root_config': copy.deepcopy(root_config),
        'profile_config': copy.deepcopy(profile_config)}
    semantic = []
    for document, path in sorted(CHANGE_PATHS):
        row = indexed[(document, path)]
        before = _at(documents[document], path)
        if path == TEMPLATE_INPUTS:
            require(set(row) == {'document', 'path', 'before_sha256', 'after_reference'}
                and row['before_sha256'] == fingerprint(before),
                'worker_declaration_worker_inputs_cas_changed')
            _reference(row['after_reference'])
            after = worker_inputs
        else:
            require(set(row) == {'document', 'path', 'before', 'after'}
                and _same(before, row['before']), 'worker_declaration_beforeimage_changed')
            require(_same(row['after'], deployment),
                'worker_declaration_deployment_join_changed')
            after = row['after']
        require(not _same(before, after), 'worker_declaration_noop_not_four_changes')
        _replace(documents[document], path, after)
        semantic.append({'document': document, 'path': list(path),
            'before_sha256': fingerprint(before), 'after_sha256': fingerprint(after)})
    # Prove the complement, including dynamic identity collections and all
    # browser/web/compressor/model settings, with type-sensitive equality.
    for name, original in (('root_config', root_config), ('profile_config', profile_config)):
        restored = copy.deepcopy(documents[name])
        for document, path in CHANGE_PATHS:
            if document == name:
                _replace(restored, path, _at(original, path))
        require(_same(original, restored), 'worker_declaration_unrelated_delta')
    return {'schema': 'friday.worker-declaration-delta.v1',
        'state': 'SOURCE_DECLARATION_DELTA_ONLY_NOT_NATIVE_AUTHORITY',
        'ready': False, 'native_authority': False, 'native_apply_implemented': True,
        'workers_enabled': False,
        'root_config': documents['root_config'], 'profile_config': documents['profile_config'],
        'semantic_changes': semantic, 'principal': identity['principal'],
        'generation': identity['generation'], 'profile': str(profile_home),
        'launcher': {'reference': copy.deepcopy(launcher),
            'state': 'ALREADY_PROMOTED_LAUNCHER_REQUIRED_AT_NATIVE_APPLY', 'installed': False},
        'missing_native_prerequisites': list(NATIVE_GAPS)}


def load_declaration_source(companion):
    """Read exact private JSON pins; no public request supplies callbacks."""
    require(type(companion) is dict and set(companion) == {'bundle', 'worker_inputs', 'identity'},
        'worker_declaration_exact_source_companion_required')
    bundle = _read_reference(companion['bundle'])
    identity = _read_reference(companion['identity'])
    inputs = _read_reference(companion['worker_inputs'])
    require(_same(bundle.get('identity_reference'), companion['identity']),
        'worker_declaration_identity_reference_changed')
    rows = bundle.get('changes')
    require(type(rows) is list, 'worker_declaration_change_shape_invalid')
    refs = [row.get('after_reference') for row in rows if type(row) is dict
        and row.get('document') == 'root_config' and row.get('path') == list(TEMPLATE_INPUTS)]
    require(len(refs) == 1 and _same(refs[0], companion['worker_inputs']),
        'worker_declaration_inputs_reference_changed')
    return bundle, inputs, identity


def validate_declaration_source(companion, root_config, profile_config, *, root_home, profile_home):
    """Authenticated Onboarding companion preflight; return redacted proof only.

    The caller owns the signed session, native current_access/generation/proof
    checks and config/admission locks. This function grants none of them. The
    stale attachment is a historical member: its returned digest must match
    the archive engine's exact before-tree inventory. The engine retains that
    custody across rename; this function never guesses a replacement path.
    """
    bundle, inputs, identity = load_declaration_source(companion)
    plan = plan_declaration_delta(root_config, profile_config, inputs, identity, bundle)
    require(Path(root_home) == Path(identity['profile']).parent.parent
        and Path(profile_home) == Path(identity['profile']),
        'worker_declaration_native_home_changed')
    for name, ref in identity['source_refs'].items():
        if name != 'stale_attachment':
            _read_reference(ref, json_document=False)
    return {'schema': 'friday.worker-declaration-source-join.v1',
        'state': plan['state'], 'status': 'SOURCE_JOIN_ONLY_NOT_NATIVE_AUTHORITY',
        'ready': False, 'native_authority': False,
        'native_apply_implemented': plan['native_apply_implemented'],
        'binding_sha256': identity['binding_sha256'],
        'generation': identity['generation'], 'principal': identity['principal'],
        'stale_attachment_sha256': identity['source_refs']['stale_attachment']['sha256'],
        'bundle_sha256': companion['bundle']['sha256'],
        # Semantic JSON fingerprints, never native YAML/raw configuration pins.
        'candidate_root_sha256': fingerprint(plan['root_config']),
        'candidate_profile_sha256': fingerprint(plan['profile_config']),
        'candidate_digest_kind': 'semantic-canonical-json-not-native-yaml-raw',
        'source': copy.deepcopy(companion),
        'semantic_changes': copy.deepcopy(plan['semantic_changes']),
        'delta_sha256': fingerprint(plan['semantic_changes']),
        'launcher_state': plan['launcher']['state'],
        'native_migration': 'NOT_INVOKED',
        'missing_native_prerequisites': list(NATIVE_GAPS)}
