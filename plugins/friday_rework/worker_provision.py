"""Protected per-profile inputs for the existing worker admission contract.

No receipt producer, launch, capability, account store or automatic adoption.
The operator supplies intact pinned sources and original limits; readiness is
checked by host_runtime, not inferred from rendered configuration.
"""
import copy
import hashlib
import json
from pathlib import Path

from hermes_cli import friday_user_scope as scope
from .host_runtime import HostUnavailable, validate_runtime, _pin
from .host_record import digest


def pin(path):
    scope._private(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def own_runtime(home, profile, worker, runtime):
    c = validate_runtime(runtime)
    if worker not in ('dsh', 'a0') or (worker == 'a0') != ('a0' in c):
        raise HostUnavailable('worker_runtime_mismatch')
    root = home / 'workers' / worker
    if c['runtime_home'] != str(home) or c['runtime_profile'] != profile:
        raise HostUnavailable('foreign_worker_runtime_home')
    # Configuration preparation has a fixed exclusive per-worker private tree.
    # Shared source/toolchain mounts remain read-only through the native adapter.
    expected = {'workspace_root': root / 'jobs', 'staging_root': root / 'staging'}
    if any(c[k] != str(p) for k, p in expected.items()) or c['cache_roots'] != [str(root / 'cache')]:
        raise HostUnavailable('exclusive_user_worker_roots_required')
    receipt = Path(c['runtime_receipt']['path'])
    if receipt != root / 'runtime-receipt.json':
        raise HostUnavailable('own_worker_receipt_required')
    for p in [root, *expected.values(), root / 'cache', root / 'inputs', receipt]:
        if p.resolve() != p:
            raise HostUnavailable('unsafe_user_worker_path')
    return c, root


def prepare_inputs(home, profile, worker, runtime, config, *, a0_network=None):
    """Return an explicit plan before any write; never read/copy readiness."""
    from .onboarding import validate_template
    # Validate the actual profile, including local routes and accepted SAFE tools.
    validate_template({'config': config, 'tools': sorted(scope.SAFE),
                       'required_secrets': [config['providers']['friday-local']['key_env'], 'EXA_API_KEY']})
    c, root = own_runtime(home, profile, worker, runtime)
    files = {}; names = []; unobserved = ['native execution', 'model', 'network', 'runtime receipt', 'independent review']
    if worker == 'dsh':
        if a0_network is not None:
            raise HostUnavailable('unexpected_a0_inputs')
        d = c['dsh']; provider = config['providers']['friday-local']; model = config['model']
        if d['key_name'] != provider['key_env'] or d['web']['profile'] != 'exa-paid':
            raise HostUnavailable('own_worker_credential_and_web_required')
        from tools.render_dsh_local import build_patch
        capacity = provider['models'][model['default']]; bounds = capacity['bounded_context']
        rows = build_patch(purpose='temporary-local-test', api='openai-completions',
            base_url=model['base_url'], model=model['default'], api_key_env=d['key_name'],
            context_window=capacity['context_length'], max_tokens=bounds['main_max_output_tokens'],
            summary_max_tokens=bounds['compression_max_output_tokens'],
            headroom_tokens=bounds['safety_margin_tokens'] + bounds['template_overhead_tokens'], web_profile='exa-paid')
        data = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
        expected = {'path': str(root / 'inputs/dsh-local.json'), 'sha256': hashlib.sha256(data).hexdigest()}
        if d['patch'] != expected:
            raise HostUnavailable('rendered_user_worker_patch_mismatch')
        files[Path(expected['path'])] = data
        from .worker_web import DshWebInputs
        # Read every pinned source/web input; no shared receipt or key is read.
        for p in (d['node'], d['cli'], *d['native_files']): _pin(p).read()
        web = DshWebInputs(*(_pin(d['web'][k]) for k in ('resolver', 'trust_bundle', 'egress_evidence', 'research_policy')))
        web.checked_patch(data)
        names = [d['key_name'], 'EXA_API_KEY']
    else:
        if not isinstance(a0_network, dict) or set(a0_network) != {'name', 'endpoints', 'policy'}:
            raise HostUnavailable('explicit_a0_local_network_inputs_required')
        from .adapters.a0_config import LocalNetwork, local_profile, KEY_REFERENCES
        from .worker_web import a0_web_files
        deployment = c['a0'].get('deployment')
        if deployment != config.get('a0_deployment'):
            raise HostUnavailable('a0_configured_deployment_profile_mismatch')
        network = LocalNetwork(a0_network['name'], tuple(a0_network['endpoints']), _pin(a0_network['policy']), deployment)
        native = local_profile(network)
        chat = native['plugins/_model_config/presets.yaml'][0]['chat']
        capacity = config['providers']['friday-local']['models'][config['model']['default']]
        if (chat['api_base'] != config['model']['base_url'] or chat['name'] != config['model']['default']
                or chat['ctx_length'] != capacity['context_length']
                or chat['kwargs']['max_tokens'] != capacity['bounded_context']['main_max_output_tokens']):
            raise HostUnavailable('a0_original_local_profile_mismatch')
        if deployment is not None:
            if config['providers']['friday-local']['key_env'] != KEY_REFERENCES['API_KEY_OPENAI']:
                raise HostUnavailable('a0_scoped_profile_key_mismatch')
        for k in ('runtime', 'launcher', 'docker', 'daemon_unit', 'policy'): _pin(c['a0'][k]).read()
        # Explicit native file contents only. Installation/network/capability are
        # intentionally unobserved. Nothing is installed into a donor or service.
        files[root / 'inputs/a0-native-files.json'] = (json.dumps({**native, **a0_web_files('searxng-google')}, sort_keys=True, indent=2) + '\n').encode()
        names = list(KEY_REFERENCES.values()) + ['EXA_API_KEY']
        unobserved.append('A0 reconciliation and current per-job capability')
    for k in ('workspace_root', 'staging_root', 'cache_roots', 'runtime_home'):
        if k in c[worker]: raise HostUnavailable('duplicate_worker_roots')
    return c, root, files, names, unobserved


def preparation(home, profile, worker, reference):
    """Read exact private preparation bytes and recheck original ownership."""
    p = _pin(reference); expected = home / 'workers' / worker / 'runtime-input.json'
    if p.path != expected: raise HostUnavailable('foreign_worker_preparation')
    scope._private(p.path)
    v = json.loads(p.read())
    if (not isinstance(v, dict) or set(v) != {'runtime', 'inputs', 'principal_binding_sha256', 'generation', 'state', 'unobserved'}
            or v['state'] != 'PREPARED_RUNTIME_UNOBSERVED'):
        raise HostUnavailable('invalid_worker_preparation')
    c, root = own_runtime(home, profile, worker, v['runtime'])
    for f in v['inputs']:
        q = _pin(f)
        if not q.path.is_relative_to(root / 'inputs'): raise HostUnavailable('foreign_worker_inputs')
        scope._private(q.path); q.read()
    return v, c
