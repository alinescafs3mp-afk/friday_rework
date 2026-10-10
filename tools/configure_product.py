"""Compose a nonsecret normal Friday profile for the reviewed Hermes installation.

Rendering and fresh materialization never grant admission or runtime readiness.
The installation launcher owns native auth/rendezvous and scoped credential checks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

try:
    from tools.configure_local_test import build_config, read_owned_file
    from tools.web_profile import hermes_web_config, research_policy
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from configure_local_test import build_config, read_owned_file
    from web_profile import hermes_web_config, research_policy

ROOT = Path(__file__).resolve().parents[1]
INFERENCE = frozenset({'base_url', 'model', 'key_env', 'context', 'max_input',
                       'main_output', 'summary_output', 'margin', 'template_overhead'})
AUTH_NAMES = ('HERMES_DASHBOARD_BASIC_AUTH_USERNAME',
              'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH', 'HERMES_DASHBOARD_BASIC_AUTH_SECRET')
NORMAL_TOOLSETS = ['hermes-cli', 'web', 'friday_rework']
USER_TOOLSETS = ['web', 'memory', 'file', 'session_search', 'delegation', 'skills', 'friday_rework']


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + '_explicit_fields_required')
    return value


def _text(value, label, *, empty=False):
    if (not isinstance(value, str) or (not empty and not value) or value != value.strip()
            or len(value) > 256 or '${' in value or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(label + '_explicit_value_required')
    return value


def _dashboard(value):
    _exact(value, {'host', 'port', 'public_url', 'operator'} | ({'tls'} if isinstance(value, dict) and 'tls' in value else set()), 'dashboard')
    host = _text(value['host'], 'dashboard_host')
    try:
        ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('literal_dashboard_bind_required') from exc
    if type(value['port']) is not int or not 1 <= value['port'] <= 65535:
        raise ValueError('dashboard_port_required')
    public = _text(value['public_url'], 'dashboard_public_url')
    p = urlsplit(public)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username is not None
            or p.password is not None or p.query or p.fragment
            or any(c in public for c in (' ', '\\', '"', "'", '<', '>'))
            or p.path not in ('', '/') or p.port != value['port']):
        raise ValueError('exact_dashboard_authority_required')
    hostname = p.hostname
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if (len(hostname) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                     for label in hostname.split('.'))):
            raise ValueError('exact_dashboard_hostname_required')
    # This is the actual native gate predicate, not an inert YAML auth flag.
    from hermes_cli.web_server import should_require_dashboard_auth
    if not should_require_dashboard_auth(host, frozenset({p.hostname.lower()}), require_auth=True):
        raise ValueError('loopback_alone_does_not_require_dashboard_auth')
    if p.scheme != 'https' and (p.hostname not in ('localhost', '127.0.0.1', '::1')
                               or not ipaddress.ip_address(host).is_loopback):
        raise ValueError('remote_dashboard_https_required')
    if 'tls' in value:
        from hermes_cli.friday_dashboard_tls import validate
        validate(value['tls'], host, value['port'], public)
    operator = _exact(value['operator'], {'provider', 'user_id', 'org_id'}, 'operator')
    # Native BasicAuth mints provider=basic, user_id=username, org_id="".
    # An OAuth installation needs its own reviewed explicit native settings.
    if operator['provider'] != 'basic' or operator['org_id'] != '':
        raise ValueError('native_basic_operator_identity_required')
    _text(operator['user_id'], 'operator_user_id')
    return copy.deepcopy(value)


def compose_product(spec):
    """Return native config + an installation contract; inspect no credentials.

    Operator capabilities use native defaults. Ordinary users retain the exact
    accepted scope; this renderer cannot expand its SAFE set or admit workers.
    """
    _exact(spec, {'profile', 'inference', 'web', 'dashboard', 'accounts', 'runtime'} |
           ({'a0_deployment'} if isinstance(spec, dict) and 'a0_deployment' in spec else set()), 'product')
    from hermes_cli.friday_product_access import profile_name
    # Identity validation is pure; native config imports can create home state.
    profile = profile_name(spec['profile'])
    from hermes_cli.config import DEFAULT_CONFIG, validate_env_var_name_for_write
    from hermes_cli import friday_user_scope as scope
    from plugins.friday_rework.onboarding import validate_template

    inference = _exact(spec['inference'], INFERENCE, 'inference')
    validate_env_var_name_for_write(inference['key_env'])
    # Reuse the accepted local/capacity validator and bounded-context contract.
    # Only routing fields are shared; the deliberately narrow test capabilities
    # are not copied into the normal product configuration.
    local = build_config(**inference)
    web = _exact(spec['web'], {'profile', 'extract_char_limit', 'extract_timeout'}, 'web')
    if web['profile'] not in ('exa-paid','exa-keyless'):
        raise ValueError('mandatory_explicit_scoped_web_required')
    if any(web[k] is None for k in ('extract_char_limit', 'extract_timeout')):
        raise ValueError('web_limits_required')
    retrieval = hermes_web_config(**{'profile': web['profile'],
        'extract_char_limit': web['extract_char_limit'], 'extract_timeout': web['extract_timeout']})
    dashboard = _dashboard(spec['dashboard'])
    accounts = spec['accounts']
    if not isinstance(accounts, list) or not accounts:
        raise ValueError('explicit_receiving_accounts_required')
    from gateway.config import Platform, PLATFORM_TOKEN_ENV_NAMES
    seen = set(); channel_names = {}
    for row in accounts:
        _exact(row, {'platform', 'transport_profile', 'account_id'}, 'account')
        platform = Platform(row['platform'])
        if platform not in PLATFORM_TOKEN_ENV_NAMES:
            raise ValueError('channel_specific_native_input_contract_required')
        channel_names[row['platform']] = [PLATFORM_TOKEN_ENV_NAMES[platform]]
        _text(row['account_id'], 'account_id')
        if row['transport_profile'] != profile:
            raise ValueError('receiving_transport_authority_required')
        key = row['platform'], row['transport_profile']
        if key in seen:
            raise ValueError('duplicate_receiving_account')
        seen.add(key)
    runtime = copy.deepcopy(spec['runtime'])
    if runtime != {'enabled': False}:
        from plugins.friday_rework.host_runtime import configured_runtimes, HostUnavailable
        try:
            runtime_rows = configured_runtimes(runtime)
        except HostUnavailable as exc:
            raise ValueError('explicit_worker_runtime_contract_required') from exc
        for kind, selected_runtime in runtime_rows.items():
            if selected_runtime['runtime_profile'] != profile:
                raise ValueError('foreign_worker_runtime_profile')
            if kind == 'a0':
                if selected_runtime['a0'].get('web',{}).get('profile') != 'searxng-google':
                    raise ValueError('a0_useful_web_runtime_contract_unavailable')
            elif selected_runtime.get('dsh', {}).get('web', {}).get('profile') != web['profile']:
                raise ValueError('mandatory_worker_web_contract_required')

    # Config loading supplies the remaining untouched native defaults. Copy
    # the useful sections explicitly, not historical owner settings/state.
    config = {k: copy.deepcopy(DEFAULT_CONFIG[k]) for k in
              ('agent', 'compression', 'memory', 'skills', 'tools', 'approvals', 'delegation')}
    config.update({k: copy.deepcopy(local[k]) for k in ('model', 'providers', 'fallback_providers', 'fallback_model')})
    if 'a0_deployment' in spec:
        from plugins.friday_rework.adapters.a0_profile import checked_profile
        deployment = checked_profile(spec['a0_deployment'])
        chat = deployment['chat']
        if (chat['endpoint'] != config['model']['base_url'] or chat['model'] != inference['model']
                or chat['context_length'] != inference['context']
                or chat['max_output_tokens'] != inference['main_output']
                or inference['key_env'] != 'FRIDAY_LLM_API_KEY'):
            raise ValueError('a0_product_inference_profile_mismatch')
        config['a0_deployment'] = deployment
    config['auth'] = {'adopt_external_logins': False}
    config['model']['key_env'] = inference['key_env']
    route = {'provider': config['model']['provider'], 'model': inference['model'],
             'base_url': config['model']['base_url'], 'key_env': inference['key_env'],
             'api_mode': 'chat_completions', 'fallback_chain': []}
    config['auxiliary'] = {}
    for name, defaults in DEFAULT_CONFIG['auxiliary'].items():
        if isinstance(defaults, dict) and 'provider' in defaults:
            block = copy.deepcopy(defaults)
            block.pop('api_key', None)
            block.update(copy.deepcopy(route))
            block.setdefault('extra_body', {})['max_tokens'] = inference['summary_output']
            config['auxiliary'][name] = block
    config['auxiliary']['compression']['context_length'] = inference['context']
    config['auxiliary']['transient_retries'] = DEFAULT_CONFIG['auxiliary']['transient_retries']
    config['compression'].update(local['compression'])
    config['delegation'].pop('api_key', None)
    config['delegation'].update({k: v for k, v in route.items() if k != 'fallback_chain'})
    config['delegation']['fallback_providers'] = []
    config['agent']['environment_hint'] = research_policy()
    config['toolsets'] = list(NORMAL_TOOLSETS)
    config['platform_toolsets'] = {p: list(NORMAL_TOOLSETS) for p in sorted({'cli', *[a['platform'] for a in accounts]})}
    config['web'] = retrieval['web']
    # Useful native caching is preserved; explicit provider/rescue policy stays.
    config['web']['cache_enabled'] = DEFAULT_CONFIG['web']['cache_enabled']
    config['plugins'] = copy.deepcopy(retrieval['plugins'])
    config['plugins']['enabled'] += ['friday_rework', 'dashboard_auth/basic']
    config['plugins']['disabled'] += ['dashboard_auth/nous', 'dashboard_auth/self_hosted', 'dashboard_auth/drain']
    settings = {'runtime': runtime, 'results': {'enabled': True},
        'admin': {'enabled': True, 'operators': [dashboard['operator']], 'profiles': [profile]},
        'product_access': {'enabled': True, 'accounts': [dict(a, runtime_profiles=[profile]) for a in accounts]}}
    config['plugins']['entries'] = {'friday_rework': {'allow_gateway_work': True,
        'allow_gateway_control': True, 'settings': settings}}
    config['dashboard'] = {'public_url': dashboard['public_url'].rstrip('/'), 'require_auth': True,
                           'basic_auth': {'username': dashboard['operator']['user_id']}}
    config['gateway'] = {'multiplex_profiles': True, 'profile_routes': []}
    # Explicit disables beat credential-presence auto enable in native gateway
    # loading. Only declared receiving surfaces can become listeners.
    from gateway.config_env import _ENV_ENABLE_CREDENTIALS
    configured = {a['platform'] for a in accounts}
    channel_surfaces = {p.value for p in Platform} | {p.value for p in _ENV_ENABLE_CREDENTIALS}
    config['platforms'] = {name: {'enabled': name in configured} for name in sorted(channel_surfaces) if name != 'local'}

    # The protected template has settings/persona only: no receiving/admin
    # authority, worker receipt, keys, history, memory files or owner skills.
    if 'tls' in dashboard:
        config['dashboard']['tls'] = copy.deepcopy(dashboard['tls'])
    ordinary = copy.deepcopy(config)
    ordinary.pop('dashboard'); ordinary.pop('gateway'); ordinary.pop('platforms')
    ordinary['toolsets'] = list(USER_TOOLSETS)
    ordinary['platform_toolsets'] = {p: list(USER_TOOLSETS) for p in config['platform_toolsets']}
    ordinary['plugins']['enabled'].remove('dashboard_auth/basic')
    ordinary['plugins']['disabled'].append('dashboard_auth/basic')
    ordinary['plugins']['entries']['friday_rework']['settings'] = {
        'runtime': {'enabled': False}, 'results': {'enabled': True}}
    # Per-user native skill dirs start empty; no owner/project auto-discovery.
    ordinary['skills'].update(create_dir=None, external_dirs=[], project_discovery=False, trusted_project_dirs=[], auto_load=[])
    web_names = ['EXA_API_KEY'] if web['profile'] == 'exa-paid' else []
    service_names = []
    required = [inference['key_env'], *web_names]
    if 'a0_deployment' in spec or 'a0' in runtime or 'a0' in runtime.get('workers', {}):
        if inference['key_env'] != 'FRIDAY_LLM_API_KEY':
            raise ValueError('a0_scoped_inference_key_required')
        service_names = ['FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET']
        required += service_names
    if (len(set(required)) != len(required) or inference['key_env'] in AUTH_NAMES
            or any(inference['key_env'] in names for names in channel_names.values())):
        raise ValueError('separate_scoped_credential_references_required')
    # A normal installation must carry the scoped native delegation overlay.
    # Do not render an apparently complete profile against the older denied surface.
    if 'delegate_task' not in scope.SAFE:
        raise ValueError('scoped_native_delegation_required')
    # Skill toolsets require matching scoped native capabilities as well.
    if not {'skills_list', 'skill_view', 'skill_manage'} <= scope.SAFE:
        raise ValueError('scoped_native_skills_required')
    template = {'config': ordinary, 'tools': sorted(scope.SAFE), 'required_secrets': required}
    # Installation-owned declarations only: never propagate owner readiness,
    # profile identity, receipts, keys or per-job capabilities into a user.
    from plugins.friday_rework.user_worker_join import installation_inputs
    template['worker_inputs'] = installation_inputs(runtime)
    validate_template(template)
    settings['onboarding'] = {'templates': {'friday-local': template}}
    soul = (ROOT / 'config/SOUL.md').read_bytes()
    if soul != (ROOT / 'plugins/friday_rework/SOUL.md').read_bytes():
        raise ValueError('friday_persona_source_mismatch')
    return {'config': config, 'soul': soul.decode(), 'contract': {
        'schema': 'friday.product-profile.v1', 'kind': 'normal_product', 'profile': profile,
        'state': 'TEMPLATE_INCOMPLETE', 'ready': False,
        'required_scoped_names': {'inference_web': required, 'inference': [inference['key_env']],
            'web': web_names, 'worker_service': service_names, 'dashboard': list(AUTH_NAMES), 'channels': channel_names},
        'native_dashboard': {'host': dashboard['host'], 'port': dashboard['port'],
            'public_url': config['dashboard']['public_url'], 'auth_required': True,
            'operator': dashboard['operator'], 'insecure': False,
            'desktop_ssh_exemption_allowed': False,
            **({'tls': copy.deepcopy(dashboard['tls'])} if 'tls' in dashboard else {})},
        'soul_sha256': hashlib.sha256(soul).hexdigest(),
        'ordinary_scope': sorted(scope.SAFE),
        'remaining': ['Trusted plugin installation and exact patched native source verification',
            'Launcher must verify native auth gate, exact operator and controlled Host/Origin after scoped credential load; reject ambient username/password/public URL overrides',
            'Native BasicAuth reads raw process env, not context-local secret_scope; only explicit protected launch environment may supply auth names',
            'Native receiving account/token identities and profile homes require actual launcher verification',
            'Selected accepted bounded-context compatibility is text-only; multimodal requests require separately reviewed local capacity compatibility',
            'Native named-provider credential pool takes priority; fresh scoped pool/credential ownership must be verified',
            'Native worker runtime receipts and scoped key readiness not checked by rendering',
            'Ordinary users use accepted SAFE tools; direct skill/cron/terminal expansion requires separate policy review',
            'Fresh user remains disabled until both own-profile worker deployments are qualified',
            'Independent review and mandatory live journeys not run'],
    }}


def materialize_product(home, spec):
    """Fresh private home only, using the native process lock and atomic writer.

    A failure leaves a partial fresh home for reconciliation; it is never adopted
    on retry or automatically removed. Existing files and grants are untouched.
    """
    home = Path(home).absolute()
    parent = home.parent
    from hermes_cli import friday_user_scope as scope
    if parent.resolve(strict=True) != parent:
        raise PermissionError('real_private_parent_required')
    scope._private(parent, directory=True)
    if home.exists() or home.is_symlink():
        raise FileExistsError('existing_home_not_adopted')
    bundle = compose_product(spec)
    runtime = bundle['config']['plugins']['entries']['friday_rework']['settings']['runtime']
    from plugins.friday_rework.host_runtime import configured_runtimes
    if any(r['runtime_home'] != str(home) for r in configured_runtimes(runtime).values()):
        raise ValueError('foreign_worker_runtime_home')
    from hermes_cli.config import atomic_config_replace, config_write_transaction
    home.mkdir(mode=0o700)
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        with config_write_transaction(home / 'config.yaml'):
            atomic_config_replace(home / 'config.yaml', bundle['config'])
        for name, data in (('SOUL.md', bundle['soul'].encode()),
            ('FRIDAY-PROFILE.json', (json.dumps(bundle['contract'], sort_keys=True, indent=2) + '\n').encode())):
            fd = os.open(home / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
        from plugins.friday_rework.associations import _sync_directory
        _sync_directory(home)
    finally:
        reset_hermes_home_override(token)
    return {'state': 'TEMPLATE_INCOMPLETE', 'ready': False, 'home': str(home),
            'config_sha256': hashlib.sha256((home / 'config.yaml').read_bytes()).hexdigest(),
            'soul_sha256': bundle['contract']['soul_sha256'], 'runtime_acceptance': 'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input', type=Path, required=True, help='Owned private JSON; references only, no credentials')
    parser.add_argument('--home', type=Path, help='Optional fresh home beneath an existing private parent')
    args = parser.parse_args()
    try:
        spec = json.loads(read_owned_file(args.input, private=True), object_pairs_hook=_unique_object)
        bundle = compose_product(spec)
        output = materialize_product(args.home, spec) if args.home else bundle
    except (OSError, ValueError, KeyError, TypeError, PermissionError):
        parser.exit(2, 'Product profile refused: explicit inputs, native auth and fresh private ownership required\n')
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_input_field')
        result[key] = value
    return result


if __name__ == '__main__':
    main()
