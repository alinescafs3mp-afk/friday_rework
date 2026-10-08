"""Ordinary-install wiring from native preparer outputs; never a live grant.

The existing per-worker input format and admission consumers own configuration.
Pending receipts deliberately fail the admission consumers. A separate fixed
native observation transition can qualify deployment, never per-job authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.friday_install import canonical, directory, digest, owned_file, pin, publish, read_json, require


def settings(value):
    """Validate explicit deployment/resource declarations before install effects."""
    spec = value['worker_install']
    require(isinstance(spec, dict) and set(spec) == {'dsh', 'a0'}, 'both_worker_install_settings_required')
    require(value['product']['runtime'] == {'enabled': False}, 'generated_workers_require_unconfigured_input')
    require('a0_deployment' in value['product'], 'explicit_normal_a0_deployment_required')
    for worker in ('dsh', 'a0'):
        row = spec[worker]
        extra = {'toolchain_root', 'resources', 'web'} if worker == 'dsh' else {
            'docker', 'policy', 'git_metadata', 'expected_files', 'owner_slot', 'network', 'web'}
        require(isinstance(row, dict) and set(row) == {'budget_seconds', 'max_file_bytes', 'max_total_bytes'} | extra,
                'explicit_worker_install_settings_required')
        for k in ('budget_seconds', 'max_file_bytes', 'max_total_bytes'):
            low = 215 if worker == 'a0' and k == 'budget_seconds' else 1
            ceiling = (1800 if worker == 'a0' else 86400) if k == 'budget_seconds' else (
                16 * 1024**2 if worker == 'a0' or k == 'max_file_bytes' else 64 * 16 * 1024**2)
            require(type(row[k]) is int and low <= row[k] <= ceiling, 'explicit_worker_install_limits_required')
        if worker == 'dsh':
            canonical(row['toolchain_root'])
            require(isinstance(row['resources'], dict) and set(row['resources']) == {
                'memory_bytes', 'cpu_percent', 'tasks', 'shutdown_seconds', 'tmp_bytes'}, 'explicit_dsh_resources_required')
            for k, ceiling in (('memory_bytes', 2*1024**3), ('cpu_percent', 400), ('tasks', 64),
                               ('shutdown_seconds', 2), ('tmp_bytes', 64*1024**2)):
                require(type(row['resources'][k]) is int and 0 < row['resources'][k] <= ceiling,
                        'explicit_dsh_resource_bounds_required')
            require(isinstance(row['web'], dict) and set(row['web']) == {'resolver', 'trust_bundle', 'egress_evidence'},
                    'explicit_dsh_web_inputs_required')
            for ref in row['web'].values(): pin(ref)
        else:
            from plugins.friday_rework.adapters.a0_web import checked_web
            checked_web(row['web'])
            pin(row['docker']); pin(row['policy'])
            require(isinstance(row['network'], dict) and set(row['network']) == {'name', 'endpoints', 'policy'}
                    and row['network']['policy'] == row['policy'], 'explicit_a0_network_policy_required')
            from plugins.friday_rework.adapters.a0_config import LocalNetwork
            from plugins.friday_rework.host_runtime import _pin
            LocalNetwork(row['network']['name'], tuple(row['network']['endpoints']), _pin(row['policy']),
                         value['product']['a0_deployment']).checked()
            require(isinstance(row['git_metadata'], dict) and set(row['git_metadata']) == {'source', 'manifest_sha256'},
                    'explicit_a0_metadata_required')
            from scripts.a0_runtime import metadata_descriptor
            metadata_descriptor(row['git_metadata'])
            require(row['owner_slot'] in ('astra', 'sol'), 'explicit_a0_owner_slot_required')
    return copy.deepcopy(spec)


def _common(value, home, worker, row):
    root = home / 'workers' / worker
    return {'enabled': True, 'runtime_profile': value['product']['profile'], 'runtime_home': str(home),
            'workspace_root': str(root / 'jobs'), 'staging_root': str(root / 'staging'),
            'cache_roots': [str(root / 'cache')], **{k: row[k] for k in
            ('budget_seconds', 'max_file_bytes', 'max_total_bytes')},
            'runtime_receipt': {'path': str(root / 'runtime-receipt.json'), 'sha256': '0' * 64}}


def declared_a0(value, home):
    """Explicit future source/registration plan; no native qualification."""
    row = value['worker_install']['a0']
    from scripts.a0_prepare import service_sources, SERVICE_SOURCE
    from scripts import a0_runtime, rootless_docker_launch
    payload = service_sources(value['project_files'])
    a = _common(value, home, 'a0', row)
    a['a0'] = {'runtime': {'path': str(home / 'worker-runtime-source/scripts/a0_runtime.py'),
                          'sha256': digest(payload['scripts/a0_runtime.py'])},
        'launcher': {'path': str(a0_runtime.LAUNCHER), 'sha256': digest(payload['scripts/rootless_docker_launch.py'])},
        'daemon_unit': {'path': str(rootless_docker_launch.ROOT / 'supervisor' / a0_runtime.DAEMON),
                        'sha256': digest(payload[SERVICE_SOURCE])},
        **{k: row[k] for k in ('docker', 'policy', 'git_metadata', 'expected_files', 'owner_slot', 'web')},
        'deployment': value['product']['a0_deployment'], 'capability': None}
    return a


def prepared_product(value, home, budget):
    """Derive both exact runtimes from checked native preparation outputs."""
    spec = budget.call(settings, value)
    lock = budget.call(read_json, value['sources_lock']['path'])
    donors = {r['id']: r for r in lock['repositories']}
    evidence = {w: [] for w in spec}
    harness = home / 'harness'
    require(str(harness) == value['dsh_donor'], 'owned_harness_destination_required')
    reports = {}
    for phase in ('source', 'toolchain', 'build', 'smoke'):
        path = home / 'preparation/harness' / ('dsh-' + phase + '.json')
        raw = budget.call(owned_file, path)
        report = json.loads(raw)
        identity = report['source']
        require(report.get('donor') == str(harness) and identity.get('commit') == donors['dsh']['commit']
                and identity.get('tree') == donors['dsh']['tree']
                and identity.get('source_lock_sha256') == value['sources_lock']['sha256']
                and identity.get('tracked_clean') is True and identity.get('index_matches_head') is True,
                'native_harness_preparation_changed')
        reports[phase] = report
        evidence['dsh'].append({'path': str(path), 'sha256': digest(raw)})
    smoke = reports['smoke']
    require([r.get('kind') for r in smoke.get('smoke', [])] ==
            ['version', 'help', 'headless-config', 'headless-help']
            and all(r.get('returncode') == 0 and r.get('timeout') is False and r.get('reaped') is True
                    for r in smoke['smoke']), 'complete_native_harness_smoke_required')
    for field in ('install', 'build'):
        r = reports['build'].get(field, {})
        require(r.get('returncode') == 0 and r.get('timeout') is False and r.get('reaped') is True,
                'complete_native_harness_build_required')
    tool = smoke['toolchain']
    require(all(r['toolchain']['node_executable'] == tool['node_executable'] and
                r['toolchain']['node_sha256'] == tool['node_sha256'] for r in reports.values()),
            'harness_toolchain_generation_changed')
    from scripts.dsh_prepare import verify_source, build_inventory
    current = budget.call(verify_source, harness, donors['dsh'])
    current['source_lock_sha256'] = value['sources_lock']['sha256']
    require(all(r['source'] == current for r in reports.values()), 'harness_source_generation_changed')
    inventory = budget.call(build_inventory, harness)
    recorded = budget.call(read_json, home / 'preparation/harness/dsh-build-inventory.json')
    require(inventory == recorded and inventory['file_count'] > 0
            and all(r.get('workspace_build_identity') == {k: inventory[k] for k in ('file_count', 'sha256')}
                    for r in (reports['build'], smoke)), 'harness_generated_build_changed')
    node = {'path': tool['node_executable'], 'sha256': tool['node_sha256']}
    budget.call(pin, node)
    node_path = canonical(node['path']); toolchain = canonical(spec['dsh']['toolchain_root'])
    require(node_path == toolchain / 'bin/node' and not toolchain.is_relative_to(home)
            and not home.is_relative_to(toolchain), 'harness_toolchain_root_mismatch')
    cli = smoke['cli']; require(cli == reports['build']['cli'] and cli['path'] == str(harness / 'apps/cli/lib/bin.js'),
                               'native_harness_cli_path_changed')
    budget.call(pin, cli)
    product = copy.deepcopy(value['product'])
    # Reuse the actual profile compiler and its capacities, never ambient config.
    from tools.configure_product import compose_product
    bundle = budget.call(compose_product, product)
    from tools.render_dsh_local import build_patch
    c = bundle['config']; provider = c['providers']['friday-local']; model = c['model']
    capacity = provider['models'][model['default']]; bounds = capacity['bounded_context']
    patch = build_patch(purpose='temporary-local-test', api='openai-completions',
        base_url=model['base_url'], model=model['default'], api_key_env=provider['key_env'],
        context_window=capacity['context_length'], max_tokens=bounds['main_max_output_tokens'],
        summary_max_tokens=bounds['compression_max_output_tokens'],
        headroom_tokens=bounds['safety_margin_tokens'] + bounds['template_overhead_tokens'], web_profile=product['web']['profile'])
    patch_bytes = (json.dumps(patch, ensure_ascii=False, indent=2) + '\n').encode()
    d = _common(value, home, 'dsh', spec['dsh'])
    d['dsh'] = {'payload_root': str(harness), 'toolchain_root': str(toolchain), 'node': node, 'cli': cli,
        'patch': {'path': str(home / 'workers/dsh/inputs/dsh-local.json'), 'sha256': digest(patch_bytes)},
        'native_files': [{'path': str(harness / n), 'sha256': h} for n, h in inventory['files']],
        'key_name': provider['key_env'], 'profile': 'headless', **spec['dsh']['resources'],
        'web': {'profile': product['web']['profile'], **spec['dsh']['web'],
                'research_policy': {'path': str(home / 'worker-runtime-source/config/RESEARCH.md'),
                                    'sha256': value['project_files']['config/RESEARCH.md']}}}
    a0path = home / 'preparation/a0.json'; raw = budget.call(owned_file, a0path)
    a0 = json.loads(raw); identity = a0['source']
    require(a0.get('donor') == 'a0' and a0.get('checkout') == value['a0_donor']
            and a0.get('source_lock_sha256') == value['sources_lock']['sha256']
            and identity.get('commit') == donors['a0']['commit'] and identity.get('tree') == donors['a0']['tree']
            and identity.get('tracked_bytes_modes_and_index') == 'PASS', 'native_a0_inventory_changed')
    from scripts.a0_prepare import check_checkout
    current, files = budget.call(check_checkout, Path(value['a0_donor']), donors['a0'])
    require(current == identity, 'a0_source_generation_changed')
    from scripts.a0_runtime import check_git_metadata
    budget.call(check_git_metadata, spec['a0']['git_metadata'], budget=budget.check)
    evidence['a0'].append({'path': str(a0path), 'sha256': digest(raw)})
    a = budget.call(declared_a0, value, home)
    # Pending is a real declaration of missing qualification, never ready:true.
    from plugins.friday_rework.host_runtime import configured_runtimes
    rows = {'dsh': d, 'a0': a}
    product['runtime'] = {'enabled': True, 'workers': rows}
    configured_runtimes(product['runtime'])
    from scripts.a0_prepare import service_plan
    budget.call(service_plan, dict(value, product=product), home)
    return product, evidence


def materialize(value, home, product, evidence, budget):
    """Publish only new owned inputs, and pin honest pending qualification."""
    folder = home / 'workers'
    require(not folder.exists() and not folder.is_symlink(), 'existing_workers_not_adopted')
    from tools.configure_product import compose_product
    from plugins.friday_rework.worker_provision import prepare_inputs
    from plugins.friday_rework.host_record import digest as record_digest
    bundle = budget.call(compose_product, product)
    plans = {}
    input_config = bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']['config']
    # Validate the complete coherent package before creating any worker roots.
    for worker, runtime in product['runtime']['workers'].items():
        network = value['worker_install']['a0']['network'] if worker == 'a0' else None
        plans[worker] = budget.call(prepare_inputs, home, product['profile'], worker, runtime,
                                    input_config, a0_network=network)
    require(all(not (root.exists() or root.is_symlink()) for _, root, _, _, _ in plans.values()),
            'existing_worker_not_adopted')
    budget.call(folder.mkdir, mode=0o700)
    for worker, (runtime, root, files, names, unobserved) in plans.items():
        budget.call(root.mkdir, mode=0o700)
        for leaf in ('jobs', 'staging', 'cache', 'inputs'): budget.call((root / leaf).mkdir, mode=0o700)
        for path, data in files.items():
            # Existing provisioning returns bytes; preserve its exact format.
            import os
            budget.check()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as f:
                budget.call(f.write, data); budget.call(f.flush); budget.call(os.fsync, f.fileno())
        source = home / 'plugins/friday_rework'
        pending = {'schema': 'friday-rework.' + ('dsh-runtime.v1' if worker == 'dsh' else 'a0-runtime.v2'),
            'ready': False, 'runtime_sha256': record_digest({k: v for k, v in runtime.items() if k != 'runtime_receipt'}),
            'evidence': evidence[worker]}
        if worker == 'dsh':
            pending['adapter_sha256'] = digest(budget.call(owned_file, source / 'adapters/dsh.py'))
            pending['web_source_pins'] = {'plugins/friday_rework/worker_web.py': value['project_files']['plugins/friday_rework/worker_web.py'],
                'tools/web_profile.py': value['project_files']['tools/web_profile.py'],
                'config/RESEARCH.md': value['project_files']['config/RESEARCH.md']}
            if product['web']['profile'] == 'exa-keyless':
                pending['web_source_pins']['plugins/friday_rework/adapters/dsh_keyless_web.mjs'] = value['project_files']['plugins/friday_rework/adapters/dsh_keyless_web.mjs']
        else:
            pending['source_pins'] = {k: value['project_files']['plugins/friday_rework/' + p] for k, p in {
                'host': 'host.py', 'host_runtime': 'host_runtime.py', 'host_record': 'host_record.py',
                'associations': 'associations.py', 'adapter': 'adapters/a0.py', 'native': 'adapters/a0_native.py',
                'config': 'adapters/a0_config.py', 'profile': 'adapters/a0_profile.py', 'web': 'adapters/a0_web.py'}.items()}
        receipt = root / 'runtime-receipt.json'
        publish(receipt, pending, budget=budget)
        runtime['runtime_receipt']['sha256'] = digest(budget.call(owned_file, receipt, private=True))
        prepared = {'runtime': runtime, 'inputs': [{'path': str(p), 'sha256': digest(b)} for p, b in files.items()],
            'principal_binding_sha256': record_digest({'home': str(home), 'profile': product['profile'],
                                                      'operator': product['dashboard']['operator']}),
            'generation': 1, 'state': 'PREPARED_RUNTIME_UNOBSERVED', 'unobserved': unobserved}
        publish(root / 'runtime-input.json', prepared, budget=budget)
        product['runtime']['workers'][worker] = runtime
    return product


def installed_product(value, home):
    """Read the original generated package; never regenerate or adopt a receipt."""
    from plugins.friday_rework.worker_provision import preparation
    product = copy.deepcopy(value['product']); rows = {}
    marker_path = home / 'FRIDAY-INSTALL.json'
    marker = read_json(marker_path) if marker_path.exists() else {}
    qualified = marker.get('worker_state') == 'BOTH_DEPLOYMENTS_QUALIFIED'
    for worker in ('dsh', 'a0'):
        path = home / 'workers' / worker / 'runtime-input.json'
        ref = {'path': str(path), 'sha256': digest(owned_file(path, private=True))}
        prepared, runtime = preparation(home, product['profile'], worker, ref,
                                        private_check=lambda p: owned_file(p,private=True))
        from scripts.worker_qualification import original_receipt
        pending = original_receipt(home, worker, runtime, marker)
        from plugins.friday_rework.host_record import digest as record_digest
        fields = {'schema', 'ready', 'runtime_sha256', 'evidence'} | (
            {'adapter_sha256', 'web_source_pins'} if worker == 'dsh' else {'source_pins'})
        require(isinstance(pending, dict) and set(pending) == fields
                and pending.get('schema') == 'friday-rework.' + ('dsh-runtime.v1' if worker == 'dsh' else 'a0-runtime.v2')
                and pending.get('ready') is False
                and pending.get('runtime_sha256') == record_digest({k:v for k,v in runtime.items() if k != 'runtime_receipt'}),
                'install_pending_receipt_not_qualification')
        expected_evidence = ([str(home / 'preparation/harness' / ('dsh-' + phase + '.json'))
                              for phase in ('source', 'toolchain', 'build', 'smoke')]
                             if worker == 'dsh' else [str(home / 'preparation/a0.json')])
        evidence = pending['evidence']
        require(isinstance(evidence, list) and len(evidence) == len(expected_evidence)
                and all(isinstance(row, dict) and row.get('path') == expected
                        for row, expected in zip(evidence, expected_evidence)),
                'original_worker_preparation_evidence_required')
        for row in evidence:
            pin(row)
        rows[worker] = runtime
    product['runtime'] = {'enabled': True, 'workers': rows}
    from plugins.friday_rework.host_runtime import configured_runtimes
    configured_runtimes(product['runtime'])
    if qualified:
        from scripts.worker_qualification import checked_product
        return checked_product(value,home,product,marker)
    return product


def installed_files(home):
    """Pin deployment inputs, leaving native job/staging/cache contents owned.

    Mutable job output is checked by its existing per-row adapter/controller.
    It is never adopted as deployment evidence or added to the install marker.
    """
    from scripts.friday_install import directory
    root = home / 'workers'; directory(root)
    require({p.name for p in root.iterdir()} == {'dsh','a0'}, 'installed_worker_roots_changed')
    files = set()
    for kind in ('dsh','a0'):
        worker = root / kind; directory(worker)
        names = {p.name for p in worker.iterdir()}
        extra = set()
        if kind == 'a0' and names & {'bootstrap', 'probe-plan.json'}:
            from plugins.friday_rework.a0_bootstrap import installed_inventory
            extra = installed_inventory(home)
        require(names == {'jobs','staging','cache','inputs','runtime-input.json','runtime-receipt.json'} | extra,
                'installed_worker_layout_changed')
        for name in ('jobs','staging','cache','inputs'): directory(worker / name)
        for name in ('runtime-input.json','runtime-receipt.json'):
            files.add(str((worker / name).relative_to(home)))
        for path in (worker / 'inputs').rglob('*'):
            require(path.resolve() == path and not path.is_symlink(), 'installed_worker_input_path_changed')
            if path.is_file(): files.add(str(path.relative_to(home)))
    return files
