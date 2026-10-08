#!/usr/bin/env python3
"""Finite Friday composition over native preparers, PM and launchers.

Installation is an explicit effectful operator action. Planning and inspection
never install dependencies, read credentials or grant worker admission.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import importlib.util
import importlib.machinery
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'friday.native-install.v1'
MARKER = 'FRIDAY-INSTALL.json'
FAILURE = 'FRIDAY-INSTALL.failure.json'


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Friday entry refused: phase=arguments reason=invalid_cli_arguments\n')


class Refused(ValueError):
    """A reason supplied by this source, rather than arbitrary exception text."""
    def __init__(self, reason):
        self.reason = reason if re.fullmatch('[a-z][a-z0-9_]{0,127}', reason) else 'invalid_input'
        super().__init__(self.reason)


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def safe_diagnostic(exc, phase):
    from scripts.dsh_prepare import CommandFailed, StopUnconfirmed, safe_observation
    result = {'phase': phase, 'reason': 'native_operation_failed'}
    if isinstance(exc, StopUnconfirmed):
        result.update(reason='stop_unconfirmed', cessation='UNCONFIRMED')
        if hasattr(exc, 'observation'):
            result.update(safe_observation(exc.observation))
            result.update(reason='stop_unconfirmed', cessation='UNCONFIRMED')
    elif isinstance(exc, CommandFailed):
        result.update(safe_observation(exc.observation))
        result['cessation'] = 'REAPED' if exc.observation['reaped'] else 'UNCONFIRMED'
    elif isinstance(exc, Refused):
        result['reason'] = exc.reason
    elif isinstance(exc, OSError):
        result.update(reason='native_io_failed', errno=exc.errno)
    elif isinstance(exc, (KeyError, TypeError)):
        result['reason'] = 'invalid_input_shape'
    elif isinstance(exc, ValueError) and exc.args == ('original_install_budget_exhausted',):
        result['reason'] = 'original_install_budget_exhausted'
    return result


def diagnostic_text(value):
    parts = [f"phase={value['phase']}", f"reason={value['reason']}"]
    if 'returncode' in value:
        parts.extend([f"child_exit={value['returncode']}",
                      f"timeout={str(value['timeout']).lower()}",
                      f"reaped={str(value['reaped']).lower()}"])
    return ' '.join(parts)


def canonical(value):
    p = Path(value)
    require(p.is_absolute() and str(p) == value and '..' not in p.parts
            and p != Path('/') and p.resolve() == p, 'real_absolute_path_required')
    return p


def owned_file(path, *, private=False):
    p = canonical(str(path))
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_nlink == 1
                and (not private or not info.st_mode & 0o077), 'owned_regular_input_required')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(64 * 1024**2 + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_nlink')
        require(len(data) <= 64 * 1024**2 and all(getattr(info, k) == getattr(after, k) for k in fields),
                'input_changed_or_too_large')
        return data
    finally:
        os.close(fd)


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate_input_field')
        out[key] = value
    return out


def read_json(path):
    return json.loads(owned_file(path, private=True), object_pairs_hook=unique)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and isinstance(value['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'exact_input_pin_required')
    require(digest(owned_file(value['path'])) == value['sha256'], 'input_pin_changed')
    return canonical(value['path'])


def bootstrap_pin(value):
    """Hash the protected PM Python as a bounded executable, not JSON/source.

    The native standalone Python can exceed the 64 MiB document limit. Read
    this explicitly typed input in chunks; all other input limits stay intact.
    """
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and isinstance(value['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'exact_input_pin_required')
    path = canonical(value['path'])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        limit = 256 * 1024**2
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and not before.st_mode & 0o022
                and bool(before.st_mode & 0o111) and 0 < before.st_size <= limit,
                'owned_protected_bootstrap_executable_required')
        hasher = hashlib.sha256(); total = 0
        while True:
            block = os.read(fd, min(1024**2, limit - total + 1))
            if not block:
                break
            total += len(block)
            require(total <= limit, 'bootstrap_executable_too_large')
            hasher.update(block)
        after, named = os.fstat(fd), path.lstat()
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_nlink')
        require(total == before.st_size and all(
            getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields),
            'bootstrap_executable_changed')
        require(hasher.hexdigest() == value['sha256'], 'input_pin_changed')
    finally:
        os.close(fd)
    return path


def directory(path):
    p = canonical(str(path)); info = p.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'owned_private_directory_required')
    return p


def spec_checked(value):
    fields = {'home', 'bootstrap_python', 'hermes_donor', 'hermes_prepare',
              'sources_lock', 'dsh_donor', 'a0_donor', 'product', 'project_files', 'seconds', 'containment'}
    require(isinstance(value, dict) and set(value) == fields | (set(value) & {'dashboard_tls', 'credential_sources', 'worker_install'}), 'explicit_install_fields_required')
    if 'credential_sources' in value:
        from scripts.install_credentials import references
        references(value['credential_sources'])
    home = canonical(value['home']); directory(home.parent)
    require(home != Path.home() / '.hermes' and home != ROOT
            and not ROOT.is_relative_to(home), 'separate_product_home_required')
    require(type(value['seconds']) is int and 30 <= value['seconds'] <= 7200,
            'finite_install_budget_required')
    bootstrap_pin(value['bootstrap_python'])
    for key in ('hermes_prepare', 'sources_lock'):
        pin(value[key])
    for key in ('hermes_donor', 'dsh_donor', 'a0_donor'):
        canonical(value[key])
    require(canonical(value['dsh_donor']) == home / 'harness', 'owned_harness_destination_required')
    files = value['project_files']
    require(isinstance(files, dict) and files, 'reviewed_project_inventory_required')
    required = {'scripts/friday_install.py', 'scripts/friday_native.py',
                'scripts/dsh_prepare.py', 'plugins/friday_rework/adapters/dsh_keyless_web.mjs', 'scripts/a0_prepare.py', 'scripts/install_containment.py',
                'scripts/friday_start.py', 'scripts/install_credentials.py',
                'scripts/a0_runtime.py', 'scripts/rootless_docker_launch.py',
                'scripts/friday-rework-docker.service',
                'tools/configure_product.py', 'tools/configure_local_test.py',
                'tools/web_profile.py', 'config/SOUL.md', 'config/RESEARCH.md'}
    if 'worker_install' in value:
        required.update({'scripts/worker_install.py','scripts/worker_qualification.py', 'tools/render_dsh_local.py'})
    required.update(str(p.relative_to(ROOT)) for p in (ROOT / 'plugins/friday_rework').rglob('*')
                    if p.is_file())
    required.update(str(p.relative_to(ROOT)) for p in (ROOT / 'patches/hermes').rglob('*')
                    if p.is_file())
    require(required.issubset(files), 'complete_installer_plugin_inventory_required')
    for name, expected in files.items():
        require(isinstance(name, str) and not name.startswith('/')
                and '..' not in Path(name).parts and isinstance(expected, str)
                and re.fullmatch('[0-9a-f]{64}', expected), 'invalid_project_inventory')
        require(digest(owned_file(ROOT / name)) == expected, 'project_source_changed')
    from scripts.a0_prepare import service_sources
    service_sources(files, root=ROOT)
    product = value['product']
    require(isinstance(product, dict) and product.get('profile') == 'default',
            'native_default_receiving_home_required')
    require(isinstance(product.get('dashboard'), dict)
            and set(product['dashboard']) == {'host', 'port', 'public_url', 'operator'} | ({'tls'} if 'tls' in product['dashboard'] else set()),
            'explicit_dashboard_authority_required')
    # Reuse the existing pure local/capacity validator before any install
    # effects. Full native profile/provider/auth consumption happens later.
    # Load pure validators without claiming Hermes' native `tools` package.
    name = '_friday_install_validation'
    if name not in sys.modules:
        module = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(name, loader=None, is_package=True))
        module.__path__ = [str(ROOT / 'tools')]
        sys.modules[name] = module
    require(list(sys.modules[name].__path__) == [str(ROOT / 'tools')], 'foreign_validator_package')
    build_config = importlib.import_module(name + '.configure_local_test').build_config
    hermes_web_config = importlib.import_module(name + '.web_profile').hermes_web_config
    # Host-root ownership is checked at command admission, not by this pure
    # consumer inside an unprivileged namespace (where host UID 0 is unmapped).
    containment = value['containment']
    require(isinstance(containment, dict) and set(containment) == {'path', 'sha256'}
            and containment['path'] == '/usr/bin/bwrap'
            and isinstance(containment['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', containment['sha256']),
            'explicit_system_bubblewrap_pin_required')
    require(set(product) == {'profile', 'inference', 'web', 'dashboard', 'accounts', 'runtime'} | ({'a0_deployment'} if 'a0_deployment' in product else set()),
            'explicit_normal_product_required')
    if 'a0_deployment' in product:
        spec = importlib.util.spec_from_file_location('_friday_a0_profile_validator', ROOT / 'plugins/friday_rework/adapters/a0_profile.py')
        profile_validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile_validator)
        deployment = profile_validator.checked_profile(product['a0_deployment'])
        selected = product['inference']
        chat = deployment['chat']
        require(chat['endpoint'] == selected['base_url'] and chat['model'] == selected['model']
                and chat['context_length'] == selected['context']
                and chat['max_output_tokens'] == selected['main_output']
                and selected['key_env'] == 'FRIDAY_LLM_API_KEY', 'a0_product_inference_profile_mismatch')
    if 'worker_install' in value:
        from scripts.worker_install import settings
        settings(value)
    build_config(**product['inference'])
    require(product['web'].get('profile') in ('exa-paid','exa-keyless')
            and set(product['web']) == {'profile', 'extract_char_limit', 'extract_timeout'}
            and all(product['web'][k] is not None for k in ('extract_char_limit', 'extract_timeout')),
            'mandatory_scoped_web_required')
    hermes_web_config(**product['web'])
    dash = product['dashboard']; ipaddress.ip_address(dash['host'])
    require(type(dash['port']) is int and 1 <= dash['port'] <= 65535, 'explicit_dashboard_port_required')
    public = urlsplit(dash['public_url'])
    local_http = (public.scheme == 'http' and public.hostname in ('localhost', '127.0.0.1', '::1')
                  and ipaddress.ip_address(dash['host']).is_loopback)
    require((public.scheme == 'https' or local_http) and public.hostname and public.username is None
            and public.password is None and public.port == dash['port']
            and public.path in ('', '/') and not public.query and not public.fragment,
            'protected_dashboard_public_authority_required')
    dashboard_tls_inputs(value, home)
    lock = json.loads(owned_file(pin(value['sources_lock'])))
    donors = {r['id']: r for r in lock['repositories']}
    require({'hermes', 'dsh', 'a0'}.issubset(donors), 'complete_donor_pins_required')
    return home, donors


def dashboard_tls_inputs(value, home):
    """Explicit protected deployment inputs; no issuer or trust-store writes."""
    dash = value['product']['dashboard']
    names = {'certfile': 'dashboard-tls/server.pem', 'keyfile': 'dashboard-tls/server.key',
             'cafile': 'dashboard-tls/ca.pem'}
    if 'tls' not in dash:
        require('dashboard_tls' not in value, 'undeclared_dashboard_tls_inputs')
        return {}
    require(dash['tls'] == names, 'explicit_owned_dashboard_tls_files_required')
    bind = ipaddress.ip_address(dash['host'])
    require(not bind.is_unspecified and not bind.is_multicast
            and urlsplit(dash['public_url']).scheme == 'https', 'explicit_dashboard_tls_authority_required')
    inputs = value.get('dashboard_tls')
    require(isinstance(inputs, dict) and set(inputs) == set(names), 'dashboard_tls_deployment_inputs_required')
    parents = set(); output = {}
    for key, row in inputs.items():
        path = pin(row); directory(path.parent); parents.add(path.parent)
        require(path.name == Path(names[key]).name and not path.is_relative_to(home),
                'separate_owned_dashboard_tls_input_required')
        raw = owned_file(path, private=True)
        require(digest(raw) == row['sha256'], 'dashboard_tls_input_changed')
        output[key] = raw
    require(len(parents) == 1, 'one_owned_dashboard_tls_input_scope_required')
    return output


def commands(value):
    """Generate native argv; no custom PM flags or replacement service backend."""
    home, _ = spec_checked(value); source = home / 'hermes-agent'
    from scripts.install_containment import checked_binary
    checked_binary(value['containment'])
    python = value['bootstrap_python']['path']; helper = str(ROOT / 'scripts/friday_native.py')
    launcher = str(source / '.hermes/bin/hermes')
    from scripts.a0_prepare import service_plan
    planned = value
    if 'worker_install' in value:
        from scripts.worker_install import declared_a0
        product = dict(value['product'], runtime=declared_a0(value, home))
        planned = dict(value, product=product)
    return {
        'worker_preparation_mode': 'BOTH_WORKERS_REQUIRED' if 'worker_install' in value else 'LEGACY_EXPLICIT_TEMPLATE',
        'a0_service_effect_plan': service_plan(planned, home),
        'compose': [python, '-B', value['hermes_prepare']['path'], '--repository', str(ROOT),
                    '--donor', value['hermes_donor'], '--destination', str(source),
                    '--seconds', str(min(120, value['seconds']))],
        'tools': [python, '-B', '-m', 'pm.cli', 'install', '--tools-only'],
        'dependencies': [python, '-B', '-m', 'pm.cli', 'install', '--extra', 'all',
                         '--extra', 'telegram', '--extra', 'web', '--extra', 'exa'],
        'native_completion': ['<native PM project_python>', '-B', helper, 'install'],
        'harness': [[python, '-B', str(ROOT / 'scripts/dsh_prepare.py'), phase,
                     '--donor', value['dsh_donor'], '--lock', value['sources_lock']['path'],
                     '--evidence', str(home / 'preparation/harness')]
                    for phase in ('source', 'toolchain', 'build', 'smoke')],
        'a0_inventory': [python, '-B', str(ROOT / 'scripts/a0_prepare.py'), 'prepare',
                         '--lock', value['sources_lock']['path'], '--checkout', value['a0_donor'],
                         '--output', str(home / 'preparation/a0.json')],
        'gateway_install': [launcher, '-p', 'default', 'gateway', 'install',
                            '--no-start-now', '--no-start-on-login'],
        'gateway_start': [launcher, '-p', 'default', 'gateway', 'start'],
        'dashboard': [launcher, '-p', 'default', 'dashboard', '--host',
                      value['product']['dashboard']['host'], '--port',
                      str(value['product']['dashboard']['port']), '--no-open'],
    }


def clean_environment(home):
    # Preserve the OS account HOME: native host rendezvous remains host-wide.
    # No ambient provider/token/auth/profile/runtime/PYTHONPATH influences PM.
    names = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM',
             'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'https_proxy', 'http_proxy', 'no_proxy')
    env = {k: os.environ[k] for k in names if k in os.environ}
    env.update(HERMES_HOME=str(home), PYTHONDONTWRITEBYTECODE='1', GIT_OPTIONAL_LOCKS='0',
               GIT_TERMINAL_PROMPT='0', PYTHONNOUSERSITE='1')
    return env


def source_checked(source, receipt, donor):
    """Check every exported/overlaid byte; receipt status alone is insufficient."""
    require(receipt.get('schema') == 'friday.hermes-source.v1'
            and receipt.get('commit') == donor['commit']
            and receipt.get('base_tree') == donor['tree']
            and receipt.get('status') == 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED',
            'hermes_composition_identity_required')
    files = receipt.get('files')
    require(isinstance(files, dict) and len(files) > 1000, 'complete_hermes_inventory_required')
    for name, row in files.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                'unsafe_source_inventory_path')
        data = owned_file(source / name)
        require(digest(data) == row['sha256'] and len(data) == row['bytes']
                and bool((source / name).stat().st_mode & 0o111) == (row['mode'] == '100755'),
                'composed_source_changed')
    # Generated native products may coexist; never load a hidden source .env.
    require(not (source / '.env').exists() and not (source / '.env').is_symlink()
            and all(str(p.relative_to(source)) in files for p in source.glob('.env*')),
            'source_credential_file_refused')
    generated = ('.hermes/', 'node_modules/', 'hermes_cli/web_dist/', 'ui-tui/dist/',
                 'ui-tui/node_modules/', 'web/node_modules/', 'apps/shared/node_modules/')
    generated_files = {'install-stamp.json', '.hermes-bytecode-fingerprint'}
    for p in source.rglob('*'):
        name = str(p.relative_to(source))
        if p.is_symlink():
            require(name.startswith(generated), 'unexpected_source_link')
        if p.is_dir():
            continue
        require(name in files or name in generated_files or name.startswith(generated),
                'unexpected_composed_source_file')
    return files


def composition_checked(value, source, receipt, donor):
    require(receipt.get('sources_lock_sha256') == value['sources_lock']['sha256'],
            'composition_source_lock_changed')
    rows = receipt.get('layers')
    require(isinstance(rows, list), 'composition_overlay_inventory_missing')
    manifests = {n: h for n, h in value['project_files'].items()
                 if n.startswith('patches/hermes/') and n.endswith('.json')}
    require(len(rows) == len(manifests) and {r.get('manifest') for r in rows} == set(manifests),
            'composition_overlay_set_changed')
    for row in rows:
        name = row['manifest']; require(row.get('manifest_sha256') == manifests[name],
                                        'composition_overlay_manifest_changed')
        body = json.loads(owned_file(ROOT / name))
        patch = body.get('patch') or 'patches/hermes/' + body['patch_file']
        require(row.get('patch_sha256') == body['patch_sha256'] == value['project_files'][patch],
                'composition_overlay_patch_changed')
    return source_checked(source, receipt, donor)


def publish(path, value, *, budget=None):
    # Serialize before opening a file; long serialization cannot admit a write.
    payload = json.dumps(value, sort_keys=True, indent=2) + '\n'
    if budget: budget.check()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        if budget: budget.check()
        f.write(payload)
        if budget: budget.check()
        f.flush()
        if budget: budget.check()
        os.fsync(f.fileno())
        if budget: budget.check()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if budget: budget.check()
        os.fsync(fd)
        if budget: budget.check()
    finally:
        os.close(fd)


def partial_claim(input_hash, budget):
    return {'schema': SCHEMA, 'state': 'PARTIAL', 'input_sha256': input_hash,
            'deadline_mono': budget.deadline,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def reconcile(value, input_hash):
    """Read-only PARTIAL observation, with no replay or fresh execution grant.

    Legacy claims contain no durable child identity/cessation receipt. A clean
    directory, absent parent or lock availability cannot fill that evidence gap.
    Even a new failure receipt is historical evidence, not current quiescence.
    """
    require(isinstance(value, dict), 'explicit_install_fields_required')
    home = canonical(value['home']); directory(home)
    claim = read_json(home / MARKER)
    require(set(claim) == {'schema', 'state', 'input_sha256', 'deadline_mono', 'boot_id'}
            and claim['schema'] == SCHEMA and claim['state'] == 'PARTIAL'
            and claim['input_sha256'] == input_hash, 'exact_original_partial_claim_required')
    require(claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'original_install_boot_changed')
    deadline = claim['deadline_mono']
    require(type(deadline) in (int, float) and math.isfinite(deadline) and deadline > 0,
            'original_install_deadline_required')
    extra = False; count = 0
    with os.scandir(home) as entries:
        for item in entries:
            count += 1
            if item.name not in (MARKER, FAILURE): extra = True
            require(count <= 128, 'partial_observation_inventory_limit')
    failure = home / FAILURE
    has_failure = failure.exists() or failure.is_symlink()
    if has_failure:
        observation = read_json(failure)
        require(observation.get('schema') == 'friday.native-install-failure.v1'
                and observation.get('original_attempt') == claim
                and observation.get('resume_allowed') is False, 'failure_receipt_not_bound')
    remaining = max(0, deadline - time.monotonic())
    return {'state': 'PARTIAL_RETAINED_NO_REPLAY', 'effects': 'NONE', 'ready': False,
            'resume_allowed': False, 'original_attempt': claim,
            'original_remaining_seconds': remaining, 'original_budget_expired': remaining == 0,
            'contains_other_files': extra, 'historical_failure_receipt_bound': has_failure,
            'cessation': 'CURRENT_NATIVE_VERIFICATION_REQUIRED',
            'next': 'Independent lead review of original attempt, current cessation, repaired source pins and original clock; no replay admission'}


def install(value, input_path, *, budget=None):
    """One original clock includes intake, execution, IO and final admission."""
    from scripts.install_containment import Budget, Containment
    require(isinstance(value, dict), 'explicit_install_fields_required')
    budget = budget or Budget(value.get('seconds'))
    home, donors = budget.call(spec_checked, value)
    argv = budget.call(commands, value)
    raw = budget.call(owned_file, input_path, private=True)
    require(json.loads(raw, object_pairs_hook=unique) == value, 'install_input_changed')
    input_hash = digest(raw); budget.check()
    if home.exists():
        budget.call(directory, home)
        marker = budget.call(read_json, home / MARKER)
        require(marker.get('schema') == SCHEMA and marker.get('input_sha256') == input_hash,
                'foreign_existing_install_not_adopted')
        require(marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE',
                'partial_install_requires_reconciliation')
        return budget.call(inspect, value, input_hash)
    containment = Containment(value['containment'], budget, clean_environment(home))
    # Actual required namespace capability before claiming/writing any home.
    try:
        containment.probe(value['bootstrap_python']['path'], ROOT)
    except (OSError, ValueError, RuntimeError) as exc:
        exc.friday_diagnostic = safe_diagnostic(exc, 'namespace_probe')
        raise
    budget.call(home.mkdir, mode=0o700)
    claim = partial_claim(input_hash, budget)
    publish(home / MARKER, claim, budget=budget)
    def execute(phase, command, cwd, timeout=1800):
        try:
            return containment.run(command, cwd, timeout=timeout,
                                   log=home / 'preparation/native-install' / phase)[0]
        except (OSError, ValueError, RuntimeError) as exc:
            diagnostic = safe_diagnostic(exc, phase)
            exc.friday_diagnostic = diagnostic
            exc.friday_attempt = claim
            # This receipt is evidence, never permission to replay the attempt.
            failure = {'schema': 'friday.native-install-failure.v1',
                       'original_attempt': claim, 'diagnostic': diagnostic,
                       'resume_allowed': False}
            try:
                require(read_json(home / MARKER) == claim, 'install_claim_changed')
                publish(home / FAILURE, failure, budget=budget)
            except (OSError, ValueError, RuntimeError):
                diagnostic['failure_receipt'] = 'NOT_PUBLISHED'
            raise
    execute('compose', argv['compose'], ROOT, 130)
    source = home / 'hermes-agent'; receipt_path = home / 'hermes-agent.source.json'
    receipt = budget.call(read_json, receipt_path)
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    for phase in ('tools', 'dependencies'):
        execute(phase, argv[phase], source)
    expression = 'from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))'
    selected = execute('pm_python', [value['bootstrap_python']['path'], '-B', '-c', expression], source, 15)
    require(Path(selected).is_absolute() and Path(selected).is_file(), 'native_pm_python_missing')
    def prepare_harness():
        for phase, command in zip(('source', 'toolchain', 'build', 'smoke'), argv['harness']):
            execute('harness_' + phase, command, ROOT)
    if 'worker_install' in value:
        prepare_harness()
        execute('a0_inventory', argv['a0_inventory'], ROOT, 120)
    execute('native_completion', [selected, '-B', str(ROOT / 'scripts/friday_native.py'), 'install',
             '--input', str(input_path), '--deadline', str(budget.deadline)], source)
    if 'worker_install' not in value:
        prepare_harness()
    return finish_install(value, input_hash, home, donors, source, receipt, receipt_path, claim, budget, execute, argv)


def finish_install(value, input_hash, home, donors, source, receipt, receipt_path, claim, budget, execute, argv):
    """The same remaining completion path for fresh and explicitly resumed installs."""
    if 'worker_install' not in value:
        if value['product']['web']['profile'] == 'exa-keyless':
            budget.call(stage_keyless_provider, Path(value['dsh_donor']))
        execute('a0_inventory', argv['a0_inventory'], ROOT, 120)
    effective = value
    if 'worker_install' in value:
        from scripts.worker_install import installed_product
        effective = dict(value, product=budget.call(installed_product, value, home))
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    marker = {'schema': SCHEMA, 'state': 'INSTALLED_TEMPLATE_INCOMPLETE',
              'input_sha256': input_hash, 'source_receipt_sha256': digest(budget.call(owned_file, receipt_path)),
              'home': str(home), 'source': str(source), 'runtime_ready': False,
              'gateway_installed': False, 'remaining': gaps(),
              'worker_preparation_mode': 'BOTH_WORKERS_REQUIRED' if 'worker_install' in value else 'LEGACY_EXPLICIT_TEMPLATE',
              'original_attempt': claim,
              'invocation_completion': 'NOT_PROVEN_BY_OUTPUT_RECEIPT'}
    if 'tls' in value['product']['dashboard']:
        marker['tls_files'] = {path: digest(budget.call(owned_file, home / path, private=True))
            for path in value['product']['dashboard']['tls'].values()}
        require(marker['tls_files'] == {path: value['dashboard_tls'][key]['sha256']
            for key, path in value['product']['dashboard']['tls'].items()}, 'installed_dashboard_tls_changed')
    marker['profile_files'] = {name: digest(budget.call(owned_file, home / name, private=True))
                               for name in ('config.yaml', 'SOUL.md', 'FRIDAY-PROFILE.json')}
    marker['plugin_files'] = {name: sha for name, sha in value['project_files'].items()
                              if name.startswith('plugins/friday_rework/')}
    from scripts.a0_prepare import service_required, service_receipt_checked
    if service_required(effective):
        budget.call(service_receipt_checked, effective, home, original_attempt=claim)
        marker['a0_service_receipt_sha256'] = digest(budget.call(
            owned_file, home / 'preparation/a0-service.receipt.json', private=True))
    if 'worker_install' in value:
        marker['worker_files'] = {str(p.relative_to(home)): digest(budget.call(owned_file, p, private=True))
                                  for p in sorted((home / 'workers').rglob('*')) if p.is_file()}
        marker['worker_state'] = 'BOTH_CONFIGURED_QUALIFICATION_PENDING'
    pending = home / (MARKER + '.completed')
    publish(pending, marker, budget=budget)
    require(budget.call(read_json, home / MARKER) == claim, 'install_claim_changed')
    budget.call(os.replace, pending, home / MARKER)
    budget.check()
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        budget.check()
        budget.call(os.fsync, fd)
    finally:
        os.close(fd)
    budget.check()
    return marker


def gaps():
    return ['A0 portable image/toolchain preparation is absent; fixed deployment needs separately admitted kernel/resources; finite inactive service registration is not runtime qualification',
            'Both-worker configuration is available; A0 useful-web runtime admission and mixed live execution remain unverified',
            'Native Dashboard boundary requires independent source review and actual authenticated startup/attach acceptance',
            'Protected credential provisioning, actual account ownership, PM/build realization and all seven live journeys require independent acceptance']


RESUME = 'FRIDAY-INSTALL.harness-resume.json'


def resume_inputs(request):
    """Explicit pinned continuation of one settled failure, never a new clock."""
    require(isinstance(request, dict) and set(request) ==
            {'original_input', 'original_claim', 'original_failure', 'current_input'},
            'explicit_harness_resume_pins_required')
    paths = {name: pin(row) for name, row in request.items()}
    # Operational input and all retained evidence are private owned documents.
    old, value, claim, failure = (read_json(paths[name]) for name in
        ('original_input', 'current_input', 'original_claim', 'original_failure'))
    require(all(isinstance(v, dict) for v in (old, value, claim, failure)), 'invalid_resume_input_shape')
    require('worker_install' not in old and 'worker_install' not in value,
            'normal_worker_partial_requires_reconciliation')
    home = canonical(old['home']); directory(home)
    require(paths['original_claim'] == home / MARKER
            and paths['original_failure'] == home / FAILURE,
            'original_install_evidence_path_required')
    require(set(claim) == {'schema', 'state', 'input_sha256', 'deadline_mono', 'boot_id'}
            and claim['schema'] == SCHEMA and claim['state'] == 'PARTIAL'
            and claim['input_sha256'] == request['original_input']['sha256'],
            'exact_original_partial_claim_required')
    require(claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'original_install_boot_changed')
    deadline = claim['deadline_mono']
    require(type(deadline) in (int, float) and math.isfinite(deadline) and deadline > 0,
            'original_install_deadline_required')
    from scripts.install_containment import Budget
    budget = Budget(old.get('seconds'), deadline=deadline)
    diagnostic = failure.get('diagnostic', {})
    require(isinstance(diagnostic, dict), 'invalid_resume_diagnostic_shape')
    require(set(failure) == {'schema', 'original_attempt', 'diagnostic', 'resume_allowed'}
            and failure.get('schema') == 'friday.native-install-failure.v1'
            and failure.get('original_attempt') == claim and failure.get('resume_allowed') is False
            and diagnostic.get('phase') == 'harness_build'
            and diagnostic.get('reason') == 'command_nonzero_exit'
            and type(diagnostic.get('returncode')) is int and diagnostic['returncode'] > 0
            and diagnostic.get('timeout') is False and diagnostic.get('reaped') is True
            and diagnostic.get('namespace_init_exit_verified') is True
            and diagnostic.get('cessation') == 'REAPED', 'settled_harness_build_failure_required')
    allowed = {'scripts/friday_install.py', 'scripts/dsh_prepare.py'}
    require(isinstance(old.get('project_files'), dict) and isinstance(value, dict)
            and isinstance(value.get('project_files'), dict)
            and set(old['project_files']) == set(value['project_files']),
            'resume_project_inventory_changed')
    require({k: v for k, v in old.items() if k != 'project_files'} ==
            {k: v for k, v in value.items() if k != 'project_files'},
            'resume_operational_settings_changed')
    require(all(value['project_files'][name] == sha for name, sha in old['project_files'].items()
                if name not in allowed), 'resume_unrelated_source_changed')
    require(not (home / RESUME).exists() and not (home / RESUME).is_symlink(),
            'harness_resume_already_consumed')
    budget.call(spec_checked, value)
    return value, paths, claim, budget


def verify_completed_native(input_path, deadline):
    """Read-only preflight in the installed PM Python and native namespace."""
    from scripts.install_containment import Budget
    value = read_json(input_path); budget = Budget(value['seconds'], deadline=deadline)
    home, donors = budget.call(spec_checked, value); source = home / 'hermes-agent'
    receipt = budget.call(read_json, home / 'hermes-agent.source.json')
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    sys.path.insert(0, str(source))
    import tools, plugins, scripts
    for package in (tools, plugins):
        expected = source / package.__name__ / '__init__.py'
        require(Path(package.__file__ or '').resolve() == expected
                and list(package.__path__) == [str(expected.parent)], 'native_package_provenance_required')
        package.__path__.append(str(ROOT / package.__name__))
    scripts.__path__.append(str(source / 'scripts'))
    from pm.environments import project_python
    from pm.paths import repo_root
    require(repo_root() == source and Path(sys.executable) == project_python(source),
            'native_pm_install_owner_mismatch')
    from tools.configure_product import compose_product
    from scripts.friday_native import native_profile_check
    bundle = budget.call(compose_product, value['product'])
    budget.call(completed_profile_checked, value, home, bundle, budget)
    budget.call(native_profile_check, bundle, home)
    stamp = budget.call(read_json, source / 'install-stamp.json')
    require(stamp.get('fridaySource') == {'baseTree': receipt['base_tree'], 'layers': receipt['layers']}
            and stamp.get('commit') == receipt['commit'], 'completed_install_stamp_changed')
    # Reuse the native pure launcher renderer; do not republish commands.
    import shlex
    from hermes_cli._launchers import ENTRY_POINTS, _launcher_script, resolve_store_python
    interpreter = budget.call(resolve_store_python, source, publication=True)
    require(interpreter is not None, 'completed_launcher_python_missing')
    for name in ENTRY_POINTS:
        path = source / '.hermes/bin' / name
        command = [str(interpreter), '-I', '-c', _launcher_script(name, source, None)]
        expected = f'#!/bin/sh\nexec {shlex.join(command)} "$@"\n'.encode()
        require(budget.call(owned_file, path) == expected and os.access(path, os.X_OK),
                'completed_native_launcher_changed')
    from hermes_cli.source_build import source_product_current
    require(budget.call(source_product_current, source, 'tui', source / 'ui-tui/dist')
            and budget.call(source_product_current, source, 'web', source / 'hermes_cli/web_dist'),
            'native_frontend_freshness_not_verified')
    return {'state': 'COMPLETED_NATIVE_REVALIDATED', 'ready': False}


def completed_profile_checked(value, home, bundle, budget):
    import hermes_yaml as yaml
    require(budget.call(read_json, home / 'FRIDAY-PROFILE.json') == bundle['contract']
            and yaml.safe_load(budget.call(owned_file, home / 'config.yaml', private=True)) == bundle['config']
            and budget.call(owned_file, home / 'SOUL.md', private=True) == bundle['soul'].encode(),
            'completed_profile_changed')
    for name, sha in value['project_files'].items():
        if name.startswith('plugins/friday_rework/'):
            require(digest(budget.call(owned_file, home / name)) == sha, 'installed_plugin_changed')
    for key, name in value['product']['dashboard'].get('tls', {}).items():
        require(digest(budget.call(owned_file, home / name, private=True)) == value['dashboard_tls'][key]['sha256'],
                'installed_dashboard_tls_changed')
    from scripts.a0_prepare import service_required, service_receipt_checked
    if service_required(value):
        budget.call(service_receipt_checked, value, home, original_attempt=read_json(home / MARKER))


def resume_harness(request, request_path, *, prepared=None):
    value, paths, claim, budget = prepared or resume_inputs(request)
    require(read_json(request_path) == request, 'resume_request_changed')
    home, donors = budget.call(spec_checked, value); argv = budget.call(commands, value)
    source = home / 'hermes-agent'; receipt_path = home / 'hermes-agent.source.json'
    receipt = budget.call(read_json, receipt_path)
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    require(not any((home / name).exists() or (home / name).is_symlink() for name in
                    (MARKER + '.original', MARKER + '.completed', 'preparation/harness-resume',
                     'preparation/a0.json', 'FRIDAY-INSTALL.harness-resume.failure.json')),
            'resume_destination_already_exists')
    from scripts.install_containment import Containment
    custody = Containment(value['containment'], budget, clean_environment(home))
    # Claim consumption before the first command. A crash or failed preflight
    # remains consumed and requires reconciliation, never an automatic retry.
    publish(home / RESUME, {'original_attempt': claim, 'request': request,
                          'state': 'CONSUMED_NOT_COMPLETE'}, budget=budget)
    # Preserve the precise original bytes before the normal final marker swap.
    original = budget.call(owned_file, paths['original_claim'], private=True)
    fd = os.open(home / (MARKER + '.original'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        budget.check(); stream.write(original); stream.flush(); os.fsync(stream.fileno()); budget.check()
    evidence = home / 'preparation/harness-resume'
    budget.call(evidence.mkdir, mode=0o700)
    def execute(phase, command, cwd, timeout=1800):
        try:
            budget.call(resume_pins_unchanged, request, claim, budget)
            # Completed PM/profile verification needs no host writes. Use the
            # existing namespace itself, never a nested sandbox or weaker
            # fallback, and keep its private diagnostic output on the host.
            options = ({'read_only': True, 'log': evidence / phase}
                       if phase in ('pm_python', 'completed_native_check') else {})
            return custody.run(command, cwd, timeout=timeout, **options)[0]
        except (OSError, ValueError, RuntimeError) as exc:
            diagnostic = safe_diagnostic(exc, phase)
            exc.friday_diagnostic = diagnostic; exc.friday_attempt = claim
            try:
                publish(home / 'FRIDAY-INSTALL.harness-resume.failure.json', {
                    'schema': 'friday.native-install-failure.v1', 'original_attempt': claim,
                    'diagnostic': diagnostic, 'resume_allowed': False}, budget=budget)
            except (OSError, ValueError, RuntimeError):
                diagnostic['failure_receipt'] = 'NOT_PUBLISHED'
            raise
    expression = 'from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))'
    selected = execute('pm_python', [value['bootstrap_python']['path'], '-B', '-c', expression], source, 15)
    require(Path(selected).is_absolute() and Path(selected).is_file(), 'native_pm_python_missing')
    code = ('import sys;sys.path.insert(0,' + repr(str(ROOT)) + ');'
            'from scripts.friday_install import verify_completed_native;'
            'verify_completed_native(sys.argv[1],float(sys.argv[2]))')
    execute('completed_native_check', [selected, '-B', '-c', code,
                                     str(paths['current_input']), str(budget.deadline)], source, 120)
    # Check complete tracked source and the exact previous Node/toolchain identity.
    command = list(argv['harness'][0]); command[3] = 'check'
    command[command.index('--evidence') + 1] = str(evidence)
    execute('harness_check', command, ROOT, 120)
    checked = budget.call(read_json, evidence / 'dsh-check.json')
    previous = budget.call(read_json, home / 'preparation/harness/dsh-toolchain.json')
    require(checked['source'] == previous['source'] and checked['donor'] == previous['donor']
            and checked['toolchain'] == {k: v for k, v in previous['toolchain'].items() if k != 'observed_pnpm'},
            'completed_harness_identity_changed')
    for phase, command in zip(('build', 'smoke'), argv['harness'][2:]):
        command = list(command); command[command.index('--evidence') + 1] = str(evidence)
        execute('harness_' + phase, command, ROOT)
    budget.call(resume_pins_unchanged, request, claim, budget)
    return finish_install(value, request['current_input']['sha256'], home, donors, source,
                          receipt, receipt_path, claim, budget, execute, argv)


def resume_pins_unchanged(request, claim, budget):
    budget.check()
    for row in request.values():
        budget.call(pin, row)
    require(budget.call(read_json, request['original_claim']['path']) == claim, 'install_claim_changed')


def inspect(value, input_hash):
    home, donors = spec_checked(value); directory(home)
    marker = read_json(home / MARKER)
    require(marker.get('schema') == SCHEMA and marker.get('home') == str(home)
            and marker.get('input_sha256') == input_hash
            and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE', 'foreign_or_partial_install')
    if 'tls' in value['product']['dashboard']:
        expected = {path: value['dashboard_tls'][key]['sha256']
            for key, path in value['product']['dashboard']['tls'].items()}
        require(marker.get('tls_files') == expected
                and all(digest(owned_file(home / path, private=True)) == pin for path, pin in expected.items()),
                'installed_dashboard_tls_changed')
    receipt_path = home / 'hermes-agent.source.json'
    require(digest(owned_file(receipt_path)) == marker.get('source_receipt_sha256'),
            'source_receipt_changed')
    composition_checked(value, home / 'hermes-agent', read_json(receipt_path), donors['hermes'])
    profile_files = marker.get('profile_files')
    require(isinstance(profile_files, dict)
            and set(profile_files) == {'config.yaml', 'SOUL.md', 'FRIDAY-PROFILE.json'},
            'installed_profile_inventory_missing')
    for name, sha in profile_files.items():
        require(digest(owned_file(home / name, private=True)) == sha, 'installed_profile_changed')
    expected_plugins = {name: sha for name, sha in value['project_files'].items()
                        if name.startswith('plugins/friday_rework/')}
    require(marker.get('plugin_files') == expected_plugins, 'installed_plugin_inventory_changed')
    for name, sha in expected_plugins.items():
        require(digest(owned_file(home / name, private=True)) == sha, 'installed_plugin_changed')
    effective = value
    if 'worker_install' in value:
        files = marker.get('worker_files')
        from scripts.worker_install import installed_files
        actual = installed_files(home)
        require(isinstance(files, dict) and set(files) == actual
                and all(digest(owned_file(home / p, private=True)) == h for p, h in files.items()),
                'installed_worker_inputs_changed')
        from scripts.worker_install import installed_product
        effective = dict(value, product=installed_product(value, home))
    from scripts.a0_prepare import service_required, service_receipt_checked
    if service_required(effective):
        path = home / 'preparation/a0-service.receipt.json'
        require(digest(owned_file(path, private=True)) == marker.get('a0_service_receipt_sha256'),
                'a0_service_receipt_changed')
        service_receipt_checked(effective, home, original_attempt=marker['original_attempt'])
    qualified = marker.get('worker_state') == 'BOTH_DEPLOYMENTS_QUALIFIED'
    return {'state': 'DEPLOYMENTS_QUALIFIED' if qualified else 'TEMPLATE_INCOMPLETE', 'ready': False, 'home': str(home),
            'effects': 'NONE', 'remaining': (['Fresh per-job native route/deadline/credentials and stop admission',
                'Current authenticated native Dashboard and receiving gateway ownership',
                'Independent acceptance and mandatory live journeys'] if qualified else gaps()),
            'per_job_authority': 'NOT_GRANTED',
            'invocation_completion': 'NOT_PROVEN_BY_OUTPUT_RECEIPT'}


def start(value, input_hash, *, budget=None, input_path=None, plan_ref=None, phase='start'):
    from scripts.install_containment import Budget, Containment
    budget = budget or Budget(value.get('seconds'))
    budget.call(inspect, value, input_hash)
    home = Path(value['home'])
    marker = budget.call(read_json,home / MARKER) if 'worker_install' in value else {}
    pending = marker.get('worker_state') == 'BOTH_CONFIGURED_QUALIFICATION_PENDING'
    if phase == 'qualify' or (pending and plan_ref is not None):
        require(pending, 'pending_qualification_and_current_a0_plan_required')
        require(marker['original_attempt']['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'original_install_boot_changed')
        # Native observation inherits the original installation clock. No new
        # startup invocation can revive an expired or partially qualified home.
        budget = Budget(value['seconds'],deadline=marker['original_attempt']['deadline_mono'])
    elif pending:
        raise ValueError('ordinary_worker_qualification_required')
    # A source/rendered status cannot stand in for any configured runtime.
    effective = value
    if 'worker_install' in value:
        from scripts.worker_install import installed_product
        effective = dict(value, product=budget.call(installed_product, value, Path(value['home'])))
    require(effective['product']['runtime'].get('enabled') is True,
            'mandatory_a0_web_kernel_and_final_native_dashboard_owner_not_admitted')
    require(input_path is not None, 'original_start_input_required')
    require(digest(budget.call(owned_file, input_path, private=True)) == input_hash,
            'original_start_input_changed')
    home = Path(value['home']); source = home / 'hermes-agent'
    custody = Containment(value['containment'], budget, clean_environment(home))
    expression = 'from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))'
    selected = custody.run([value['bootstrap_python']['path'], '-B', '-c', expression], source, timeout=15)[0]
    require(Path(selected).is_absolute() and Path(selected).is_file(), 'native_pm_python_missing')
    # Re-exec the existing internal completion helper in the exact selected PM
    # generation. It revalidates all bytes and gates before any service effect.
    budget.call(inspect, value, input_hash)
    argv = [selected, '-B', str(ROOT / 'scripts/friday_native.py'), phase,
            '--input', str(input_path), '--deadline', str(budget.deadline)]
    if plan_ref is not None:
        pin(plan_ref)
        argv += ['--a0-plan',plan_ref['path'],'--a0-plan-sha256',plan_ref['sha256']]
    budget.check()
    os.execve(selected, argv, clean_environment(home))


def main():
    started = time.monotonic()  # before parser/input IO; never reset on dispatch
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=('plan', 'install', 'check', 'dashboard-check', 'start', 'qualify', 'reconcile', 'resume-harness'))
    parser.add_argument('--input', required=True, type=Path, help='Private pinned JSON, no credential values')
    parser.add_argument('--a0-plan', type=Path, help='Existing owned live native probe plan; never a readiness report')
    parser.add_argument('--a0-plan-sha256')
    args = parser.parse_args(); os.umask(0o077)
    sys.path.insert(0, str(ROOT))
    from scripts.dsh_prepare import StopUnconfirmed
    try:
        raw = owned_file(args.input, private=True)
        require((args.a0_plan is None) == (args.a0_plan_sha256 is None)
                and (args.a0_plan is None or args.phase in ('start','qualify')),
                'qualification_plan_arguments_required')
        plan_ref = None if args.a0_plan is None else {'path':str(args.a0_plan),'sha256':args.a0_plan_sha256}
        value = json.loads(raw, object_pairs_hook=unique); sha = digest(raw)
        from scripts.install_containment import Budget
        require(isinstance(value, dict), 'explicit_install_fields_required')
        prepared = resume_inputs(value) if args.phase == 'resume-harness' else None
        budget = prepared[3] if prepared else Budget(value.get('seconds'), started=started)
        budget.check()
        if args.phase == 'resume-harness':
            result = resume_harness(value, args.input, prepared=prepared)
        elif args.phase == 'reconcile':
            result = reconcile(value, sha)
        elif args.phase == 'plan':
            result = {'state': 'PLANNED_NOT_EXECUTED', 'ready': False,
                      'commands': commands(value), 'remaining': gaps()}
        elif args.phase == 'install':
            result = install(value, args.input, budget=budget)
        elif args.phase == 'check':
            result = inspect(value, sha)
        elif args.phase == 'dashboard-check':
            inspect(value, sha)
            from scripts.friday_native import dashboard_source_check
            result = dashboard_source_check(Path(value['home']))
        else:
            result = start(value, sha, budget=budget, input_path=args.input,plan_ref=plan_ref,phase=args.phase)
        payload = json.dumps(result, sort_keys=True, indent=2)
        budget.check()
        print(payload, flush=True)
        budget.check()
    except StopUnconfirmed as exc:
        # Fixed text only: neither argv, stderr nor a chained error is safe to
        # print. Keep uncertain process custody distinct from a normal refusal.
        detail = diagnostic_text(getattr(exc, 'friday_diagnostic', safe_diagnostic(exc, args.phase)))
        if hasattr(exc, 'friday_attempt'): detail += ' attempt=' + exc.friday_attempt['input_sha256']
        parser.exit(3, 'STOP_UNCONFIRMED: ' + detail + '; owned command cessation is unconfirmed; '
                       'do not retry or release ownership before reconciliation\n')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        # Native errors/inputs can contain credentials: print no exception body.
        detail = diagnostic_text(getattr(exc, 'friday_diagnostic', safe_diagnostic(exc, args.phase)))
        if hasattr(exc, 'friday_attempt'): detail += ' attempt=' + exc.friday_attempt['input_sha256']
        parser.exit(2, 'Friday entry refused: ' + detail + '\n')



def stage_keyless_provider(harness):
    """After intact donor build/smoke; exact extra product source, no ready grant."""
    raw = owned_file(ROOT / "plugins/friday_rework/adapters/dsh_keyless_web.mjs")
    target = harness / "friday-web-keyless.mjs"
    require(target.parent.resolve() == target.parent and not target.exists() and not target.is_symlink(), "existing_keyless_provider_not_replaced")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    return {"path": str(target), "sha256": digest(raw), "runtime_ready": False}

if __name__ == '__main__':
    main()
