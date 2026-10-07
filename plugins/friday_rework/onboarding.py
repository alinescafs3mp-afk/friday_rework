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
    if not isinstance(template, dict) or set(template) != {'config', 'tools', 'required_secrets'}:
        raise ValueError('invalid_onboarding_template')
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
            or web.get('keyless_fallback') is not False or 'EXA_API_KEY' not in names):
        raise ValueError('explicit_useful_scoped_web_required')
    plugins = config.get('plugins', {})
    if not {'friday_rework', 'web/exa'} <= set(plugins.get('enabled', [])):
        raise ValueError('required_native_plugins_missing')
    settings = plugins.get('entries', {}).get('friday_rework', {}).get('settings', {})
    if set(settings) - {'runtime', 'results'} or any(k in config for k in ('gateway', 'secrets', 'mcp_servers')):
        raise ValueError('ordinary_profile_cannot_import_authority')
    if (config.get('memory', {}).get('memory_enabled') is not True
            or config.get('memory', {}).get('user_profile_enabled') is not True
            or config.get('agent', {}).get('environment_hint') != (RESOURCE / 'RESEARCH.md').read_text().strip()
            or config.get('display', {}).get('personality')
            or config.get('agent', {}).get('system_prompt')):
        raise ValueError('explicit_private_context_and_friday_persona_required')
    runtime = settings.get('runtime')
    if runtime != {'enabled': False}:
        from .host_runtime import validate_runtime
        validate_runtime(runtime)
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
    }
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


class Onboarding:
    def __init__(self, administration):
        self.admin = administration

    @contextmanager
    def transaction(self, profile, expected_config_sha256):
        """Same protected native association and process config mutation locks.

        Product-admin generic config writers are denied by the native middleware.
        Supported onboarding/user writers share this admission lock; external
        operator edits still require the explicit file CAS on the next action.
        """
        from hermes_cli import config as native
        with self.admin.scope(profile) as root:
            scope._private(root, directory=True)
            from hermes_constants import get_routing_process_hermes_home
            if root != get_routing_process_hermes_home():
                raise PermissionError('primary_multiplex_route_authority_required')
            ProductAccess.require_transport(profile)
            state = self.admin._state(); access = ProductAccess(state); store = access.store
            with store._locked(), native.config_write_transaction(root / 'config.yaml'):
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
        return result

    def prepare(self, profile, *, expected_config_sha256, template, platform,
                transport_profile, account_id, user_id, runtime_profile):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        key = principal_id(platform, transport_profile, account_id, user_id)
        profile_name(runtime_profile)
        if runtime_profile == 'default': raise ValueError('exclusive_new_profile_required')
        with self.transaction(profile, expected_config_sha256) as (root, access, config):
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
            from hermes_constants import get_default_hermes_root
            home = get_default_hermes_root(home=root) / 'profiles' / runtime_profile
            if home.exists() or home.is_symlink(): raise ValueError('existing_home_not_adopted')
            if home.parent.exists(): scope._private(home.parent, directory=True)
            if home.parent.resolve() != home.parent: raise PermissionError('unsafe_profile_parent')
            runtime = native_config['plugins']['entries']['friday_rework']['settings']['runtime']
            if runtime.get('enabled') is True and (runtime['runtime_home'] != str(home) or runtime['runtime_profile'] != runtime_profile):
                raise ValueError('foreign_worker_runtime_template')
            binding = dict(platform=platform, transport_profile=transport_profile, account_id=account_id,
                           user_id=user_id, runtime_profile=runtime_profile, tools=tools)
            isolation = settings.setdefault('user_isolation', {'enabled': True, 'bindings': []})
            if isolation['enabled'] is not True or any(b['runtime_profile'] == runtime_profile or
                    principal_id(*(b[k] for k in IDENTITY)) == key for b in isolation['bindings']):
                raise ValueError('existing_binding_not_adopted')
            gateway = config.setdefault('gateway', {})
            if gateway.get('multiplex_profiles') is not True:
                raise ValueError('native_multiplex_installation_required')
            routes = gateway.setdefault('profile_routes', [])
            if any(r.get('platform') == platform and (r.get('bot_profile') or 'default') == profile
                   and r.get('user_id') == user_id for r in routes):
                raise ValueError('conflicting_native_route')
            # Disabled tombstone is persisted FIRST, before any route/home setup.
            user = access._write_user_locked(key, dict(platform=platform, transport_profile=profile,
                account_id=account_id, user_id=user_id, enabled=False, role='user'))
            isolation['bindings'].append(binding)
            matches[0]['runtime_profiles'].append(runtime_profile)
            settings['admin']['profiles'].append(runtime_profile)
            routes.append(dict(name='friday-' + key, platform=platform, bot_profile=profile,
                               user_id=user_id, profile=runtime_profile, enabled=True))
            from hermes_cli.config import atomic_config_write
            if digest(root / 'config.yaml') != expected_config_sha256:
                raise ValueError('onboarding_config_conflict_reload')
            atomic_config_write(root / 'config.yaml', config)
            # Never publish the user capability marker for incomplete setup.
            scope.provision_new_home(root, binding, {}, publish=False)
            if runtime.get('enabled') is True:
                for field in ('workspace_root', 'staging_root'):
                    directory = Path(runtime[field])
                    if not directory.is_relative_to(home) or directory.resolve() != directory:
                        raise PermissionError('worker_setup_directory_outside_private_home')
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Explicit per-profile settings, no owner/ambient secrets or history.
            with scope.authority(home):
                native_config['terminal'] = {'cwd': str(home / 'workspace')}
                atomic_config_write(home / 'config.yaml', native_config)
            soul = (RESOURCE / 'SOUL.md').read_bytes()
            if hashlib.sha256(soul).hexdigest() != SOUL_SHA256: raise ValueError('reviewed_friday_soul_changed')
            _new_file(home / 'SOUL.md', soul)
            st = scope._private(home, directory=True)
            receipt = dict(schema='friday.onboarding.v1', binding_sha256=scope._fingerprint(binding),
                config_sha256=digest(home / 'config.yaml'), soul_sha256=digest(home / 'SOUL.md'),
                required_secrets=names, directory_identity=[st.st_dev, st.st_ino], template=template,
                authorization_home=str(root))
            _new_file(home / scope.ONBOARDING, (json.dumps(receipt, sort_keys=True) + '\n').encode())
            return dict(state='DISABLED_INCOMPLETE', enabled=False, principal_id=key,
                        runtime_profile=runtime_profile, generation=user['generation'],
                        config_sha256=digest(root / 'config.yaml'), required_names=names,
                        admission='NATIVE_GRANT_AND_COMPLETE_SETUP_REQUIRED')

    def _prepared(self, root, state, platform, transport_profile, account_id, user_id, generation):
        from hermes_cli.friday_product_access import settings
        key = principal_id(platform, transport_profile, account_id, user_id)
        row = current_access(state)['users'].get(key)
        if not row or row['generation'] != generation or row['role'] != 'user':
            raise ValueError('onboarding_access_generation_conflict')
        bindings = settings()['user_isolation']['bindings']
        binding = next((b for b in bindings if principal_id(*(b[k] for k in IDENTITY)) == key), None)
        if not binding: raise ValueError('onboarding_binding_missing')
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
        return home, binding, row, proof

    def credentials(self, profile, *, expected_config_sha256, generation, platform,
                    transport_profile, account_id, user_id, name, value):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile, expected_config_sha256) as (root, access, _):
            state = access.state
            home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
            if row['enabled'] or (home / scope.MARKER).exists() or name not in proof['required_secrets']:
                raise PermissionError('pending_scoped_credential_capture_required')
            if not isinstance(value, str) or not value.strip() or len(value) > 8192:
                raise ValueError('invalid_scoped_credential')
            path = home / '.env'
            if path.exists() or path.is_symlink(): scope._private(path)
            from hermes_cli.config import save_env_value_secure
            from agent.secret_scope import load_env_file, set_secret_scope, reset_secret_scope, get_secret
            with scope.authority(home):
                # Empty local scope prevents the native lifecycle from borrowing
                # the process's current provider credential during capture.
                token = set_secret_scope(load_env_file(path), profile_home=str(home))
                try: save_env_value_secure(name, value)
                finally: reset_secret_scope(token)
                scope._private(path)
                local = load_env_file(path)
                token = set_secret_scope(local, profile_home=str(home))
                try:
                    if get_secret(name) != value: raise RuntimeError('scoped_secret_write_unconfirmed')
                finally: reset_secret_scope(token)
            return {'state': 'DISABLED_SETUP_PENDING', 'recorded': True, 'enabled': False}

    def activate(self, profile, *, expected_config_sha256, generation, platform,
                 transport_profile, account_id, user_id):
        if transport_profile != profile: raise PermissionError('receiving_transport_authority_required')
        with self.transaction(profile, expected_config_sha256) as (root, access, _):
            state = access.state
            home, binding, row, proof = self._prepared(root, state, platform, transport_profile, account_id, user_id, generation)
            # No repeated enabled action can revive a revoked retained grant.
            if row['enabled']: raise ValueError('already_enabled_reload')
            from agent.secret_scope import load_env_file
            path = home / '.env'
            if not path.exists() and not path.is_symlink():
                return {'state': 'DISABLED_SCOPED_KEYS_MISSING', 'enabled': False}
            scope._private(path)
            if any(not load_env_file(path).get(k) for k in proof['required_secrets']):
                return {'state': 'DISABLED_SCOPED_KEYS_MISSING', 'enabled': False}
            scope.check_onboarding_home(root, home, binding)
            from gateway.pairing import PairingStore
            if not PairingStore().is_approved(platform, user_id):
                return {'state': 'DISABLED_NATIVE_GRANT_MISSING', 'enabled': False}
            from hermes_cli.config import load_config_readonly
            with scope.authority(home):
                runtime = load_config_readonly()['plugins']['entries']['friday_rework']['settings']['runtime']
                if runtime.get('enabled') is True:
                    if 'a0' in runtime:
                        return {'state': 'DISABLED_A0_RECONCILIATION_REQUIRED', 'enabled': False}
                    from .host_runtime import check_runtime, HostUnavailable
                    from hermes_cli.plugins_state import PluginState
                    try:
                        check_runtime(runtime, Associations(PluginState('friday_rework')))
                    except (HostUnavailable, OSError, ValueError):
                        return {'state': 'DISABLED_WORKER_RUNTIME_UNVERIFIED', 'enabled': False}
            marker = {'schema': 'friday.user-home.v1', 'principal': principal_id(*(binding[k] for k in IDENTITY)),
                      'profile': binding['runtime_profile'], 'binding_sha256': scope._fingerprint(binding),
                      'onboarding_sha256': digest(home / scope.ONBOARDING)}
            path = home / scope.MARKER
            if path.exists() or path.is_symlink():
                scope._private(path)
                if json.loads(path.read_text()) != marker: raise PermissionError('foreign_home_marker')
            else: _new_file(path, (json.dumps(marker, sort_keys=True) + '\n').encode())
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
