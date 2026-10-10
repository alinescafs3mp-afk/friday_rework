"""Friday admission over native homes, scopes, pools and channel consumers.

No secret store or readiness receipt. Non-Friday homes retain donor behavior.
Errors carry static codes; credentials are never copied into evidence.
"""
from __future__ import annotations
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import stat

SOURCE = Path(__file__).resolve().parents[1]


class CredentialDenied(ValueError):
    def __init__(self, code):
        super().__init__('friday_credential_' + code)


def require(ok, code):
    if not ok:
        raise CredentialDenied(code)


def managed(home=None):
    from hermes_constants import get_hermes_home
    home = Path(home) if home is not None else get_hermes_home()
    return any((home / n).exists() or (home / n).is_symlink() for n in
               ('FRIDAY-PROFILE.json', 'FRIDAY-INSTALL.json', '.friday-user-scope.json')) or (
                   SOURCE.parent / 'hermes-agent.source.json').exists()


def private_home(home):
    from hermes_cli.friday_dashboard_owner import read_owned
    home = Path(home)
    owner_uid = getattr(os, 'getuid', None)
    require(callable(owner_uid), 'home_unproved')
    st = home.lstat()
    require(home.is_absolute() and home.resolve() == home and stat.S_ISDIR(st.st_mode)
            and st.st_uid == owner_uid() and not st.st_mode & 0o077, 'home_unproved')
    read_owned(home / 'config.yaml', private=True)
    return home


def configuration(home):
    from hermes_cli.config_effective import load_user_config_effective
    from hermes_yaml import YAMLError
    private_home(home)
    from hermes_cli.friday_dashboard_owner import read_owned
    require(b'${' not in read_owned(home / 'config.yaml', private=True), 'config_interpolation_refused')
    try:
        return load_user_config_effective(home / 'config.yaml', fail_closed=True)
    except YAMLError:
        raise CredentialDenied('config_unreadable') from None


def owned_values(home):
    """Native protected dotenv, parsed without process interpolation or project fallback."""
    from dotenv import dotenv_values
    from hermes_cli.friday_dashboard_owner import read_owned
    private_home(home)
    p = home / '.env'
    if not p.exists() and not p.is_symlink():
        return {}
    raw = read_owned(p, private=True).decode('utf-8-sig')
    require('${' not in raw, 'dotenv_interpolation_refused')
    values = dotenv_values(stream=io.StringIO(raw), interpolate=False)
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()), 'dotenv_invalid')
    return dict(values)


def keyless(cfg):
    """Explicit retrieval tier; presence/absence of ambient keys selects nothing."""
    web = cfg.get('web') or {}
    enabled = web.get('keyless_fallback')
    require(type(enabled) is bool and web.get('keyless_rescue') is False
            and web.get('provider_tier', {}).get('exa') == ('free' if enabled else 'paid'), 'web_tier_mismatch')
    if enabled:
        require(all(web.get('provider_tier', {}).get(n) == 'paid' for n in ('parallel','firecrawl','keenable')), 'keyless_alternate_route_refused')
    return enabled


def _local_cli_accounts(home, settings, contract, accounts):
    """Validate native local accounts separately from receiving token adapters.

    Bootstrap runs before initialize_cli. A protected declaration is not a
    capability: initial unprovisioned accounts stay disabled/unadmitted. Once
    onboarding writes a UID map, native bindings and access generations must
    agree; initialize_cli still owns the enabled-user admission.
    """
    from hermes_cli import friday_user_scope as user
    from hermes_cli.friday_cli_principal import cli_policy, numeric_os_uid
    from hermes_cli.friday_product_access import access_policy, current_access, principal_id
    local = [a for a in accounts if a.get('platform') == 'cli']
    declaration = contract.get('local_cli')
    if not local:
        require(declaration is None and settings.get('cli_admission') is None,
                'local_cli_declaration_mismatch')
        return
    private_home(home)
    uid = numeric_os_uid()
    require(isinstance(declaration, dict) and set(declaration) == {
                'accounts', 'admission', 'owner_contract', 'ingress_work_result'}
            and declaration['admission'] == 'EXPLICIT_OPERATOR_UID_MAPPING_AND_COMPLETE_SETUP_REQUIRED'
            and declaration['owner_contract'] == 'SAME_NUMERIC_UID_PRIVATE_AUTHORIZATION_AND_PROFILE_FILES'
            and declaration['ingress_work_result'] == 'SEPARATE_NATIVE_CONSUMER_REQUIRED'
            and contract['profile'] == 'default'
            and declaration['accounts'] == [dict(platform=a['platform'],
                transport_profile=a['transport_profile'], account_id=a['account_id']) for a in local]
            and all(a['transport_profile'] == 'default' for a in local),
            'local_cli_declaration_mismatch')
    with user.authority(home):
        native = access_policy()
        require(native is not None and native['accounts'] == accounts, 'local_cli_account_policy_mismatch')
        bindings = user.policy(home)
        access = current_access()['users']
    local_bindings = [] if bindings is None else [b for b in bindings['bindings'] if b['platform'] == 'cli']
    local_access = {k: v for k, v in access.items() if v['platform'] == 'cli'}
    if settings.get('cli_admission') is None:
        require(not local_bindings and not local_access, 'local_cli_mapping_missing')
        return
    rows = cli_policy(home)['principals']
    keys = {principal_id('cli', r['transport_profile'], r['account_id'], r['user_id']) for r in rows}
    require(all(r['uid'] == uid for r in rows) and set(local_access) == keys
            and {principal_id(*(b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')))
                 for b in local_bindings} == keys, 'local_cli_principal_mapping_mismatch')
    for row in rows:
        key = principal_id('cli', row['transport_profile'], row['account_id'], row['user_id'])
        matches = [b for b in local_bindings if
                   principal_id(*(b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))) == key]
        require(len(matches) == 1 and any(a['transport_profile'] == row['transport_profile']
                and a['account_id'] == row['account_id'] and matches[0]['runtime_profile'] in a['runtime_profiles']
                for a in local), 'local_cli_binding_mismatch')
        principal = local_access[key]
        require(type(principal.get('generation')) is int and principal['generation'] >= 1,
                'local_cli_generation_missing')


def profile_policy(home, cfg):
    from hermes_cli.friday_dashboard_owner import read_owned
    from hermes_cli import friday_user_scope as user
    if (home / user.MARKER).exists() or (home / user.MARKER).is_symlink():
        capability = user._CURRENT.get()
        require(capability is not None and capability.home == home, 'user_authority_missing')
        capability.check()
        require(not cfg.get('dashboard') and not cfg.get('gateway') and not cfg.get('platforms'),
                'user_receiving_authority_refused')
        return None
    contract = json.loads(read_owned(home / 'FRIDAY-PROFILE.json', private=True))
    require(contract.get('schema') == 'friday.product-profile.v1'
            and contract.get('kind') == 'normal_product', 'product_contract_missing')
    settings = cfg.get('plugins', {}).get('entries', {}).get('friday_rework', {}).get('settings', {})
    accounts = settings.get('product_access', {}).get('accounts')
    require(isinstance(accounts, list) and bool(accounts), 'receiving_accounts_missing')
    domains = contract['required_scoped_names']
    names = domains['channels']
    key = cfg.get('model', {}).get('key_env')
    web_names = [] if keyless(cfg) else ['EXA_API_KEY']
    runtime = settings.get('runtime', {})
    require(isinstance(runtime, dict), 'worker_runtime_shape')
    has_a0 = 'a0_deployment' in cfg or 'a0' in runtime
    if 'workers' in runtime:
        workers = runtime['workers']
        require(set(runtime) == {'enabled', 'workers'} and runtime['enabled'] is True
                and isinstance(workers, dict) and bool(workers)
                and set(workers) <= {'dsh', 'a0'}, 'worker_map_shape')
        require(all(isinstance(child, dict) and child.get('enabled') is True
                    and kind in child and 'workers' not in child
                    and not ({'dsh', 'a0'} - {kind}).intersection(child)
                    for kind, child in workers.items()), 'worker_map_shape')
        has_a0 = has_a0 or 'a0' in workers
    services = ['FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET'] if has_a0 else []
    expected = [key, *web_names, *services]
    require(key not in ('EXA_API_KEY','FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET')
            and domains.get('inference_web') == expected, 'inference_contract_mismatch')
    if any(k in domains for k in ('inference','web','worker_service')):
        require(domains.get('inference') == [key] and domains.get('web') == web_names
                and domains.get('worker_service') == services, 'credential_split_mismatch')
    foreign = set(domains.get('dashboard', [])) | {v for vs in names.values() for v in vs}
    require(not foreign.intersection(domains['inference_web']), 'credential_domains_overlap')
    from gateway.config import PLATFORM_TOKEN_ENV_NAMES, Platform
    require(isinstance(names, dict), 'receiving_mapping_mismatch')
    receiving = [r for r in accounts if r.get('platform') != 'cli']
    _local_cli_accounts(home, settings, contract, accounts)
    require(len(names) == len(receiving) and set(names) == {r['platform'] for r in receiving},
            'receiving_mapping_mismatch')
    for row in receiving:
        require(row['transport_profile'] == contract['profile']
                and names[row['platform']] == [PLATFORM_TOKEN_ENV_NAMES[Platform(row['platform'])]],
                'receiving_profile_mismatch')
    for name, row in cfg.get('platforms', {}).items():
        require(row.get('enabled') is (name in names), 'undeclared_channel_enable')
    require(all(cfg.get('platforms', {}).get(n, {}).get('enabled') is True for n in names),
            'declared_channel_disabled')
    require(cfg.get('gateway', {}).get('multiplex_profiles') is True, 'native_scope_required')
    require(cfg.get('dashboard', {}).get('basic_auth', {}).get('username') ==
            contract['native_dashboard']['operator']['user_id'], 'operator_mismatch')
    return contract


def local_route(cfg):
    from ipaddress import ip_address
    from urllib.parse import urlsplit
    m = cfg.get('model') or {}; provider = m.get('provider'); url = m.get('base_url'); key = m.get('key_env')
    require(isinstance(provider, str) and provider.startswith('custom:') and bool(m.get('default')),
            'named_local_route_required')
    p = urlsplit(url or '')
    try:
        host = ip_address(p.hostname or '')
    except ValueError:
        raise CredentialDenied('literal_local_endpoint_required') from None
    require((host.is_loopback or host.is_private) and not host.is_unspecified and not host.is_multicast
            and p.scheme in ('http', 'https') and p.path == '/v1' and p.port is not None
            and p.username is None and p.password is None and not p.query and not p.fragment,
            'local_endpoint_required')
    from gateway.config import PLATFORM_TOKEN_ENV_NAMES
    require(isinstance(key, str) and key.isidentifier() and key != 'EXA_API_KEY'
            and key not in PLATFORM_TOKEN_ENV_NAMES.values()
            and not key.startswith('HERMES_DASHBOARD_'), 'inference_key_reference_required')
    # Native keyed providers also match normalized display-name aliases, in
    # insertion order. Validate the same candidates WITHOUT resolving secrets;
    # a dictionary-key lookup alone can admit a different native winner.
    from hermes_cli.providers import custom_provider_aliases
    from hermes_cli.config import is_provider_enabled
    from hermes_cli.runtime_provider_custom import _entry_url, _normalize_custom_provider_name
    providers = cfg.get('providers') or {}
    require(isinstance(providers, dict), 'named_provider_mismatch')
    requested = _normalize_custom_provider_name(provider)
    matches = [(name, entry) for name, entry in providers.items()
               if isinstance(entry, dict) and is_provider_enabled(entry) and _entry_url(entry)
               and requested in custom_provider_aliases(str(entry.get('name', '') or name), str(name))]
    require(len(matches) == 1 and matches[0][0] == provider.split(':', 1)[1],
            'named_provider_ambiguous')
    row = matches[0][1]
    require(_entry_url(row) == url and row.get('key_env') == key
            and row.get('enabled', True) is True, 'named_provider_mismatch')
    require(not cfg.get('fallback_providers') and not cfg.get('fallback_model'), 'fallback_refused')
    require(not m.get('openai_runtime') and not m.get('api_key') and not row.get('api_key')
            and not row.get('key_cmd'), 'alternate_credentials_refused')
    # Check every native alias before any factory or request merger consumes it.
    blocks = [m, row, cfg.get('delegation') or {}, *(cfg.get('auxiliary') or {}).values()]
    blocks += list((cfg.get('providers') or {}).values()) + list(cfg.get('custom_providers') or [])
    for block in blocks:
        if isinstance(block, dict):
            extensions(block.get('default_headers'), block.get('extra_body'))
            extensions(block.get('extra_headers'))
            overrides = block.get('request_overrides') or {}
            require(isinstance(overrides, dict), 'request_extensions_invalid')
            extensions(overrides.get('extra_headers'), overrides.get('extra_body'))
            require(not set(overrides).intersection(_ROUTE_FIELDS - {'extra_headers'}), 'request_route_override_refused')
    require(cfg.get('auth', {}).get('adopt_external_logins', False) is False, 'external_login_refused')
    web = cfg.get('web') or {}
    require(all(web.get(n) == 'exa' for n in ('backend', 'search_backend', 'extract_backend'))
            and web.get('keyless_rescue') is False, 'web_route_mismatch')
    keyless(cfg)
    for name, a in (cfg.get('auxiliary') or {}).items():
        if not isinstance(a, dict):
            continue
        require(a.get('provider') == provider and a.get('model') == m['default']
                and a.get('base_url') == url and a.get('key_env') == key
                and not a.get('api_key') and a.get('fallback_chain') == [], 'auxiliary_route_mismatch')
    d = cfg.get('delegation') or {}
    require(d.get('provider') == provider and d.get('model') == m['default']
            and d.get('base_url') == url and d.get('key_env') == key
            and not d.get('api_key') and d.get('fallback_providers') == [], 'delegation_route_mismatch')
    return provider, m['default'], url, key



# Friday supports native capacity/reasoning bodies and these non-authority header
# overrides. Other header names need an explicit scoped contract, not an ambient
# alternate credential/virtual-host path. Donor configuration remains unchanged.
_USER_HEADERS = frozenset({'accept', 'accept-language', 'user-agent', 'x-request-id',
                          'x-correlation-id', 'traceparent', 'tracestate'})
_ROUTE_FIELDS = frozenset({'model', 'provider', 'base_url', 'url', 'api', 'api_key',
                          'key_env', 'key_cmd', 'api_mode', 'authorization', 'host',
                          'headers', 'default_headers', 'extra_headers', 'extra_query'})


def extensions(headers=None, body=None):
    if headers:
        require(isinstance(headers, dict), 'request_headers_invalid')
        require(all(isinstance(k, str) and k.lower() in _USER_HEADERS
                    and isinstance(v, str) and '\r' not in v and '\n' not in v
                    for k, v in headers.items()), 'request_headers_refused')
    if body:
        require(isinstance(body, dict), 'request_body_invalid')
        require(not any(not isinstance(k, str) or k.lower() in _ROUTE_FIELDS for k in body),
                'request_route_override_refused')


_SDK_CLASSES = {}


def sdk_class(base):
    """Guard native OpenAI wire construction, including SDK copy/with_options.

    No SDK monkeypatch: only Friday's native factories choose this subclass.
    Both SDK transports build requests synchronously before their first effect.
    """
    if not managed():
        return base
    if base in _SDK_CLASSES:
        return _SDK_CLASSES[base]

    class AdmittedClient(base):
        def __init__(self, *args, **kwargs):
            from hermes_constants import get_hermes_home
            require(not args, 'client_positional_override_refused')
            extensions(kwargs.get('default_headers'))
            require(not kwargs.get('organization') and not kwargs.get('project')
                    and not kwargs.get('default_query'), 'client_authority_override_refused')
            require(isinstance(kwargs.get('api_key'), str) and len(kwargs['api_key'].strip()) >= 4
                    and kwargs['api_key'] != 'no-key-required', 'client_key_missing')
            route = route_inputs(api_key=kwargs.get('api_key'))
            from httpx import URL
            # Native async conversion and SDK copies pass an already normalized
            # base_url (including omission of :80/:443).
            require(URL(str(kwargs.get('base_url', '')).rstrip('/')) == URL(route[2]),
                    'route_override_refused')
            self._friday_home = get_hermes_home()
            require(not os.environ.get('OPENAI_ORG_ID') and not os.environ.get('OPENAI_PROJECT_ID'),
                    'client_authority_override_refused')
            super().__init__(**kwargs)
            require(not self.organization and not self.project, 'client_authority_override_refused')

        def _build_request(self, options, *, retries_taken=0):
            from hermes_constants import get_hermes_home
            require(get_hermes_home() == self._friday_home, 'client_scope_changed')
            route = route_inputs(api_key=self.api_key)
            extensions(options.headers, options.extra_json)
            # httpx auth/hooks and redirects run AFTER SDK construction; none may
            # rewrite an admitted request or carry it to a different endpoint.
            require(self._client.auth is None and not self._client.event_hooks.get('request'),
                    'client_authority_override_refused')
            options.follow_redirects = False
            request = super()._build_request(options, retries_taken=retries_taken)
            # Match the actual HTTPX canonical URL/Host representation: default
            # ports are omitted and IPv6 authority formatting stays with HTTPX.
            from httpx import URL
            expected = URL(route[2] + '/chat/completions')
            require(request.method == 'POST' and request.url == expected,
                    'wire_route_mismatch')
            require(request.headers.get_list('authorization') == ['Bearer ' + self.api_key]
                    and request.headers.get_list('host') == [expected.netloc.decode('ascii')],
                    'wire_authority_mismatch')
            builtin = {'authorization', 'host', 'content-type', 'content-length', 'connection',
                       'accept-encoding'}
            require(all(k in builtin or k in _USER_HEADERS or k.startswith('x-stainless-')
                        for k in request.headers), 'wire_headers_refused')
            try:
                body = json.loads(request.content)
            except (ValueError, UnicodeError):
                raise CredentialDenied('wire_body_invalid') from None
            require(isinstance(body, dict) and body.get('model') == route[1], 'wire_model_mismatch')
            require(not (set(body) & (_ROUTE_FIELDS - {'model'})), 'wire_route_override_refused')
            return request

    _SDK_CLASSES[base] = AdmittedClient
    return AdmittedClient


def own_pool(provider):
    """Use native auth.json schema; never consult the native global-root fallback."""
    from hermes_constants import get_hermes_home
    from hermes_cli.friday_dashboard_owner import read_owned
    home = private_home(get_hermes_home()); p = home / 'auth.json'
    if not p.exists() and not p.is_symlink():
        return {} if provider is None else []
    try:
        store = json.loads(read_owned(p, private=True))
    except (ValueError, UnicodeError):
        raise CredentialDenied('auth_store_unreadable') from None
    pool = store.get('credential_pool', {})
    require(isinstance(pool, dict), 'pool_invalid')
    require(all(isinstance(k, str) and isinstance(v, list) for k, v in pool.items()), 'pool_invalid')
    return dict(pool) if provider is None else list(pool.get(provider, []))


@contextmanager
def scoped(home, values=None):
    """Existing native contextvars, including strict misses for the launch profile."""
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from agent.secret_scope import set_secret_scope, reset_secret_scope, set_multiplex_context, reset_multiplex_context
    h = set_hermes_home_override(str(home)); s = set_secret_scope(
        owned_values(home) if values is None else values, profile_home=str(home)); m = set_multiplex_context(True)
    try:
        yield
    finally:
        reset_multiplex_context(m); reset_secret_scope(s); reset_hermes_home_override(h)


def route_inputs(requested=None, base_url=None, api_key=None, model=None):
    from hermes_constants import get_hermes_home
    from agent.secret_scope import current_secret_scope, current_secret_scope_home
    home = get_hermes_home(); cfg = configuration(home); profile_policy(home, cfg)
    provider, selected, url, key = local_route(cfg)
    require(requested in (None, provider, 'custom') and base_url in (None, url)
            and model in (None, selected), 'route_override_refused')
    values = owned_values(home)
    require(current_secret_scope_home() == str(home) and current_secret_scope() is not None,
            'scope_home_mismatch')
    scope = current_secret_scope()
    # Native managed/ambient secrets cannot fill missing product/user references.
    require(all(scope.get(n) == v for n, v in values.items()), 'scope_provenance_mismatch')
    if not keyless(cfg):
        require(scope.get('EXA_API_KEY') == values.get('EXA_API_KEY') and bool(values.get('EXA_API_KEY')),
                'exa_key_missing')
    require(scope.get(key) == values.get(key), 'inference_scope_mismatch')
    rows = own_pool(provider)
    for row in rows:
        require(isinstance(row, dict) and row.get('base_url') == url
                and isinstance(row.get('access_token', ''), str)
                and not row.get('refresh_token') and row.get('auth_type', 'api_key') == 'api_key',
                'pool_route_mismatch')
    allowed = {values.get(key)} | {r.get('access_token') for r in rows}
    require(api_key is None or (isinstance(api_key, str) and api_key in allowed), 'explicit_foreign_key_refused')
    require(bool(values.get(key)) or any(bool(r.get('access_token')) for r in rows), 'local_key_missing')
    require(not any(os.environ.get(n) for n in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')), 'inference_proxy_refused')
    return provider, selected, url


def runtime_checked(runtime, route):
    provider, model, url = route
    require(runtime.get('base_url') == url and runtime.get('api_mode') == 'chat_completions'
            and runtime.get('model', model) == model and runtime.get('provider') in (provider, 'custom'),
            'resolved_route_mismatch')
    key = runtime.get('api_key')
    require(isinstance(key, str) and len(key.strip()) >= 4 and key != 'no-key-required', 'resolved_key_missing')
    from hermes_constants import get_hermes_home
    home = get_hermes_home(); name = local_route(configuration(home))[3]
    allowed = {owned_values(home).get(name)} | {r.get('access_token') for r in own_pool(provider)}
    require(key in allowed, 'resolved_key_provenance_mismatch')
    return runtime


def client_inputs(provider, model, url, key, mode):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    selected = route_inputs(provider, url, key, model)
    require(mode in (None, '', 'chat_completions'), 'client_transport_override_refused')
    resolved = resolve_runtime_provider(requested=selected[0], target_model=selected[1])
    return selected[0], selected[1], selected[2], resolved['api_key'], 'chat_completions'


def auxiliary(task, provider, model, base_url, api_key):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    route = route_inputs(provider, base_url, api_key, model)
    runtime = resolve_runtime_provider(requested=route[0], target_model=route[1])
    return route[0], route[1], route[2], runtime['api_key'], runtime['api_mode']


def bootstrap(home):
    """Called by the actual native dotenv startup before project/managed fallback."""
    from hermes_constants import get_hermes_home
    from hermes_cli.friday_cli_principal import current_cli
    retained = current_cli()
    if retained is not None:
        require(home in (retained.home, retained.authorization_home)
                and retained.authorization_home == SOURCE.parent, 'launch_home_mismatch')
    if not managed(home):
        return None
    if home != SOURCE.parent:
        # Entry/CLI admission precedes this native dotenv consumer. Never
        # initialize or infer a CLI principal from a target home here.
        from hermes_cli.friday_cli_principal import current_cli
        cap = current_cli(required=True)
        require(cap.home == home and cap.authorization_home == SOURCE.parent
                and get_hermes_home() == home, 'launch_home_mismatch')
        from hermes_cli.friday_dashboard_owner import source_identity
        source_identity(cap.authorization_home, source=SOURCE)
        cfg = configuration(home)
        require(profile_policy(home, cfg) is None, 'user_launch_required')
        provider, model, url, key = local_route(cfg)
        values = owned_values(home)
        rows = own_pool(provider)
        require(bool(values.get(key)) or any(bool(r.get('access_token'))
                and r.get('base_url') == url for r in rows), 'local_key_missing')
        require(keyless(cfg) or bool(values.get('EXA_API_KEY')), 'launch_key_missing')
        with scoped(home, values):
            route_inputs(requested=provider, base_url=url, model=model)
        cap.check()  # readiness/generation are checked again before installing a scope
        from agent.secret_scope import set_secret_scope, set_multiplex_context
        set_secret_scope(values, profile_home=str(home))
        set_multiplex_context(True)
        return [home / '.env']
    require(home == SOURCE.parent, 'launch_home_mismatch')
    if get_hermes_home() != home:
        require(managed(get_hermes_home()), 'launch_home_mismatch')
        return []
    from hermes_cli.friday_dashboard_owner import source_identity
    source_identity(home, source=SOURCE)
    cfg = configuration(home); contract = profile_policy(home, cfg); local_route(cfg)
    require(contract is not None, 'operator_launch_required')
    values = owned_values(home)
    names = contract['required_scoped_names']
    required = [*names.get('web', [] if keyless(cfg) else ['EXA_API_KEY']),
                *names.get('worker_service', []), *[v for vs in names['channels'].values() for v in vs]]
    require(all(bool(values.get(n)) for n in required), 'launch_key_missing')
    provider, model, url, key = local_route(cfg)
    rows = own_pool(provider)
    require(bool(values.get(key)) or any(bool(r.get('access_token')) and r.get('base_url') == url for r in rows), 'local_key_missing')
    require(not os.environ.get('HERMES_DASHBOARD_PUBLIC_URL')
            or os.environ['HERMES_DASHBOARD_PUBLIC_URL'] == contract['native_dashboard']['public_url'], 'ambient_public_url_refused')
    require(not any(os.environ.get(n) for n in ('HERMES_DESKTOP_OWNED', 'HERMES_DESKTOP_BACKEND', 'HERMES_DESKTOP_SSH_REMOTE')), 'desktop_authority_refused')
    for name, value in os.environ.items():
        if name.startswith('HERMES_DASHBOARD_BASIC_AUTH_'):
            require(value == values.get(name), 'ambient_operator_refused')
    from agent.secret_scope import _is_global_env, set_secret_scope, set_multiplex_context
    # OS/deployment facts stay native; product keys come from this home's protected file.
    for name in list(os.environ):
        if not _is_global_env(name):
            os.environ.pop(name, None)
    os.environ.update(values)
    set_secret_scope(values, profile_home=str(home)); set_multiplex_context(True)
    return [home / '.env']


def channel_inputs():
    from hermes_constants import get_hermes_home
    from agent.secret_scope import current_secret_scope_home
    home = get_hermes_home(); cfg = configuration(home); contract = profile_policy(home, cfg)
    require(contract is not None, 'user_listener_refused')
    require(current_secret_scope_home() == str(home), 'channel_scope_home_mismatch')
    require(not (home / 'gateway.json').exists() and not (home / 'gateway.json').is_symlink(),
            'legacy_channel_config_refused')
    return contract, owned_values(home)


def channel_config(config):
    from hermes_constants import get_hermes_home
    from agent.secret_scope import current_secret_scope_home, current_secret_scope
    contract, values = channel_inputs()
    names = contract['required_scoped_names']['channels']
    for platform, pcfg in config.platforms.items():
        declared = platform.value in names
        require(not pcfg.enabled or declared, 'ambient_channel_refused')
        if declared:
            name = names[platform.value][0]; token = values.get(name)
            from hermes_cli.auth import has_usable_secret
            require(pcfg.enabled and has_usable_secret(token) and pcfg.token == token
                    and current_secret_scope().get(name) == token, 'channel_token_mismatch')
    return config


def channel_identity(platform, account_id):
    from hermes_constants import get_hermes_home
    home = get_hermes_home(); cfg = configuration(home); contract = profile_policy(home, cfg)
    require(contract is not None, 'user_channel_identity_refused')
    rows = cfg['plugins']['entries']['friday_rework']['settings']['product_access']['accounts']
    matches = [r for r in rows if r['platform'] == platform and r['transport_profile'] == contract['profile']]
    require(len(matches) == 1 and str(account_id) == matches[0]['account_id'], 'native_account_mismatch')
