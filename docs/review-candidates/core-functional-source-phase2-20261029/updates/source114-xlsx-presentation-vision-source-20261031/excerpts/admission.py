# Exported exact definition excerpts; not a complete product module.
from __future__ import annotations

class CredentialDenied(ValueError):
    def __init__(self, code):
        super().__init__('friday_credential_' + code)


def require(ok, code):
    if not ok:
        raise CredentialDenied(code)


def route_inputs(requested=None, base_url=None, api_key=None, model=None):
    from hermes_constants import get_hermes_home
    from agent.secret_scope import current_secret_scope, current_secret_scope_home
    home = get_hermes_home(); cfg = configuration(home); profile_policy(home, cfg)
    main = local_route(cfg)
    compression = _compression_route(cfg, main)
    route = main
    if compression is not None and requested == compression[0]:
        _compression_context(cfg, compression)
        route = compression
    provider, selected, url, key = route
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


def client_inputs(provider, model, url, key, mode, *, task=None):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    selected = route_inputs(provider, url, key, model)
    from hermes_constants import get_hermes_home
    cfg = configuration(get_hermes_home()); main = local_route(cfg)
    compression = _compression_route(cfg, main)
    require(compression is None or selected != compression[:3] or task == 'compression',
            'compression_task_required')
    require(mode in (None, '', 'chat_completions'), 'client_transport_override_refused')
    resolved = resolve_runtime_provider(requested=selected[0], target_model=selected[1])
    return selected[0], selected[1], selected[2], resolved['api_key'], 'chat_completions'


def auxiliary(task, provider, model, base_url, api_key):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_constants import get_hermes_home
    cfg = configuration(get_hermes_home()); main = local_route(cfg)
    compression = _compression_route(cfg, main)
    if task == 'compression' and compression is not None:
        # Native feasibility asks for route/credential resolution before any call.
        # Scope only this synchronous resolution; no client or request escapes it.
        from agent.bounded_context import _SUMMARY_POLICY, compression_policy_from_config
        from agent.auxiliary_client import _relay_aux_call_scope
        policy = compression_policy_from_config(cfg)
        active = _SUMMARY_POLICY.get()
        require(active is None or active == policy, 'compression_context_required')
        token = _SUMMARY_POLICY.set(policy)
        try:
            with _relay_aux_call_scope(('compression',), {}):
                route = route_inputs(provider or compression[0], base_url, api_key, model)
                require(route == compression[:3], 'compression_role_mismatch')
                runtime = resolve_runtime_provider(requested=route[0], target_model=route[1])
        finally:
            _SUMMARY_POLICY.reset(token)
    else:
        # Title, vision, delegation and arbitrary auxiliary work retain main.
        require(compression is None or provider != compression[0], 'compression_task_required')
        route = route_inputs(provider or main[0], base_url, api_key, model)
        require(route == main[:3], 'compression_task_required')
        runtime = resolve_runtime_provider(requested=route[0], target_model=route[1])
    return route[0], route[1], route[2], runtime['api_key'], runtime['api_mode']

