"""Remaining native installer preparation for an existing ordinary receiver.

The new request owns one finite attempt. Native reports stay in its exclusive
directory; existing attempts, users, hosts and qualification remain untouched.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import resource
from pathlib import Path

from scripts import friday_install as f
from scripts import friday_ordinary_install as ordinary

SCHEMA = 'friday.ordinary-worker-preparation.v1'
NAMES = {'source': 'dsh-source.json', 'toolchain': 'dsh-toolchain.json',
         'build': 'dsh-build.json', 'smoke': 'dsh-smoke.json',
         'inventory': 'dsh-build-inventory.json', 'a0': 'a0.json'}
BUILD_FIELDS = {'memory_bytes', 'swap_bytes', 'cpu_percent', 'tasks', 'affinity',
                'fsize_bytes', 'core_bytes', 'seconds', 'cleanup_seconds'}


def build_settings(value):
    """One explicit reviewed build-only trial; never change job runtime limits."""
    f.require(type(value) is dict and set(value) == BUILD_FIELDS and
              all(type(value[k]) is int for k in BUILD_FIELDS - {'affinity'}) and
              type(value['affinity']) is list and all(type(n) is int for n in value['affinity']) and
              value == {'memory_bytes': 6*1024**3, 'swap_bytes': 0, 'cpu_percent': 200,
                        'tasks': 256, 'affinity': [0, 1], 'fsize_bytes': 256*1024**2,
                        'core_bytes': 0, 'seconds': 900, 'cleanup_seconds': 60},
              'ordinary_worker_explicit_build_resources_required')
    return value


def reference(path):
    return {'path': str(path), 'sha256': f.digest(f.owned_file(path))}


def configuration_settings(config):
    return config['plugins']['entries']['friday_rework']['settings']


def staged_sources(value, home, budget):
    from scripts.a0_prepare import service_sources
    payload = budget.call(service_sources, value['project_files'])
    for name, data in payload.items():
        f.require(f.owned_file(home / 'worker-runtime-source' / name) == data,
                  'ordinary_worker_staged_source_changed')
    f.require(f.digest(f.owned_file(home / 'worker-runtime-source/config/RESEARCH.md')) ==
              value['project_files']['config/RESEARCH.md'], 'ordinary_worker_research_source_changed')


def installed(request, budget):
    fields = {'schema', 'request_id', 'seconds', 'home', 'current_input', 'preparation_input',
              'marker', 'source_receipt', 'configuration', 'profile',
              'reports', 'history', 'native_unit', 'build_resources'}
    f.require(type(request) is dict and set(request) == fields and request['schema'] == SCHEMA
              and isinstance(request['request_id'], str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', request['request_id'])
              and type(request['seconds']) is int and 30 <= request['seconds'] <= 7200,
              'ordinary_worker_explicit_request_required')
    home = f.directory(f.canonical(request['home']))
    build_settings(request['build_resources'])
    paths = {name: budget.call(f.pin, request[name]) for name in
             ('current_input', 'preparation_input', 'marker', 'source_receipt', 'configuration', 'profile', 'native_unit')}
    for name, path in {'marker': home / f.MARKER, 'source_receipt': home / 'hermes-agent.source.json',
                       'configuration': home / 'config.yaml', 'profile': home / 'FRIDAY-PROFILE.json'}.items():
        f.require(paths[name] == path, 'ordinary_worker_installed_paths_required')
    current = f.read_json(paths['current_input']); value = f.read_json(paths['preparation_input'])
    f.require(current['home'] == value['home'] == str(home)
              and request['current_input'] != request['preparation_input'], 'ordinary_worker_new_input_required')
    # A new reviewed installer inventory and a freshly admitted policy are data.
    # Neither changes the old install clock, resources, model or operational spec.
    old = copy.deepcopy(current); new = copy.deepcopy(value)
    for candidate in (old, new):
        candidate.pop('project_files')
        candidate['worker_install']['dsh']['web'].pop('egress_evidence')
    f.require(old == new and value['product']['runtime'] == {'enabled': False},
              'ordinary_worker_operational_settings_changed')
    worker_helper = 'scripts/friday_worker_preparation.py'
    registration_helper = 'scripts/friday_ordinary_a0_registration.py'
    # Admit the coherent accepted installer package, including the optional A0
    # registration entry. Every other source pin and every old inventory member
    # stays fixed; spec_checked still verifies the complete fresh project root.
    allowed = {'scripts/friday_install.py', 'scripts/friday_ordinary_install.py',
               'scripts/worker_install.py', worker_helper, 'scripts/a0_prepare.py',
               registration_helper}
    prior = current['project_files']; fresh = value['project_files']
    f.require(set(fresh) == set(prior) | {worker_helper} |
              ({registration_helper} if registration_helper in fresh else set())
              and all(fresh[n] == sha for n, sha in prior.items() if n not in allowed),
              'ordinary_worker_only_installer_source_change_required')
    _, donors = budget.call(f.spec_checked, value)  # Checks current policy before effects.
    marker = f.read_json(paths['marker']); receipt = f.read_json(paths['source_receipt'])
    f.require(marker.get('schema') == f.SCHEMA and marker.get('home') == str(home)
              and marker.get('source') == str(home / 'hermes-agent')
              and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
              and marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
              and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
              and marker.get('runtime_ready') is False
              and marker.get('input_sha256') == request['current_input']['sha256']
              and marker.get('source_receipt_sha256') == request['source_receipt']['sha256'],
              'ordinary_worker_current_installation_required')
    budget.call(f.composition_checked, current, home / 'hermes-agent', receipt, donors['hermes'])
    ordinary.checked_plugin_inventory(home, marker['plugin_files'])
    staged_sources(value, home, budget)
    f.native_packages(home / 'hermes-agent')
    from hermes_cli.friday_ordinary_gateway import check
    check(home, role=False)
    from hermes_cli.config import require_readable_config_before_write
    config = require_readable_config_before_write(paths['configuration'])
    settings = configuration_settings(config)
    templates = settings['onboarding']['templates']
    f.require(settings.get('runtime') == {'enabled': False} and 'worker_requirements' not in settings
              and templates['friday-local'].get('worker_inputs') == {'required': ['dsh', 'a0'], 'workers': {}}
              and 'worker_inputs' not in templates['friday-ordinary-local'],
              'ordinary_worker_empty_declarations_required')
    reports = request['reports']; history = request['history']
    f.require(type(reports) is dict and set(reports) <= set(NAMES)
              and type(history) is list, 'ordinary_worker_explicit_reports_required')
    for name, ref in reports.items():
        path = budget.call(f.pin, ref)
        f.require(path.is_relative_to(home / 'preparation') and path.name == NAMES[name],
                  'ordinary_worker_foreign_report')
    for ref in history:
        path = budget.call(f.pin, ref)
        f.require(path.is_relative_to(home / 'preparation') or
                  (path.parent == home and path.name.startswith('FRIDAY-INSTALL.')),
                  'ordinary_worker_foreign_history')
    return home, value, marker, config, donors


def reusable(value, home, reports, donors, budget):
    """Check real current native identity before skipping a completed phase."""
    from scripts.dsh_prepare import verify_source, build_inventory
    if not reports: return
    if set(reports) - {'a0'}:
        identity = budget.call(verify_source, home / 'harness', donors['dsh'])
        identity['source_lock_sha256'] = value['sources_lock']['sha256']
        node = Path(value['worker_install']['dsh']['toolchain_root']) / 'bin/node'
        for phase in ('source', 'toolchain', 'build', 'smoke'):
            if phase not in reports: continue
            row = f.read_json(f.pin(reports[phase])); tool = row.get('toolchain', {})
            f.require(row.get('donor') == str(home / 'harness') and row.get('source') == identity
                      and tool.get('node_executable') == str(node),
                      'ordinary_worker_completed_source_changed')
            # Node is a protected executable and may exceed the document cap.
            budget.call(f.bootstrap_pin, {'path': str(node), 'sha256': tool.get('node_sha256')})
            if phase == 'build':
                f.require(all(row.get(k, {}).get('returncode') == 0 and
                              row[k].get('timeout') is False and row[k].get('reaped') is True
                              for k in ('install', 'build')), 'complete_native_harness_build_required')
            if phase == 'smoke':
                observations = row.get('smoke', [])
                f.require([r.get('kind') for r in observations] ==
                          ['version', 'help', 'headless-config', 'headless-help'] and
                          all(r.get('returncode') == 0 and r.get('timeout') is False and r.get('reaped') is True
                              for r in observations), 'complete_native_harness_smoke_required')
            if phase in ('build', 'smoke'):
                f.require('inventory' in reports, 'ordinary_worker_inventory_required')
                inventory = budget.call(build_inventory, home / 'harness')
                f.require(inventory == f.read_json(f.pin(reports['inventory'])) and inventory['file_count'] > 0
                          and row.get('workspace_build_identity') ==
                          {k: inventory[k] for k in ('file_count', 'sha256')}
                          and row.get('cli') == reference(home / 'harness/apps/cli/lib/bin.js'),
                          'ordinary_worker_completed_build_changed')
    if 'a0' in reports:
        from scripts.a0_prepare import check_checkout
        identity, _ = budget.call(check_checkout, Path(value['a0_donor']), donors['a0'])
        row = f.read_json(f.pin(reports['a0']))
        f.require(row.get('donor') == 'a0' and row.get('checkout') == value['a0_donor']
                  and row.get('source') == identity and row.get('source_lock_sha256') == value['sources_lock']['sha256'],
                  'ordinary_worker_completed_a0_changed')


def native_resources(resources, *, membership=Path('/proc/self/cgroup'), root=Path('/sys/fs/cgroup')):
    """Read the existing native scope; never install or relax resource limits."""
    # Preparation runs only inside a separately admitted native resource scope.
    # This command neither creates a service nor changes its limits.
    rows = membership.read_text().splitlines()
    f.require(len(rows) == 1 and rows[0].startswith('0::/') and '..' not in Path(rows[0][3:]).parts,
              'ordinary_worker_native_resource_scope_required')
    group = root / rows[0][3:].lstrip('/')
    build_settings(resources)
    f.require(group != root and
              (group / 'memory.max').read_text().strip() == str(resources['memory_bytes']) and
              (group / 'pids.max').read_text().strip() == str(resources['tasks']) and
              (group / 'memory.swap.max').read_text().strip() == str(resources['swap_bytes']),
              'ordinary_worker_native_resource_scope_required')
    cpu = [int(n) for n in (group / 'cpu.max').read_text().split()]
    f.require(len(cpu) == 2 and cpu[0] * 100 == cpu[1] * resources['cpu_percent'],
              'ordinary_worker_native_cpu_scope_required')
    f.require(os.sched_getaffinity(0) == set(resources['affinity']) and
              resource.getrlimit(resource.RLIMIT_CORE) == (resources['core_bytes'],)*2 and
              resource.getrlimit(resource.RLIMIT_FSIZE) == (resources['fsize_bytes'],)*2,
              'ordinary_worker_native_process_limits_required')


def native_preparation(value, home, tx, reports, donors, budget, verify, *, build_resources):
    """Existing native preparers, same namespace custody and finite deadline."""
    missing = set(NAMES) - set(reports)
    if not missing: return reports
    from scripts.install_containment import Containment
    build_settings(build_resources)
    reserve = build_resources['cleanup_seconds']
    budget.check(reserve=reserve+5)
    native_resources(build_resources)
    env = f.clean_environment(home)
    env['PATH'] = value['worker_install']['dsh']['toolchain_root'] + '/bin:' + env.get('PATH', '/usr/bin:/bin')
    custody = Containment(value['containment'], budget, env)
    verify()
    budget.check(reserve=reserve+5)
    custody.probe(value['bootstrap_python']['path'], f.ROOT)
    verify()
    evidence = tx / 'harness'; evidence.mkdir(mode=0o700)
    def execute(phase, argv):
        verify(); native_resources(build_resources); budget.check(reserve=reserve)
        custody.run(argv, f.ROOT, timeout=min(900, budget.check(reserve=reserve)), log=tx / ('native-' + phase))
        verify()
    python = value['bootstrap_python']['path']
    if 'source' in reports or 'toolchain' in reports:
        execute('check', [python, '-B', str(f.ROOT / 'scripts/dsh_prepare.py'), 'check',
                '--donor', value['dsh_donor'], '--lock', value['sources_lock']['path'], '--evidence', str(evidence)])
        checked = f.read_json(evidence / 'dsh-check.json')
        for phase in ('source', 'toolchain'):
            if phase not in reports: continue
            previous = f.read_json(f.pin(reports[phase]))
            f.require(checked['source'] == previous['source'] and checked['donor'] == previous['donor']
                      and checked['toolchain'] == {k: v for k, v in previous['toolchain'].items() if k != 'observed_pnpm'},
                      'ordinary_worker_completed_toolchain_changed')
    # A build is the existing native preparer's indivisible install+build phase;
    # failed observations are never treated as a completed dependency inventory.
    for phase in ('source', 'toolchain', 'build', 'smoke'):
        if phase in reports: continue
        argv = [python, '-B', str(f.ROOT / 'scripts/dsh_prepare.py'), phase,
                '--donor', value['dsh_donor'], '--lock', value['sources_lock']['path'],
                '--evidence', str(evidence), '--build-timeout', str(min(900, int(budget.check(reserve=reserve))))]
        execute(phase, argv)
        reports[phase] = reference(evidence / NAMES[phase])
    if 'inventory' not in reports:
        reports['inventory'] = reference(evidence / NAMES['inventory'])
    if 'a0' not in reports:
        path = tx / 'a0.json'
        execute('a0', [python, '-B', str(f.ROOT / 'scripts/a0_prepare.py'), 'check',
                      '--lock', value['sources_lock']['path'], '--checkout', value['a0_donor'], '--output', str(path)])
        reports['a0'] = reference(path)
    return reports


def prepare(request, request_path, budget):
    home, value, marker, config, donors = installed(request, budget)
    raw = f.owned_file(request_path, private=True)
    f.require(json.loads(raw, object_pairs_hook=f.unique) == request, 'ordinary_worker_request_changed')
    sha = f.digest(raw)
    parent = home / 'preparation'; f.directory(parent)
    tx = parent / ('ordinary-workers-' + request['request_id'])
    f.require(not os.path.lexists(tx), 'ordinary_worker_attempt_consumed_no_retry')
    reports = copy.deepcopy(request['reports'])
    staged_native_files = []
    reusable(value, home, reports, donors, budget)
    def verify():
        budget.check()
        f.require(f.digest(f.owned_file(request_path, private=True)) == sha, 'ordinary_worker_request_changed')
        for name in ('current_input', 'preparation_input', 'marker', 'source_receipt', 'configuration', 'profile', 'native_unit'):
            f.pin(request[name])
        for ref in [*request['reports'].values(), *request['history']]: f.pin(ref)
        # Every command and final publication consumes the reviewed nested
        # source/executable/policy pins, not just the outer input JSON hash.
        budget.call(f.spec_checked, value)
        ordinary.checked_plugin_inventory(home, marker['plugin_files'])
        staged_sources(value, home, budget)
        for ref in staged_native_files: budget.call(f.pin, ref)
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify(); tx.mkdir(mode=0o700)
        original = {'request_sha256': sha, 'request_id': request['request_id'],
                    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    'started_mono': budget.deadline - request['seconds'], 'deadline_mono': budget.deadline,
                    'seconds': request['seconds'], 'resume_allowed': False}
        f.publish(tx / 'intent.json', original, budget=budget)
        try:
            f.require(set(reports) == set(NAMES) or request['seconds'] == request['build_resources']['seconds'],
                      'ordinary_worker_original_build_clock_required')
            reports = native_preparation(value, home, tx, reports, donors, budget, verify,
                                         build_resources=request['build_resources'])
            from scripts.worker_install import prepared_product
            product, evidence = budget.call(prepared_product, value, home, budget, preparation=reports)
            verify()
            # Finish intact donor/build checks before adding the product-only
            # keyless source; it is not part of the native build inventory.
            budget.call(prepared_product, value, home, budget, preparation=reports)
            def declaration_files():
                # Pending host maintenance must leave the donor reusable. Stage
                # only under the same stop/config locks as declaration writes.
                if product['web']['profile'] == 'exa-keyless':
                    keyless = budget.call(f.stage_keyless_provider, home / 'harness')
                    f.require(keyless['sha256'] == value['project_files'][
                        'plugins/friday_rework/adapters/dsh_keyless_web.mjs'],
                        'ordinary_worker_keyless_source_changed')
                    staged_native_files.append({k: keyless[k] for k in ('path', 'sha256')})
                    product['runtime']['workers']['dsh']['dsh']['native_files'].extend(staged_native_files)
                from plugins.friday_rework.user_worker_join import installation_inputs, validate_installation_inputs
                declarations = validate_installation_inputs(installation_inputs(product['runtime']))
                f.require(set(declarations['workers']) == {'dsh', 'a0'} and
                          declarations['source_scope'] == {'home': str(home), 'profile': value['product']['profile']},
                          'ordinary_worker_both_declarations_required')
                changed = copy.deepcopy(config)
                configuration_settings(changed)['onboarding']['templates']['friday-local']['worker_inputs'] = declarations
                updated = copy.deepcopy(marker)
                updated['input_sha256'] = request['preparation_input']['sha256']
                updated['ordinary_gateway']['operator_entry'] = {
                    'input': request['preparation_input'], 'script': {'path': str(f.ROOT / 'scripts/friday_native.py'),
                    'sha256': value['project_files']['scripts/friday_native.py']}}
                from hermes_cli.friday_ordinary_gateway import normalized_configuration
                from hermes_cli.config_effective import _effective
                updated['ordinary_gateway']['configuration_sha256'] = normalized_configuration(_effective(changed))
                return changed, updated
            pending = publish_declarations(request, home, tx, declaration_files, budget, verify)
            from scripts.a0_prepare import service_plan
            plan = service_plan(dict(value, product=product), home)
            absent = [plan[k] for k in ('launcher', 'unit_source', 'registration') if not os.path.lexists(plan[k])]
            result = {'state': ('PENDING_NATIVE_HOST_MAINTENANCE_REQUIRED' if pending else
                               'BOTH_WORKER_DECLARATIONS_PUBLISHED_QUALIFICATION_PENDING'), 'ready': False,
                      'runtime_enabled': False, 'runtime_acceptance': 'NOT_GRANTED', 'reports': reports,
                      'a0_service': 'UNREGISTERED' if absent else 'REGISTRATION_NOT_OBSERVED',
                      'missing_a0_service_paths': absent, 'original_attempt': original,
                      'configuration_sha256': reference(home / 'config.yaml')['sha256'],
                      'next': ('Native stop of exact gateway and WebUI owners; new explicit bounded publication request reusing completed reports'
                               if pending else 'Native fresh start of gateway/WebUI, separately admitted A0 registration, real user grant and qualification')}
            if pending: result['maintenance_reason'] = pending
            f.publish(tx / 'result.json', result, budget=budget)
            return result
        except BaseException as exc:
            diagnostic = f.retained_diagnostic(exc, 'ordinary-worker-preparation')
            try:
                f.publish(tx / 'failure.json', {'state': 'PENDING_PREPARATION_NO_RUNTIME_ADMISSION',
                                               'original_attempt': original, 'diagnostic': diagnostic,
                                               'reports': reports, 'resume_allowed': False})
            except BaseException as secondary:
                f.remember_secondary(exc, secondary)
            raise
    finally:
        os.close(fd)


def publish_declarations(request, home, tx, declaration_files, budget, verify):
    """The live boot identity is immutable. Publish only under native stop locks."""
    from hermes_cli.config import config_write_transaction
    entered = False
    try:
        with ordinary.stopped_consumers(home, request['native_unit'], budget) as prove:
            entered = True
            # The config writer lock is held only for this finite publication.
            with config_write_transaction(home / 'config.yaml'):
                verify(); prove()
                changed, updated = declaration_files()
                verify(); prove()
                saved = {name: ordinary.update_file_state(home / name) for name in ('config.yaml', f.MARKER)}
                f.require(all(f.digest(row['data']) == request['configuration' if name == 'config.yaml' else 'marker']['sha256']
                              for name, row in saved.items()), 'ordinary_worker_publication_beforeimage_changed')
                for name, row in saved.items(): ordinary.write(tx / ('before-' + name), row['data'])
                owned = {}
                try:
                    ordinary.publish_update_file(home / 'config.yaml',
                        __import__('hermes_yaml').safe_dump(changed, allow_unicode=True, sort_keys=False).encode(),
                        saved['config.yaml']['mode'], saved['config.yaml'], owned, 'config.yaml')
                    updated['profile_files']['config.yaml'] = f.digest(f.owned_file(home / 'config.yaml', private=True))
                    ordinary.publish_update_file(home / f.MARKER, ordinary.encoded(updated),
                        saved[f.MARKER]['mode'], saved[f.MARKER], owned, f.MARKER)
                    from hermes_cli.friday_ordinary_gateway import check
                    check(home, role=False); prove()
                except BaseException:
                    ordinary.restore_update_files(home, saved, owned)
                    raise
    except f.Refused as exc:
        if exc.reason == 'ordinary_update_native_lock_release_unconfirmed':
            from scripts.dsh_prepare import StopUnconfirmed
            raise StopUnconfirmed('native publication lock release requires reconciliation') from exc
        if entered: raise
        return exc.reason
    except OSError:
        if entered: raise
        return 'ordinary_worker_native_maintenance_not_proved'
    return None
