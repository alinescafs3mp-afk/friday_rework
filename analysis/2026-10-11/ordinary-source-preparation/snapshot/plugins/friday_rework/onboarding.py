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


def digest(path):
    scope._private(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local(url):
    p = urlsplit(url)
    address = ipaddress.ip_address(p.hostname or '')
    nets = [ipaddress.ip_network(n) for n in
            ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128')]
    if (p.scheme not in ('http', 'https') or not p.port or p.username or p.password
            or p.query or p.fragment or p.path.rstrip('/') != '/v1'
            or not any(address.version == n.version and address in n for n in nets)):
        raise ValueError('explicit_local_inference_required')
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
            or len(set(tools)) != len(tools) or not set(tools) <= scope.SAFE
            or not {'web_search', 'web_extract', 'friday_work', 'friday_result'} <= set(tools)
            or not isinstance(names, list) or not names or len(set(names)) != len(names)
            or any(not isinstance(k, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,127}', k) for k in names)):
        raise ValueError('incomplete_onboarding_template')
    from hermes_cli.config import validate_env_var_name_for_write
    for name in names:
        validate_env_var_name_for_write(name)
    model = config['model']; provider = model['provider']; url = _local(model['base_url'])
    if (provider not in ('custom', 'custom:friday-local') or not isinstance(model['default'], str)
            or not model['default'].strip() or model['default'] == 'auto'
            or config.get('fallback_providers') != [] or config.get('fallback_model') != {}):
        raise ValueError('explicit_local_inference_required')
    providers = config.get('providers', {})
    if provider == 'custom:friday-local':
        entry = providers.get('friday-local', {})
        if (_local(entry['api']) != url or entry.get('key_env') not in names
                or entry.get('discover_models') is not False):
            raise ValueError('explicit_scoped_provider_required')
    elif config.get('api_key_env') not in names:
        raise ValueError('explicit_scoped_provider_required')
    for route in config.get('auxiliary', {}).values():
        if isinstance(route, dict) and route.get('enabled') is not False:
            if (route.get('provider') != provider or route.get('base_url', '').rstrip('/') != url
                    or route.get('fallback_chain') != [] or route.get('key_env') not in names):
                raise ValueError('auxiliary_local_route_required')
    delegation = config.get('delegation', {})
    if delegation.get('provider') != provider or delegation.get('fallback_providers') != []:
        raise ValueError('delegation_local_route_required')
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


class Onboarding:
    def __init__(self, administration):
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
    def _native_grant(root, binding):
        if binding['platform'] == 'cli':
            _cli_admission(root, binding)
            return True  # Explicit operator map; product enable remains separate.
        from gateway.pairing import PairingStore
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
            if not user or user['enabled']: continue
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
                'required_names': proof['required_secrets'], 'enabled': False,
                'state': 'DISABLED_SETUP_PENDING', 'recoverable': True, 'config_sha256': digest(root / 'config.yaml')})
            if binding['platform'] == 'cli': result[-1]['uid'] = _cli_admission(root, binding)['uid']
            from hermes_cli.config import require_readable_config_before_write
            result[-1].update(self._worker_summary(home,binding,user['generation'],proof,
                require_readable_config_before_write(root / 'config.yaml')))
        return result

    def prepare(self, profile, *, session=None, expected_config_sha256, template, platform,
                transport_profile, account_id, user_id, runtime_profile, uid=None):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        key = principal_id(platform, transport_profile, account_id, user_id)
        profile_name(runtime_profile)
        if runtime_profile == 'default': raise ValueError('exclusive_new_profile_required')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            state = access.state
            settings = config['plugins']['entries']['friday_rework']['settings']
            plans = settings.get('onboarding', {}).get('templates', {})
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
                if template=='friday-local' or 'worker_inputs' in plans[template]:
                    native_config['plugins']['entries']['friday_rework']['settings']['worker_requirements']=['dsh','a0']
                atomic_config_write(home / 'config.yaml', native_config)
            soul = (RESOURCE / 'SOUL.md').read_bytes()
            if hashlib.sha256(soul).hexdigest() != SOUL_SHA256: raise ValueError('reviewed_friday_soul_changed')
            self._verify_operator(profile, session)
            _new_file(home / 'SOUL.md', soul)
            st = scope._private(home, directory=True)
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

    def credentials(self, profile, *, session=None, expected_config_sha256, generation, platform,
                    transport_profile, account_id, user_id, name, value):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile, expected_config_sha256, session) as (root, access, config):
            state = access.state
            home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
            if row['enabled'] or (home / scope.MARKER).exists() or name not in proof['required_secrets']:
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
            return {'state': 'DISABLED_SETUP_PENDING', 'recorded': True, 'enabled': False,
                **self._worker_summary(home,binding,generation,proof,config)}

    def prepare_worker(self, profile, *, session=None, expected_config_sha256, generation, platform,
                       transport_profile, account_id, user_id, worker, runtime, a0_network=None, _declared_files=None):
        """Operator-only source/config preparation for one disabled own profile.

        Exactly one fresh worker input tree, no adoption/retry of partial writes.
        Original budget/limits and reviewed source references are caller inputs.
        """
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        from .worker_provision import prepare_inputs, pin
        with self.transaction(profile, expected_config_sha256, session) as (root, access, _):
            home, binding, row, proof = self._prepared(root, access.state, platform, transport_profile, account_id, user_id, generation)
            if row['enabled'] or (home / scope.MARKER).exists():
                raise PermissionError('disabled_fresh_worker_setup_required')
            from hermes_cli.config import require_readable_config_before_write, config_write_transaction
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                self._verify_operator(profile, session)
                if digest(home / 'config.yaml') != proof['config_sha256']:
                    raise PermissionError('prepared_home_changed')
                config = require_readable_config_before_write(home / 'config.yaml')
                from .host_runtime import configured_runtimes
                if worker in configured_runtimes(config['plugins']['entries']['friday_rework']['settings']['runtime']):
                    raise PermissionError('existing_worker_not_adopted')
                c, directory, files, names, unobserved = prepare_inputs(home, binding['runtime_profile'], worker, runtime, config,
                    a0_network=a0_network, declared_files=_declared_files)
                if directory.exists() or directory.is_symlink():
                    raise FileExistsError('existing_worker_preparation_not_adopted')
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
                path = directory / 'runtime-input.json'
                self._verify_operator(profile, session)
                _new_file(path, (json.dumps(candidate, sort_keys=True, indent=2) + '\n').encode())
                # Same existing protected scoped credential capture, no key copy.
                # No new receipt/schema or activation marker is produced.
                updated = dict(proof, required_secrets=list(dict.fromkeys(proof['required_secrets'] + names)))
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
        if not required: return result
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
            result['can_prepare_workers']=not present and not partial and not attempted
            result['can_activate']=all(x['qualified'] for x in result['workers'].values())
            bootstrap=home / 'workers/a0/bootstrap'
            probe_attempted=bootstrap.exists() or bootstrap.is_symlink() or (home / join.PLAN).exists() or (home / join.PLAN).is_symlink()
            result['can_qualify_workers']=len(present)==2 and not partial and not attempted and not probe_attempted
            if result['can_activate']:
                result['worker_execution']='OWN_DEPLOYMENTS_QUALIFIED_LIVE_JOURNEYS_NOT_RUN'
                try:
                    with scope.authority(Path(proof['authorization_home'])):
                        scope.check_onboarding_home(Path(proof['authorization_home']),home,binding)
                        if not self._native_grant(Path(proof['authorization_home']), binding):
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
            return {'state':'DISABLED_SETUP_PENDING','enabled':row['enabled'],'generation':generation,
                'config_sha256':digest(root / 'config.yaml'),'required_names':proof['required_secrets'],
                **self._worker_summary(home,binding,generation,proof,config)}

    def prepare_workers(self, profile, *, session=None, expected_config_sha256, generation, platform,
                        transport_profile, account_id, user_id):
        """Normal UI producer: derive both plans from the approved installation."""
        if transport_profile!=profile: raise PermissionError('receiving_transport_authority_required')
        from . import user_worker_join as join
        from .worker_provision import prepare_inputs
        from hermes_cli.config import require_readable_config_before_write, config_write_transaction
        values=dict(session=session,expected_config_sha256=expected_config_sha256,generation=generation,
            platform=platform,transport_profile=transport_profile,account_id=account_id,user_id=user_id)
        with self.transaction(profile,expected_config_sha256,session) as (root,access,config):
            home,binding,row,proof=self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
            if row['enabled'] or (home / scope.MARKER).exists() or (home / scope.MARKER).is_symlink():
                raise PermissionError('disabled_fresh_worker_setup_required')
            summary=self._worker_summary(home,binding,generation,proof,config)
            if not summary['can_prepare_workers']:
                return {'state':'DISABLED_WORKER_SETUP_REQUIRES_INSPECTION','enabled':False,**summary}
            inputs=config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates'][proof['template']].get('worker_inputs')
            if not inputs or not inputs.get('workers'):
                return {'state':'DISABLED_INSTALLATION_WORKER_INPUTS_MISSING','enabled':False,**summary}
            with scope.authority(home), config_write_transaction(home / 'config.yaml'):
                own=require_readable_config_before_write(home / 'config.yaml')
                runtimes,network,(policy_path,policy_bytes)=join.derive_inputs(home,binding['runtime_profile'],inputs,own)
                # Check the entire coherent package before the first write.
                for kind,c in runtimes.items():
                    prepare_inputs(home,binding['runtime_profile'],kind,c,own,
                        a0_network=network if kind=='a0' else None,
                        declared_files={policy_path:policy_bytes} if kind=='dsh' else None)
        for kind in ('dsh','a0'):
            self.prepare_worker(profile,**values,worker=kind,runtime=runtimes[kind],
                a0_network=network if kind=='a0' else None,
                _declared_files={policy_path:policy_bytes} if kind=='dsh' else None)
        return self.workers_state(profile,**values)

    def qualify_workers(self, profile, *, session=None, expected_config_sha256, generation, platform,
                        transport_profile, account_id, user_id):
        """Protected initial A0 owner, bounded observations and BOTH-worker attach.

        Ordinary handlers cannot call this owning setup operation. Missing
        native prerequisites stay pending; partial attempts never auto-replay.
        """
        import time
        accepted_monotonic=time.monotonic()
        if transport_profile!=profile: raise PermissionError('receiving_transport_authority_required')
        from . import user_worker_join as join
        from .worker_provision import pin, preparation
        from .host_runtime import check_runtime, HostUnavailable
        from hermes_cli.config import require_readable_config_before_write,config_write_transaction,atomic_config_write
        from hermes_cli.plugins_state import PluginState
        with self.transaction(profile,expected_config_sha256,session) as (root,access,config):
            home,binding,row,proof=self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
            if row['enabled'] or (home / scope.MARKER).exists() or (home / scope.MARKER).is_symlink():
                raise PermissionError('disabled_fresh_worker_setup_required')
            scope.check_onboarding_home(root,home,binding)
            if not self._native_grant(root, binding):
                return {'state':'DISABLED_NATIVE_GRANT_MISSING','enabled':False}
            with scope.authority(home),config_write_transaction(home / 'config.yaml'):
                own=require_readable_config_before_write(home / 'config.yaml')
                if own['plugins']['entries']['friday_rework']['settings']['runtime']!={'enabled':False}:
                    return {'state':'DISABLED_WORKER_SETUP_REQUIRES_INSPECTION','enabled':False,
                        **self._worker_summary(home,binding,generation,proof,config)}
                prepared={k:pin(home / 'workers' / k / 'runtime-input.json') for k in ('dsh','a0')}
                for k,ref in prepared.items():
                    v,c=preparation(home,binding['runtime_profile'],k,ref)
                    if v['generation']!=generation or v['principal_binding_sha256']!=scope._fingerprint(binding):
                        raise PermissionError('foreign_or_revoked_worker_preparation')
                def verify():
                    with scope.authority(root):
                        self._verify_operator(profile,session)
                        self._prepared(root,access.state,platform,transport_profile,account_id,user_id,generation)
                        scope.check_onboarding_home(root,home,binding)
                        if not self._native_grant(root, binding): raise PermissionError('native_grant_revoked')
                try: runtimes=join.qualify(home,binding,generation,prepared,verify=verify,
                    accepted_monotonic=accepted_monotonic)
                except HostUnavailable as exc:
                    from .a0_bootstrap import PrerequisitePending
                    if isinstance(exc,PrerequisitePending):
                        return {'state':'DISABLED_OWN_A0_NATIVE_PREREQUISITES_PENDING','enabled':False,
                            **self._worker_summary(home,binding,generation,proof,config)}
                    raise
                for c in runtimes.values():
                    verify(); check_runtime(c,Associations(PluginState('friday_rework')))
                    join.deployment_health(c,binding=binding,generation=generation)
                own['plugins']['entries']['friday_rework']['settings']['runtime']={'enabled':True,'workers':runtimes}
                edit=prepare_admin_config_edit(home,own)
                verify(); atomic_config_write(home / 'config.yaml',own)
                self._verify_operator(profile,session); finish_admin_config_edit(home,edit)
                updated=json.loads((home / scope.ONBOARDING).read_text())
                return {'state':'CONFIGURED_NATIVE_ACTIVATION_REQUIRED','enabled':False,
                    'config_sha256':digest(root / 'config.yaml'),'required_names':updated['required_secrets'],
                    **self._worker_summary(home,binding,generation,updated,config)}

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
            if not self._native_grant(root, binding):
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
                if not self._native_grant(root, binding):
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
                        'worker_execution': 'SOURCE_RUNTIME_VERIFIED_LIVE_NOT_RUN' if runtime.get('enabled') is True else 'DISABLED_EXPLICIT_INSTALLATION_INPUT'}


def prepare_admin_config_edit(home, candidate):
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
