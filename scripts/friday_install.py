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


def remember_secondary(exc, secondary):
    # Retain objects only in memory; never stringify exceptions or traceback
    # inventories. The finite installation path uses at most sixteen entries.
    previous = getattr(exc, 'friday_secondary_failures', ())
    if type(previous) is not tuple:
        previous = ()
    exc.friday_secondary_failures = (previous + (secondary,))[:16]


class InstallerExit(SystemExit):
    """CLI status is not a proof of command cessation; keep the original cause."""
    def __init__(self, code, original):
        super().__init__(code)
        self.friday_custody_primary = original
        self.friday_custody_state = 'UNCONFIRMED' if code == 3 else 'REFUSAL_UNPROVEN'


def retained_diagnostic(exc, phase):
    fallback = {'phase': phase, 'reason': 'diagnostic_unavailable'}
    try:
        from scripts.dsh_prepare import StopUnconfirmed
        if isinstance(exc, StopUnconfirmed):
            fallback.update(reason='stop_unconfirmed', cessation='UNCONFIRMED')
        existing = getattr(exc, 'friday_diagnostic', None)
        diagnostic = existing if type(existing) is dict else safe_diagnostic(exc, phase)
        if type(diagnostic) is not dict:
            raise TypeError('diagnostic_object_required')
        exc.friday_diagnostic = diagnostic
        return diagnostic
    except BaseException as secondary:
        remember_secondary(exc, secondary)
        exc.friday_diagnostic = fallback
        return fallback


def exit_retaining_cause(parser, code, exc, phase):
    # Construct the typed transfer before any diagnostic, formatting or output.
    # argparse's generic SystemExit and failed diagnostics never own custody.
    transfer = InstallerExit(code, exc)
    try:
        detail = diagnostic_text(retained_diagnostic(exc, phase))
        attempt = getattr(exc, 'friday_attempt', None)
        if type(attempt) is dict:
            sha = attempt.get('input_sha256')
            if type(sha) is str and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha):
                detail += ' attempt=' + sha
        message = ('STOP_UNCONFIRMED: ' + detail + '; owned command cessation is unconfirmed; '
                   'do not retry or release ownership before reconciliation\n' if code == 3 else
                   'Friday entry refused: ' + detail + '\n')
        parser.exit(code, message)
        remember_secondary(exc, RuntimeError('parser_exit_returned'))
    except BaseException as secondary:
        if not (type(secondary) is SystemExit and type(secondary.code) is int and secondary.code == code):
            remember_secondary(exc, secondary)
    transfer.friday_custody_secondary = getattr(exc, 'friday_secondary_failures', ())
    raise transfer from exc


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



def project_plugin(name, value):
    """Pure project validators have their own namespace; native plugins stay cold."""
    prefix = 'plugins/friday_rework/'
    for path, expected in value['project_files'].items():
        if path.startswith(prefix):
            require(digest(owned_file(ROOT/path)) == expected, 'project_source_changed')
    alias = '_friday_install_validation_plugins'
    if alias not in sys.modules:
        module = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(alias, loader=None, is_package=True))
        module.__path__ = [str(ROOT/'plugins')]
        sys.modules[alias] = module
    require(list(sys.modules[alias].__path__) == [str(ROOT/'plugins')], 'foreign_validator_package')
    module = importlib.import_module(alias + '.friday_rework.' + name)
    for key, loaded in tuple(sys.modules.items()):
        if key.startswith(alias + '.') and getattr(loaded, '__file__', None):
            relative = 'plugins/' + key[len(alias)+1:].replace('.', '/') + '.py'
            expected = ROOT/relative
            if getattr(loaded, '__path__', None) is not None:
                expected = ROOT/relative[:-3]/'__init__.py'
            require(Path(loaded.__file__).resolve() == expected
                    and digest(owned_file(expected)) == value['project_files'][str(expected.relative_to(ROOT))],
                    'foreign_validator_module')
    return module


def native_packages(source):
    """Execute verified regular native packages before extending their search path."""
    sys.path.insert(0, str(source))
    for name in ('tools', 'plugins'):
        package = importlib.import_module(name)
        expected = source/name/'__init__.py'
        base, extension = str(expected.parent), str(ROOT/name)
        require(Path(package.__file__ or '').resolve() == expected
                and package.__spec__.origin == str(expected)
                and list(package.__path__) in ([base], [base, extension]),
                'native_package_provenance_required')
        if extension not in package.__path__:
            package.__path__.append(extension)
    package = importlib.import_module('scripts')
    allowed={str(ROOT/'scripts'),str(source/'scripts')}
    require(set(package.__path__).issubset(allowed) and str(ROOT/'scripts') in package.__path__
            and Path(sys.modules['scripts.friday_install'].__file__).resolve()==ROOT/'scripts/friday_install.py',
            'project_scripts_provenance_required')
    package.__path__=[str(ROOT/'scripts'),str(source/'scripts')]


def spec_checked(value, *, cli_only=False):
    require(type(cli_only) is bool, 'explicit_cli_declaration_mode_required')
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
        settings(value, cli_only=cli_only)
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
        retained_diagnostic(exc, 'namespace_probe')
        raise
    budget.call(home.mkdir, mode=0o700)
    claim = partial_claim(input_hash, budget)
    publish(home / MARKER, claim, budget=budget)
    def execute(phase, command, cwd, timeout=1800):
        try:
            return containment.run(command, cwd, timeout=timeout,
                                   log=home / 'preparation/native-install' / phase)[0]
        except (OSError, ValueError, RuntimeError) as exc:
            diagnostic = retained_diagnostic(exc, phase)
            exc.friday_diagnostic = diagnostic
            exc.friday_attempt = claim
            # This receipt is evidence, never permission to replay the attempt.
            failure = {'schema': 'friday.native-install-failure.v1',
                       'original_attempt': claim, 'diagnostic': diagnostic,
                       'resume_allowed': False}
            try:
                require(read_json(home / MARKER) == claim, 'install_claim_changed')
                publish(home / FAILURE, failure, budget=budget)
            except BaseException as secondary:
                remember_secondary(exc, secondary)
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


def verify_completed_native(input_path, deadline, *, cli_host=False):
    """Read-only preflight in the installed PM Python and native namespace."""
    from scripts.install_containment import Budget
    value = read_json(input_path); budget = Budget(value['seconds'], deadline=deadline)
    home, donors = budget.call(spec_checked, value, cli_only=cli_host); source = home / 'hermes-agent'
    receipt = budget.call(read_json, home / 'hermes-agent.source.json')
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    budget.call(native_packages, source)
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
    if not cli_host:
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
            diagnostic = retained_diagnostic(exc, phase)
            exc.friday_diagnostic = diagnostic; exc.friday_attempt = claim
            try:
                publish(home / 'FRIDAY-INSTALL.harness-resume.failure.json', {
                    'schema': 'friday.native-install-failure.v1', 'original_attempt': claim,
                    'diagnostic': diagnostic, 'resume_allowed': False}, budget=budget)
            except BaseException as secondary:
                remember_secondary(exc, secondary)
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


CLI_RESUME = 'FRIDAY-INSTALL.cli-host.intent.json'
CLI_STAGE = 'CLI_HOST_ONLY'
CLI_OVERLAY = 'patches/hermes/cli-host-stage-manifest.json'


def cli_resume_inputs(request, *, consumed=False, budget=None, validation_value=None):
    """One exact normal install, one original clock, one explicitly consumed stage."""
    require(isinstance(request, dict) and set(request) == {
        'original_input', 'current_input', 'original_claim', 'original_supervision',
        'completed_phases', 'failed_build'}, 'explicit_cli_resume_pins_required')
    names = ('original_input', 'current_input', 'original_claim', 'original_supervision', 'failed_build')
    paths = {k: pin(request[k]) for k in names}
    old, value, claim, supervisor, failed = [read_json(paths[k]) for k in names]
    home = canonical(old['home']); directory(home)
    require('worker_install' in old and 'worker_install' in value
            and old['product']['runtime'] == value['product']['runtime'] == {'enabled': False},
            'normal_pending_workers_cli_stage_required')
    require(paths['original_claim'] == home / MARKER and set(claim) == {
        'schema', 'state', 'input_sha256', 'deadline_mono', 'boot_id'}
        and claim == dict(claim, schema=SCHEMA, state='PARTIAL',
                          input_sha256=request['original_input']['sha256']),
        'exact_original_partial_claim_required')
    require(claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'original_install_boot_changed')
    from scripts.install_containment import Budget
    budget = budget or Budget(old['seconds'], deadline=claim['deadline_mono'])
    require({k:v for k,v in old.items() if k != 'project_files'} ==
            {k:v for k,v in value.items() if k != 'project_files'}, 'resume_operational_settings_changed')
    added = {CLI_OVERLAY, 'patches/hermes/cli-host-stage.patch'}
    require(set(value['project_files']) == set(old['project_files']) | added
            and all(value['project_files'][n] == h for n,h in old['project_files'].items()
                    if n not in {'scripts/friday_install.py', 'scripts/friday_native.py'}),
            'resume_unrelated_source_changed')
    require(set(supervisor) == {'schema', 'original_attempt', 'unit', 'invocation_id',
            'cgroup', 'gnu_pid', 'gnu_starttime_ticks'}
            and supervisor['schema'] == 'friday.install-native-supervision.v1'
            and supervisor['original_attempt'] == claim
            and isinstance(supervisor['unit'], str)
            and re.fullmatch(r'friday-rework-[A-Za-z0-9-]+\.service', supervisor['unit'])
            and re.fullmatch('[0-9a-f]{32}', supervisor['invocation_id'])
            and type(supervisor['gnu_pid']) is int and supervisor['gnu_pid'] > 1
            and type(supervisor['gnu_starttime_ticks']) is int and supervisor['gnu_starttime_ticks'] > 0,
            'original_native_supervision_identity_required')
    cgroup = Path(supervisor['cgroup'])
    require(cgroup.is_absolute() and '..' not in cgroup.parts
            and cgroup.is_relative_to('/sys/fs/cgroup') and cgroup != Path('/sys/fs/cgroup'),
            'original_own_cgroup_required')
    phases = request['completed_phases']
    require(isinstance(phases, dict) and set(phases) == {
        'compose', 'tools', 'dependencies', 'pm_python', 'harness_source', 'harness_toolchain'},
        'exact_completed_phase_inventory_required')
    original_root = Path(old['hermes_prepare']['path']).parents[1]
    python = old['bootstrap_python']['path']
    expected = {
        'compose':[python,'-B',old['hermes_prepare']['path'],'--repository',str(original_root),
                   '--donor',old['hermes_donor'],'--destination',str(home/'hermes-agent'),
                   '--seconds',str(min(120,old['seconds']))],
        'tools':[python,'-B','-m','pm.cli','install','--tools-only'],
        'dependencies':[python,'-B','-m','pm.cli','install','--extra','all','--extra','telegram','--extra','web','--extra','exa'],
        'pm_python':[python,'-B','-c','from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))']}
    for phase in ('source','toolchain'):
        expected['harness_'+phase] = [python,'-B',str(original_root/'scripts/dsh_prepare.py'),phase,
            '--donor',old['dsh_donor'],'--lock',old['sources_lock']['path'],'--evidence',str(home/'preparation/harness')]
    for name, row in phases.items():
        path = pin(row); receipt = read_json(path)
        require(path == home/'preparation/native-install'/(name+'.json')
                and receipt.get('returncode') == 0 and type(receipt.get('returncode')) is int
                and receipt.get('timeout') is False and receipt.get('reaped') is True
                and isinstance(receipt.get('argv'),list) and '--' in receipt['argv']
                and receipt['argv'][receipt['argv'].index('--')+1:] == expected[name],
                'successful_original_phase_required')
    require(paths['failed_build'] == home/'preparation/harness/dsh-build.json'
            and failed.get('reason') == 'command_nonzero_exit'
            and type(failed.get('returncode')) is int and failed['returncode'] != 0
            and failed.get('timeout') is False and failed.get('reaped') is True
            and failed.get('argv') == ['corepack','pnpm','run','build'], 'retained_worker_build_failure_required')
    require((home/CLI_RESUME).exists() is consumed and not (home/CLI_RESUME).is_symlink(),
            'cli_host_resume_already_consumed')
    if validation_value is not None:
        require({k:v for k,v in value.items() if k!='project_files'} ==
                {k:v for k,v in validation_value.items() if k!='project_files'}, 'cli_segment_operational_settings_changed')
        allowed={'scripts/friday_install.py','scripts/friday_native.py','scripts/worker_install.py','plugins/friday_rework/worker_web.py',CLI_OVERLAY,'patches/hermes/cli-host-stage.patch'}
        require(set(value['project_files'])==set(validation_value['project_files'])
                and all(validation_value['project_files'][n]==h for n,h in value['project_files'].items() if n not in allowed),
                'cli_segment_unrelated_source_changed')
        value=validation_value
    budget.call(spec_checked, value, cli_only=True)
    return value, paths, claim, budget


def cli_request_unchanged(request, claim, budget):
    for key in ('original_input','current_input','original_claim','original_supervision','failed_build'):
        budget.call(pin, request[key])
    for row in request['completed_phases'].values(): budget.call(pin, row)
    require(budget.call(read_json,request['original_claim']['path']) == claim, 'install_claim_changed')


def cli_cessation_checked(supervisor, observation):
    require(type(observation) is str and len(observation) <= 65536, 'native_cessation_observation_required')
    rows = {}
    for line in observation.splitlines():
        require('=' in line, 'native_cessation_observation_required')
        key, value = line.split('=',1); require(key not in rows, 'native_cessation_observation_required'); rows[key]=value
    require(set(rows) == {'Id','InvocationID','ActiveState','SubState','MainPID','ControlPID','ControlGroup'}
            and rows['Id'] == supervisor['unit'] and rows['InvocationID'] == supervisor['invocation_id']
            and rows['ActiveState'] in ('inactive','failed') and rows['SubState'] in ('dead','failed')
            and rows['MainPID'] == rows['ControlPID'] == '0' and rows['ControlGroup'] == '',
            'original_native_unit_not_settled')
    require(not os.path.lexists(supervisor['cgroup']), 'original_native_cgroup_still_present')
    try:
        actor=supervisor.get('owned_child',{'pid':supervisor.get('gnu_pid'),'starttime_ticks':supervisor.get('gnu_starttime_ticks')})
        raw = Path('/proc')/str(actor['pid'])/'stat'
        data = raw.read_text(); birth = int(data[data.rfind(')')+2:].split()[19])
        require(birth != actor['starttime_ticks'], 'original_owned_birth_still_present')
    except FileNotFoundError:
        pass


CLI_SEGMENT = 'FRIDAY-INSTALL.cli-segment.intent.json'


def cli_segment_admission():
    """The new budget starts at the actual direct GNU birth, never the old claim."""
    pid = os.getppid()
    proc = Path('/proc')/str(pid)
    raw = (proc/'stat').read_text()
    ticks = int(raw[raw.rfind(')')+2:].split()[19])
    executable = (proc/'exe').resolve()
    expected = Path('/usr/bin/gnutimeout')
    info = expected.stat()
    argv = (proc/'cmdline').read_bytes().split(b'\0')
    require(executable == expected and stat.S_ISREG(info.st_mode) and info.st_uid == 0
            and not info.st_mode & 0o022 and argv[1:4] ==
            [b'--signal=TERM', b'--kill-after=2s', b'900s'], 'direct_bounded_gnu_admission_required')
    start = ticks/os.sysconf('SC_CLK_TCK') + time.monotonic() - time.clock_gettime(time.CLOCK_BOOTTIME)
    require(0 <= time.monotonic()-start < 5, 'fresh_cli_segment_admission_required')
    return {'schema':'friday.cli-segment-clock.v1','seconds':900,'cleanup_seconds':90,
            'started_mono':start,'deadline_mono':start+900,'useful_deadline_mono':start+810,
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'gnu_pid':pid,'gnu_starttime_ticks':ticks}


def cli_segment_clock(clock, deadline=None):
    require(type(clock) is dict and set(clock) == {'schema','seconds','cleanup_seconds',
        'started_mono','deadline_mono','useful_deadline_mono','boot_id','gnu_pid','gnu_starttime_ticks'}
        and clock['schema']=='friday.cli-segment-clock.v1' and clock['seconds']==900
        and clock['cleanup_seconds']==90 and type(clock['started_mono']) in (int,float)
        and math.isfinite(clock['started_mono']) and clock['started_mono'] <= time.monotonic()
        and clock['deadline_mono']==clock['started_mono']+900
        and clock['useful_deadline_mono']==clock['started_mono']+810
        and clock['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        and type(clock['gnu_pid']) is int and clock['gnu_pid']>1
        and type(clock['gnu_starttime_ticks']) is int and clock['gnu_starttime_ticks']>0
        and (deadline is None or deadline==clock['useful_deadline_mono']),
        'exact_cli_segment_clock_required')
    from scripts.install_containment import Budget
    return Budget(900, started=clock['started_mono'], deadline=clock['useful_deadline_mono'])


def cli_segment_inputs(request, budget):
    require(type(request) is dict and set(request)=={'schema','assignment','generation',
        'previous_request','previous_helper','previous_intent','failed_phase','failed_stdout','failed_stderr',
        'previous_cli_supervision','current_input','original_source_receipt'}
        and request['schema']=='friday.cli-segment-request.v1'
        and type(request['assignment']) is str and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
        and request['generation']==1 and type(request['generation']) is int,
        'explicit_cli_segment_pins_required')
    paths={k:budget.call(pin,request[k]) for k in ('previous_request','previous_helper','previous_intent',
        'failed_phase','failed_stdout','failed_stderr','previous_cli_supervision',
        'current_input','original_source_receipt')}
    previous=read_json(paths['previous_request'])
    value=read_json(paths['current_input'])
    prepared=cli_resume_inputs(previous,consumed=True,budget=budget,validation_value=value)
    prepared=(prepared[0],dict(prepared[1],current_input=paths['current_input']),prepared[2],prepared[3])
    _, prior_paths, claim, _ = prepared
    home=Path(value['home'])
    require(time.monotonic()>=claim['deadline_mono'], 'original_attempt_must_remain_exhausted')
    require(paths['previous_intent']==home/CLI_RESUME and read_json(paths['previous_intent'])==
        {'state':'CONSUMED_NOT_COMPLETE','request':previous,'original_attempt':claim},
        'exact_prior_consumed_cli_intent_required')
    require(paths['original_source_receipt']==home/'hermes-agent.source.json',
        'original_full_source_receipt_required')
    for key,suffix in (('failed_phase','.json'),('failed_stdout','.stdout'),('failed_stderr','.stderr')):
        require(paths[key]==home/'preparation/cli-host'/('source_continuation'+suffix),
                'exact_preoverlay_failure_paths_required')
    failure=read_json(paths['failed_phase'])
    stderr=owned_file(paths['failed_stderr']); stdout=owned_file(paths['failed_stdout'])
    previous_value=read_json(pin(previous['current_input']))
    helper=paths['previous_helper']
    require(helper.name=='friday_install.py' and helper.parent.name=='scripts'
            and request['previous_helper']['sha256']==previous_value['project_files']['scripts/friday_install.py'],
            'exact_previous_helper_source_required')
    expected_code='import sys;sys.path.insert(0,'+repr(str(helper.parents[1]))+');from scripts.friday_install import continue_cli_source;continue_cli_source(sys.argv[1],float(sys.argv[2]))'
    from scripts.install_containment import argv as containment_argv
    direct=[value['bootstrap_python']['path'],'-B','-c',expected_code,str(paths['previous_request']),str(claim['deadline_mono'])]
    argv=failure.get('argv',[])
    require(type(argv) is list and len(argv)>3 and argv[0:2]==['/usr/bin/bwrap','--json-status-fd']
            and re.fullmatch('[0-9]+',argv[2]) and argv[3:]==containment_argv('/usr/bin/bwrap',direct)[1:],
            'exact_previous_contained_helper_argv_required')
    code=expected_code
    require(failure.get('returncode')==1 and type(failure.get('returncode')) is int
        and failure.get('timeout') is False and failure.get('reaped') is True
        and failure.get('reason')=='command_nonzero_exit'
        and failure.get('stderr_sha256')==digest(stderr) and failure.get('stdout_sha256')==digest(stdout)
        and failure.get('stderr_bytes')==len(stderr) and failure.get('stdout_bytes')==len(stdout)
        and stdout==b'' and b"ModuleNotFoundError: No module named 'plugins.friday_rework'" in stderr
        and b'worker_install.py' in stderr and b'spec_checked' in stderr
        and isinstance(code,str) and ';from scripts.friday_install import continue_cli_source;' in code
        and failure['argv'][-2:]==[str(paths['previous_request']),str(claim['deadline_mono'])]
        and type(failure.get('pid')) is int and failure['pid']>1
        and type(failure.get('starttime_ticks')) is int and failure['starttime_ticks']>0,
        'exact_known_preoverlay_failure_required')
    supervisor=read_json(paths['previous_cli_supervision'])
    require(set(supervisor)=={'schema','original_attempt','unit','invocation_id','cgroup','owned_child','gnu_birth','witness'}
        and supervisor['schema']=='friday.cli-native-cessation.v1' and supervisor['original_attempt']==claim
        and re.fullmatch(r'friday-rework-[A-Za-z0-9-]+\.service',supervisor['unit'])
        and re.fullmatch('[0-9a-f]{32}',supervisor['invocation_id'])
        and supervisor['owned_child']=={'kind':'bwrap_pid_namespace','pid':failure['pid'],'starttime_ticks':failure['starttime_ticks']}
        and supervisor['gnu_birth']=={'state':'UNKNOWN_NOT_RESOURCE_PROOF'}
        and Path(supervisor['cgroup']).is_relative_to('/sys/fs/cgroup')
        and Path(supervisor['cgroup'])!=Path('/sys/fs/cgroup') and '..' not in Path(supervisor['cgroup']).parts,
        'prior_cli_native_supervision_required')
    witness=read_json(pin(supervisor['witness']))
    props=witness['actual_native_properties']; child=witness['genuine_known_child']
    require(witness['state']=='VERIFIED_NATIVEUNIT_TERMINATED_CGROUP_GONE_DIRECT_BWRAP_CHILD_KNOWN_REAPED'
            and props['Id']==supervisor['unit'] and props['InvocationID']==supervisor['invocation_id']
            and props['MainPID']==props['ControlPID']=='0' and props['ControlGroup']==''
            and props['ActiveState']=='failed' and props['SubState']=='failed'
            and props['ExecMainCode']=='1' and props['ExecMainStatus']=='2'
            and child['pid']==failure['pid'] and child['birth_ticks']==failure['starttime_ticks']
            and child['kind']=='bwrap_PIDnamespace_owner' and child['returncode']==1 and child['reaped'] is True
            and child['phase_json_path']==str(paths['failed_phase'])
            and child['phase_json_sha256']==request['failed_phase']['sha256']
            and witness['GNU_birth_ticks']=='UNKNOWN_not_derived_from_native_exec_timestamp',
            'genuine_prior_cli_custody_witness_required')
    closure=witness['closure']
    require(digest(owned_file(closure['path'],private=True))==closure['sha256']
            and read_json(closure['path'])['own_cgroup_absent'] is True,
            'prior_cli_cgroup_closure_required')
    require(supervisor['cgroup']==str(Path(read_json(prior_paths['original_supervision'])['cgroup']).with_name(supervisor['unit'])),
            'exact_prior_cli_cgroup_required')
    proxy=dict(previous,current_input=request['current_input'])
    return proxy, prepared, supervisor


def cli_segment_recheck(request, claim, budget):
    for key in ('previous_request','previous_helper','previous_intent','failed_phase','failed_stdout',
        'failed_stderr','previous_cli_supervision','current_input','original_source_receipt'):
        # Source receipt is legitimately replaced by the exact overlay after admission.
        if key!='original_source_receipt': budget.call(pin,request[key])
    prior=read_json(pin(request['previous_cli_supervision']))
    budget.call(pin,prior['witness'])
    previous=read_json(pin(request['previous_request']))
    cli_request_unchanged(dict(previous,current_input=request['current_input']),claim,budget)


def continue_cli_segment_source(request_path, deadline):
    request=read_json(request_path)
    value=read_json(pin(request['current_input'])); home=Path(value['home'])
    intent=read_json(home/CLI_SEGMENT)
    require(intent.get('state')=='CONSUMED_NOT_COMPLETE' and intent.get('request')==request,
            'consumed_cli_segment_intent_required')
    budget=cli_segment_clock(intent['clock'],deadline)
    proxy,prepared,_=cli_segment_inputs(request,budget)
    require(intent['original_attempt']==prepared[2], 'original_attempt_changed')
    return _continue_cli_source(proxy,prepared)


def resume_cli_segment(request, request_path, *, admission):
    budget=cli_segment_clock(admission)
    proxy,prepared,supervisor=cli_segment_inputs(request,budget)
    return resume_cli(proxy,request_path,prepared=prepared,
        segment={'request':request,'clock':admission,'supervisor':supervisor})


def continue_cli_source(request_path, deadline):
    """Legitimate exact overlay plus full-byte receipt; no compose/PM replay."""
    request = read_json(request_path)
    value, paths, claim, budget = cli_resume_inputs(request, consumed=True)
    require(deadline == budget.deadline, 'original_install_deadline_required')
    home = Path(value['home']); old = read_json(paths['original_input'])
    require(read_json(home/CLI_RESUME) == {'state':'CONSUMED_NOT_COMPLETE','request':request,
                'original_attempt':claim}, 'cli_host_intent_changed')
    return _continue_cli_source(request,(value,paths,claim,budget))


def _continue_cli_source(request, prepared):
    value,paths,claim,budget=prepared
    home=Path(value['home']);old=read_json(paths['original_input'])
    source = home/'hermes-agent'; receipt_path = home/'hermes-agent.source.json'
    receipt = read_json(receipt_path)
    donors = {r['id']:r for r in read_json(pin(value['sources_lock']))['repositories']}
    budget.call(composition_checked,old,source,receipt,donors['hermes'])
    manifest_path = ROOT/CLI_OVERLAY; manifest = read_json(manifest_path)
    require(manifest['base_commit'] == receipt['commit']
            and manifest['patch'] == 'patches/hermes/cli-host-stage.patch', 'cli_overlay_identity_changed')
    for name, expected in manifest['prerequisites'].items():
        require(old['project_files'].get(name) == expected, 'cli_overlay_prerequisite_changed')
    require({r['path'] for r in manifest['files']} == {
        'hermes_cli/friday_credential_admission.py','hermes_cli/friday_dashboard_owner.py'}, 'cli_overlay_scope_changed')
    for row in manifest['files']:
        require(digest(budget.call(owned_file,source/row['path'])) == row['before_sha256']
                and receipt['files'][row['path']]['sha256'] == row['before_sha256'], 'cli_overlay_input_changed')
    patch = pin({'path':str(ROOT/manifest['patch']),'sha256':manifest['patch_sha256']})
    original = budget.call(owned_file,receipt_path,private=True)
    preserved = home/'hermes-agent.source.json.original-cli'
    fd=os.open(preserved,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream: stream.write(original);stream.flush();os.fsync(stream.fileno())
    from scripts.dsh_prepare import run
    env=clean_environment(home)
    for checking in (True,False):
        command=['git','--no-optional-locks','apply','--whitespace=nowarn']
        if checking: command.append('--check')
        command.append(str(patch))
        run(command,source,timeout=min(30,budget.check(reserve=1)),env=env,deadline=budget.deadline)
    for row in manifest['files']:
        data=budget.call(owned_file,source/row['path'])
        require(digest(data)==row['sha256'] and len(data)==row['bytes']
                and not (source/row['path']).stat().st_mode & 0o111, 'cli_overlay_output_changed')
        receipt['files'][row['path']]={k:row[k] for k in ('sha256','bytes','mode')}
    receipt['layers'].append({'manifest':CLI_OVERLAY,
        'manifest_sha256':value['project_files'][CLI_OVERLAY], 'patch_sha256':manifest['patch_sha256']})
    budget.call(composition_checked,value,source,receipt,donors['hermes'])
    cli_request_unchanged(request,claim,budget)
    staged=home/'hermes-agent.source.json.cli-completed'
    publish(staged,receipt,budget=budget);budget.call(os.replace,staged,receipt_path)
    budget.call(composition_checked,value,source,read_json(receipt_path),donors['hermes'])
    return {'state':'CLI_SOURCE_CONTINUED_FULL_BYTES_VERIFIED','ready':False}


def resume_cli(request, request_path, *, prepared=None, segment=None):
    value, paths, claim, budget = prepared or cli_resume_inputs(request)
    require(read_json(request_path)==(segment['request'] if segment else request), 'resume_request_changed')
    home=Path(value['home']); source=home/'hermes-agent'; supervisor=read_json(paths['original_supervision'])
    require(not any(os.path.lexists(home/n) for n in ('FRIDAY-PROFILE.json','config.yaml','.env','auth.json',
        'preparation/a0-service.intent.json','preparation/a0-service.receipt.json','workers',
        MARKER+'.cli-completed','hermes-agent.source.json.original-cli')), 'cli_resume_effect_destination_exists')
    from scripts.install_containment import Containment
    custody=Containment(value['containment'],budget,clean_environment(home))
    old=read_json(paths['original_input']); donors={r['id']:r for r in read_json(pin(value['sources_lock']))['repositories']}
    budget.call(composition_checked,old,source,read_json(home/'hermes-agent.source.json'),donors['hermes'])
    runtime=directory(Path('/run/user')/str(os.getuid()))
    bus=runtime/'bus'; info=bus.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1, 'owned_user_bus_required')
    command=['/usr/bin/env','XDG_RUNTIME_DIR='+str(runtime),
        'DBUS_SESSION_BUS_ADDRESS=unix:path='+str(bus), '/usr/bin/systemctl','--user','show',
        supervisor['unit'],'--property=Id,InvocationID,ActiveState,SubState,MainPID,ControlPID,ControlGroup']
    # User systemd owns the native host namespace. This fixed read-only query
    # uses the existing directly reaped command runner; all effectful phases
    # below still require the original PID-namespace Containment.
    from scripts.dsh_prepare import run
    observation=run(command,ROOT,timeout=min(15,budget.check(reserve=1)),
        env=custody.env,deadline=budget.deadline)[0]
    budget.call(cli_cessation_checked,supervisor,observation)
    cli_request_unchanged(request,claim,budget)
    if segment:
        previous=segment['supervisor']
        observation=run(command[:-2]+[previous['unit'],command[-1]],ROOT,timeout=min(15,budget.check(reserve=1)),env=custody.env,deadline=budget.deadline)[0]
        budget.call(cli_cessation_checked,previous,observation)
        cli_segment_recheck(segment['request'],claim,budget)
        require(not os.path.lexists(home/CLI_SEGMENT) and not os.path.lexists(home/(MARKER+'.original-cli-segment'))
                and not os.path.lexists(home/'preparation/cli-host-segment'), 'cli_segment_already_consumed')
        publish(home/CLI_SEGMENT,{'state':'CONSUMED_NOT_COMPLETE','request':segment['request'],'clock':segment['clock'],'original_attempt':claim},budget=budget)
        raw=budget.call(owned_file,home/MARKER,private=True)
        fd=os.open(home/(MARKER+'.original-cli-segment'),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            budget.check();stream.write(raw);stream.flush();os.fsync(stream.fileno());budget.check()
    else:
        publish(home/CLI_RESUME,{'state':'CONSUMED_NOT_COMPLETE','request':request,'original_attempt':claim},budget=budget)
    def execute(phase, command, *, read_only=False, timeout=120):
        cli_request_unchanged(request,claim,budget)
        if segment: cli_segment_recheck(segment['request'],claim,budget)
        return custody.run(command,source,timeout=timeout,read_only=read_only,
            log=home/('preparation/cli-host-segment' if segment else 'preparation/cli-host')/phase)[0]
    code='import sys;sys.path.insert(0,'+repr(str(ROOT))+');from scripts.friday_install import continue_cli_source;continue_cli_source(sys.argv[1],float(sys.argv[2]))'
    if segment: code=code.replace('continue_cli_source','continue_cli_segment_source')
    execute('source_continuation',[value['bootstrap_python']['path'],'-B','-c',code,str(request_path),str(budget.deadline)])
    expression='from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))'
    selected=execute('pm_python',[value['bootstrap_python']['path'],'-B','-c',expression],read_only=True,timeout=15)
    require(Path(selected).is_absolute() and Path(selected).is_file(), 'native_pm_python_missing')
    execute('native_cli_completion',[selected,'-B',str(ROOT/'scripts/friday_native.py'),'install-cli',
        '--input',str(paths['current_input']),'--deadline',str(budget.deadline)],timeout=300)
    code='import sys;sys.path.insert(0,'+repr(str(ROOT))+');from scripts.friday_install import verify_completed_native;verify_completed_native(sys.argv[1],float(sys.argv[2]),cli_host=True)'
    execute('completed_cli_check',[selected,'-B','-c',code,str(paths['current_input']),str(budget.deadline)],read_only=True)
    receipt_path=home/'hermes-agent.source.json'; receipt=read_json(receipt_path)
    marker={'schema':SCHEMA,'state':'INSTALLED_TEMPLATE_INCOMPLETE','completion_stage':CLI_STAGE,
        'worker_state':'BOTH_WORKERS_PREPARATION_PENDING','worker_preparation_mode':'BOTH_WORKERS_REQUIRED',
        'native_frontends':'PENDING','input_sha256':request['current_input']['sha256'],
        'source_receipt_sha256':digest(owned_file(receipt_path)), 'home':str(home),'source':str(source),
        'runtime_ready':False,'gateway_installed':False,'original_attempt':claim,
        'remaining':gaps(),'invocation_completion':'NOT_PROVEN_BY_OUTPUT_RECEIPT',
        'profile_files':{n:digest(owned_file(home/n,private=True)) for n in ('config.yaml','SOUL.md','FRIDAY-PROFILE.json')},
        'plugin_files':{n:h for n,h in value['project_files'].items() if n.startswith('plugins/friday_rework/')}}
    if segment:
        marker['cli_segment']={'clock':segment['clock'],'request':segment['request'],'intent_sha256':digest(owned_file(home/CLI_SEGMENT,private=True)),'original_claim_sha256':digest(owned_file(home/(MARKER+'.original-cli-segment'),private=True))}
    if 'tls' in value['product']['dashboard']:
        marker['tls_files']={p:digest(owned_file(home/p,private=True)) for p in value['product']['dashboard']['tls'].values()}
    cli_request_unchanged(request,claim,budget)
    publish(home/(MARKER+'.cli-completed'),marker,budget=budget)
    require(read_json(home/MARKER)==claim,'install_claim_changed')
    budget.call(os.replace,home/(MARKER+'.cli-completed'),home/MARKER)
    return budget.call(inspect,value,request['current_input']['sha256'])


def inspect(value, input_hash):
    home = canonical(value['home']); directory(home)
    marker = read_json(home / MARKER)
    require(marker.get('schema') == SCHEMA and marker.get('home') == str(home)
            and marker.get('input_sha256') == input_hash
            and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE', 'foreign_or_partial_install')
    home, donors = spec_checked(value, cli_only=marker.get('completion_stage') == CLI_STAGE)
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
    if marker.get('completion_stage') == CLI_STAGE:
        require(marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
                and marker.get('runtime_ready') is False and value['product']['runtime'] == {'enabled':False}
                and marker.get('gateway_installed') is False and marker.get('native_frontends') == 'PENDING',
                'cli_host_pending_state_required')
        return {'state':'CLI_HOST_WORKERS_PENDING','ready':False,'home':str(home),'effects':'NONE',
                'per_job_authority':'NOT_GRANTED','full_start_allowed':False,'remaining':gaps()}
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
    require(budget.call(read_json,home/MARKER).get('completion_stage') != CLI_STAGE, 'cli_host_full_start_refused')
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
    parser.add_argument('phase', choices=('plan', 'install', 'check', 'dashboard-check', 'start', 'qualify', 'reconcile', 'resume-harness', 'resume-cli', 'continue-cli-segment'))
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
        admission = cli_segment_admission() if args.phase=='continue-cli-segment' else None
        prepared = (resume_inputs(value) if args.phase == 'resume-harness' else
                    cli_resume_inputs(value) if args.phase == 'resume-cli' else None)
        budget = cli_segment_clock(admission) if admission else (prepared[3] if prepared else Budget(value.get('seconds'), started=started))
        budget.check()
        if args.phase == 'continue-cli-segment':
            result = resume_cli_segment(value,args.input,admission=admission)
        elif args.phase == 'resume-harness':
            result = resume_harness(value, args.input, prepared=prepared)
        elif args.phase == 'resume-cli':
            result = resume_cli(value,args.input,prepared=prepared)
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
        exit_retaining_cause(parser, 3, exc, args.phase)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        # Native errors/inputs can contain credentials: print no exception body.
        exit_retaining_cause(parser, 2, exc, args.phase)



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
    # Helpers import require/Refused from this canonical module. Executing the
    # file as __main__ must keep the same class identity, or typed refusals are
    # misreported as generic native failures at the public CLI boundary.
    canonical_module = sys.modules.get('scripts.friday_install')
    if canonical_module is not None and canonical_module is not sys.modules[__name__]:
        print('Friday entry refused: phase=entry reason=installer_module_identity_conflict', file=sys.stderr)
        raise SystemExit(2)
    sys.modules['scripts.friday_install'] = sys.modules[__name__]
    main()
