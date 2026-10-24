"""Operator-only orchestration over native profiles, config, secrets and grants.

Preparation is never admission. The native user marker is published only after
all setup and the native grant are verified; uncertain writes are not replayed.
"""
from contextlib import contextmanager
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from hermes_cli.friday_product_access import current_access, principal_id, profile_name
from hermes_cli import friday_user_scope as scope
from .access import ProductAccess
from .associations import Associations, _sync_directory

RESOURCE = Path(__file__).parent
SOUL_SHA256 = 'b00cf7a17bb5c0e8b9bb4df66992f9cdd854f148ccdaed3be2ffff403aaf9311'
IDENTITY = ('platform', 'transport_profile', 'account_id', 'user_id')
WORKER_ATTACHMENT = 'workers/attachment.json'

# One API-request context; never captures a request body, session or identity.
from contextvars import ContextVar
_PREPARE_DIAGNOSTIC = ContextVar('friday_prepare_diagnostic', default=None)
_PREPARE_PHASES = frozenset(('dispatch', 'identity', 'transaction', 'template',
    'source_history', 'prepared_home', 'derive_inputs', 'validate_inputs',
    'publish_attachment', 'publish_profile', 'publish_inputs', 'publish_receipt',
    'worker_dsh', 'worker_a0', 'state', 'complete'))


def _prepare_phase(phase):
    if phase not in _PREPARE_PHASES:
        raise ValueError('invalid_prepare_diagnostic_phase')
    current = _PREPARE_DIAGNOSTIC.get()
    if current is not None:
        current['phase'] = phase


def _write_prepare_diagnostic(root, value):
    """Latest observation only, atomically replaced in the private launch home.

    Neither a caller-selected profile nor an exception can choose the destination.
    Refuse links, shared permissions and nonregular existing targets. Diagnostic
    failure is best effort and must never change the original action outcome.
    """
    import stat
    import secrets
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root:
        raise PermissionError('unsafe_prepare_diagnostic_parent')
    temporary = '.friday-worker-prepare-' + secrets.token_hex(16)
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = 'friday-worker-prepare-diagnostic.json'
    created = False
    try:
        st = os.fstat(parent)
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
            raise PermissionError('unsafe_prepare_diagnostic_parent')
        try:
            old = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None and (not stat.S_ISREG(old.st_mode) or old.st_uid != os.getuid()
                or stat.S_IMODE(old.st_mode) != 0o600 or old.st_nlink != 1):
            raise PermissionError('unsafe_prepare_diagnostic_file')
        data = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
        if len(data) > 4096:
            raise ValueError('prepare_diagnostic_too_large')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=parent)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        created = False
        os.fsync(parent)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=parent)
        finally:
            os.close(parent)


@contextmanager
def prepare_diagnostic(root, action):
    """Protected fixed metadata around one authenticated prepare API call."""
    import secrets
    import time
    if action not in ('onboarding_prepare', 'worker_prepare', 'workers_prepare'):
        raise ValueError('invalid_prepare_diagnostic_action')
    try:
        current = {'schema': 'friday.worker-prepare-diagnostic.v1',
            'request_id': secrets.token_hex(16), 'action': action, 'phase': 'dispatch',
            'accepted_unix': time.time()}
        token = _PREPARE_DIAGNOSTIC.set(current)
    except Exception:
        # A diagnostic setup failure must not suppress the requested operation.
        yield
        return
    def record(state, exc=None):
        try:
            value = dict(current, state=state)
            if exc is not None:
                from .user_worker_join import _failure_location
                value.update(_failure_location(exc))
            _write_prepare_diagnostic(root, value)
        except Exception:
            pass
    try:
        record('STARTED')
        try:
            yield
        except BaseException as exc:
            record('FAILED_OR_CANCELLED', exc)
            raise
        else:
            _prepare_phase('complete')
            record('RETURNED')
    finally:
        _PREPARE_DIAGNOSTIC.reset(token)



def digest(path):
    scope._private(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local(url):
    try:
        if not isinstance(url, str) or url != url.strip() or any(ord(c) < 32 or ord(c) == 127 for c in url):
            raise ValueError
        p = urlsplit(url)
        address = ipaddress.ip_address(p.hostname or '')
        nets = [ipaddress.ip_network(n) for n in
                ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128')]
        if (p.scheme not in ('http', 'https') or not p.port or p.username or p.password
                or p.query or p.fragment or p.path != '/v1'
                or not any(address.version == n.version and address in n for n in nets)):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('explicit_local_inference_required') from None
    return url.rstrip('/')


def validate_template(template):
    """Installation-owned normal profile, never a copied owner config."""
    if not isinstance(template, dict) or set(template) not in ({'config', 'tools', 'required_secrets'}, {'config', 'tools', 'required_secrets', 'worker_inputs'}):
        raise ValueError('invalid_onboarding_template')
    if 'worker_inputs' in template:
        from .user_worker_join import validate_installation_inputs
        validate_installation_inputs(template['worker_inputs'])
    config = copy.deepcopy(template['config'])
    tools, names = template['tools'], template['required_secrets']
    if (not isinstance(config, dict) or not isinstance(tools, list) or not tools
            or any(not isinstance(k, str) for k in tools)
            or len(set(tools)) != len(tools) or not set(tools) <= scope.SAFE | scope.BROWSER_TOOLS
            or not {'web_search', 'web_extract', 'friday_work', 'friday_result'} <= set(tools)
            or not isinstance(names, list) or not names
            or any(not isinstance(k, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,127}', k) for k in names)
            or len(set(names)) != len(names)):
        raise ValueError('incomplete_onboarding_template')
    from hermes_cli.config import DEFAULT_CONFIG, validate_env_var_name_for_write
    from gateway.config import PLATFORM_TOKEN_ENV_NAMES
    for name in names:
        validate_env_var_name_for_write(name)
    model = config.get('model')
    if not isinstance(model, dict):
        raise ValueError('explicit_local_inference_required')
    provider, selected = model.get('provider'), model.get('default')
    url = _local(model.get('base_url'))
    if (provider != 'custom:friday-local' or not isinstance(selected, str)
            or not selected or selected != selected.strip() or selected.lower() == 'auto'
            or '${' in selected or any(ord(c) < 32 or ord(c) == 127 for c in selected)
            or model.get('api_mode') != 'chat_completions' or model.get('openai_runtime')
            or type(config.get('fallback_providers')) is not list or config['fallback_providers'] != []
            or type(config.get('fallback_model')) is not dict or config['fallback_model'] != {}):
        raise ValueError('explicit_local_inference_required')
    key = model.get('key_env')
    if (not isinstance(key, str) or key not in names or key == 'EXA_API_KEY'
            or key in PLATFORM_TOKEN_ENV_NAMES.values() or key.startswith('HERMES_DASHBOARD_')):
        raise ValueError('explicit_scoped_provider_required')
    auth = config.get('auth')
    if not isinstance(auth, dict) or auth.get('adopt_external_logins') is not False:
        raise ValueError('explicit_scoped_provider_required')
    providers = config.get('providers', {})
    if not isinstance(providers, dict) or set(providers) not in (
            {'friday-local'}, {'friday-local', 'friday-compression'}):
        raise ValueError('explicit_scoped_provider_required')
    def checked_entry(name, expected_model, expected_url, expected_key):
        entry = providers[name]
        if (not isinstance(entry, dict) or _local(entry.get('api')) != expected_url
                or entry.get('key_env') != expected_key or entry.get('default_model') != expected_model
                or entry.get('transport') != 'chat_completions'
                or entry.get('discover_models') is not False or entry.get('enabled', True) is not True
                or entry.get('name', name) != name
                or not isinstance(entry.get('models'), dict) or set(entry['models']) != {expected_model}
                or not isinstance(entry['models'][expected_model], dict)):
            raise ValueError('explicit_scoped_provider_required')
        return entry
    entry = checked_entry('friday-local', selected, url, key)
    main_route = (provider, selected, url, key)
    compression_route = None
    if 'friday-compression' in providers:
        comp = providers['friday-compression']
        if not isinstance(comp, dict):
            raise ValueError('explicit_scoped_compressor_required')
        comp_model, comp_key = comp.get('default_model'), comp.get('key_env')
        if (not isinstance(comp_model, str) or not comp_model or comp_model != comp_model.strip()
                or comp_model.lower() == 'auto' or '${' in comp_model
                or any(ord(c) < 32 or ord(c) == 127 for c in comp_model)
                or not isinstance(comp_key, str) or comp_key not in names or comp_key == key
                or comp_key == 'EXA_API_KEY' or comp_key in PLATFORM_TOKEN_ENV_NAMES.values()
                or comp_key.startswith('HERMES_DASHBOARD_')):
            raise ValueError('explicit_scoped_compressor_required')
        comp_url = _local(comp.get('api'))
        checked_entry('friday-compression', comp_model, comp_url, comp_key)
        compression_route = ('custom:friday-compression', comp_model, comp_url, comp_key)
    if config.get('custom_providers', []) != []:
        raise ValueError('explicit_scoped_provider_required')
    # Native route aliases and request mergers must not replace the installation
    # route or obtain a different credential. Capacity/reasoning fields remain
    # native inputs; this is validation, not an inference implementation.
    route_fields = {'model', 'provider', 'base_url', 'url', 'api', 'api_key', 'api_key_env',
                    'key_env', 'key_cmd', 'api_mode', 'authorization', 'host', 'headers',
                    'default_headers', 'extra_headers', 'extra_query', 'fallback_chain',
                    'fallback_model', 'fallback_providers'}
    user_headers = {'accept', 'accept-language', 'user-agent', 'x-request-id',
                    'x-correlation-id', 'traceparent', 'tracestate'}
    def extensions(block, expected=main_route):
        expected_provider, expected_model, expected_url, expected_key = expected
        if 'api_key' in block or 'key_cmd' in block:
            raise ValueError('inline_credentials_refused')
        if 'key_env' in block and block['key_env'] != expected_key:
            raise ValueError('explicit_scoped_provider_required')
        if 'api_key_env' in block and block['api_key_env'] != expected_key:
            raise ValueError('explicit_scoped_provider_required')
        for field in ('base_url', 'url', 'api'):
            if field in block and _local(block[field]) != expected_url:
                raise ValueError('inference_route_override_refused')
        for field, value in (('model', expected_model), ('default_model', expected_model),
                                ('provider', expected_provider), ('api_mode', 'chat_completions'),
                                ('transport', 'chat_completions')):
            if field in block and block[field] != value:
                raise ValueError('inference_route_override_refused')
        for field in ('default_headers', 'extra_headers'):
            if field in block:
                value = block[field]
                if (not isinstance(value, dict) or any(not isinstance(k, str) or k.lower() not in user_headers
                        or not isinstance(v, str) or '\r' in v or '\n' in v for k, v in value.items())):
                    raise ValueError('inference_route_override_refused')
        if 'extra_body' in block:
            value = block['extra_body']
            if not isinstance(value, dict) or any(not isinstance(k, str) or k.lower() in route_fields for k in value):
                raise ValueError('inference_route_override_refused')
        if 'request_overrides' in block:
            value = block['request_overrides']
            if not isinstance(value, dict) or any(not isinstance(k, str) or k.lower() in route_fields - {'extra_headers'} for k in value):
                raise ValueError('inference_route_override_refused')
            extensions(value, expected)
        for field, empty in (('fallback_chain', []), ('fallback_providers', []), ('fallback_model', {})):
            if field in block and (type(block[field]) is not type(empty) or block[field] != empty):
                raise ValueError('explicit_local_inference_required')
    extensions(model)
    extensions(entry)
    extensions(entry['models'][selected])
    if compression_route is not None:
        extensions(comp, compression_route)
        extensions(comp['models'][comp_model], compression_route)
    def same_route(block, reason, fallback, expected=main_route):
        expected_provider, expected_model, expected_url, expected_key = expected
        if (not isinstance(block, dict) or block.get('provider') != expected_provider
                or block.get('model') != expected_model or not isinstance(block.get('base_url'), str)
                or _local(block['base_url']) != expected_url or block.get('key_env') != expected_key
                or block.get('api_mode') != 'chat_completions'
                or type(block.get(fallback)) is not list or block[fallback] != []
                or ('enabled' in block and type(block['enabled']) is not bool)):
            raise ValueError(reason)
        extensions(block, expected)
    auxiliary = config.get('auxiliary')
    required_aux = {name for name, value in DEFAULT_CONFIG['auxiliary'].items()
                    if isinstance(value, dict) and 'provider' in value}
    if (not isinstance(auxiliary, dict) or not required_aux <= set(auxiliary)
            or type(auxiliary.get('transient_retries')) is not int or auxiliary['transient_retries'] < 0):
        raise ValueError('auxiliary_local_route_required')
    for name, route in auxiliary.items():
        if name != 'transient_retries':
            expected = compression_route if name == 'compression' and compression_route is not None else main_route
            same_route(route, 'auxiliary_local_route_required', 'fallback_chain', expected)
    delegation = config.get('delegation')
    if not isinstance(delegation, dict):
        raise ValueError('delegation_local_route_required')
    same_route(delegation, 'delegation_local_route_required', 'fallback_providers')
    web = config.get('web', {})
    if (web.get('backend') != 'exa' or web.get('search_backend') != 'exa'
            or web.get('extract_backend') != 'exa' or web.get('keyless_rescue') is not False
            or type(web.get('keyless_fallback')) is not bool
            or web.get('provider_tier',{}).get('exa') != ('free' if web['keyless_fallback'] else 'paid')
            or ('EXA_API_KEY' in names) is web['keyless_fallback']):
        raise ValueError('explicit_useful_scoped_web_required')
    plugins = config.get('plugins', {})
    if not {'friday_rework', 'web/exa'} <= set(plugins.get('enabled', [])):
        raise ValueError('required_native_plugins_missing')
    settings = plugins.get('entries', {}).get('friday_rework', {}).get('settings', {})
    if set(settings) - {'runtime', 'results', 'worker_requirements'} or any(k in config for k in ('gateway', 'secrets', 'mcp_servers')):
        raise ValueError('ordinary_profile_cannot_import_authority')
    if 'worker_requirements' in settings and settings['worker_requirements']!=['dsh','a0']:
        raise ValueError('both_normal_workers_required')
    if (config.get('memory', {}).get('memory_enabled') is not True
            or config.get('memory', {}).get('user_profile_enabled') is not True
            or config.get('agent', {}).get('environment_hint') != (RESOURCE / 'RESEARCH.md').read_text().strip()
            or config.get('display', {}).get('personality')
            or config.get('agent', {}).get('system_prompt')):
        raise ValueError('explicit_private_context_and_friday_persona_required')
    if compression_route is not None:
        display = config.get('display', {})
        if (not isinstance(display, dict) or display.get('show_reasoning') is not False
                or not isinstance(display.get('platforms'), dict)
                or not isinstance(display['platforms'].get('telegram'), dict)
                or display['platforms']['telegram'].get('show_reasoning') is not False):
            raise ValueError('private_protocol_reasoning_must_remain_hidden')
    if 'a0_deployment' in config:
        from .adapters.a0_profile import checked_profile
        checked_profile(config['a0_deployment'])
    runtime = settings.get('runtime')
    if runtime != {'enabled': False}:
        from .host_runtime import configured_runtimes
        configured_runtimes(runtime)
    friday = plugins['entries']['friday_rework']
    if (settings.get('results') != {'enabled': True}
            or friday.get('allow_gateway_work') is not True
            or friday.get('allow_gateway_control') is not True
            or not {'web', 'friday_rework'} <= set(config.get('toolsets', []))):
        raise ValueError('useful_native_worker_result_hooks_required')
    scope.validate_browser_config(config, tools)
    # Config is nonsecret, including recursively nested plugin/provider fields.
    # Native normal profiles carry these token *counts*, not credentials. Keep
    # the exception path-specific and numeric so arbitrary "token" fields,
    # nested plugin credentials and string/callable interpolation still refuse.
    native_counts = {
        ('compression', 'proactive_prune_tokens'),
        ('compression', 'proactive_prune_min_reclaim_tokens'),
        ('compression', 'micro_compact_defrag_threshold_tokens'),
        ('delegation', 'compression_threshold_tokens'),
        ('tools', 'tool_search', 'listing_max_tokens'),
        ('a0_deployment', 'chat', 'max_output_tokens'),
        ('a0_deployment', 'utility', 'max_output_tokens'),
    }
    for prefix in (
        ('plugins','entries','friday_rework','settings','runtime','a0','deployment'),
        ('plugins','entries','friday_rework','settings','runtime','workers','a0','a0','deployment'),
    ):
        native_counts.update(prefix+(slot,'max_output_tokens') for slot in ('chat','utility'))
    def nonsecret(value, path=()):
        if isinstance(value, dict):
            for k, v in value.items():
                count = path + (k,) in native_counts and type(v) is int and v >= 0
                if not count and re.search(r'password|secret|token|credential|api[_-]?key', str(k), re.I) and k not in (
                        'key_env', 'api_key_env', 'context_length', 'threshold_tokens', 'server_max_input_tokens',
                        'main_max_output_tokens', 'compression_max_output_tokens', 'safety_margin_tokens',
                        'template_overhead_tokens', 'max_tokens'):
                    raise ValueError('inline_credentials_refused')
                nonsecret(v, path + (k,))
        elif isinstance(value, list):
            for v in value: nonsecret(v, path + ('[]',))
        elif isinstance(value, str) and ('${' in value or 'Bearer ' in value):
            raise ValueError('ambient_templates_or_credentials_refused')
    nonsecret(config)
    return config, list(tools), list(names)


def _new_file(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(value); f.flush(); os.fsync(f.fileno())
    _sync_directory(path.parent)


def _cli_admission(root, binding):
    """Read the frozen local helper's exact map; never infer a local grant.

    Native private-file ownership currently supports the process's own UID
    only. Foreign UID provisioning needs a separate owner-file contract.
    """
    from hermes_cli.friday_cli_principal import cli_policy, numeric_os_uid
    from hermes_cli.friday_product_access import access_policy
    key = principal_id(*(binding[k] for k in IDENTITY))
    rows = [r for r in cli_policy(root)['principals'] if
            principal_id('cli', r['transport_profile'], r['account_id'], r['user_id']) == key]
    if len(rows) != 1 or rows[0]['uid'] != numeric_os_uid():
        raise PermissionError('explicit_local_cli_owner_mapping_required')
    with scope.authority(root):
        accounts = access_policy()['accounts']
    matches = [a for a in accounts if tuple(a[k] for k in IDENTITY[:3]) ==
               tuple(binding[k] for k in IDENTITY[:3]) and binding['runtime_profile'] in a['runtime_profiles']]
    if len(matches) != 1:
        raise PermissionError('foreign_product_account')
    return rows[0]


def _prepare_cli_admission(root, settings, transport_profile, account_id, user_id, uid):
    from hermes_cli.friday_cli_principal import cli_policy, numeric_os_uid
    from hermes_constants import get_default_hermes_root
    # The frozen helper resolves authority from the runtime profile's native
    # default root. A named gateway authorization home cannot stand in for it.
    if transport_profile != 'default' or root != get_default_hermes_root(home=root):
        raise PermissionError('native_cli_default_authorization_home_required')
    if type(uid) is not int or uid < 0:
        raise ValueError('explicit_numeric_cli_uid_required')
    if uid != numeric_os_uid():
        raise PermissionError('foreign_cli_uid_owner_contract_unsupported')
    previous = settings.get('cli_admission')
    rows = [] if previous is None else copy.deepcopy(cli_policy(root)['principals'])
    key = principal_id('cli', transport_profile, account_id, user_id)
    if len(rows) >= 10000 or any(r['uid'] == uid or
            principal_id('cli', r['transport_profile'], r['account_id'], r['user_id']) == key for r in rows):
        raise ValueError('existing_or_ambiguous_cli_mapping_not_adopted')
    row = dict(uid=uid, transport_profile=transport_profile, account_id=account_id, user_id=user_id)
    return {'enabled': True, 'principals': [*rows, row]}, row


def _inactive_worker_tree(folder):
    """Exact private tree through retained directory FDs; no followed links."""
    import stat
    files = {}; directories = {}
    identity = lambda i: [i.st_dev, i.st_ino, i.st_uid, i.st_mode, i.st_nlink,
        i.st_size, i.st_mtime_ns, i.st_ctime_ns]
    def walk(fd, prefix):
        info = os.fstat(fd)
        if (info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise PermissionError('worker_successor_private_tree_required')
        directories[prefix or '.'] = identity(info)[:5]
        for leaf in os.listdir(fd):
            name = prefix + '/' + leaf if prefix else leaf
            before = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(before.st_mode)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory: flags |= os.O_DIRECTORY
            child = os.open(leaf, flags, dir_fd=fd)
            try:
                if identity(os.fstat(child)) != identity(before):
                    raise PermissionError('worker_successor_tree_changed')
                if directory:
                    walk(child, name)
                else:
                    if (before.st_uid != os.getuid() or not stat.S_ISREG(before.st_mode)
                            or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                            or before.st_size > 32 * 1024 * 1024):
                        raise PermissionError('worker_successor_private_tree_required')
                    sha = hashlib.sha256(); size = 0
                    while True:
                        data = os.read(child, 1024 * 1024)
                        if not data: break
                        size += len(data)
                        if size > 32 * 1024 * 1024:
                            raise PermissionError('worker_successor_private_tree_required')
                        sha.update(data)
                    files[name] = {'sha256': sha.hexdigest(), 'identity': identity(before)}
                if identity(os.fstat(child)) != identity(before) or identity(os.stat(
                        leaf, dir_fd=fd, follow_symlinks=False)) != identity(before):
                    raise PermissionError('worker_successor_tree_changed')
            finally: os.close(child)
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        original = identity(os.fstat(fd))
        walk(fd, '')
        if identity(folder.lstat()) != original:
            raise PermissionError('worker_successor_tree_changed')
    finally: os.close(fd)
    return {'files': files, 'directories': directories}


def _worker_successor_location(root, home, binding, generation, checked):
    from .worker_declarations import _read_reference
    identity = _read_reference(checked['receipt']['source']['identity'])
    if (identity.get('binding') != binding or identity.get('generation') != generation
            or identity.get('profile') != str(home)):
        raise PermissionError('worker_successor_current_identity_required')
    old = identity['source_refs']['stale_attachment']
    key = scope._fingerprint({'attachment': old, 'current_input': checked['receipt']['current_input'],
        'binding': binding, 'generation': generation})
    parent = root / 'preparation'; scope._private(parent, directory=True)
    return parent / ('ordinary-worker-preparation-' + key), old


def _replace_inactive_worker_inputs(root, home, binding, generation, checked, declaration, plans,
                                     *, budget, verify):
    """Existing protected prepare action: archive only authenticated inactive inputs.

    One consumed intent precedes rename. Partial/unknown effects require inspection;
    neither this helper nor a later HTTP call reopens any qualification or clock.
    """
    from .worker_provision import pin, preparation
    from .worker_declarations import _read_reference
    tx, old_ref = _worker_successor_location(root, home, binding, generation, checked)
    if tx.exists() or tx.is_symlink():
        raise PermissionError('worker_successor_consumed_requires_inspection')
    folder = home / 'workers'
    if (declaration['generation'] != generation
            or declaration['binding_sha256'] != scope._fingerprint(binding)):
        raise PermissionError('worker_successor_original_owner_or_limits_changed')
    budget.check(); verify()
    if old_ref['path'] != str(folder / 'attachment.json'):
        raise PermissionError('worker_successor_authenticated_attachment_required')
    old = _read_reference(old_ref)
    fields = {'template', 'template_sha256', 'installation_config_sha256', 'config_sha256',
        'proof', 'marker', 'binding_sha256', 'generation', 'runtimes', 'a0_network', 'required_names'}
    if (set(old) != fields or old['binding_sha256'] != scope._fingerprint(binding)
            or old['generation'] != generation or set(old['runtimes']) != {'dsh', 'a0'}
            or old['template'] != declaration['template']
            or any(old[k].get('path') != str(home / name) or not re.fullmatch('[0-9a-f]{64}', old[k].get('sha256', ''))
                for k, name in (('proof', scope.ONBOARDING), ('marker', scope.MARKER)))
            or old['installation_config_sha256'] == declaration['installation_config_sha256']):
        raise PermissionError('worker_successor_stale_preparation_required')
    names = {'attachment.json'}
    directories = {'.'}
    for kind in ('dsh', 'a0'):
        path = folder / kind / 'runtime-input.json'
        ref = checked['request']['retained'].get(str(path.relative_to(root)))
        if ref is None or ref['path'] != str(path):
            raise PermissionError('worker_successor_exact_unobserved_tree_required')
        secure = _read_reference(ref)
        prepared, runtime = preparation(home, binding['runtime_profile'], kind, ref)
        if prepared != secure:
            raise PermissionError('worker_successor_tree_changed')
        if (prepared.get('attachment') != old_ref or runtime != old['runtimes'][kind]
                or prepared['generation'] != generation
                or prepared['principal_binding_sha256'] != scope._fingerprint(binding)
                or any(runtime[k] != declaration['runtimes'][kind][k]
                    for k in ('budget_seconds', 'max_file_bytes', 'max_total_bytes'))):
            raise PermissionError('worker_successor_original_owner_or_limits_changed')
        if kind == 'dsh' and any(runtime['dsh'][k] != declaration['runtimes'][kind]['dsh'][k]
                for k in ('memory_bytes', 'cpu_percent', 'tasks', 'shutdown_seconds', 'tmp_bytes')):
            raise PermissionError('worker_successor_original_resources_changed')
        names.add(kind + '/runtime-input.json')
        directories.update(kind + '/' + n for n in ('jobs', 'staging', 'cache', 'inputs'))
        directories.add(kind)
        for ref in prepared['inputs']:
            relative = str(Path(ref['path']).relative_to(folder))
            names.add(relative)
            directories.update(str(p) for p in Path(relative).parents)
    before = _inactive_worker_tree(folder)
    # Every old file is already retained by the authenticated maintenance request.
    # Unlisted activity/receipts/qualification/bootstrap/probes/current are refused.
    retained = checked['request']['retained']
    if (set(before['files']) != names or set(before['directories']) != directories
            or any(retained.get(str((folder / n).relative_to(root))) !=
                {'path': str(folder / n), 'sha256': row['sha256']} for n, row in before['files'].items())):
        raise PermissionError('worker_successor_exact_unobserved_tree_required')
    verify(); budget.check()
    if _inactive_worker_tree(folder) != before:
        raise PermissionError('worker_successor_tree_changed')
    verify(); budget.check()
    tx.mkdir(mode=0o700)
    _new_file(tx / 'intent.json', (json.dumps({'state': 'CONSUMED_NO_RETRY',
        'attachment': old_ref, 'maintenance': checked['receipt']['current_input'],
        'binding_sha256': scope._fingerprint(binding), 'generation': generation,
        'clock': {'started_mono': budget.started, 'deadline_mono': budget.deadline, 'seconds': budget.seconds},
        'old_tree': before, 'archive_mapping': {str(folder): str(tx / 'workers')},
        'workers_enabled': False, 'qualification_started': False}, sort_keys=True) + '\n').encode())
    _sync_directory(tx); _sync_directory(tx.parent)
    verify(); budget.check()
    if _inactive_worker_tree(folder) != before:
        raise PermissionError('worker_successor_tree_changed')
    budget.check()
    os.rename(folder, tx / 'workers'); _sync_directory(home); _sync_directory(tx)
    if _inactive_worker_tree(tx / 'workers') != before:
        raise PermissionError('worker_successor_archive_changed')
    verify(); budget.check(); folder.mkdir(mode=0o700)
    _new_file(home / WORKER_ATTACHMENT, (json.dumps(declaration, sort_keys=True) + '\n').encode())
    attachment = pin(home / WORKER_ATTACHMENT)
    for kind, (runtime, directory, files, names, unobserved) in plans.items():
        verify(); budget.check(); directory.mkdir(mode=0o700)
        for name in ('jobs', 'staging', 'cache', 'inputs'):
            budget.check(); (directory / name).mkdir(mode=0o700)
        for path, data in files.items():
            verify(); budget.check(); _new_file(path, data)
        candidate = dict(runtime=runtime, inputs=[pin(p) for p in files],
            principal_binding_sha256=scope._fingerprint(binding), generation=generation,
            state='PREPARED_RUNTIME_UNOBSERVED', unobserved=unobserved, attachment=attachment)
        verify(); budget.check()
        _new_file(directory / 'runtime-input.json', (json.dumps(candidate, sort_keys=True, indent=2) + '\n').encode())
    verify(); budget.check()
    for kind in ('dsh', 'a0'):
        prepared, runtime = preparation(home, binding['runtime_profile'], kind, pin(folder / kind / 'runtime-input.json'))
        if runtime != declaration['runtimes'][kind] or prepared.get('attachment') != attachment:
            raise PermissionError('worker_successor_publication_changed')
    if _inactive_worker_tree(tx / 'workers') != before:
        raise PermissionError('worker_successor_archive_changed')
    verify(); budget.check()
    _new_file(tx / 'committed.json', (json.dumps({'state': 'INACTIVE_PREPARATION_SUCCESSOR_COMMITTED',
        'attachment': attachment, 'archive': str(tx / 'workers'),
        'workers_enabled': False, 'qualification_started': False, 'resume_allowed': False}, sort_keys=True) + '\n').encode())
    _sync_directory(folder); _sync_directory(tx)
    budget.check()
    return tx


def current_main_config(config, required_secrets):
    """Pure exact current-main selection shared by producer and provenance join."""
    from .adapters.a0_config import KEY_REFERENCES
    from .adapters.a0_profile import checked_profile
    candidate = copy.deepcopy(config)
    deployment = checked_profile(candidate.get('a0_deployment'))
    main = candidate['model']; provider = candidate['providers']['friday-local']
    if (main.get('provider') != 'custom:friday-local'
            or main.get('key_env') != KEY_REFERENCES['API_KEY_OPENAI']
            or provider.get('key_env') != KEY_REFERENCES['API_KEY_OPENAI']
            or not set(KEY_REFERENCES.values()) <= set(required_secrets)):
        raise PermissionError('a0_scoped_profile_key_mismatch')
    capacity = provider['models'][main['default']]
    for role in ('chat', 'utility'):
        deployment[role].update(endpoint=main['base_url'], model=main['default'],
            context_length=capacity['context_length'],
            max_output_tokens=capacity['bounded_context']['main_max_output_tokens'])
    if deployment['name'] == 'legacy-local-test': deployment['name'] = 'current-main'
    candidate['a0_deployment'] = checked_profile(deployment)
    return candidate


class Onboarding:
    def __init__(self, administration, *, storage_readonly=True):
        if type(storage_readonly) is not bool:
            raise ValueError('invalid_onboarding_storage_mode')
        self._storage_readonly = storage_readonly
        self.admin = administration

    def _verify_operator(self, profile, session):
        # Retained ordinary authority cannot be promoted by changing the home,
        # even when a caller supplies a valid operator Session. Check the native
        # context before _verify_session enters the launch authority home. An
        # engaged process with no current user still permits its dashboard.
        if scope._CURRENT.get() is not None:
            raise PermissionError('operator_source_scope_required')
        self.admin._verify_session(profile, session)

    @staticmethod
    def _native_grant(root, binding, *, storage_readonly=True):
        if type(storage_readonly) is not bool:
            raise ValueError('invalid_onboarding_storage_mode')
        if binding['platform'] == 'cli':
            _cli_admission(root, binding)
            return True  # Explicit operator map; product enable remains separate.
        from gateway.pairing import PairingStore
        if storage_readonly:
            return PairingStore.is_approved_storage_readonly(binding['platform'], binding['user_id'])
        # Explicit mutation-authorized source-update phase uses the genuine
        # currently imported native API; publishing files does not reload it.
        return PairingStore().is_approved(binding['platform'], binding['user_id'])

    @contextmanager
    def transaction(self, profile, expected_config_sha256, session=None):
        """Same protected native association and process config mutation locks.

        Product-admin generic config writers are denied by the native middleware.
        Supported onboarding/user writers share this admission lock; external
        operator edits still require the explicit file CAS on the next action.
        """
        self._verify_operator(profile, session)
        from hermes_cli import config as native
        with self.admin.scope(profile) as root:
            scope._private(root, directory=True)
            from hermes_constants import get_routing_process_hermes_home
            if root != get_routing_process_hermes_home():
                raise PermissionError('primary_multiplex_route_authority_required')
            ProductAccess.require_transport(profile)
            state = self.admin._state(); access = ProductAccess(state); store = access.store
            with store._locked(), native.config_write_transaction(root / 'config.yaml'):
                self._verify_operator(profile, session)
                path = root / 'config.yaml'
                if digest(path) != expected_config_sha256:
                    raise ValueError('onboarding_config_conflict_reload')
                raw = native.require_readable_config_before_write(path)
                yield root, access, raw

    def templates(self, profile):
        with self.admin.scope(profile) as root:
            self.admin.users(profile)
            from hermes_cli.friday_product_access import settings
            plans = settings().get('onboarding', {}).get('templates', {})
            if not isinstance(plans, dict): raise ValueError('invalid_onboarding_templates')
            pending = self.pending(root, profile)
            return {'config_sha256': digest(root / 'config.yaml'), 'templates': sorted(plans), 'pending': pending,
                    'worker_templates': sorted(k for k,v in plans.items() if v.get('worker_inputs',{}).get('workers')),
                    'state': 'INSTALLATION_INPUT_MISSING' if not plans else 'EXPLICIT_NATIVE_TEMPLATES',
                    'credentials': 'NEW_PROFILE_NATIVE_SECRET_CAPTURE_ONLY'}

    def pending(self, root, profile):
        """Read existing bindings/PluginState/preparation proofs, never a new DB."""
        active = scope.policy(root)
        if active is None: return []
        from hermes_constants import get_default_hermes_root
        state = self.admin._state(); users = current_access(state)['users']; result = []
        for binding in active['bindings']:
            if binding['transport_profile'] != profile: continue
            key = principal_id(*(binding[k] for k in IDENTITY)); user = users.get(key)
            if not user: continue
            home = get_default_hermes_root(home=root) / 'profiles' / binding['runtime_profile']
            if not (home / scope.ONBOARDING).exists():
                result.append({'principal_id': key, 'runtime_profile': binding['runtime_profile'],
                               'state': 'PARTIAL_OR_EXISTING_PROFILE_NO_ADOPTION', 'recoverable': False})
                continue
            try:
                _, _, _, proof = self._prepared(root, state, *(binding[k] for k in IDENTITY), user['generation'])
            except (PermissionError, ValueError, OSError, KeyError):
                result.append({'principal_id': key, 'runtime_profile': binding['runtime_profile'],
                               'state': 'SETUP_CHANGED_RECONCILIATION_REQUIRED', 'recoverable': False})
                continue
            result.append({**{k: binding[k] for k in IDENTITY}, 'runtime_profile': binding['runtime_profile'],
                'principal_id': key, 'template': proof['template'], 'generation': user['generation'],
                'required_names': proof['required_secrets'], 'enabled': user['enabled'],
                'state': 'ADMITTED_WORKER_SETUP_AVAILABLE' if user['enabled'] else 'DISABLED_SETUP_PENDING',
                'recoverable': True, 'config_sha256': digest(root / 'config.yaml'),
                'target_config_sha256': proof['config_sha256'],
                'binding_sha256': proof['binding_sha256'],
                'browser_execution': scope.browser_admission_error(binding['tools']),
                'can_configure_browser': not user['enabled'] and not (home / scope.MARKER).exists()
                    and not (home / 'workers').exists() and not (set(binding['tools']) & scope.BROWSER_TOOLS)})
            if binding['platform'] == 'cli': result[-1]['uid'] = _cli_admission(root, binding)['uid']
            from hermes_cli.config import require_readable_config_before_write
            result[-1].update(self._worker_summary(home,binding,user['generation'],proof,
                require_readable_config_before_write(root / 'config.yaml')))
        return result

    def prepare(self, profile, *, session=None, expected_config_sha256, template, platform,
                transport_profile, account_id, user_id, runtime_profile, uid=None):
        _prepare_phase('identity')
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        key = principal_id(platform, transport_profile, account_id, user_id)
        profile_name(runtime_profile)
        if runtime_profile == 'default': raise ValueError('exclusive_new_profile_required')
        _prepare_phase('transaction')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            state = access.state
            settings = config['plugins']['entries']['friday_rework']['settings']
            plans = settings.get('onboarding', {}).get('templates', {})
            _prepare_phase('template')
            native_config, tools, names = validate_template(plans[template])
            if not {'web', 'friday_rework'} <= set(native_config.get('platform_toolsets', {}).get(platform, [])):
                raise ValueError('receiving_surface_toolsets_required')
            if current_access(state)['users'].get(key) is not None:
                raise ValueError('existing_principal_not_adopted')
            accounts = settings['product_access']['accounts']
            matches = [a for a in accounts if tuple(a[k] for k in IDENTITY[:3]) ==
                       (platform, transport_profile, account_id)]
            if len(matches) != 1: raise ValueError('foreign_product_account')
            cli_policy, cli_row = None, None
            if platform == 'cli':
                cli_policy, cli_row = _prepare_cli_admission(root, settings, transport_profile, account_id, user_id, uid)
            elif uid is not None:
                raise ValueError('cli_uid_only_for_local_transport')
            from hermes_constants import get_default_hermes_root
            home = get_default_hermes_root(home=root) / 'profiles' / runtime_profile
            if home.exists() or home.is_symlink(): raise ValueError('existing_home_not_adopted')
            if home.parent.exists(): scope._private(home.parent, directory=True)
            if home.parent.resolve() != home.parent: raise PermissionError('unsafe_profile_parent')
            runtime = native_config['plugins']['entries']['friday_rework']['settings']['runtime']
            from .host_runtime import configured_runtimes
            if any(r['runtime_home'] != str(home) or r['runtime_profile'] != runtime_profile
                   for r in configured_runtimes(runtime).values()):
                raise ValueError('foreign_worker_runtime_template')
            binding = dict(platform=platform, transport_profile=transport_profile, account_id=account_id,
                           user_id=user_id, runtime_profile=runtime_profile, tools=tools)
            isolation = settings.setdefault('user_isolation', {'enabled': True, 'bindings': []})
            if isolation['enabled'] is not True or any(b['runtime_profile'] == runtime_profile or
                    principal_id(*(b[k] for k in IDENTITY)) == key for b in isolation['bindings']):
                raise ValueError('existing_binding_not_adopted')
            if platform != 'cli':
                gateway = config.setdefault('gateway', {})
                if gateway.get('multiplex_profiles') is not True:
                    raise ValueError('native_multiplex_installation_required')
                routes = gateway.setdefault('profile_routes', [])
                if any(r.get('platform') == platform and (r.get('bot_profile') or 'default') == profile
                       and r.get('user_id') == user_id for r in routes):
                    raise ValueError('conflicting_native_route')
            elif any(r.get('platform') == 'cli' for r in config.get('gateway', {}).get('profile_routes', [])):
                raise ValueError('cli_cannot_use_gateway_messaging_routes')
            _prepare_phase('publish_profile')
            # Disabled tombstone is persisted FIRST, before any route/home setup.
            self._verify_operator(profile, session)
            user = access._write_user_locked(key, dict(platform=platform, transport_profile=profile,
                account_id=account_id, user_id=user_id, enabled=False, role='user'))
            isolation['bindings'].append(binding)
            matches[0]['runtime_profiles'].append(runtime_profile)
            settings['admin']['profiles'].append(runtime_profile)
            if platform == 'cli': settings['cli_admission'] = cli_policy
            else: routes.append(dict(name='friday-' + key, platform=platform, bot_profile=profile,
                                    user_id=user_id, profile=runtime_profile, enabled=True))
            from hermes_cli.config import atomic_config_write
            if digest(root / 'config.yaml') != expected_config_sha256:
                raise ValueError('onboarding_config_conflict_reload')
            self._verify_operator(profile, session)
            atomic_config_write(root / 'config.yaml', config)
            # Never publish the user capability marker for incomplete setup.
            self._verify_operator(profile, session)
            scope.provision_new_home(root, binding, {}, publish=False,
                verify=lambda: self._verify_operator(profile, session))
            if runtime.get('enabled') is True:
                for field in ('workspace_root', 'staging_root'):
                    directory = Path(runtime[field])
                    if not directory.is_relative_to(home) or directory.resolve() != directory:
                        raise PermissionError('worker_setup_directory_outside_private_home')
                    self._verify_operator(profile, session)
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Explicit per-profile settings, no owner/ambient secrets or history.
            from hermes_cli.config import config_write_transaction
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                native_config['terminal'] = {'cwd': str(home / 'workspace')}
                if 'worker_inputs' in plans[template]:
                    native_config['plugins']['entries']['friday_rework']['settings']['worker_requirements']=['dsh','a0']
                atomic_config_write(home / 'config.yaml', native_config)
            soul = (RESOURCE / 'SOUL.md').read_bytes()
            if hashlib.sha256(soul).hexdigest() != SOUL_SHA256: raise ValueError('reviewed_friday_soul_changed')
            self._verify_operator(profile, session)
            _new_file(home / 'SOUL.md', soul)
            st = scope._private(home, directory=True)
            _prepare_phase('publish_receipt')
            receipt = dict(schema='friday.onboarding.v1', binding_sha256=scope._fingerprint(binding),
                config_sha256=digest(home / 'config.yaml'), soul_sha256=digest(home / 'SOUL.md'),
                required_secrets=names, directory_identity=[st.st_dev, st.st_ino], template=template,
                authorization_home=str(root))
            if cli_row is not None: receipt['cli_admission_sha256'] = scope._fingerprint(cli_row)
            self._verify_operator(profile, session)
            _new_file(home / scope.ONBOARDING, (json.dumps(receipt, sort_keys=True) + '\n').encode())
            return dict(state='DISABLED_INCOMPLETE', enabled=False, principal_id=key,
                        runtime_profile=runtime_profile, generation=user['generation'],
                        config_sha256=digest(root / 'config.yaml'), required_names=names,
                        target_config_sha256=digest(home / 'config.yaml'),
                        binding_sha256=scope._fingerprint(binding),
                        can_configure_browser=not bool(set(tools) & scope.BROWSER_TOOLS),
                        browser_execution=scope.browser_admission_error(tools),
                        admission='NATIVE_GRANT_AND_COMPLETE_SETUP_REQUIRED',
                        **({'uid': cli_row['uid'], 'local_authority': 'EXPLICIT_OPERATOR_MAPPING_PRODUCT_DISABLED'} if cli_row is not None else {}),
                        **self._worker_summary(home,binding,user['generation'],receipt,config))

    def _prepared(self, root, state, platform, transport_profile, account_id, user_id, generation):
        from hermes_cli.friday_product_access import settings
        key = principal_id(platform, transport_profile, account_id, user_id)
        row = current_access(state)['users'].get(key)
        if not row or row['generation'] != generation or row['role'] != 'user':
            raise ValueError('onboarding_access_generation_conflict')
        bindings = settings()['user_isolation']['bindings']
        matches = [b for b in bindings if principal_id(*(b[k] for k in IDENTITY)) == key]
        if not matches: raise ValueError('onboarding_binding_missing')
        if len(matches) != 1: raise ValueError('onboarding_binding_ambiguous')
        binding = matches[0]
        from hermes_constants import get_default_hermes_root
        home = get_default_hermes_root(home=root) / 'profiles' / binding['runtime_profile']
        st = scope._private(home, directory=True)
        scope._private(home / scope.ONBOARDING)
        proof = json.loads((home / scope.ONBOARDING).read_text())
        if (proof['binding_sha256'] != scope._fingerprint(binding) or proof['authorization_home'] != str(root)
                or proof['directory_identity'] != [st.st_dev, st.st_ino]
                or proof['config_sha256'] != digest(home / 'config.yaml')
                or proof['soul_sha256'] != digest(home / 'SOUL.md')):
            raise PermissionError('prepared_home_changed')
        if platform == 'cli' and proof.get('cli_admission_sha256') != scope._fingerprint(_cli_admission(root, binding)):
            raise PermissionError('prepared_cli_admission_changed')
        return home, binding, row, proof

    def configure_a0_main(self, profile, *, session=None, expected_config_sha256,
                          expected_target_config_sha256, expected_binding_sha256,
                          generation, platform, transport_profile, account_id, user_id,
                          selection):
        """Select the already configured primary for both inactive native roles.

        No route, model, credential, capacity or runtime input is accepted from
        the caller. Existing prepared/attempted workers require reconciliation.
        """
        if transport_profile != profile:
            raise PermissionError('receiving_transport_authority_required')
        if selection != 'current-main':
            raise ValueError('explicit_current_main_selection_required')
        from hermes_cli.config import config_write_transaction, atomic_config_write
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            home, binding, row, proof = self._prepared(root, access.state,
                platform, transport_profile, account_id, user_id, generation)
            with config_write_transaction(home / 'config.yaml'):
                def verify():
                    self._verify_operator(profile, session)
                    if (digest(root / 'config.yaml') != expected_config_sha256
                            or digest(home / 'config.yaml') != expected_target_config_sha256
                            or proof['binding_sha256'] != expected_binding_sha256):
                        raise ValueError('a0_declaration_config_conflict_reload')
                    workers = home / 'workers'
                    if workers.exists() or workers.is_symlink():
                        raise PermissionError('a0_existing_worker_custody_reconciliation_required')
                    self._admitted_worker_home(root, home, binding, generation, proof)
                verify()
                candidate = self._admitted_worker_home(root, home, binding, generation, proof)
                candidate = current_main_config(candidate, proof['required_secrets'])
                with scope.authority(home):
                    prepared = prepare_admin_config_edit(home, candidate)
                if prepared is None:
                    raise PermissionError('managed_setup_receipt_missing')
                verify()
                with scope.authority(home):
                    atomic_config_write(home / 'config.yaml', candidate)
                self._verify_operator(profile, session)
                finish_admin_config_edit(home, prepared)
                return {'state': 'INACTIVE_A0_CURRENT_MAIN_DECLARED', 'enabled': row['enabled'],
                    'generation': generation, 'runtime_profile': binding['runtime_profile'],
                    'config_sha256': digest(root / 'config.yaml'),
                    'target_config_sha256': digest(home / 'config.yaml'),
                    'binding_sha256': proof['binding_sha256'],
                    'required_names': proof['required_secrets'],
                    'worker_execution': 'NOT_PREPARED', 'observed_live_reload': False}

    def configure_browser(self, profile, *, session=None, expected_config_sha256,
                          expected_target_config_sha256, expected_binding_sha256,
                          generation, platform, transport_profile, account_id, user_id,
                          preset):
        """Prepare the named local family in the original disabled home.

        The existing root admission/config lock and target config lock cover all
        writes. No identity, generation, secret, history, worker or job changes.
        Interrupted multi-file commits retain a disabled, mismatched proof and
        require reconciliation; they are never silently adopted or replayed.
        """
        if transport_profile != profile:
            raise PermissionError('receiving_transport_authority_required')
        if preset != 'local-headless-basic':
            raise ValueError('explicit_browser_preset_required')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            from hermes_cli.config import (config_write_transaction,
                require_readable_config_before_write, atomic_config_write)
            home, binding, row, proof = self._prepared(root, access.state,
                platform, transport_profile, account_id, user_id, generation)
            with config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                home, binding, row, proof = self._prepared(root, access.state,
                    platform, transport_profile, account_id, user_id, generation)
                if row['enabled']:
                    raise PermissionError('disabled_prepared_browser_setup_required')
                if ((home / scope.MARKER).exists() or (home / scope.MARKER).is_symlink()
                        or (home / 'workers').exists() or (home / 'workers').is_symlink()):
                    raise PermissionError('browser_existing_custody_reconciliation_required')
                if (proof['config_sha256'] != expected_target_config_sha256
                        or proof['binding_sha256'] != expected_binding_sha256):
                    raise ValueError('browser_config_conflict_reload')
                with scope.authority(home):
                    candidate = require_readable_config_before_write(home / 'config.yaml')
                if set(binding['tools']) & scope.BROWSER_TOOLS or 'browser' in candidate:
                    raise ValueError('browser_already_configured_reload')
                tools = sorted(set(binding['tools']) | scope.BROWSER_TOOLS)
                candidate['browser'] = copy.deepcopy(scope.BROWSER_LOCAL_CONFIG)
                selected = candidate.setdefault('toolsets', [])
                if 'browser' in selected:
                    raise ValueError('broad_browser_toolset_refused')
                if scope.BROWSER_TOOLSET not in selected:
                    selected.append(scope.BROWSER_TOOLSET)
                platforms = candidate.setdefault('platform_toolsets', {})
                receiving = platforms.setdefault(platform, list(selected))
                if scope.BROWSER_TOOLSET not in receiving:
                    receiving.append(scope.BROWSER_TOOLSET)
                scope.validate_browser_config(candidate, tools, platform)
                validate_template({'config': candidate, 'tools': tools,
                                   'required_secrets': proof['required_secrets']})
                updated = dict(binding, tools=tools)
                bindings = config['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings']
                matches = [i for i, item in enumerate(bindings) if item == binding]
                if len(matches) != 1:
                    raise PermissionError('browser_binding_changed')
                prepared = {'proof': dict(proof, binding_sha256=scope._fingerprint(updated)),
                    'receipt_sha256': digest(home / scope.ONBOARDING),
                    'marker': None, 'marker_sha256': None}
                bindings[matches[0]] = updated
                if digest(root / 'config.yaml') != expected_config_sha256:
                    raise ValueError('onboarding_config_conflict_reload')
                self._verify_operator(profile, session)
                atomic_config_write(root / 'config.yaml', config)
                self._verify_operator(profile, session)
                with scope.authority(home):
                    atomic_config_write(home / 'config.yaml', candidate)
                self._verify_operator(profile, session)
                finish_admin_config_edit(home, prepared)
                return {'state': 'DISABLED_BROWSER_PREPARED_CUSTODY_REQUIRED',
                    'enabled': False, 'generation': generation,
                    'runtime_profile': binding['runtime_profile'],
                    'config_sha256': digest(root / 'config.yaml'),
                    'target_config_sha256': digest(home / 'config.yaml'),
                    'binding_sha256': scope._fingerprint(updated),
                    'browser_preset': preset, 'browser_tools': sorted(scope.BROWSER_TOOLS),
                    'browser_execution': scope.browser_admission_error(tools),
                    'can_configure_browser': False}

    def credentials(self, profile, *, session=None, expected_config_sha256, generation, platform,
                    transport_profile, account_id, user_id, name, value):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            state = access.state
            home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
            def staged_credential_names():
                from .worker_provision import preparation, pin
                attachment=self._worker_attachment(root,home,binding,generation,proof,config)
                for kind in ('dsh','a0'):
                    prepared,c=preparation(home,binding['runtime_profile'],kind,
                        pin(home / 'workers' / kind / 'runtime-input.json'))
                    if (prepared.get('attachment')!=pin(home / WORKER_ATTACHMENT)
                            or prepared['generation']!=generation
                            or prepared['principal_binding_sha256']!=scope._fingerprint(binding)
                            or c!=attachment['runtimes'][kind]):
                        raise PermissionError('worker_credential_preparation_changed')
                return attachment['required_names']
            if row['enabled']:
                from agent.secret_scope import load_env_file
                if name not in staged_credential_names() or load_env_file(home / '.env').get(name):
                    raise PermissionError('only_missing_staged_worker_credential_capture_allowed')
            elif (home / scope.MARKER).exists() or name not in proof['required_secrets']:
                raise PermissionError('pending_scoped_credential_capture_required')
            if not isinstance(value, str) or not value.strip() or len(value) > 8192:
                raise ValueError('invalid_scoped_credential')
            path = home / '.env'
            if path.exists() or path.is_symlink(): scope._private(path)
            from hermes_cli.config import save_env_value_secure, config_write_transaction, _env_write_lock
            from agent.secret_scope import load_env_file, set_secret_scope, reset_secret_scope, get_secret
            with config_write_transaction(home / 'config.yaml'), _env_write_lock(path):
                self._verify_operator(profile, session)
                self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
                if row['enabled'] and (name not in staged_credential_names() or load_env_file(path).get(name)):
                    raise PermissionError('only_missing_staged_worker_credential_capture_allowed')
                with scope.authority(home):
                    # Empty local scope prevents the native lifecycle from borrowing
                    # the process's current provider credential during capture.
                    token = set_secret_scope(load_env_file(path), profile_home=str(home))
                    try:
                        self._verify_operator(profile, session)
                        save_env_value_secure(name, value)
                    finally: reset_secret_scope(token)
                    scope._private(path)
                    local = load_env_file(path)
                    token = set_secret_scope(local, profile_home=str(home))
                    try:
                        if get_secret(name) != value: raise RuntimeError('scoped_secret_write_unconfirmed')
                    finally: reset_secret_scope(token)
            return {'state': 'ADMITTED_WORKER_SETUP_PENDING' if row['enabled'] else 'DISABLED_SETUP_PENDING',
                'recorded': True, 'enabled': row['enabled'],
                **self._worker_summary(home,binding,generation,proof,config)}

    def prepare_worker(self, profile, *, session=None, expected_config_sha256, generation, platform,
                       transport_profile, account_id, user_id, worker, runtime, a0_network=None, _declared_files=None,
                       _attachment=None, _history_walk=None):
        """Operator-only source/config preparation for one disabled own profile.

        Exactly one fresh worker input tree, no adoption/retry of partial writes.
        Original budget/limits and reviewed source references are caller inputs.
        """
        _prepare_phase('identity')
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        from .worker_provision import prepare_inputs, pin
        _prepare_phase('transaction')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, root_config):
            _prepare_phase('prepared_home')
            home, binding, row, proof = self._prepared(root, access.state, platform, transport_profile, account_id, user_id, generation)
            if row['enabled']:
                if _attachment is None:
                    raise PermissionError('explicit_reviewed_worker_attachment_required')
                attachment=self._worker_attachment(root,home,binding,generation,proof,root_config)
                if _attachment!=pin(home / WORKER_ATTACHMENT) or runtime!=attachment['runtimes'].get(worker):
                    raise PermissionError('explicit_reviewed_worker_attachment_required')
                if a0_network!=(attachment['a0_network'] if worker=='a0' else None):
                    raise PermissionError('worker_attachment_network_changed')
            elif (home / scope.MARKER).exists() or _attachment is not None:
                raise PermissionError('disabled_fresh_worker_setup_required')
            from hermes_cli.config import require_readable_config_before_write, config_write_transaction
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                if digest(home / 'config.yaml') != proof['config_sha256']:
                    raise PermissionError('prepared_home_changed')
                config = require_readable_config_before_write(home / 'config.yaml')
                current_main = (self._current_main_source_target(root, home, binding, generation, proof)
                    if row['enabled'] and worker == 'a0' else None)
                from .host_runtime import configured_runtimes
                if worker in configured_runtimes(config['plugins']['entries']['friday_rework']['settings']['runtime']):
                    raise PermissionError('existing_worker_not_adopted')
                _prepare_phase('validate_inputs')
                c, directory, files, names, unobserved = prepare_inputs(home, binding['runtime_profile'], worker, runtime, config,
                    a0_network=a0_network, declared_files=_declared_files, tools=binding['tools'],
                    _history_walk=_history_walk, _current_main=current_main)
                if directory.exists() or directory.is_symlink():
                    raise FileExistsError('existing_worker_preparation_not_adopted')
                _prepare_phase('publish_inputs')
                self._verify_operator(profile, session)
                parent = directory.parent
                if parent.exists(): scope._private(parent, directory=True)
                else: parent.mkdir(mode=0o700)
                directory.mkdir(mode=0o700)
                for name in ('jobs', 'staging', 'cache', 'inputs'):
                    (directory / name).mkdir(mode=0o700)
                for path, data in files.items():
                    self._verify_operator(profile, session)
                    _new_file(path, data)
                candidate = dict(runtime=c, inputs=[pin(p) for p in files],
                    principal_binding_sha256=scope._fingerprint(binding), generation=generation,
                    state='PREPARED_RUNTIME_UNOBSERVED', unobserved=unobserved)
                if row['enabled']: candidate['attachment']=_attachment
                path = directory / 'runtime-input.json'
                self._verify_operator(profile, session)
                _new_file(path, (json.dumps(candidate, sort_keys=True, indent=2) + '\n').encode())
                # Same existing protected scoped credential capture, no key copy.
                # No new receipt/schema or activation marker is produced.
                updated = dict(proof, required_secrets=list(dict.fromkeys(proof['required_secrets'] + names)))
                if row['enabled']:
                    # Staging must leave the admitted ordinary receipt/marker
                    # byte-identical; worker names enter admission only at commit.
                    return {'state':'PREPARED_RUNTIME_UNOBSERVED','enabled':True,
                        'worker':worker,'preparation':pin(path),'runtime':c,
                        'required_names':attachment['required_names'],'unobserved':unobserved}
                _prepare_phase('publish_receipt')
                previous_sha = digest(home / scope.ONBOARDING)
                if json.loads((home / scope.ONBOARDING).read_text()) != proof:
                    raise PermissionError('prepared_home_changed')
                import secrets
                temporary = home / (scope.ONBOARDING + '.worker-' + secrets.token_hex(8))
                try:
                    self._verify_operator(profile, session)
                    _new_file(temporary, (json.dumps(updated, sort_keys=True) + '\n').encode())
                    if digest(home / scope.ONBOARDING) != previous_sha:
                        raise PermissionError('prepared_home_changed')
                    self._verify_operator(profile, session)
                    os.replace(temporary, home / scope.ONBOARDING); _sync_directory(home)
                finally:
                    if temporary.exists(): temporary.unlink()
            return {'state': 'PREPARED_RUNTIME_UNOBSERVED', 'enabled': False,
                    'worker': worker, 'preparation': pin(path), 'runtime': c,
                    'required_names': updated['required_secrets'], 'unobserved': unobserved}

    def _admitted_worker_home(self, root, home, binding, generation, proof):
        """Narrow ordinary-first transition; never adopt worker state."""
        from hermes_cli.config import require_readable_config_before_write
        with scope.authority(root):
            _,current,row,current_proof=self._prepared(root,self.admin._state(),
                *(binding[k] for k in IDENTITY),generation)
            if not row['enabled'] or current!=binding or current_proof!=proof:
                raise PermissionError('admitted_ordinary_worker_attachment_required')
            scope.check_onboarding_home(root,home,binding)
            if not self._native_grant(root,binding, storage_readonly=self._storage_readonly): raise PermissionError('native_grant_revoked')
        own=require_readable_config_before_write(home / 'config.yaml')
        scope._private(home / scope.MARKER)
        marker=json.loads((home / scope.MARKER).read_text())
        if marker!={'schema':'friday.user-home.v1','principal':principal_id(*(binding[k] for k in IDENTITY)),
                'profile':binding['runtime_profile'],'binding_sha256':scope._fingerprint(binding),
                'onboarding_sha256':digest(home / scope.ONBOARDING)}:
            raise PermissionError('managed_setup_marker_changed')
        settings=own['plugins']['entries']['friday_rework']['settings']
        if settings['runtime']!={'enabled':False} or settings.get('worker_requirements'):
            raise PermissionError('ordinary_worker_free_home_required')
        with scope.authority(home):
            from hermes_cli.plugins_state import PluginState
            state = PluginState('friday_rework')
            if self._storage_readonly:
                associations = Associations(state, storage_readonly=True).snapshot_storage_readonly()
            else:
                associations = Associations(state).snapshot()
            if associations:
                raise PermissionError('existing_worker_associations_require_reconciliation')
        return own

    def _current_main_source_target(self, root, home, binding, generation, proof):
        """Fresh native admission first; this handoff grants source custody only."""
        own = self._admitted_worker_home(root, home, binding, generation, proof)
        try:
            selected = current_main_config(own, proof['required_secrets'])
        except (KeyError, ValueError, PermissionError):
            # Ineligible legacy profiles retain the strict source path. Native
            # authority failures above are never caught or converted to a grant.
            return None
        if json.dumps(selected, sort_keys=True) != json.dumps(own, sort_keys=True):
            return None
        return {'home': str(home), 'profile': binding['runtime_profile'],
            'binding_sha256': proof['binding_sha256']}

    def _worker_attachment(self,root,home,binding,generation,proof,root_config):
        from .worker_provision import pin
        self._admitted_worker_home(root,home,binding,generation,proof)
        path=home / WORKER_ATTACHMENT
        if not path.exists() and not path.is_symlink():
            raise PermissionError('explicit_reviewed_worker_attachment_required')
        scope._private(path); attachment=json.loads(path.read_text())
        plans=root_config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
        template=plans[attachment['template']]
        if (set(attachment)!={'template','template_sha256','installation_config_sha256','config_sha256',
                'proof','marker','binding_sha256','generation','runtimes','a0_network','required_names'}
                or attachment['template_sha256']!=scope._fingerprint(template)
                or attachment['installation_config_sha256']!=digest(root / 'config.yaml')
                or attachment['config_sha256']!=proof['config_sha256']
                or attachment['proof']!=pin(home / scope.ONBOARDING)
                or attachment['marker']!=pin(home / scope.MARKER)
                or attachment['binding_sha256']!=scope._fingerprint(binding)
                or attachment['generation']!=generation or set(attachment['runtimes'])!={'dsh','a0'}):
            raise PermissionError('worker_attachment_changed_reconciliation_required')
        return attachment

    def _worker_summary(self, home, binding, generation, proof, root_config):
        """Bounded protected-file inspection; no native probe or resubmission."""
        from . import user_worker_join as join
        from .worker_provision import preparation, pin
        from .host_runtime import configured_runtimes, check_runtime
        from hermes_cli.config import require_readable_config_before_write
        from hermes_cli.plugins_state import PluginState
        required = join.required_workers(root_config,proof,home)
        result = {'required_workers':['dsh','a0'] if required else [], 'workers':{},
            'can_prepare_workers':False,'can_qualify_workers':False,'can_activate':not required,
            'worker_execution':'BOTH_REQUIRED_WORKERS_PENDING' if required else 'DISABLED_EXPLICIT_INSTALLATION_INPUT'}
        attaching=False
        if not required:
            root=Path(proof['authorization_home'])
            if not (home / scope.MARKER).exists(): return result
            result.update(can_activate=False,can_attach_workers=False,worker_attachment=True)
            try:
                path=home / WORKER_ATTACHMENT
                if not path.exists() and not path.is_symlink():
                    self._admitted_worker_home(root,home,binding,generation,proof)
                    result['can_attach_workers']=not (home / 'workers').exists() and not (home / 'workers').is_symlink()
                    return result
                attachment=self._worker_attachment(root,home,binding,generation,proof,root_config)
                from agent.secret_scope import load_env_file
                local=load_env_file(home / '.env')
                result.update(required_workers=['dsh','a0'],required_names=attachment['required_names'],
                    capture_names=[n for n in attachment['required_names'] if not local.get(n)])
                attaching=True
            except (OSError,ValueError,PermissionError,RuntimeError,KeyError,TypeError):
                result['worker_execution']='QUALIFICATION_OR_SETUP_REQUIRES_RECONCILIATION_NO_REPLAY'
                return result
        present = []
        with scope.authority(home):
            runtime=require_readable_config_before_write(home / 'config.yaml')['plugins']['entries']['friday_rework']['settings']['runtime']
            rows=configured_runtimes(runtime)
            for kind in ('dsh','a0'):
                directory=home / 'workers' / kind
                state='NOT_PREPARED'
                if directory.exists() or directory.is_symlink():
                    try:
                        v,c=preparation(home,binding['runtime_profile'],kind,pin(directory / 'runtime-input.json'))
                        if v['generation']!=generation or v['principal_binding_sha256']!=scope._fingerprint(binding):
                            raise PermissionError('foreign_worker_preparation')
                        if attaching and c!=attachment['runtimes'][kind]:
                            raise PermissionError('worker_attachment_runtime_changed')
                        state='PREPARED_RUNTIME_UNOBSERVED'; present.append(kind)
                        if kind in rows:
                            check_runtime(rows[kind],Associations(PluginState('friday_rework')))
                            join.deployment_health(rows[kind],binding=binding,generation=generation)
                            state='OWN_DEPLOYMENT_QUALIFIED_JOURNEYS_NOT_RUN'
                    except (OSError,ValueError,PermissionError,RuntimeError,KeyError,TypeError):
                        state='RECONCILIATION_REQUIRED'
                result['workers'][kind]={'state':state,'qualified':state=='OWN_DEPLOYMENT_QUALIFIED_JOURNEYS_NOT_RUN'}
            partial = any(x['state']=='RECONCILIATION_REQUIRED' for x in result['workers'].values())
            folder=home / join.FOLDER
            attempted=folder.exists() or folder.is_symlink()
            result['can_prepare_workers']=not attaching and not present and not partial and not attempted
            result['can_activate']=all(x['qualified'] for x in result['workers'].values())
            bootstrap=home / 'workers/a0/bootstrap'
            probe_attempted=bootstrap.exists() or bootstrap.is_symlink() or (home / join.PLAN).exists() or (home / join.PLAN).is_symlink()
            result['can_qualify_workers']=len(present)==2 and not partial and not attempted and not probe_attempted and not result.get('capture_names')
            if result['can_activate']:
                result['worker_execution']='OWN_DEPLOYMENTS_QUALIFIED_LIVE_JOURNEYS_NOT_RUN'
                try:
                    with scope.authority(Path(proof['authorization_home'])):
                        scope.check_onboarding_home(Path(proof['authorization_home']),home,binding)
                        if not self._native_grant(Path(proof['authorization_home']), binding, storage_readonly=self._storage_readonly):
                            raise PermissionError('native_grant_missing')
                except (OSError,ValueError,PermissionError):
                    result['can_activate']=False
                    result['worker_execution']='QUALIFIED_WORKERS_NATIVE_ACCESS_PENDING'
            elif attempted or partial or probe_attempted: result['worker_execution']='QUALIFICATION_OR_SETUP_REQUIRES_RECONCILIATION_NO_REPLAY'
            elif len(present)==2: result['worker_execution']='PENDING_OWN_A0_NATIVE_PREREQUISITES_AND_QUALIFICATION'
        return result

    def workers_state(self, profile, *, session=None, expected_config_sha256, generation, platform,
                      transport_profile, account_id, user_id):
        if transport_profile!=profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile,expected_config_sha256,session) as (root,access,config):
            home,binding,row,proof=self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
            summary=self._worker_summary(home,binding,generation,proof,config)
            complete=summary['required_workers']==['dsh','a0'] and all(v['qualified'] for v in summary['workers'].values())
            return {'state':('ADMITTED_BOTH_WORKERS_ATTACHED' if complete else 'ADMITTED_WORKER_SETUP_PENDING') if row['enabled'] else 'DISABLED_SETUP_PENDING',
                'enabled':row['enabled'],'generation':generation,
                'config_sha256':digest(root / 'config.yaml'),'required_names':proof['required_secrets'],
                **summary}

    def prepare_workers(self, profile, *, session=None, expected_config_sha256, generation, platform,
                        transport_profile, account_id, user_id, template=None, web_policy=None):
        """Normal UI producer: derive both plans from the approved installation."""
        import time
        from .runtime_containment import Budget
        _prepare_phase('source_history')
        accepted_monotonic = time.monotonic()
        budget = Budget(180, started=accepted_monotonic)
        from .worker_provision import worker_source_scope
        with worker_source_scope(budget=budget):
            return self._prepare_workers(profile, session=session,
                expected_config_sha256=expected_config_sha256, generation=generation,
                platform=platform, transport_profile=transport_profile, account_id=account_id,
                user_id=user_id, template=template, budget=budget, web_policy=web_policy)

    def _prepare_workers(self, profile, *, session, expected_config_sha256, generation, platform,
                         transport_profile, account_id, user_id, template, budget, web_policy=None):
        _prepare_phase('identity')
        if transport_profile!=profile: raise PermissionError('receiving_transport_authority_required')
        from .worker_provision import source_module
        from . import user_worker_join as join
        from .worker_provision import prepare_inputs, pin, checked_installed_a0_source_successor
        from hermes_cli.config import require_readable_config_before_write, config_write_transaction
        values=dict(session=session,expected_config_sha256=expected_config_sha256,generation=generation,
            platform=platform,transport_profile=transport_profile,account_id=account_id,user_id=user_id)
        _prepare_phase('transaction')
        with self.transaction(profile,expected_config_sha256,session) as (root,access,config):
            _prepare_phase('source_history')
            history_walk = source_module('scripts.friday_ordinary_install')._HistoryWalk(budget=budget)
            _prepare_phase('prepared_home')
            home,binding,row,proof=self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
            attaching=row['enabled']
            if attaching:
                self._admitted_worker_home(root,home,binding,generation,proof)
                if not template: raise PermissionError('explicit_reviewed_worker_template_required')
            elif (home / scope.MARKER).exists() or (home / scope.MARKER).is_symlink() or template is not None:
                raise PermissionError('disabled_fresh_worker_setup_required')
            summary=self._worker_summary(home,binding,generation,proof,config)
            if not attaching and not summary['can_prepare_workers']:
                return {'state':'DISABLED_WORKER_SETUP_REQUIRES_INSPECTION','enabled':False,**summary}
            selected=config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates'][template if attaching else proof['template']]
            _prepare_phase('template')
            validate_template(selected)
            inputs=selected.get('worker_inputs')
            if not inputs or not inputs.get('workers'):
                return {'state':'INSTALLATION_WORKER_INPUTS_MISSING','enabled':row['enabled'],**summary}
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                own=require_readable_config_before_write(home / 'config.yaml')
                current_main = (self._current_main_source_target(root, home, binding, generation, proof)
                    if attaching else None)
                _prepare_phase('derive_inputs')
                runtimes,network,declared_files=join.derive_inputs(home,binding['runtime_profile'],inputs,own,web_policy=web_policy)
                # Check the entire coherent package before the first write.
                names=list(proof['required_secrets'])
                plans = {}
                for kind,c in runtimes.items():
                    budget.check()
                    _prepare_phase('validate_inputs')
                    plan=prepare_inputs(home,binding['runtime_profile'],kind,c,own,
                        a0_network=network if kind=='a0' else None,
                        declared_files=declared_files[kind], tools=binding['tools'],
                        _history_walk=history_walk, _current_main=current_main)
                    plans[kind] = plan
                    names.extend(plan[3])
                _prepare_phase('publish_attachment')
                attachment=None
                if attaching:
                    declaration=dict(template=template,template_sha256=scope._fingerprint(selected),
                        installation_config_sha256=expected_config_sha256,config_sha256=proof['config_sha256'],
                        proof=pin(home / scope.ONBOARDING),marker=pin(home / scope.MARKER),
                        binding_sha256=scope._fingerprint(binding),generation=generation,
                        runtimes=runtimes,a0_network=network,required_names=list(dict.fromkeys(names)))
                    checked = checked_installed_a0_source_successor(runtimes['a0'], _history_walk=history_walk, _current_main=current_main)
                    successor = None if checked is None else _worker_successor_location(root,home,binding,generation,checked)[0]
                    if (home / 'workers').exists() or (home / 'workers').is_symlink() or (successor is not None and (successor.exists() or successor.is_symlink())):
                        if checked is None:
                            return {'state':'ADMITTED_WORKER_SETUP_REQUIRES_INSPECTION','enabled':True,
                                **self._worker_summary(home,binding,generation,proof,config)}
                        def verify():
                            budget.check(); self._verify_operator(profile,session)
                            self._admitted_worker_home(root,home,binding,generation,proof)
                            if digest(root / 'config.yaml') != expected_config_sha256:
                                raise PermissionError('onboarding_config_conflict_reload')
                            if checked_installed_a0_source_successor(runtimes['a0'], _history_walk=history_walk, _current_main=current_main) != checked:
                                raise PermissionError('worker_successor_maintenance_changed')
                        _replace_inactive_worker_inputs(root,home,binding,generation,checked,declaration,plans,
                            budget=budget,verify=verify)
                        return {'state':'ADMITTED_WORKER_SETUP_PENDING','enabled':True,
                            **budget.call(self._worker_summary,home,binding,generation,proof,config)}
                    budget.check(); (home / 'workers').mkdir(mode=0o700)
                    self._verify_operator(profile,session)
                    _new_file(home / WORKER_ATTACHMENT,(json.dumps(declaration,sort_keys=True)+'\n').encode())
                    attachment=pin(home / WORKER_ATTACHMENT)
        for kind in ('dsh','a0'):
            budget.check()
            _prepare_phase('worker_dsh' if kind == 'dsh' else 'worker_a0')
            self.prepare_worker(profile,**values,worker=kind,runtime=runtimes[kind],
                a0_network=network if kind=='a0' else None,
                _declared_files=declared_files[kind],_attachment=attachment,_history_walk=history_walk)
            budget.check()
        _prepare_phase('state')
        return budget.call(self.workers_state,profile,**values)

    def qualify_workers(self, profile, *, session=None, expected_config_sha256, generation, platform,
                        transport_profile, account_id, user_id):
        """Protected initial A0 owner, bounded observations and BOTH-worker attach.

        Ordinary handlers cannot call this owning setup operation. Missing
        native prerequisites stay pending; partial attempts never auto-replay.
        """
        import time
        accepted_monotonic=time.monotonic()
        from .runtime_containment import Budget
        from .worker_provision import worker_source_scope
        # Includes canonical-source preparation in this original qualification.
        with worker_source_scope(budget=Budget(300, started=accepted_monotonic)):
            return self._qualify_workers(profile, session=session,
                expected_config_sha256=expected_config_sha256, generation=generation,
                platform=platform, transport_profile=transport_profile, account_id=account_id,
                user_id=user_id, accepted_monotonic=accepted_monotonic)

    def _qualify_workers(self, profile, *, session, expected_config_sha256, generation, platform,
                         transport_profile, account_id, user_id, accepted_monotonic):
        if transport_profile!=profile: raise PermissionError('receiving_transport_authority_required')
        from . import user_worker_join as join
        from .worker_provision import pin, preparation
        from .host_runtime import check_runtime, HostUnavailable
        from hermes_cli.config import require_readable_config_before_write,config_write_transaction,atomic_config_write
        from hermes_cli.plugins_state import PluginState
        with self.transaction(profile,expected_config_sha256,session) as (root,access,config):
            home,binding,row,proof=self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
            attaching=row['enabled']
            attachment=None
            if attaching:
                attachment=self._worker_attachment(root,home,binding,generation,proof,config)
            elif (home / scope.MARKER).exists() or (home / scope.MARKER).is_symlink():
                raise PermissionError('disabled_fresh_worker_setup_required')
            scope.check_onboarding_home(root,home,binding)
            if not self._native_grant(root, binding, storage_readonly=self._storage_readonly):
                return {'state':'DISABLED_NATIVE_GRANT_MISSING','enabled':False}
            with scope.authority(home),config_write_transaction(home / 'config.yaml'):
                own=require_readable_config_before_write(home / 'config.yaml')
                if own['plugins']['entries']['friday_rework']['settings']['runtime']!={'enabled':False}:
                    return {'state':'WORKER_SETUP_REQUIRES_INSPECTION','enabled':row['enabled'],
                        **self._worker_summary(home,binding,generation,proof,config)}
                if attaching:
                    from agent.secret_scope import load_env_file
                    local=load_env_file(home / '.env')
                    if any(not local.get(n) for n in attachment['required_names']):
                        return {'state':'ADMITTED_WORKER_SCOPED_KEYS_PENDING','enabled':True,
                            **self._worker_summary(home,binding,generation,proof,config)}
                prepared={k:pin(home / 'workers' / k / 'runtime-input.json') for k in ('dsh','a0')}
                for k,ref in prepared.items():
                    v,c=preparation(home,binding['runtime_profile'],k,ref)
                    if v['generation']!=generation or v['principal_binding_sha256']!=scope._fingerprint(binding):
                        raise PermissionError('foreign_or_revoked_worker_preparation')
                    if attaching and (c!=attachment['runtimes'][k] or v.get('attachment')!=pin(home / WORKER_ATTACHMENT)):
                        raise PermissionError('worker_attachment_runtime_changed')
                def verify():
                    with scope.authority(root):
                        self._verify_operator(profile,session)
                        self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
                        if digest(root / 'config.yaml')!=expected_config_sha256:
                            raise PermissionError('onboarding_config_conflict_reload')
                        scope.check_onboarding_home(root,home,binding)
                        if not self._native_grant(root, binding, storage_readonly=self._storage_readonly): raise PermissionError('native_grant_revoked')
                        if attaching:
                            if self._worker_attachment(root,home,binding,generation,proof,config)!=attachment:
                                raise PermissionError('worker_attachment_changed_reconciliation_required')
                source_target = (lambda: self._current_main_source_target(root, home, binding, generation, proof)) if attaching else None
                try: runtimes=join.qualify(home,binding,generation,prepared,verify=verify,
                    accepted_monotonic=accepted_monotonic, _source_target=source_target)
                except HostUnavailable as exc:
                    from .a0_bootstrap import PrerequisitePending
                    if isinstance(exc,PrerequisitePending):
                        return {'state':'ADMITTED_OWN_A0_NATIVE_PREREQUISITES_PENDING' if attaching else 'DISABLED_OWN_A0_NATIVE_PREREQUISITES_PENDING',
                            'enabled':row['enabled'],
                            **self._worker_summary(home,binding,generation,proof,config)}
                    raise
                from .runtime_containment import Budget
                budget = Budget(min(300, *(c['budget_seconds'] for c in runtimes.values())),
                    started=accepted_monotonic)
                for c in runtimes.values():
                    verify(); budget.call(check_runtime,c,Associations(PluginState('friday_rework')))
                    budget.call(join.deployment_health,c,binding=binding,generation=generation)
                own['plugins']['entries']['friday_rework']['settings']['runtime']={'enabled':True,'workers':runtimes}
                if attaching:
                    own['plugins']['entries']['friday_rework']['settings']['worker_requirements']=['dsh','a0']
                edit=budget.call(prepare_admin_config_edit,home,own,
                    required_secrets=attachment['required_names'] if attaching else None)
                verify(); budget.call(atomic_config_write,home / 'config.yaml',own)
                self._verify_operator(profile,session); budget.call(finish_admin_config_edit,home,edit)
                budget.check()
                updated=json.loads((home / scope.ONBOARDING).read_text())
                summary=budget.call(self._worker_summary,home,binding,generation,updated,config)
                return {'state':'ADMITTED_BOTH_WORKERS_ATTACHED' if attaching else 'CONFIGURED_NATIVE_ACTIVATION_REQUIRED',
                    'enabled':row['enabled'],
                    'config_sha256':budget.call(digest,root / 'config.yaml'),'required_names':updated['required_secrets'],
                    **summary}

    def configure_worker(self, profile, *, session=None, expected_config_sha256, generation, platform,
                         transport_profile, account_id, user_id, worker, preparation, runtime_receipt):
        """Attach independently supplied evidence via the original host checker.

        Normal A0 requires the own-profile native producer, never a bare receipt.
        No launch, receipt fabrication, budget or grant reset.
        """
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        from .worker_provision import preparation as read_preparation, own_runtime
        from .host_runtime import check_runtime, HostUnavailable
        from hermes_cli.config import atomic_config_write, require_readable_config_before_write, config_write_transaction
        with self.transaction(profile, expected_config_sha256, session) as (root, access, root_config):
            home, binding, row, proof = self._prepared(root, access.state, platform, transport_profile, account_id, user_id, generation)
            if row['enabled'] or (home / scope.MARKER).exists():
                raise PermissionError('disabled_fresh_worker_setup_required')
            v, c = read_preparation(home, binding['runtime_profile'], worker, preparation)
            if v['principal_binding_sha256'] != scope._fingerprint(binding) or v['generation'] != generation:
                raise PermissionError('foreign_or_revoked_worker_preparation')
            # The receipt hash is supplied by its independent evidence producer,
            # never generated from these preparation bytes or the owner runtime.
            c['runtime_receipt'] = runtime_receipt
            own_runtime(home, binding['runtime_profile'], worker, c)
            from .user_worker_join import required_workers, deployment_health
            normal = required_workers(root_config,proof,home)
            if worker == 'a0' and not normal:
                return {'state': 'DISABLED_A0_RECONCILIATION_REQUIRED', 'enabled': False}
            scope.check_onboarding_home(root, home, binding)
            if not self._native_grant(root, binding, storage_readonly=self._storage_readonly):
                return {'state': 'DISABLED_NATIVE_GRANT_MISSING', 'enabled': False}
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                if digest(home / 'config.yaml') != proof['config_sha256']:
                    raise PermissionError('prepared_home_changed')
                config = require_readable_config_before_write(home / 'config.yaml')
                from .host_runtime import configured_runtimes, add_runtime
                current_runtime = config['plugins']['entries']['friday_rework']['settings']['runtime']
                if worker in configured_runtimes(current_runtime):
                    raise PermissionError('existing_worker_not_adopted')
                from hermes_cli.plugins_state import PluginState
                try:
                    check_runtime(c, Associations(PluginState('friday_rework')))
                    if normal: deployment_health(c,binding=binding,generation=generation)
                except (HostUnavailable, OSError, ValueError):
                    return {'state': 'DISABLED_WORKER_RUNTIME_UNVERIFIED', 'enabled': False}
                config['plugins']['entries']['friday_rework']['settings']['runtime'] = add_runtime(current_runtime, worker, c)
                prepared = prepare_admin_config_edit(home, config)
                self._verify_operator(profile, session)
                atomic_config_write(home / 'config.yaml', config)
                self._verify_operator(profile, session)
                finish_admin_config_edit(home, prepared)
            return {'state': 'CONFIGURED_NATIVE_ACTIVATION_REQUIRED', 'enabled': False,
                    'runtime_acceptance': 'SOURCE_CONTRACT_CHECKED_LIVE_NOT_RUN'}

    def activate(self, profile, *, session=None, expected_config_sha256, generation, platform,
                 transport_profile, account_id, user_id):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            state = access.state
            home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
            # No repeated enabled action can revive a revoked retained grant.
            if row['enabled']: raise ValueError('already_enabled_reload')
            from hermes_cli.config import config_write_transaction
            with config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                # Recheck the proof after acquiring the target config lock.
                home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
                from agent.secret_scope import load_env_file
                path = home / '.env'
                if not path.exists() and not path.is_symlink():
                    return {'state': 'DISABLED_SCOPED_KEYS_MISSING', 'enabled': False}
                scope._private(path)
                if any(not load_env_file(path).get(k) for k in proof['required_secrets']):
                    return {'state': 'DISABLED_SCOPED_KEYS_MISSING', 'enabled': False}
                scope.check_onboarding_home(root, home, binding)
                if not self._native_grant(root, binding, storage_readonly=self._storage_readonly):
                    return {'state': 'DISABLED_NATIVE_GRANT_MISSING', 'enabled': False}
                from hermes_cli.config import load_config_readonly
                with scope.authority(home):
                    runtime = load_config_readonly()['plugins']['entries']['friday_rework']['settings']['runtime']
                    from .user_worker_join import required_workers
                    required = required_workers(config, proof,home)
                    from .host_runtime import configured_runtimes
                    rows = configured_runtimes(runtime)
                    if required and set(rows) != {'dsh', 'a0'}:
                        return {'state': 'DISABLED_REQUIRED_WORKERS_PENDING', 'enabled': False,
                                'worker_execution': 'BOTH_REQUIRED_WORKERS_UNQUALIFIED'}
                    if runtime.get('enabled') is True:
                        from .host_runtime import configured_runtimes
                        rows = configured_runtimes(runtime)
                        if 'a0' in rows and not required:
                            return {'state': 'DISABLED_A0_RECONCILIATION_REQUIRED', 'enabled': False}
                        from .host_runtime import check_runtime, HostUnavailable
                        from hermes_cli.plugins_state import PluginState
                        try:
                            for selected in rows.values():
                                check_runtime(selected, Associations(PluginState('friday_rework')))
                                if required:
                                    from .user_worker_join import deployment_health
                                    deployment_health(selected, binding=binding, generation=generation)
                        except (HostUnavailable, OSError, ValueError):
                            return {'state': 'DISABLED_WORKER_RUNTIME_UNVERIFIED', 'enabled': False}
                marker = {'schema': 'friday.user-home.v1', 'principal': principal_id(*(binding[k] for k in IDENTITY)),
                          'profile': binding['runtime_profile'], 'binding_sha256': scope._fingerprint(binding),
                          'onboarding_sha256': digest(home / scope.ONBOARDING)}
                path = home / scope.MARKER
                if path.exists() or path.is_symlink():
                    scope._private(path)
                    if json.loads(path.read_text()) != marker: raise PermissionError('foreign_home_marker')
                else:
                    self._verify_operator(profile, session)
                    _new_file(path, (json.dumps(marker, sort_keys=True) + '\n').encode())
                self._verify_operator(profile, session)
                confirmed = access._write_user_locked(principal_id(platform, profile, account_id, user_id),
                    dict(platform=platform, transport_profile=profile, account_id=account_id,
                         user_id=user_id, enabled=True, role='user'))
                return {'state': 'ADMITTED_NEXT_NATIVE_REQUEST', 'enabled': True,
                        'generation': confirmed['generation'], 'runtime_profile': binding['runtime_profile'],
                        'browser_execution': scope.browser_admission_error(binding['tools']),
                        'worker_execution': 'SOURCE_RUNTIME_VERIFIED_LIVE_NOT_RUN' if runtime.get('enabled') is True else 'DISABLED_EXPLICIT_INSTALLATION_INPUT'}


def prepare_admin_config_edit(home, candidate, *, required_secrets=None):
    """Validate a managed setup before an authorized native config edit.

    Old homes retain their existing contract. A managed home cannot lose its
    receipt, persona, scoped key references or mandatory useful capabilities.
    The caller owns the native config transaction and verified admin session.
    """
    receipt = home / scope.ONBOARDING
    marker_path = home / scope.MARKER
    marker = None
    if marker_path.exists() or marker_path.is_symlink():
        scope._private(marker_path)
        marker = json.loads(marker_path.read_text())
    if not receipt.exists() and not receipt.is_symlink():
        if isinstance(marker, dict) and 'onboarding_sha256' in marker:
            raise PermissionError('managed_setup_receipt_missing')
        return None
    scope._private(receipt)
    proof = json.loads(receipt.read_text())
    from hermes_constants import get_default_hermes_root
    root = get_default_hermes_root(home=home)
    if proof.get('authorization_home') != str(root):
        raise PermissionError('managed_setup_authority_changed')
    with scope.authority(root):
        active = scope.policy(root)
        if active is None: raise PermissionError('managed_setup_binding_missing')
        bindings = [b for b in active['bindings'] if b['runtime_profile'] == home.name]
        if len(bindings) != 1: raise PermissionError('managed_setup_binding_missing')
        binding = bindings[0]
        from hermes_cli.plugins_state import PluginState
        state = PluginState('friday_rework')
        key = principal_id(*(binding[k] for k in IDENTITY))
        row = current_access(state)['users'].get(key)
        if row is None: raise PermissionError('managed_setup_access_missing')
        verified_home, _, _, verified = Onboarding(None)._prepared(
            root, state, *(binding[k] for k in IDENTITY), row['generation'])
        if verified_home != home or verified != proof:
            raise PermissionError('managed_setup_home_changed')
        expected = {'schema': 'friday.user-home.v1', 'principal': key,
                    'profile': binding['runtime_profile'], 'binding_sha256': scope._fingerprint(binding),
                    'onboarding_sha256': digest(receipt)}
        if marker is not None and marker != expected:
            raise PermissionError('managed_setup_marker_changed')
        if row['enabled']:
            if marker is None: raise PermissionError('managed_setup_marker_missing')
            scope.check_onboarding_home(root, home, binding)
            from .user_worker_join import required_workers
            from .host_runtime import configured_runtimes
            from hermes_cli.config import require_readable_config_before_write
            if required_workers(require_readable_config_before_write(root / 'config.yaml'),proof,home):
                runtime=candidate['plugins']['entries']['friday_rework']['settings']['runtime']
                if (set(configured_runtimes(runtime))!={'dsh','a0'} or
                        candidate['plugins']['entries']['friday_rework']['settings'].get('worker_requirements')!=['dsh','a0']):
                    raise PermissionError('managed_profile_requires_both_workers')
    if required_secrets is not None:
        if not set(proof['required_secrets'])<=set(required_secrets):
            raise PermissionError('managed_setup_required_credentials_cannot_drop')
        proof=dict(proof,required_secrets=required_secrets)
    validate_template({'config': candidate, 'tools': binding['tools'],
                       'required_secrets': proof['required_secrets']})
    return {'proof': proof, 'receipt_sha256': digest(receipt), 'marker': marker,
            'marker_sha256': digest(marker_path) if marker is not None else None}


def finish_admin_config_edit(home, prepared):
    """Reseal only the verified new config; interrupted writes stay fail closed.

    No job/session or admission generation is rewritten. A failure after the
    config commit leaves the old receipt mismatched and requires reconciliation.
    """
    if prepared is None: return
    if digest(home / scope.ONBOARDING) != prepared['receipt_sha256']:
        raise PermissionError('managed_setup_receipt_changed')
    if prepared['marker'] is not None and digest(home / scope.MARKER) != prepared['marker_sha256']:
        raise PermissionError('managed_setup_marker_changed')
    def replace_private(path, value):
        import secrets
        temporary = path.with_name(path.name + '.admin-' + secrets.token_hex(8))
        try:
            _new_file(temporary, (json.dumps(value, sort_keys=True) + '\n').encode())
            os.replace(temporary, path); _sync_directory(home)
        finally:
            if temporary.exists(): temporary.unlink()
    proof = dict(prepared['proof'], config_sha256=digest(home / 'config.yaml'))
    replace_private(home / scope.ONBOARDING, proof)
    if prepared['marker'] is not None:
        marker = dict(prepared['marker'], onboarding_sha256=digest(home / scope.ONBOARDING))
        replace_private(home / scope.MARKER, marker)
