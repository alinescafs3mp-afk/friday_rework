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
INSTALLED_CLI_QUERY = ('С помощью инструмента read_file прочитай строки 30–34 файла '+str(ROOT/'README.md')+'. Назови три главных компонента архитектуры Пятницы одним предложением по-русски. Ничего не изменяй.')


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


def source_checked(source, receipt, donor, *, proven_cache=None):
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
        require(name in files or name in generated_files or name.startswith(generated)
                or (proven_cache is not None and name in proven_cache
                    and digest(owned_file(p,private=True))==proven_cache[name]['sha256']),
                'unexpected_composed_source_file')
    return files


def composition_checked(value, source, receipt, donor, *, proven_cache=None):
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
    return source_checked(source, receipt, donor,proven_cache=proven_cache)


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


def cli_resume_inputs(request, *, consumed=False, budget=None, validation_value=None, closed_history=False):
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
    if closed_history:
        require(consumed and budget is not None and cli_historical_scope_closed(claim,'friday.native-install.v1'),
                'original_attempt_must_remain_exhausted')
    else:
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
    prepared=cli_resume_inputs(previous,consumed=True,budget=budget,validation_value=value,closed_history=True)
    prepared=(prepared[0],dict(prepared[1],current_input=paths['current_input']),prepared[2],prepared[3])
    _, prior_paths, claim, _ = prepared
    home=Path(value['home'])
    require(cli_historical_scope_closed(claim,'friday.native-install.v1'), 'original_attempt_must_remain_exhausted')
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


def inspect(value, input_hash, *, marker_override=None):
    home = canonical(value['home']); directory(home)
    marker = read_json(home / MARKER) if marker_override is None else marker_override
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


CLI_RUNTIME_CAPS = {'memory.max':'2147483648','memory.swap.max':'0',
                    'pids.max':'128','cpu.max':'200000 100000'}


def installed_cli_clock():
    """Observe the actual direct GNU birth once, independently of installation."""
    pid = os.getppid(); proc = Path('/proc')/str(pid)
    raw = (proc/'stat').read_text(); ticks = int(raw.rsplit(')',1)[1].split()[19])
    binary = Path('/usr/bin/gnutimeout'); info = binary.stat()
    require((proc/'exe').resolve() == binary and stat.S_ISREG(info.st_mode)
            and info.st_uid == 0 and not info.st_mode & 0o022
            and (proc/'cmdline').read_bytes().split(b'\0')[1:4] ==
                [b'--signal=TERM',b'--kill-after=2s',b'180s'],
            'installed_cli_direct_gnu180_required')
    start = ticks/os.sysconf('SC_CLK_TCK') + time.monotonic()-time.clock_gettime(time.CLOCK_BOOTTIME)
    require(0 <= time.monotonic()-start < 5, 'installed_cli_fresh_gnu_birth_required')
    return {'schema':'friday.installed-cli-clock.v1','seconds':180,'cleanup_seconds':30,
            'started_mono':start,'deadline_mono':start+180,'useful_deadline_mono':start+150,
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'gnu_pid':pid,'gnu_starttime_ticks':ticks}


def installed_cli_kernel(request, clock, *, phase="installed-cli"):
    require(phase in ("installed-cli", "repair-installed-cli", "repair-frontend-close", "repair-native-bootstrap", "repair-session-artifact"), "installed_cli_exact_phase_required")
    if phase in ("repair-installed-cli", "repair-frontend-close", "repair-native-bootstrap", "repair-session-artifact"):
        require(request.get("phase") == phase, "installed_cli_exact_phase_required")
    """Prove current GNU, native owner and kernel caps before admission writes."""
    import resource
    require(os.getppid() == clock['gnu_pid']
            and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == clock['boot_id']
            and clock['started_mono'] <= time.monotonic() < clock['useful_deadline_mono']-(90 if phase == 'installed-cli' else 1),
            'installed_cli_owner_or_useful_time_changed')
    proc = Path('/proc')/str(clock['gnu_pid']); raw = (proc/'stat').read_text()
    require(int(raw.rsplit(')',1)[1].split()[19]) == clock['gnu_starttime_ticks']
            and (proc/'exe').resolve() == Path('/usr/bin/gnutimeout')
            and (proc/'cmdline').read_bytes().split(b'\0')[1:4] ==
                [b'--signal=TERM',b'--kill-after=2s',b'180s'], 'installed_cli_gnu_birth_changed')
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    require(len(rows)==1 and rows[0].startswith('0::/'), 'installed_cli_unified_cgroup_required')
    group = rows[0][3:]; unit = group.rsplit('/',1)[-1]
    require(re.fullmatch(r'friday-rework-cli-'+('runtime' if phase == 'installed-cli' else 'repair')+r'-[A-Za-z0-9-]+\.service',unit)
            and unit == request['unit'] and '..' not in Path(group).parts
            and (proc/'cgroup').read_text() == Path('/proc/self/cgroup').read_text(),
            'installed_cli_owned_native_cgroup_required')
    root = Path('/sys/fs/cgroup')/group.lstrip('/')
    require(all((root/k).read_text().strip()==v for k,v in CLI_RUNTIME_CAPS.items()),
            'installed_cli_physical_caps_required')
    require(os.sched_getaffinity(0)==os.sched_getaffinity(clock['gnu_pid'])=={0,1}
            and resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
            and resource.getrlimit(resource.RLIMIT_FSIZE)==(268435456,268435456),
            'installed_cli_native_limits_required')
    from scripts.dsh_prepare import run
    runtime = directory(Path('/run/user')/str(os.getuid())); bus=runtime/'bus'; info=bus.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink==1,
            'owned_user_bus_required')
    props='Id,InvocationID,ActiveState,SubState,MainPID,ControlPID,ControlGroup,RuntimeMaxUSec,TimeoutStopUSec,KillMode'
    command=['/usr/bin/env','XDG_RUNTIME_DIR='+str(runtime),'DBUS_SESSION_BUS_ADDRESS=unix:path='+str(bus),
             '/usr/bin/systemctl','--user','show',unit,'--property='+props]
    text=run(command,ROOT,timeout=5,env=clean_environment(Path(request['home'])),
             deadline=clock['useful_deadline_mono'])[0]
    pairs=[r.split('=',1) for r in text.splitlines()]; observed=dict(pairs)
    require(re.fullmatch('[0-9a-f]{32}', observed.get('InvocationID',''))
            and len(pairs)==len(observed)==10 and observed == {'Id':unit,'InvocationID':observed['InvocationID'],
            'ActiveState':'active','SubState':'running','MainPID':str(clock['gnu_pid']),'ControlPID':'0',
            'ControlGroup':group,'RuntimeMaxUSec':'2min 28s','TimeoutStopUSec':'30s','KillMode':'control-group'},
            'installed_cli_actual_native_unit_required')
    version=run(['/usr/bin/gnutimeout','--version'],ROOT,timeout=3,
                env=clean_environment(Path(request['home'])),deadline=clock['useful_deadline_mono'])[0]
    require(version.startswith('timeout (GNU coreutils) '), 'installed_cli_genuine_gnu_required')
    return {'unit':unit,'invocation_id':observed['InvocationID'],'cgroup':group,
            'caps':dict(CLI_RUNTIME_CAPS),'self_stat':Path('/proc/self/stat').read_text(),
            'gnu_stat':raw,'gnu_limits':(proc/'limits').read_text(),
            'self_limits':Path('/proc/self/limits').read_text(),'gnu_version':version.splitlines()[0]}


def cli_session_artifact_inputs(home, binding, *, resumed=False):
    """Exact completed owned native session, WAL-aware readonly snapshot."""
    import sqlite3, hashlib, math, re
    home = Path(home)
    require(type(binding) is dict and set(binding) == {'schema','id','database','row_sha256',
            'messages_sha256','stable_messages_sha256','initial_lifecycle_sha256','message_ids','identity','output','max_bytes'}
            and binding['schema'] == 'friday.cli-session-artifact.v2'
            and type(binding['id']) is str and re.fullmatch(r'[0-9]{8}_[0-9]{6}_[0-9a-f]{6}',binding['id'])
            and binding['database'] == str(home/'state.db')
            and binding['output'] == str(home/'user-artifacts/session-followup.txt')
            and type(binding['max_bytes']) is int and binding['max_bytes'] == 8192,
            'cli_session_artifact_scope_required')
    path = home/'state.db'; st = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
            and st.st_nlink == 1 and not st.st_mode & 0o077, 'cli_session_owned_database_required')
    for suffix in ('-wal','-shm'):
        side = path.with_name(path.name+suffix)
        if side.exists() or side.is_symlink():
            ss = side.lstat()
            require(side.resolve() == side and stat.S_ISREG(ss.st_mode) and ss.st_uid == os.getuid()
                    and ss.st_nlink == 1 and not ss.st_mode & 0o077, 'cli_session_owned_database_required')
    connection = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0.2)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
        row = connection.execute('SELECT * FROM sessions WHERE id=?',(binding['id'],)).fetchone()
        require(row is not None, 'cli_session_missing')
        row = dict(row)
        identity = {k:row[k] for k in binding['identity']}
        require(set(binding['identity']) == {'id','source','created_source','user_id','origin_json',
                'profile_name','cwd','model','billing_provider','billing_base_url','parent_session_id'}
                and identity == binding['identity'] and row['source'] == row['created_source'] == 'cli'
                and row['profile_name'] == 'default' and row['user_id'] is None and row['origin_json'] is None
                and row['parent_session_id'] is None and row['cwd'] == str(home/'hermes-agent')
                and row['model'] == 'dispatcher' and row['billing_provider'] == 'custom',
                'cli_session_foreign_identity')
        require(resumed or (type(row['ended_at']) in (int,float) and math.isfinite(row['ended_at'])
                and row['end_reason'] == 'cli_close' and row['message_count'] == 4
                and not row['archived'] and not row['hidden']), 'cli_session_unfinished')
        fingerprint = lambda value: hashlib.sha256(json.dumps(value,sort_keys=True,
                    separators=(',',':'),ensure_ascii=False,default=lambda b:{'sqlite_blob_hex':b.hex()}).encode()).hexdigest()
        require(resumed or fingerprint(row) == binding['row_sha256'], 'cli_session_row_changed')
        messages = [dict(r) for r in connection.execute(
                'SELECT * FROM messages WHERE session_id=? ORDER BY id LIMIT 65',(binding['id'],))]
        # Compression may archive/rewind originals, but their replay payload remains immutable.
        stable = [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in messages[:4]]
        lifecycle = [{k:m[k] for k in ('id','active','compacted')} for m in messages[:4]]
        require(resumed or fingerprint(lifecycle) == binding['initial_lifecycle_sha256'],
                'cli_session_initial_lifecycle_changed')
        require(len(messages) < 65 and len(messages) >= 4 and binding['message_ids'] == [r['id'] for r in messages[:4]]
                and fingerprint(stable) == binding['stable_messages_sha256']
                and (resumed or fingerprint(messages[:4]) == binding['messages_sha256'])
                and (resumed or len(messages) == 4), 'cli_session_history_changed')
        return row, messages
    finally:
        connection.close()


def cli_session_artifact_path(home, binding, *, absent=True):
    path = Path(binding['output']); parent = Path(home)/'user-artifacts'
    require(path == parent/'session-followup.txt' and path.parent.resolve() == parent,
            'cli_session_artifact_escape')
    st = parent.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077,
            'cli_session_artifact_parent_unowned')
    if absent:
        require(not path.exists() and not path.is_symlink(), 'cli_session_artifact_exists_no_retry')
    else:
        st = path.lstat()
        require(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
                and st.st_nlink == 1 and not st.st_mode & 0o077 and 0 < st.st_size <= binding['max_bytes'],
                'cli_session_artifact_invalid')
    return path


def cli_session_artifact_argv(home, binding):
    query = ('Продолжи эту сохранённую сессию. Сохрани краткое русское резюме архитектуры Пятницы '
             '(Hermes, DeepSeek Harness и Agent Zero) из предыдущего ответа с помощью инструмента '
             'write_file в файл '+str(Path(home)/'user-artifacts/session-followup.txt')+
             '. Не более 8192 байт UTF-8. После сохранения кратко подтверди результат и заверши работу.')
    return ['-p','default','--cli','chat','--oneshot','-t','file','--run-budget','90',
            '--max-turns','4','--resume',binding['id'],'--no-restore-cwd','-q',query]


def installed_cli(request, request_path, *, clock):
    session_artifact = request.get('schema') == 'friday.installed-cli-request.v4'
    require(type(request) is dict and set(request)==({'schema','assignment','generation','home',
        'installation_input','repaired_input','historical_marker','native_launcher','history','unit','invocation_id','argv'} | ({'session_artifact'} if session_artifact else set()))
        and request['schema'] in ('friday.installed-cli-request.v1','friday.installed-cli-request.v2','friday.installed-cli-request.v3','friday.installed-cli-request.v4') and request['generation']==1
        and type(request['generation']) is int
        and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
        and request['invocation_id']=='OBSERVE_NATIVE_AT_ADMISSION', 'installed_cli_exact_request_required')
    from scripts.install_containment import Budget, Containment
    budget=Budget(180,started=clock['started_mono'],deadline=clock['useful_deadline_mono'])
    physical=budget.call(installed_cli_kernel,request,clock)
    frontend = request['schema'] != 'friday.installed-cli-request.v1'
    bootstrap_chain = request['schema'] in ('friday.installed-cli-request.v3','friday.installed-cli-request.v4')
    original=read_json(pin(request['installation_input']));value=read_json(pin(request['repaired_input']))
    require({k:v for k,v in original.items() if k!='project_files'} ==
            {k:v for k,v in value.items() if k!='project_files'}
            and value['home']==request['home'], 'installed_cli_operational_settings_changed')
    home=Path(value['home']);source=home/'hermes-agent';marker=read_json(home/MARKER)
    historical=read_json(pin(request['historical_marker']))
    require(request['historical_marker']['path']==str(home/(MARKER+'.original-runtime-repair'))
            and marker['postinstall_original_marker']==request['historical_marker']
            and marker['postinstall_source_input']==request['repaired_input']
            and {k:v for k,v in marker.items() if k not in {'source_receipt_sha256',
                'postinstall_original_marker','postinstall_source_input','postinstall_native_launcher'} |
                ({'postinstall_frontend_repair'} if frontend else set()) |
                ({'postinstall_native_bootstrap_repair'} if bootstrap_chain else set()) |
                ({'postinstall_session_artifact_repair'} if session_artifact else set())} ==
                {k:v for k,v in historical.items() if k!='source_receipt_sha256'}
            and marker['input_sha256']==request['installation_input']['sha256']
            and cli_historical_scope_closed(historical['original_attempt'],'friday.native-install.v1')
            and cli_historical_scope_closed(historical['cli_segment']['clock'],'friday.cli-segment-clock.v1'),
            'installed_cli_historical_segments_changed')
    require(set(request['history'])=={CLI_SEGMENT,CLI_RESUME,MARKER+'.original-cli-segment'}
            and all(digest(owned_file(home/name,private=True))==sha for name,sha in request['history'].items()),
            'installed_cli_immutable_history_changed')
    budget.call(validated_cli_installation_history,home,marker,request['history'],owned_file)
    query=INSTALLED_CLI_QUERY
    expected=['-p','default','--cli','chat','--oneshot','-t','file','--run-budget','90','--max-turns','4','-q',query]
    if session_artifact:
        expected = cli_session_artifact_argv(home,request['session_artifact'])
        budget.call(cli_session_artifact_inputs,home,request['session_artifact'])
        budget.call(cli_session_artifact_path,home,request['session_artifact'])
    require(request['argv']==expected, 'installed_cli_exact_file_query_required')
    budget.call(inspect,value,request['installation_input']['sha256'])
    require(marker.get('completion_stage')==CLI_STAGE, 'installed_cli_host_stage_required')
    launch=source/'.hermes/bin/hermes'
    require(request['native_launcher']['path']==str(launch)
            and marker['postinstall_native_launcher']==request['native_launcher']
            and pin(request['native_launcher'])==launch and os.access(launch,os.X_OK),
            'installed_cli_native_launcher_required')
    budget.call(cli_repair_plugins,value,home,marker,{})
    full_receipt=read_json(home/'hermes-agent.source.json')
    require(len(full_receipt['layers'])==(37 if session_artifact else 36 if bootstrap_chain else 35 if frontend else 34) and read_json(source/'install-stamp.json')['fridaySource']==
            {'baseTree':full_receipt['base_tree'],'layers':full_receipt['layers']},'installed_cli_full_stamp_required')
    custody=Containment(value['containment'],budget,clean_environment(home))
    repair_intent=read_json(home/CLI_REPAIR_INTENT)
    if bootstrap_chain:
        budget.call(validated_cli_repair_chain,home,marker,request)
        delta=read_json(pin(marker['postinstall_native_bootstrap_repair']['intent']))
        frontend_delta=read_json(pin(marker['postinstall_frontend_repair']['intent']))
        expected_previous=frontend_delta['request']['previous_input']
        token = CLI_SESSION_RUNTIME_INTENT if session_artifact else CLI_BOOTSTRAP_RUNTIME_INTENT
        require(not (home/token).exists() and not (home/token).is_symlink(), 'bootstrap_journey_consumed_no_retry')
        if session_artifact:
            repair = read_json(pin(marker['postinstall_session_artifact_repair']['intent']))
            require(repair['request']['session_artifact'] == request['session_artifact'], 'cli_session_scope_changed')
            budget.call(cli_bootstrap_previous_journey,repair['request'],home,session_artifact=True)
    elif frontend:
        delta=budget.call(cli_frontend_chain,request,home,marker)
        expected_previous=delta['request']['previous_input']
        require(not (home/CLI_FRONTEND_RUNTIME_INTENT).exists()
                and not (home/CLI_FRONTEND_RUNTIME_INTENT).is_symlink(), 'frontend_journey_consumed_no_retry')
    else:
        expected_previous=request['repaired_input']
    require(repair_intent.get('schema')=='friday.installed-cli-repair-intent.v1'
            and repair_intent.get('state')=='CONSUMED_NO_RETRY'
            and repair_intent['request']['repaired_input']==expected_previous,
            'installed_cli_repair_intent_required')
    budget.call(cli_repair_native,custody,value,source,bootstrap_pin(repair_intent['request']['selected_python']),budget)
    physical=budget.call(installed_cli_kernel,request,clock)
    require(read_json(request_path)==request, 'installed_cli_request_changed')
    folder=home/'preparation/cli-runtime';folder.mkdir(mode=0o700,exist_ok=True);directory(folder)
    intent={'schema':'friday.installed-cli-invocation.v1','state':'CONSUMED_NOT_COMPLETE',
            'request':request,'clock':clock,'physical':physical,'history':request['history']}
    if bootstrap_chain:
        publish(home/(CLI_SESSION_RUNTIME_INTENT if session_artifact else CLI_BOOTSTRAP_RUNTIME_INTENT),intent,budget=budget)
    elif frontend:
        publish(home/CLI_FRONTEND_RUNTIME_INTENT,intent,budget=budget)
    publish(folder/(request['unit']+'.intent.json'),intent,budget=budget)
    result=custody.run([str(launch),*expected],source,timeout=min(120,budget.check(reserve=1)),
                       log=folder/(request['unit']+'.native'))
    if session_artifact:
        row,messages = budget.call(cli_session_artifact_inputs,home,request['session_artifact'],resumed=True)
        artifact = budget.call(cli_session_artifact_path,home,request['session_artifact'],absent=False)
        raw = owned_file(artifact,private=True)
        require(result[1]['returncode'] == 0 and result[1]['timeout'] is False
                and row['end_reason'] == 'cli_close' and row['ended_at'] is not None
                and all(name in raw.decode('utf-8') for name in ('Hermes','Harness','Zero'))
                and any(m['role']=='tool' and m['tool_name']=='write_file'
                    and json.loads(m['content']).get('success') is True for m in messages[4:]),
                'cli_session_artifact_native_completion_required')
    for name,sha in request['history'].items():
        require(digest(owned_file(home/name,private=True))==sha,'installed_cli_history_changed_after_runtime')
    require(read_json(home/MARKER)==marker, 'installed_cli_marker_changed_after_runtime')
    publish(folder/(request['unit']+'.result.json'),{'schema':'friday.installed-cli-result.v1',
            'state':'NATIVE_EXIT_OBSERVED_NOT_ACCEPTANCE','clock':clock,'observation':result[1],
            'Runtime_Go':False,'Resource_Go':False,'Release_Go':False},budget=budget)
    return {'state':'NATIVE_EXIT_OBSERVED_NOT_ACCEPTANCE','ready':False,
            'runtime_ready':False,'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}





# One postinstallation transaction; historical installation scopes never reopen.
CLI_REPAIR_INTENT = 'FRIDAY-INSTALL.postinstall-cli-repair.intent.json'
CLI_REPAIR_OVERLAYS = ('patches/hermes/cli-launcher-no-bytecode-manifest.json',
                       'patches/hermes/installed-cli-runtime-manifest.json')
CLI_CACHE_PROOF_SHA256 = '112ba47e9c48b7bd68b2ec0ea98925bb7c6c3ca349135b54e2fe9d3d7845dd84'


def cli_repair_bytes(path, data, budget, *, mode=0o600):
    """Exclusive, durable custody. Never replace an existing beforeimage."""
    budget.check()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(data);stream.flush();os.fsync(fd)
        os.fchmod(fd,mode);budget.check()
    finally:
        os.close(fd)
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(parent)
    finally:os.close(parent)


def cli_repair_replace(path, data, before_sha256, budget, *, mode):
    """A pinned preimage and exclusive staging file precede every replacement."""
    require(digest(owned_file(path))==before_sha256,'cli_repair_replace_preimage_changed')
    staged=path.with_name(path.name+'.postinstall-cli-repair.pending')
    cli_repair_bytes(staged,data,budget,mode=mode)
    require(digest(owned_file(path))==before_sha256,'cli_repair_replace_preimage_changed')
    budget.check();os.replace(staged,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    require(owned_file(path)==data,'cli_repair_publication_changed')


def cli_repair_plugins(value, home, marker, cache):
    expected={n:h for n,h in value['project_files'].items() if n.startswith('plugins/friday_rework/')}
    require(marker.get('plugin_files')==expected,'cli_repair_plugin_mapping_changed')
    names=set()
    for path in (home/'plugins/friday_rework').rglob('*'):
        require(not path.is_symlink(),'cli_repair_plugin_link_refused')
        if path.is_file():names.add(str(path.relative_to(home)))
    require(names==set(expected)|set(cache),'cli_repair_exact_plugin_inventory_required')
    for name,sha in expected.items():
        require(digest(owned_file(home/name,private=True))==sha,'cli_repair_plugin_source_changed')
    return expected


def cli_repair_history(request, home):
    require(set(request['history'])=={CLI_SEGMENT,CLI_RESUME,MARKER+'.original-cli-segment'},
            'cli_repair_exact_history_required')
    for name,sha in request['history'].items():
        require(re.fullmatch('[0-9a-f]{64}',sha) and digest(owned_file(home/name,private=True))==sha,
                'cli_repair_history_changed')
    validated_cli_installation_history(home,read_json(home/MARKER),request['history'],owned_file)


def cli_repair_cache(proof, value, home):
    require(proof.get('magic')=='2b0e0d0a' and len(proof.get('files',[]))==18,
            'cli_repair_exact_cache_proof_required')
    rows={}
    for row in proof['files']:
        path=canonical(row['path']);require(path.is_relative_to(home/'plugins/friday_rework'),
                                           'cli_repair_cache_path_refused')
        name=str(path.relative_to(home));src=row['source']
        require(name not in rows and '/__pycache__/' in name and name.endswith('.cpython-314.pyc')
                and src in value['project_files'] and row['source_sha256']==value['project_files'][src]
                and row.get('exact_code_matches_without_execution') is True,
                'cli_repair_cache_source_proof_changed')
        raw=owned_file(path,private=True)
        require(len(raw)==row['bytes'] and digest(raw)==row['sha256']
                and raw[:4].hex()==proof['magic'] and raw[4:8]==b'\0\0\0\0'
                and digest(owned_file(home/src,private=True))==row['source_sha256'],
                'cli_repair_cache_bytes_changed')
        rows[name]=row
    return rows


def cli_repair_native(custody, value, source, selected, budget, *, publish_launchers=False, log=None):
    """The original PM renderer/API, on the same selected Python; no CLI/model boot."""
    helper = """import sys,json,shlex,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from hermes_cli import _launchers as native
selected=native.resolve_store_python(root,publication=True)
assert selected is not None and selected.resolve()==Path(sys.argv[2])
assert set(native.ENTRY_POINTS)=={'hermes','hermes-acp'}
if sys.argv[3]=='publish':
    assert set(native.ensure_install_launchers(root,root/'.hermes/bin'))=={str(root/'.hermes/bin'/n) for n in native.ENTRY_POINTS}
rows={}
for name in native.ENTRY_POINTS:
    target=root/'.hermes/bin'/name
    expected=('#!/bin/sh\\nexec '+shlex.join([str(selected),'-I','-c',native._launcher_script(name,root,None)])+' \\"$@\\"\\n').encode()
    assert target.read_bytes()==expected and target.stat().st_mode&0o111
    rows[name]={'path':str(target),'sha256':hashlib.sha256(expected).hexdigest()}
print(json.dumps({'selected_alias':str(selected),'launchers':rows},sort_keys=True))
"""
    result=custody.run([str(selected),'-I','-B','-c',helper,str(source),str(selected),
                        'publish' if publish_launchers else 'check'],source,
                        timeout=min(15,budget.check(reserve=1)),read_only=not publish_launchers,log=log)
    body=json.loads(result[0],object_pairs_hook=unique)
    require(set(body)=={'selected_alias','launchers'} and set(body['launchers'])=={'hermes','hermes-acp'},
            'cli_repair_native_renderer_required')
    for name,row in body['launchers'].items():
        require(row['path']==str(source/'.hermes/bin'/name) and pin(row)==source/'.hermes/bin'/name,
                'cli_repair_native_launcher_changed')
    return body


def cli_repair_compile_cache(custody, home, selected, proof_path, budget, *, native_shards=()):
    # Deserialize only pinned marshal bytes for equality; never execute cached code.
    helper="""import sys,json,marshal,importlib.util
from pathlib import Path
from types import CodeType
def normalize(value):
    if isinstance(value,CodeType):
        fields=('co_argcount','co_posonlyargcount','co_kwonlyargcount','co_nlocals','co_stacksize','co_flags','co_code','co_consts','co_names','co_varnames','co_filename','co_name','co_qualname','co_firstlineno','co_linetable','co_exceptiontable','co_freevars','co_cellvars')
        return tuple((key,normalize(getattr(value,key))) for key in fields)
    if isinstance(value,tuple):return tuple(normalize(x) for x in value)
    return value
proof=json.loads(Path(sys.argv[1]).read_bytes());home=Path(sys.argv[2])
proof['files']+=sum([json.loads(Path(p).read_bytes())['files'] for p in sys.argv[3:]],[])
assert importlib.util.MAGIC_NUMBER.hex()==proof['magic']
for row in proof['files']:
    source=home/row['source'];cached=Path(row['path']).read_bytes()
    actual=marshal.loads(cached[16:])
    expected=compile(source.read_bytes(),str(source),'exec',dont_inherit=True,optimize=0)
    assert normalize(actual)==normalize(expected)
print(json.dumps({'compiled_without_execution':len(proof['files'])}))
"""
    body=custody.run([str(selected),'-I','-B','-c',helper,str(proof_path),str(home),*[str(pin(p)) for p in native_shards]],home,
                      timeout=min(15,budget.check(reserve=1)),read_only=True)[0]
    require(json.loads(body)=={'compiled_without_execution':18+sum(len(read_json(pin(p))['files']) for p in native_shards)},'cli_repair_cache_compile_required')



def cli_repair_native_cache(shards, receipt, source):
    require(type(shards) is list and shards,'cli_repair_native_cache_inventory_required')
    rows={}
    for shard in shards:
        raw=owned_file(pin(shard),private=True)
        require(len(raw)<=65536,'cli_repair_cache_shard_limit')
        body=json.loads(raw,object_pairs_hook=unique)
        require(set(body)=={'magic','files'} and body['magic']=='2b0e0d0a','cli_repair_native_cache_schema')
        for row in body['files']:
            path=canonical(row['path']);require(path.is_relative_to(source),'cli_repair_native_cache_path')
            name=str(path.relative_to(source));src=str(Path(name).parent.parent/Path(name).name.removesuffix('.cpython-314.pyc'))+'.py'
            require(name not in rows and '__pycache__'==Path(name).parent.name and name.endswith('.cpython-314.pyc')
                    and src in receipt['files'] and row['source']=='hermes-agent/'+src
                    and row['source_sha256']==receipt['files'][src]['sha256'],'cli_repair_native_cache_pinned_source')
            data=owned_file(source/src);cached=owned_file(path,private=True)
            require(digest(data)==row['source_sha256'] and digest(cached)==row['sha256'] and len(cached)==row['bytes']
                    and cached[:4].hex()=='2b0e0d0a' and cached[4:8]==b'\0'*4
                    and int.from_bytes(cached[8:12],'little')==(int((source/src).stat().st_mtime)&0xffffffff)
                    and int.from_bytes(cached[12:16],'little')==(len(data)&0xffffffff),'cli_repair_native_cache_header_or_bytes')
            rows[name]=row
    return rows

def repair_installed_cli(request, request_path, *, clock):
    fields={'schema','phase','assignment','generation','home','installation_input','repaired_input',
            'original_marker','original_receipt','original_stamp','native_launchers','selected_python',
            'cache_proof','native_cache_inventories','history','unit','invocation_id'}
    require(type(request) is dict and set(request)==fields
            and request['schema']=='friday.installed-cli-repair-request.v1'
            and request['phase']=='repair-installed-cli' and type(request['generation']) is int
            and request['generation']==1 and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
            and request['invocation_id']=='OBSERVE_NATIVE_AT_ADMISSION','cli_repair_exact_request_required')
    from scripts.install_containment import Budget,Containment
    from scripts.hermes_prepare import overlay_layers,git,Budget as SourceBudget
    budget=Budget(180,started=clock['started_mono'],deadline=clock['useful_deadline_mono'])
    physical=budget.call(installed_cli_kernel,request,clock,phase='repair-installed-cli')
    original=read_json(pin(request['installation_input']));value=read_json(pin(request['repaired_input']))
    require({k:v for k,v in original.items() if k!='project_files'}==
            {k:v for k,v in value.items() if k!='project_files'} and value['home']==request['home'],
            'cli_repair_operational_settings_changed')
    home,donors=budget.call(spec_checked,value,cli_only=True);directory(home);directory(home/'preparation');source=home/'hermes-agent'
    require(not (home/CLI_REPAIR_INTENT).exists() and not (home/CLI_REPAIR_INTENT).is_symlink(),
            'cli_repair_consumed_no_retry')
    paths={'original_marker':home/MARKER,'original_receipt':home/'hermes-agent.source.json',
           'original_stamp':source/'install-stamp.json'}
    for key,path in paths.items():
        require(request[key]['path']==str(path) and pin(request[key])==path,'cli_repair_exact_original_pin_required')
    marker=read_json(paths['original_marker']);receipt=read_json(paths['original_receipt']);stamp=read_json(paths['original_stamp'])
    require(marker.get('schema')==SCHEMA and marker.get('home')==str(home)
            and marker.get('source')==str(source) and marker.get('completion_stage')==CLI_STAGE
            and marker.get('input_sha256')==request['installation_input']['sha256']
            and marker.get('source_receipt_sha256')==request['original_receipt']['sha256']
            and not any(k.startswith('postinstall_') for k in marker)
            and marker.get('runtime_ready') is False and marker.get('gateway_installed') is False
            and marker.get('native_frontends')=='PENDING'
            and marker.get('worker_state')=='BOTH_WORKERS_PREPARATION_PENDING'
            and value['product']['runtime']=={'enabled':False}
            and cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
            and cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1'),
            'cli_repair_original_history_state_required')
    budget.call(cli_repair_history,request,home)
    require(len(receipt['layers'])==32 and stamp.get('fridaySource')==
            {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            and stamp.get('commit')==receipt['commit'] and stamp.get('dirty') is True,
            'cli_repair_original_stamp_required')
    native_cache=budget.call(cli_repair_native_cache,request['native_cache_inventories'],receipt,source)
    budget.call(composition_checked,original,source,receipt,donors['hermes'],proven_cache=native_cache)
    require(request['cache_proof']['sha256']==CLI_CACHE_PROOF_SHA256,'cli_repair_accepted_cache_proof_required')
    proof_path=pin(request['cache_proof']);proof=read_json(proof_path)
    cache=budget.call(cli_repair_cache,proof,value,home)
    budget.call(cli_repair_plugins,value,home,marker,cache)
    for name,sha in marker.get('profile_files',{}).items():
        require(digest(owned_file(home/name,private=True))==sha,'cli_repair_profile_changed')
    require(set(marker.get('profile_files',{}))=={'config.yaml','SOUL.md','FRIDAY-PROFILE.json'},
            'cli_repair_profile_inventory_required')
    for name,sha in marker.get('tls_files',{}).items():
        require(digest(owned_file(home/name,private=True))==sha,'cli_repair_tls_changed')
    selected=bootstrap_pin(request['selected_python'])
    require(selected.is_relative_to(home/'tools') and request['selected_python']['sha256']==value['bootstrap_python']['sha256'],
            'cli_repair_original_selected_python_required')
    custody=Containment(value['containment'],budget,clean_environment(home))
    native_before=cli_repair_native(custody,value,source,selected,budget)
    require(request['native_launchers']==native_before['launchers'],'cli_repair_original_native_launchers_changed')
    require({p.name for p in (source/'.hermes/bin').iterdir()}=={'hermes','hermes-acp'},
            'cli_repair_exact_native_launcher_inventory_required')
    budget.call(cli_repair_compile_cache,custody,home,selected,proof_path,budget,native_shards=request['native_cache_inventories'])
    cache.update({'hermes-agent/'+n:r for n,r in native_cache.items()})
    layers=budget.call(overlay_layers,ROOT,receipt['commit'],SourceBudget(budget.deadline))
    added=[(n,l) for n,l in layers if l['manifest'] in CLI_REPAIR_OVERLAYS]
    require(len(layers)==34 and len(added)==2 and {l['manifest'] for _,l in added}==set(CLI_REPAIR_OVERLAYS),
            'cli_repair_exact_two_overlays_required')
    old_layers={r['manifest']:r for r in receipt['layers']}
    for _,layer in layers:
        if layer['manifest'] not in CLI_REPAIR_OVERLAYS:
            require(old_layers.get(layer['manifest'])=={k:layer[k] for k in ('manifest','manifest_sha256','patch_sha256')},
                    'cli_repair_original_composition_changed')
    changes={}
    for _,layer in added:
        for name,row in layer['files'].items():
            require(name not in changes and not row.get('new_file') and row['mode']==receipt['files'][name]['mode']
                    and row['before_sha256']==receipt['files'][name]['sha256']
                    and digest(owned_file(source/name))==row['before_sha256'],'cli_repair_overlay_preimage_changed')
            changes[name]=row
    require(set(changes)=={'hermes_cli/_launchers.py','hermes_cli/friday_credential_admission.py'},
            'cli_repair_exact_native_source_scope_required')
    budget.call(installed_cli_kernel,request,clock,phase='repair-installed-cli')
    require(read_json(request_path)==request,'cli_repair_request_changed')
    # A fixed consumed token makes every failure non-retryable; no rollback revives it.
    intent={'schema':'friday.installed-cli-repair-intent.v1','state':'CONSUMED_NO_RETRY',
            'request':request,'clock':clock,'physical':physical}
    publish(home/CLI_REPAIR_INTENT,intent,budget=budget)
    folder=home/'preparation/cli-postinstall-repair';stage='preserve_beforeimages'
    try:
        folder.mkdir(mode=0o700);directory(folder)
        saved={}
        preserved={str(p):p for p in paths.values()}
        preserved.update({str(source/n):source/n for n in changes})
        preserved.update({v['path']:Path(v['path']) for v in request['native_launchers'].values()})
        preserved.update({str(home/n):home/n for n in cache})
        for name,path in preserved.items():
            raw=owned_file(path);mode=stat.S_IMODE(path.stat().st_mode)
            if path==home/MARKER:backup=home/(MARKER+'.original-runtime-repair')
            elif str(path.relative_to(home)) in cache:
                backup=folder/'cache'/path.relative_to(home);backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            else:
                backup=folder/'beforeimages'/path.relative_to(home)
                backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            cli_repair_bytes(backup,raw,budget,mode=0o600)
            saved[name]={'path':str(backup),'sha256':digest(raw),'bytes':len(raw),'original_mode':mode}
        publish(folder/'beforeimages.json',saved,budget=budget)
        stage='archive_exact_cache'
        for name,row in cache.items():
            path=home/name
            require(digest(owned_file(path,private=True))==row['sha256']
                    and digest(owned_file(saved[str(path)]['path'],private=True))==row['sha256'],
                    'cli_repair_cache_archive_changed')
            budget.check();path.unlink()
        budget.call(cli_repair_plugins,value,home,marker,{})
        budget.call(composition_checked,original,source,receipt,donors['hermes'])
        stage='overlay_stage';staging=folder/'source';staging.mkdir(mode=0o700)
        for name in changes:
            dest=staging/name;dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            cli_repair_bytes(dest,owned_file(source/name),budget,mode=stat.S_IMODE((source/name).stat().st_mode))
        for _,layer in added:
            git(staging,['apply','--check','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
            git(staging,['apply','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        updated=json.loads(json.dumps(receipt))
        stage='publish_native_sources'
        for name,row in changes.items():
            raw=owned_file(staging/name)
            require(digest(raw)==row['sha256'] and len(raw)==row['bytes'],'cli_repair_overlay_output_changed')
            cli_repair_replace(source/name,raw,row['before_sha256'],budget,mode=saved[str(source/name)]['original_mode'])
            updated['files'][name]={k:row[k] for k in ('sha256','bytes','mode')}
        updated['layers']=receipt['layers']+[{k:l[k] for k in ('manifest','manifest_sha256','patch_sha256')} for _,l in added]
        budget.call(composition_checked,value,source,updated,donors['hermes'])
        stage='publish_native_launchers'
        native_after=cli_repair_native(custody,value,source,selected,budget,publish_launchers=True,log=folder/'launcher-publication')
        require(native_after['selected_alias']==native_before['selected_alias'],'cli_repair_selected_interpreter_changed')
        stage='publish_full_receipt_stamp'
        receipt_data=(json.dumps(updated,sort_keys=True,indent=2)+'\n').encode()
        cli_repair_replace(paths['original_receipt'],receipt_data,request['original_receipt']['sha256'],budget,
                           mode=saved[str(paths['original_receipt'])]['original_mode'])
        newstamp=dict(stamp,fridaySource={'baseTree':receipt['base_tree'],'layers':updated['layers']})
        stamp_data=(json.dumps(newstamp,sort_keys=True,indent=2)+'\n').encode()
        cli_repair_replace(paths['original_stamp'],stamp_data,request['original_stamp']['sha256'],budget,
                           mode=saved[str(paths['original_stamp'])]['original_mode'])
        budget.call(composition_checked,value,source,read_json(paths['original_receipt']),donors['hermes'])
        require(read_json(paths['original_stamp'])==newstamp,'cli_repair_full_stamp_changed')
        budget.call(cli_repair_history,request,home)
        for name,row in saved.items():
            require(digest(owned_file(row['path'],private=True))==row['sha256'],'cli_repair_custody_changed')
        for name,sha in {**marker['profile_files'],**marker.get('tls_files',{})}.items():
            require(digest(owned_file(home/name,private=True))==sha,'cli_repair_profile_or_tls_changed')
        budget.call(cli_repair_native,custody,value,source,selected,budget)
        final=dict(marker,source_receipt_sha256=digest(receipt_data),
                   postinstall_original_marker={'path':str(home/(MARKER+'.original-runtime-repair')),
                                                'sha256':request['original_marker']['sha256']},
                   postinstall_source_input=request['repaired_input'],
                   postinstall_native_launcher=native_after['launchers']['hermes'])
        stage='final_complete_checks'
        budget.call(inspect,value,request['installation_input']['sha256'],marker_override=final)
        stage='publish_final_marker'
        budget.call(installed_cli_kernel,request,clock,phase='repair-installed-cli')
        require(read_json(request_path)==request,'cli_repair_request_changed')
        cli_repair_replace(home/MARKER,(json.dumps(final,sort_keys=True,indent=2)+'\n').encode(),
                           request['original_marker']['sha256'],budget,mode=saved[str(home/MARKER)]['original_mode'])
        require(read_json(home/MARKER)==final,'cli_repair_final_marker_changed')
        return {'state':'POSTINSTALL_SOURCE_REPAIRED_NOT_RUNTIME_ACCEPTED','layers':34,'ready':False,
                'repair_intent':str(home/CLI_REPAIR_INTENT),'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
    except BaseException as exc:
        failure={'schema':'friday.installed-cli-repair-failure.v1','state':'NO_RETRY',
                 'stage':stage,'diagnostic':retained_diagnostic(exc,'repair-installed-cli'),
                 'rollback':'NOT_AUTOMATIC; exact beforeimages retained; consumed token never renewed',
                 'clock':clock,'physical':physical,'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
        try:publish(home/'FRIDAY-INSTALL.postinstall-cli-repair.failure.json',failure)
        except BaseException as secondary:remember_secondary(exc,secondary)
        raise


CLI_FRONTEND_MANIFEST = 'patches/hermes/installed-cli-frontend-close-manifest.json'
CLI_FRONTEND_INTENT = 'FRIDAY-INSTALL.frontend-close-repair.intent.json'
CLI_FRONTEND_RUNTIME_INTENT = 'FRIDAY-INSTALL.frontend-close-journey.intent.json'


def cli_frontend_runtime_history(rows, home, previous_input):
    require(type(rows) is dict and len(rows) == 6, 'frontend_previous_runtime_inventory_required')
    base = 'preparation/cli-runtime/'
    units = set()
    for name, sha in rows.items():
        require(type(name) is str and name.startswith(base) and '/' not in name[len(base):]
                and re.fullmatch('[0-9a-f]{64}', sha), 'frontend_previous_runtime_path_required')
        units.add(name[len(base):].split('.service.')[0])
        require(digest(owned_file(home/name, private=True)) == sha, 'frontend_previous_runtime_changed')
    require(len(units) == 1, 'frontend_previous_runtime_single_epoch_required')
    unit = next(iter(units))+'.service'
    require(set(rows) == {base+unit+s for s in ('.intent.json','.json','.native-owner.json',
                                               '.result.json','.stderr','.stdout')},
            'frontend_previous_runtime_exact_inventory_required')
    old = read_json(home/(base+unit+'.intent.json'))
    require(old.get('schema') == 'friday.installed-cli-invocation.v1'
            and old.get('state') == 'CONSUMED_NOT_COMPLETE'
            and old['request']['repaired_input'] == previous_input
            and old['request']['unit'] == unit
            and cli_historical_scope_closed(old['clock'],'friday.installed-cli-clock.v1'),
            'frontend_previous_runtime_consumed_required')


def cli_frontend_chain(request, home, marker):
    """Verify saved previous epoch and both consumed repairs without rewriting either."""
    chain = marker.get('postinstall_frontend_repair')
    require(type(chain) is dict and set(chain) == {'previous_marker','previous_receipt',
            'previous_stamp','intent'}, 'frontend_complete_chain_required')
    folder = home/'preparation/frontend-close-repair'
    for key, relative in (('previous_marker',MARKER),('previous_receipt','hermes-agent.source.json'),
                          ('previous_stamp','hermes-agent/install-stamp.json')):
        require(chain[key]['path'] == str(folder/'beforeimages'/relative),
                'frontend_saved_previous_path_required')
    previous = read_json(pin(chain['previous_marker']))
    before_receipt = read_json(pin(chain['previous_receipt']))
    before_stamp = read_json(pin(chain['previous_stamp']))
    require(chain['intent']['path'] == str(home/CLI_FRONTEND_INTENT), 'frontend_intent_path_required')
    delta = read_json(pin(chain['intent']))
    require(delta.get('schema') == 'friday.frontend-close-repair-intent.v1'
            and delta.get('state') == 'CONSUMED_NO_RETRY'
            and delta['request']['repaired_input'] == request['repaired_input']
            and delta['request']['installation_input'] == request['installation_input']
            and delta['request']['original_marker']['sha256'] == chain['previous_marker']['sha256']
            and delta['request']['original_receipt']['sha256'] == chain['previous_receipt']['sha256']
            and delta['request']['original_stamp']['sha256'] == chain['previous_stamp']['sha256']
            and delta['request']['previous_input'] == previous.get('postinstall_source_input'),
            'frontend_consumed_delta_chain_required')
    require('postinstall_frontend_repair' not in previous
            and previous['source_receipt_sha256'] == chain['previous_receipt']['sha256']
            and len(before_receipt['layers']) == 34
            and before_stamp['fridaySource'] == {'baseTree':before_receipt['base_tree'],
                                               'layers':before_receipt['layers']}
            and {k:v for k,v in marker.items() if k not in {'source_receipt_sha256',
                    'postinstall_source_input','postinstall_frontend_repair'}} ==
                {k:v for k,v in previous.items() if k not in {'source_receipt_sha256','postinstall_source_input'}},
            'frontend_previous_marker_history_changed')
    old = read_json(pin(delta['request']['previous_repair_intent']))
    require(delta['request']['previous_repair_intent']['path'] == str(home/CLI_REPAIR_INTENT)
            and old.get('schema') == 'friday.installed-cli-repair-intent.v1'
            and old.get('state') == 'CONSUMED_NO_RETRY'
            and old['request']['repaired_input'] == previous['postinstall_source_input']
            and old['request']['installation_input'] == request['installation_input']
            and cli_historical_scope_closed(old['clock'],'friday.installed-cli-clock.v1')
            and delta['request']['unit'] != request['unit']
            and delta['request']['assignment'] != request['assignment'],
            'frontend_previous_consumed_repair_required')
    current=read_json(home/'hermes-agent.source.json')
    manifest=read_json(ROOT/CLI_FRONTEND_MANIFEST)
    name='hermes_cli/friday_cli_frontend.py';row=manifest['files'][0]
    require(current['layers'] == before_receipt['layers']+[
                {'manifest':CLI_FRONTEND_MANIFEST,'manifest_sha256':digest(owned_file(ROOT/CLI_FRONTEND_MANIFEST)),
                 'patch_sha256':manifest['patch_sha256']}]
            and current['files'][name] == {k:row[k] for k in ('sha256','bytes','mode')}
            and {k:v for k,v in current['files'].items() if k!=name} ==
                {k:v for k,v in before_receipt['files'].items() if k!=name}
            and {k:v for k,v in current.items() if k not in {'layers','files'}} ==
                {k:v for k,v in before_receipt.items() if k not in {'layers','files'}},
            'frontend_exact_receipt_chain_required')
    cli_frontend_runtime_history(delta['request']['previous_runtime'],home,previous['postinstall_source_input'])
    return delta


def cli_historical_scope_closed(clock, schema):
    """Closed immutable history uses its own kernel boot, never a rebased clock."""
    import math, re, time
    require(type(clock) is dict and clock.get('schema') == schema,
            'cli_history_clock_schema_required')
    if schema == 'friday.native-install.v1':
        require(set(clock) == {'schema','state','input_sha256','deadline_mono','boot_id'}
                and clock['state'] == 'PARTIAL'
                and type(clock['input_sha256']) is str
                and re.fullmatch('[0-9a-f]{64}',clock['input_sha256']),
                'cli_history_install_claim_required')
    else:
        require(schema in ('friday.cli-segment-clock.v1','friday.installed-cli-clock.v1')
                and set(clock) == {'schema','seconds','cleanup_seconds','started_mono',
                    'deadline_mono','useful_deadline_mono','boot_id','gnu_pid','gnu_starttime_ticks'},
                'cli_history_clock_fields_required')
        seconds, cleanup = (900,90) if schema == 'friday.cli-segment-clock.v1' else (180,30)
        require(type(clock['seconds']) is int and clock['seconds'] == seconds
                and type(clock['cleanup_seconds']) is int and clock['cleanup_seconds'] == cleanup
                and all(type(clock[k]) in (int,float) and math.isfinite(clock[k])
                        and clock[k] >= 0 for k in ('started_mono','useful_deadline_mono'))
                and clock['deadline_mono'] == clock['started_mono']+seconds
                and clock['useful_deadline_mono'] == clock['started_mono']+seconds-cleanup
                and type(clock['gnu_pid']) is int and clock['gnu_pid'] > 1
                and type(clock['gnu_starttime_ticks']) is int and clock['gnu_starttime_ticks'] > 0,
                'cli_history_clock_invalid')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    pattern = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    require(type(clock['boot_id']) is str and re.fullmatch(pattern,clock['boot_id'])
            and re.fullmatch(pattern,boot)
            and type(clock['deadline_mono']) in (int,float)
            and math.isfinite(clock['deadline_mono']) and clock['deadline_mono'] > 0,
            'cli_history_boot_and_deadline_required')
    return clock['boot_id'] != boot or time.monotonic() >= clock['deadline_mono']


def validated_cli_installation_history(home, marker, history, read_owned):
    """Pinned consumed installation/segment bytes grant no active authority."""
    import hashlib
    home = Path(home)
    names = {'FRIDAY-INSTALL.cli-segment.intent.json','FRIDAY-INSTALL.cli-host.intent.json',
             'FRIDAY-INSTALL.json.original-cli-segment'}
    require(type(history) is dict and set(history) == names, 'cli_history_inventory_required')
    raw = {}
    for name, expected in history.items():
        require(type(expected) is str and __import__('re').fullmatch('[0-9a-f]{64}',expected),
                'cli_history_pin_required')
        raw[name] = read_owned(home/name,private=True)
        require(hashlib.sha256(raw[name]).hexdigest() == expected, 'cli_history_pin_changed')
    claim = json.loads(raw['FRIDAY-INSTALL.json.original-cli-segment'])
    segment = marker['cli_segment']
    require(type(segment) is dict and set(segment) == {'clock','request','intent_sha256','original_claim_sha256'}
            and claim == marker['original_attempt']
            and segment['intent_sha256'] == history['FRIDAY-INSTALL.cli-segment.intent.json']
            and segment['original_claim_sha256'] == history['FRIDAY-INSTALL.json.original-cli-segment']
            and json.loads(raw['FRIDAY-INSTALL.cli-segment.intent.json']) ==
                {'state':'CONSUMED_NOT_COMPLETE','request':segment['request'],
                 'clock':segment['clock'],'original_attempt':claim}
            and segment['request']['schema'] == 'friday.cli-segment-request.v1'
            and type(segment['request']['generation']) is int and segment['request']['generation'] == 1
            and segment['request']['current_input']['sha256'] == marker['input_sha256']
            and segment['request']['previous_intent'] ==
                {'path':str(home/'FRIDAY-INSTALL.cli-host.intent.json'),
                 'sha256':history['FRIDAY-INSTALL.cli-host.intent.json']},
            'cli_history_consumed_segment_required')
    ref = segment['request']['previous_request']
    require(type(ref) is dict and set(ref) == {'path','sha256'}, 'cli_history_previous_request_required')
    prior_raw = read_owned(Path(ref['path']),private=True)
    require(hashlib.sha256(prior_raw).hexdigest() == ref['sha256'], 'cli_history_previous_request_changed')
    prior = json.loads(prior_raw)
    require(json.loads(raw['FRIDAY-INSTALL.cli-host.intent.json']) ==
                {'state':'CONSUMED_NOT_COMPLETE','request':prior,'original_attempt':claim}
            and prior['original_input']['sha256'] == claim['input_sha256']
            and prior['original_claim'] == {'path':str(home/'FRIDAY-INSTALL.json'),
                'sha256':history['FRIDAY-INSTALL.json.original-cli-segment']}
            and cli_historical_scope_closed(claim,'friday.native-install.v1')
            and cli_historical_scope_closed(segment['clock'],'friday.cli-segment-clock.v1'),
            'cli_history_original_scopes_not_closed')
    return claim


def validated_cli_repair_chain(home, marker, request):
    """Only witnessed additive Source35/36 repairs may extend the immutable marker."""
    read_owned = owned_file
    import hashlib, time, stat
    home = Path(home)
    def load(ref, expected=None):
        require(type(ref) is dict and set(ref) == {'path','sha256'}
                and (expected is None or ref['path'] == str(expected)), 'cli_runtime_chain_pin_required')
        raw = read_owned(Path(ref['path']), private=True)
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'cli_runtime_chain_pin_changed')
        return json.loads(raw)
    def local(path):
        raw = read_owned(path, private=True)
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    require(request['schema'] in ('friday.installed-cli-request.v1','friday.installed-cli-request.v2',
                                 'friday.installed-cli-request.v3','friday.installed-cli-request.v4'), 'cli_runtime_supported_request_required')
    require(('postinstall_native_bootstrap_repair' in marker) ==
            (request['schema'] in ('friday.installed-cli-request.v3','friday.installed-cli-request.v4'))
            and ('postinstall_session_artifact_repair' in marker) == (request['schema'] == 'friday.installed-cli-request.v4')
            and ('postinstall_frontend_repair' in marker) == (request['schema'] != 'friday.installed-cli-request.v1'),
            'cli_runtime_supported_chain_required')
    original = load(request['installation_input'])
    current_input = load(request['repaired_input'])
    require({k:v for k,v in original.items() if k != 'project_files'} ==
            {k:v for k,v in current_input.items() if k != 'project_files'}
            and current_input['home'] == str(home), 'cli_runtime_chain_input_changed')
    receipt, receipt_sha = local(home/'hermes-agent.source.json')
    stamp, _ = local(home/'hermes-agent/install-stamp.json')
    require(marker['source_receipt_sha256'] == receipt_sha and stamp['fridaySource'] ==
            {'baseTree':receipt['base_tree'],'layers':receipt['layers']}, 'cli_runtime_chain_source_changed')
    head = marker
    snapshots = {}
    for field, folder, token, schema, manifest_name, source_name, count, prior_token, prior_schema in (
        ('postinstall_session_artifact_repair','session-artifact-repair','FRIDAY-INSTALL.session-artifact-repair.intent.json',
         'friday.session-artifact-repair-intent.v1','installed-session-artifact-manifest.json',
         ('hermes_cli/friday_credential_admission.py','hermes_cli/friday_user_scope.py'),37,
         'FRIDAY-INSTALL.native-bootstrap-repair.intent.json','friday.native-bootstrap-repair-intent.v1'),
        ('postinstall_native_bootstrap_repair','native-bootstrap-repair','FRIDAY-INSTALL.native-bootstrap-repair.intent.json',
         'friday.native-bootstrap-repair-intent.v1','installed-native-bootstrap-repair-chain-manifest.json',
         'hermes_cli/friday_credential_admission.py',36,'FRIDAY-INSTALL.frontend-close-repair.intent.json',
         'friday.frontend-close-repair-intent.v1'),
        ('postinstall_frontend_repair','frontend-close-repair','FRIDAY-INSTALL.frontend-close-repair.intent.json',
         'friday.frontend-close-repair-intent.v1','installed-cli-frontend-close-manifest.json',
         'hermes_cli/friday_cli_frontend.py',35,'FRIDAY-INSTALL.postinstall-cli-repair.intent.json',
         'friday.installed-cli-repair-intent.v1')):
        if field not in head:
            continue
        chain = head[field]
        require(type(chain) is dict and set(chain) == {'previous_marker','previous_receipt','previous_stamp','intent'},
                'cli_runtime_chain_fields_required')
        base = home/'preparation'/folder/'beforeimages'
        previous = load(chain['previous_marker'],base/'FRIDAY-INSTALL.json')
        before = load(chain['previous_receipt'],base/'hermes-agent.source.json')
        before_stamp = load(chain['previous_stamp'],base/'hermes-agent/install-stamp.json')
        delta = load(chain['intent'],home/token); r = delta['request']
        require(cli_historical_scope_closed(delta['clock'],'friday.installed-cli-clock.v1'),
                'cli_runtime_repair_scope_not_closed')
        require(delta['schema'] == schema and delta['state'] == 'CONSUMED_NO_RETRY'
                and r['installation_input'] == request['installation_input']
                and r['repaired_input'] == head['postinstall_source_input']
                and r['home'] == str(home)
                and r['assignment'] != request['assignment'] and r['unit'] != request['unit']
                and all(r[key]['sha256'] == chain[target]['sha256']
                        and r[key]['path'] == str(home/relative) for key,target,relative in (
                    ('original_marker','previous_marker','FRIDAY-INSTALL.json'),
                    ('original_receipt','previous_receipt','hermes-agent.source.json'),
                    ('original_stamp','previous_stamp','hermes-agent/install-stamp.json')))
                and r['previous_input'] == previous['postinstall_source_input'],
                'cli_runtime_consumed_chain_required')
        require(field not in previous and previous['source_receipt_sha256'] == chain['previous_receipt']['sha256']
                and len(before['layers']) == count-1 and len(receipt['layers']) == count
                and before_stamp['fridaySource'] == {'baseTree':before['base_tree'],'layers':before['layers']}
                and {k:v for k,v in head.items() if k not in {'source_receipt_sha256','postinstall_source_input',field}} ==
                    {k:v for k,v in previous.items() if k not in {'source_receipt_sha256','postinstall_source_input'}},
                'cli_runtime_saved_history_changed')
        value = load(r['repaired_input']); oldvalue = load(r['previous_input'])
        require({k:v for k,v in value.items() if k != 'project_files'} ==
                {k:v for k,v in oldvalue.items() if k != 'project_files'} ==
                {k:v for k,v in original.items() if k != 'project_files'}, 'cli_runtime_chain_input_changed')
        manifest_relative = 'patches/hermes/'+manifest_name
        manifest_path = Path(r['repaired_input']['path']).parent/'project'/manifest_relative
        manifest_raw = read_owned(manifest_path)
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest(); manifest = json.loads(manifest_raw)
        require(value['project_files'][manifest_relative] == manifest_sha and len(manifest['files']) == (2 if count == 37 else 1),
                'cli_runtime_chain_manifest_changed')
        names = set(source_name) if isinstance(source_name,tuple) else {source_name}
        require({row['path'] for row in manifest['files']} == names
                and receipt['layers'] == before['layers']+[{'manifest':manifest_relative,
                    'manifest_sha256':manifest_sha,'patch_sha256':manifest['patch_sha256']}]
                and {k:v for k,v in receipt['files'].items() if k not in names} ==
                    {k:v for k,v in before['files'].items() if k not in names}
                and {k:v for k,v in receipt.items() if k not in {'files','layers'}} ==
                    {k:v for k,v in before.items() if k not in {'files','layers'}},
                'cli_runtime_chain_receipt_changed')
        for row in manifest['files']:
            name = row['path']
            require(row['before_sha256'] == before['files'][name]['sha256']
                    and receipt['files'][name] == {k:row[k] for k in ('sha256','bytes','mode')},
                    'cli_runtime_chain_receipt_changed')
            raw = read_owned(snapshots.get(name,home/'hermes-agent'/name))
            require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'],
                    'cli_runtime_chain_source_changed')
            if count == 37:
                prior_source = base/'hermes-agent'/name
                raw = read_owned(prior_source,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['before_sha256'], 'cli_runtime_saved_source_changed')
                snapshots[name] = prior_source
        prior = load(r['previous_repair_intent'],home/prior_token)
        require(prior['schema'] == prior_schema and prior['state'] == 'CONSUMED_NO_RETRY'
                and prior['request']['repaired_input'] == r['previous_input']
                and prior['request']['installation_input'] == request['installation_input']
                and cli_historical_scope_closed(prior['clock'],'friday.installed-cli-clock.v1'), 'cli_runtime_prior_repair_changed')
        inventory = r['previous_runtime']; prefix = 'preparation/cli-runtime/'
        require(type(inventory) is dict and len(inventory) == (4 if count == 36 else 6),
                'cli_runtime_prior_inventory_required')
        units = {name[len(prefix):].split('.service.')[0] for name in inventory
                 if name.startswith(prefix) and '/' not in name[len(prefix):]}
        require(len(units) == 1, 'cli_runtime_prior_inventory_required')
        oldunit = next(iter(units))+'.service'
        suffixes = ('.intent.json','.json','.stdout','.stderr') if count == 36 else (
            '.intent.json','.json','.stdout','.stderr','.native-owner.json','.result.json')
        require(set(inventory) == {prefix+oldunit+s for s in suffixes}, 'cli_runtime_prior_inventory_required')
        for name, sha in inventory.items():
            require(hashlib.sha256(read_owned(home/name,private=True)).hexdigest() == sha,
                    'cli_runtime_prior_inventory_changed')
        prior_runtime, _ = local(home/(prefix+oldunit+'.intent.json'))
        require(prior_runtime['schema'] == 'friday.installed-cli-invocation.v1'
                and prior_runtime['state'] == 'CONSUMED_NOT_COMPLETE'
                and prior_runtime['request']['repaired_input'] == r['previous_input']
                and prior_runtime['request']['unit'] == oldunit
                and cli_historical_scope_closed(prior_runtime['clock'],'friday.installed-cli-clock.v1'), 'cli_runtime_prior_invocation_changed')
        if count in (36,37):
            journey = load(r['previous_journey'],home/('FRIDAY-INSTALL.native-bootstrap-journey.intent.json' if count == 37 else 'FRIDAY-INSTALL.frontend-close-journey.intent.json'))
            require(journey == prior_runtime and journey['request']['schema'] == ('friday.installed-cli-request.v3' if count == 37 else 'friday.installed-cli-request.v2'),
                    'cli_runtime_prior_journey_changed')
        head, receipt = previous, before
    for name, sha in {**marker['profile_files'],**marker.get('tls_files',{})}.items():
        require(hashlib.sha256(read_owned(home/name,private=True)).hexdigest() == sha,
                'cli_runtime_profile_changed')
    return head


def repair_frontend_close(request, request_path, *, clock):
    fields={'schema','phase','assignment','generation','home','installation_input','previous_input',
            'repaired_input','original_marker','original_receipt','original_stamp','previous_repair_intent',
            'selected_python','native_launchers','history','previous_runtime','unit','invocation_id'}
    require(type(request) is dict and set(request) == fields
            and request['schema'] == 'friday.frontend-close-repair-request.v1'
            and request['phase'] == 'repair-frontend-close' and type(request['generation']) is int
            and request['generation'] == 1 and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
            and request['invocation_id'] == 'OBSERVE_NATIVE_AT_ADMISSION', 'frontend_exact_request_required')
    from scripts.install_containment import Budget,Containment
    from scripts.hermes_prepare import overlay_layers,git,Budget as SourceBudget
    budget=Budget(180,started=clock['started_mono'],deadline=clock['useful_deadline_mono'])
    physical=budget.call(installed_cli_kernel,request,clock,phase='repair-frontend-close')
    original=read_json(pin(request['installation_input']))
    previous=read_json(pin(request['previous_input']));value=read_json(pin(request['repaired_input']))
    require({k:v for k,v in original.items() if k!='project_files'} ==
            {k:v for k,v in previous.items() if k!='project_files'} ==
            {k:v for k,v in value.items() if k!='project_files'} and value['home'] == request['home'],
            'frontend_operational_settings_changed')
    home,donors=budget.call(spec_checked,value,cli_only=True)
    directory(home);directory(home/'preparation');source=home/'hermes-agent'
    require(not (home/CLI_FRONTEND_INTENT).exists() and not (home/CLI_FRONTEND_INTENT).is_symlink(),
            'frontend_consumed_no_retry')
    paths={'original_marker':home/MARKER,'original_receipt':home/'hermes-agent.source.json',
           'original_stamp':source/'install-stamp.json','previous_repair_intent':home/CLI_REPAIR_INTENT}
    for key,path in paths.items():
        require(request[key]['path'] == str(path) and pin(request[key]) == path,
                'frontend_exact_previous_pin_required')
    marker=read_json(paths['original_marker']);receipt=read_json(paths['original_receipt']);stamp=read_json(paths['original_stamp'])
    require(marker.get('schema') == SCHEMA and marker.get('home') == str(home)
            and marker.get('source') == str(source) and marker.get('completion_stage') == CLI_STAGE
            and marker.get('input_sha256') == request['installation_input']['sha256']
            and marker.get('source_receipt_sha256') == request['original_receipt']['sha256']
            and marker.get('postinstall_source_input') == request['previous_input']
            and 'postinstall_frontend_repair' not in marker
            and marker.get('runtime_ready') is False and marker.get('gateway_installed') is False
            and marker.get('native_frontends') == 'PENDING'
            and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
            and value['product']['runtime'] == {'enabled':False}
            and cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
            and cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1'),
            'frontend_previous_pending_history_required')
    old=read_json(paths['previous_repair_intent'])
    require(old.get('schema') == 'friday.installed-cli-repair-intent.v1'
            and old.get('state') == 'CONSUMED_NO_RETRY'
            and old['request']['repaired_input'] == request['previous_input']
            and old['request']['installation_input'] == request['installation_input']
            and old['request']['selected_python'] == request['selected_python']
            and cli_historical_scope_closed(old['clock'],'friday.installed-cli-clock.v1'), 'frontend_old_repair_consumed_required')
    budget.call(cli_repair_history,request,home)
    budget.call(cli_frontend_runtime_history,request['previous_runtime'],home,request['previous_input'])
    require(len(receipt['layers']) == 34 and stamp.get('fridaySource') ==
            {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            and stamp.get('commit') == receipt['commit'] and stamp.get('dirty') is True,
            'frontend_previous_full_stamp_required')
    budget.call(composition_checked,previous,source,receipt,donors['hermes'])
    budget.call(cli_repair_plugins,value,home,marker,{})
    for name,sha in {**marker['profile_files'],**marker.get('tls_files',{})}.items():
        require(digest(owned_file(home/name,private=True)) == sha, 'frontend_profile_or_tls_changed')
    selected=bootstrap_pin(request['selected_python'])
    require(selected.is_relative_to(home/'tools') and request['selected_python']['sha256'] == value['bootstrap_python']['sha256'],
            'frontend_selected_python_changed')
    custody=Containment(value['containment'],budget,clean_environment(home))
    native=budget.call(cli_repair_native,custody,value,source,selected,budget)
    require(native['launchers'] == request['native_launchers']
            and native['launchers']['hermes'] == marker['postinstall_native_launcher'], 'frontend_native_launchers_changed')
    layers=budget.call(overlay_layers,ROOT,receipt['commit'],SourceBudget(budget.deadline))
    slim=lambda l:{k:l[k] for k in ('manifest','manifest_sha256','patch_sha256')}
    require(len(layers) == 35 and len({r['manifest'] for r in receipt['layers']}) == 34
            and {l['manifest']:slim(l) for _,l in layers[:34]} == {r['manifest']:r for r in receipt['layers']}
            and layers[-1][1]['manifest'] == CLI_FRONTEND_MANIFEST, 'frontend_single_additive_overlay_required')
    layer=layers[-1][1];require(set(layer['files']) == {'hermes_cli/friday_cli_frontend.py'}, 'frontend_exact_scope_required')
    name='hermes_cli/friday_cli_frontend.py';row=layer['files'][name]
    require(not row.get('new_file') and row['mode'] == receipt['files'][name]['mode']
            and row['before_sha256'] == receipt['files'][name]['sha256']
            and digest(owned_file(source/name)) == row['before_sha256'], 'frontend_exact_preimage_required')
    budget.call(installed_cli_kernel,request,clock,phase='repair-frontend-close')
    require(read_json(request_path) == request, 'frontend_request_changed')
    intent={'schema':'friday.frontend-close-repair-intent.v1','state':'CONSUMED_NO_RETRY',
            'request':request,'clock':clock,'physical':physical}
    publish(home/CLI_FRONTEND_INTENT,intent,budget=budget)
    folder=home/'preparation/frontend-close-repair';stage='preserve_beforeimages'
    try:
        folder.mkdir(mode=0o700);directory(folder);saved={}
        preserved={**paths,'frontend':source/name}
        for path in preserved.values():
            raw=owned_file(path);backup=folder/'beforeimages'/path.relative_to(home)
            backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            cli_repair_bytes(backup,raw,budget,mode=0o600)
            saved[str(path)]={'path':str(backup),'sha256':digest(raw),'bytes':len(raw),
                              'original_mode':stat.S_IMODE(path.stat().st_mode)}
        publish(folder/'beforeimages.json',saved,budget=budget)
        # Complete all custody checks before the first source/receipt/stamp replacement.
        for path in preserved.values():
            require(digest(owned_file(saved[str(path)]['path'],private=True)) == saved[str(path)]['sha256'],
                    'frontend_beforeimage_incomplete')
        stage='overlay_stage';staging=folder/'source';staging.mkdir(mode=0o700)
        dest=staging/name;dest.parent.mkdir(mode=0o700,parents=True)
        cli_repair_bytes(dest,owned_file(source/name),budget,mode=0o600)
        git(staging,['apply','--check','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        git(staging,['apply','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        raw=owned_file(dest)
        require(digest(raw) == row['sha256'] and len(raw) == row['bytes'], 'frontend_overlay_output_changed')
        stage='publish_source';cli_repair_replace(source/name,raw,row['before_sha256'],budget,
                                                 mode=saved[str(source/name)]['original_mode'])
        updated=json.loads(json.dumps(receipt));updated['files'][name]={k:row[k] for k in ('sha256','bytes','mode')}
        updated['layers']=receipt['layers']+[slim(layer)]
        budget.call(composition_checked,value,source,updated,donors['hermes'])
        receipt_data=(json.dumps(updated,sort_keys=True,indent=2)+'\n').encode()
        stage='publish_receipt';cli_repair_replace(paths['original_receipt'],receipt_data,
            request['original_receipt']['sha256'],budget,mode=saved[str(paths['original_receipt'])]['original_mode'])
        newstamp=dict(stamp,fridaySource={'baseTree':receipt['base_tree'],'layers':updated['layers']})
        stage='publish_stamp';cli_repair_replace(paths['original_stamp'],
            (json.dumps(newstamp,sort_keys=True,indent=2)+'\n').encode(),request['original_stamp']['sha256'],
            budget,mode=saved[str(paths['original_stamp'])]['original_mode'])
        chain={key:{k:saved[str(paths[sourcekey])][k] for k in ('path','sha256')}
               for key,sourcekey in (('previous_marker','original_marker'),('previous_receipt','original_receipt'),
                                     ('previous_stamp','original_stamp'))}
        chain['intent']={'path':str(home/CLI_FRONTEND_INTENT),'sha256':digest(owned_file(home/CLI_FRONTEND_INTENT,private=True))}
        final=dict(marker,source_receipt_sha256=digest(receipt_data),postinstall_source_input=request['repaired_input'],
                   postinstall_frontend_repair=chain)
        stage='final_checks';budget.call(inspect,value,request['installation_input']['sha256'],marker_override=final)
        require(read_json(paths['original_stamp']) == newstamp, 'frontend_full_stamp_changed')
        budget.call(cli_repair_native,custody,value,source,selected,budget)
        budget.call(cli_repair_history,request,home)
        budget.call(cli_frontend_runtime_history,request['previous_runtime'],home,request['previous_input'])
        for path in preserved.values():
            require(digest(owned_file(saved[str(path)]['path'],private=True)) == saved[str(path)]['sha256'],
                    'frontend_custody_changed')
        require(digest(owned_file(home/CLI_REPAIR_INTENT,private=True)) == request['previous_repair_intent']['sha256'],
                'frontend_previous_intent_changed')
        budget.call(installed_cli_kernel,request,clock,phase='repair-frontend-close')
        require(read_json(request_path) == request, 'frontend_request_changed')
        stage='publish_marker';cli_repair_replace(home/MARKER,(json.dumps(final,sort_keys=True,indent=2)+'\n').encode(),
            request['original_marker']['sha256'],budget,mode=saved[str(home/MARKER)]['original_mode'])
        require(read_json(home/MARKER) == final, 'frontend_final_marker_changed')
        return {'state':'FRONTEND_SOURCE_REPAIRED_NOT_RUNTIME_ACCEPTED','layers':35,'ready':False,
                'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
    except BaseException as exc:
        failure={'schema':'friday.frontend-close-repair-failure.v1','state':'NO_RETRY','stage':stage,
                 'diagnostic':retained_diagnostic(exc,'repair-frontend-close'),
                 'rollback':'NOT_AUTOMATIC; exact beforeimages retained; consumed token never renewed',
                 'clock':clock,'physical':physical,'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
        try:publish(home/'FRIDAY-INSTALL.frontend-close-repair.failure.json',failure)
        except BaseException as secondary:remember_secondary(exc,secondary)
        raise


CLI_BOOTSTRAP_MANIFEST = 'patches/hermes/installed-native-bootstrap-repair-chain-manifest.json'
CLI_BOOTSTRAP_INTENT = 'FRIDAY-INSTALL.native-bootstrap-repair.intent.json'
CLI_BOOTSTRAP_RUNTIME_INTENT = 'FRIDAY-INSTALL.native-bootstrap-journey.intent.json'


CLI_SESSION_MANIFEST = 'patches/hermes/installed-session-artifact-manifest.json'
CLI_SESSION_INTENT = 'FRIDAY-INSTALL.session-artifact-repair.intent.json'
CLI_SESSION_RUNTIME_INTENT = 'FRIDAY-INSTALL.session-artifact-journey.intent.json'


def cli_bootstrap_previous_journey(request, home, *, session_artifact=False):
    ref = request['previous_journey']
    require(ref['path'] == str(home/(CLI_BOOTSTRAP_RUNTIME_INTENT if session_artifact else CLI_FRONTEND_RUNTIME_INTENT)), 'bootstrap_previous_journey_path_required')
    previous = read_json(pin(ref))
    require(previous['schema'] == 'friday.installed-cli-invocation.v1'
            and previous['state'] == 'CONSUMED_NOT_COMPLETE'
            and previous['request']['schema'] == ('friday.installed-cli-request.v3' if session_artifact else 'friday.installed-cli-request.v2')
            and previous['request']['repaired_input'] == request['previous_input']
            and previous['request']['installation_input'] == request['installation_input']
            and cli_historical_scope_closed(previous['clock'],'friday.installed-cli-clock.v1'), 'bootstrap_previous_journey_consumed_required')
    base='preparation/cli-runtime/'+previous['request']['unit']
    rows=request['previous_runtime']
    require(set(rows) == {base+s for s in (('.intent.json','.json','.stdout','.stderr','.native-owner.json','.result.json') if session_artifact else ('.intent.json','.json','.stdout','.stderr'))}
            and all(digest(owned_file(home/name,private=True)) == sha for name,sha in rows.items())
            and read_json(home/(base+'.intent.json')) == previous, 'bootstrap_previous_journey_history_changed')
    if session_artifact:
        result = read_json(home/(base+'.result.json'))
        require(result['state'] == 'NATIVE_EXIT_OBSERVED_NOT_ACCEPTANCE'
                and result['observation']['returncode'] == 0 and result['observation']['timeout'] is False,
                'cli_session_previous_native_completion_required')
        cli_session_artifact_inputs(home,request['session_artifact'])
    return previous


def repair_native_bootstrap(request, request_path, *, clock, session_artifact=False):
    phase = "repair-session-artifact" if session_artifact else "repair-native-bootstrap"
    token = CLI_SESSION_INTENT if session_artifact else CLI_BOOTSTRAP_INTENT
    prior_token = CLI_BOOTSTRAP_INTENT if session_artifact else CLI_FRONTEND_INTENT
    field = "postinstall_session_artifact_repair" if session_artifact else "postinstall_native_bootstrap_repair"
    folder_name = "session-artifact-repair" if session_artifact else "native-bootstrap-repair"
    count = 37 if session_artifact else 36
    schema = "friday.session-artifact-repair" if session_artifact else "friday.native-bootstrap-repair"
    fields={'schema','phase','assignment','generation','home','installation_input','previous_input',
            'repaired_input','original_marker','original_receipt','original_stamp','previous_repair_intent',
            'selected_python','native_launchers','history','previous_runtime','unit','invocation_id','previous_journey'}
    require(type(request) is dict and set(request) == fields | ({'session_artifact'} if session_artifact else set())
            and request['schema'] == schema+'-request.v1'
            and request['phase'] == phase and type(request['generation']) is int
            and request['generation'] == 1 and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
            and request['invocation_id'] == 'OBSERVE_NATIVE_AT_ADMISSION', 'frontend_exact_request_required')
    from scripts.install_containment import Budget,Containment
    from scripts.hermes_prepare import overlay_layers,git,Budget as SourceBudget
    budget=Budget(180,started=clock['started_mono'],deadline=clock['useful_deadline_mono'])
    physical=budget.call(installed_cli_kernel,request,clock,phase=phase)
    original=read_json(pin(request['installation_input']))
    previous=read_json(pin(request['previous_input']));value=read_json(pin(request['repaired_input']))
    require({k:v for k,v in original.items() if k!='project_files'} ==
            {k:v for k,v in previous.items() if k!='project_files'} ==
            {k:v for k,v in value.items() if k!='project_files'} and value['home'] == request['home'],
            'frontend_operational_settings_changed')
    home,donors=budget.call(spec_checked,value,cli_only=True)
    directory(home);directory(home/'preparation');source=home/'hermes-agent'
    require(not (home/token).exists() and not (home/token).is_symlink(),
            'frontend_consumed_no_retry')
    paths={'original_marker':home/MARKER,'original_receipt':home/'hermes-agent.source.json',
           'original_stamp':source/'install-stamp.json','previous_repair_intent':home/prior_token}
    for key,path in paths.items():
        require(request[key]['path'] == str(path) and pin(request[key]) == path,
                'frontend_exact_previous_pin_required')
    marker=read_json(paths['original_marker']);receipt=read_json(paths['original_receipt']);stamp=read_json(paths['original_stamp'])
    require(marker.get('schema') == SCHEMA and marker.get('home') == str(home)
            and marker.get('source') == str(source) and marker.get('completion_stage') == CLI_STAGE
            and marker.get('input_sha256') == request['installation_input']['sha256']
            and marker.get('source_receipt_sha256') == request['original_receipt']['sha256']
            and marker.get('postinstall_source_input') == request['previous_input']
            and field not in marker
            and (not session_artifact or 'postinstall_native_bootstrap_repair' in marker)
            and 'postinstall_frontend_repair' in marker
            and marker.get('runtime_ready') is False and marker.get('gateway_installed') is False
            and marker.get('native_frontends') == 'PENDING'
            and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
            and value['product']['runtime'] == {'enabled':False}
            and cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
            and cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1'),
            'frontend_previous_pending_history_required')
    budget.call(validated_cli_repair_chain,home,marker,dict(request, schema=('friday.installed-cli-request.v3' if session_artifact else 'friday.installed-cli-request.v2'),repaired_input=request['previous_input']))
    old=read_json(paths['previous_repair_intent'])
    require(old.get('schema') == ('friday.native-bootstrap-repair-intent.v1' if session_artifact else 'friday.frontend-close-repair-intent.v1')
            and old.get('state') == 'CONSUMED_NO_RETRY'
            and old['request']['repaired_input'] == request['previous_input']
            and old['request']['installation_input'] == request['installation_input']
            and old['request']['selected_python'] == request['selected_python']
            and cli_historical_scope_closed(old['clock'],'friday.installed-cli-clock.v1'), 'frontend_old_repair_consumed_required')
    budget.call(cli_repair_history,request,home)
    budget.call(cli_bootstrap_previous_journey,request,home,session_artifact=session_artifact)
    require(len(receipt['layers']) == count-1 and stamp.get('fridaySource') ==
            {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            and stamp.get('commit') == receipt['commit'] and stamp.get('dirty') is True,
            'frontend_previous_full_stamp_required')
    budget.call(composition_checked,previous,source,receipt,donors['hermes'])
    budget.call(cli_repair_plugins,value,home,marker,{})
    for name,sha in {**marker['profile_files'],**marker.get('tls_files',{})}.items():
        require(digest(owned_file(home/name,private=True)) == sha, 'frontend_profile_or_tls_changed')
    selected=bootstrap_pin(request['selected_python'])
    require(selected.is_relative_to(home/'tools') and request['selected_python']['sha256'] == value['bootstrap_python']['sha256'],
            'frontend_selected_python_changed')
    custody=Containment(value['containment'],budget,clean_environment(home))
    native=budget.call(cli_repair_native,custody,value,source,selected,budget)
    require(native['launchers'] == request['native_launchers']
            and native['launchers']['hermes'] == marker['postinstall_native_launcher'], 'frontend_native_launchers_changed')
    layers=budget.call(overlay_layers,ROOT,receipt['commit'],SourceBudget(budget.deadline))
    slim=lambda l:{k:l[k] for k in ('manifest','manifest_sha256','patch_sha256')}
    require(len(layers) == count and len({r['manifest'] for r in receipt['layers']}) == count-1
            and {l['manifest']:slim(l) for _,l in layers[:count-1]} == {r['manifest']:r for r in receipt['layers']}
            and layers[-1][1]['manifest'] == (CLI_SESSION_MANIFEST if session_artifact else CLI_BOOTSTRAP_MANIFEST), 'frontend_single_additive_overlay_required')
    layer=layers[-1][1]
    names = {'hermes_cli/friday_credential_admission.py','hermes_cli/friday_user_scope.py'} if session_artifact else {'hermes_cli/friday_credential_admission.py'}
    require(set(layer['files']) == names, 'frontend_exact_scope_required')
    for name,row in layer['files'].items():
        require(not row.get('new_file') and row['mode'] == receipt['files'][name]['mode']
                and row['before_sha256'] == receipt['files'][name]['sha256']
                and digest(owned_file(source/name)) == row['before_sha256'], 'frontend_exact_preimage_required')
    budget.call(installed_cli_kernel,request,clock,phase=phase)
    require(read_json(request_path) == request, 'frontend_request_changed')
    intent={'schema':schema+'-intent.v1','state':'CONSUMED_NO_RETRY',
            'request':request,'clock':clock,'physical':physical}
    publish(home/token,intent,budget=budget)
    folder=home/'preparation'/folder_name;stage='preserve_beforeimages'
    try:
        folder.mkdir(mode=0o700);directory(folder);saved={}
        preserved={**paths,**{name:source/name for name in names}}
        for path in preserved.values():
            raw=owned_file(path);backup=folder/'beforeimages'/path.relative_to(home)
            backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            cli_repair_bytes(backup,raw,budget,mode=0o600)
            saved[str(path)]={'path':str(backup),'sha256':digest(raw),'bytes':len(raw),
                              'original_mode':stat.S_IMODE(path.stat().st_mode)}
        publish(folder/'beforeimages.json',saved,budget=budget)
        # Complete all custody checks before the first source/receipt/stamp replacement.
        for path in preserved.values():
            require(digest(owned_file(saved[str(path)]['path'],private=True)) == saved[str(path)]['sha256'],
                    'frontend_beforeimage_incomplete')
        stage='overlay_stage';staging=folder/'source';staging.mkdir(mode=0o700)
        for name in names:
            dest=staging/name;dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            cli_repair_bytes(dest,owned_file(source/name),budget,mode=0o600)
        git(staging,['apply','--check','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        git(staging,['apply','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        updated=json.loads(json.dumps(receipt))
        for name,row in layer['files'].items():
            raw=owned_file(staging/name)
            require(digest(raw) == row['sha256'] and len(raw) == row['bytes'], 'frontend_overlay_output_changed')
            stage='publish_source';cli_repair_replace(source/name,raw,row['before_sha256'],budget,
                                                     mode=saved[str(source/name)]['original_mode'])
            updated['files'][name]={k:row[k] for k in ('sha256','bytes','mode')}
        updated['layers']=receipt['layers']+[slim(layer)]
        budget.call(composition_checked,value,source,updated,donors['hermes'])
        receipt_data=(json.dumps(updated,sort_keys=True,indent=2)+'\n').encode()
        stage='publish_receipt';cli_repair_replace(paths['original_receipt'],receipt_data,
            request['original_receipt']['sha256'],budget,mode=saved[str(paths['original_receipt'])]['original_mode'])
        newstamp=dict(stamp,fridaySource={'baseTree':receipt['base_tree'],'layers':updated['layers']})
        stage='publish_stamp';cli_repair_replace(paths['original_stamp'],
            (json.dumps(newstamp,sort_keys=True,indent=2)+'\n').encode(),request['original_stamp']['sha256'],
            budget,mode=saved[str(paths['original_stamp'])]['original_mode'])
        chain={key:{k:saved[str(paths[sourcekey])][k] for k in ('path','sha256')}
               for key,sourcekey in (('previous_marker','original_marker'),('previous_receipt','original_receipt'),
                                     ('previous_stamp','original_stamp'))}
        chain['intent']={'path':str(home/token),'sha256':digest(owned_file(home/token,private=True))}
        final=dict(marker,source_receipt_sha256=digest(receipt_data),postinstall_source_input=request['repaired_input'],
                   **{field:chain})
        stage='final_checks';budget.call(inspect,value,request['installation_input']['sha256'],marker_override=final)
        require(read_json(paths['original_stamp']) == newstamp, 'frontend_full_stamp_changed')
        budget.call(cli_repair_native,custody,value,source,selected,budget)
        budget.call(cli_repair_history,request,home)
        budget.call(cli_bootstrap_previous_journey,request,home,session_artifact=session_artifact)
        for path in preserved.values():
            require(digest(owned_file(saved[str(path)]['path'],private=True)) == saved[str(path)]['sha256'],
                    'frontend_custody_changed')
        require(digest(owned_file(home/prior_token,private=True)) == request['previous_repair_intent']['sha256'],
                'frontend_previous_intent_changed')
        budget.call(installed_cli_kernel,request,clock,phase=phase)
        require(read_json(request_path) == request, 'frontend_request_changed')
        if session_artifact:
            parent=home/'user-artifacts'
            if not parent.exists() and not parent.is_symlink():
                stage='prepare_artifact_parent';parent.mkdir(mode=0o700)
            cli_session_artifact_path(home,request['session_artifact'])
        stage='publish_marker';cli_repair_replace(home/MARKER,(json.dumps(final,sort_keys=True,indent=2)+'\n').encode(),
            request['original_marker']['sha256'],budget,mode=saved[str(home/MARKER)]['original_mode'])
        require(read_json(home/MARKER) == final, 'frontend_final_marker_changed')
        return {'state':'NATIVE_BOOTSTRAP_SOURCE_REPAIRED_NOT_RUNTIME_ACCEPTED','layers':count,'ready':False,
                'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
    except BaseException as exc:
        failure={'schema':schema+'-failure.v1','state':'NO_RETRY','stage':stage,
                 'diagnostic':retained_diagnostic(exc,'repair-native-bootstrap'),
                 'rollback':'NOT_AUTOMATIC; exact beforeimages retained; consumed token never renewed',
                 'clock':clock,'physical':physical,'Runtime_Go':False,'Resource_Go':False,'Release_Go':False}
        try:publish(home/('FRIDAY-INSTALL.session-artifact-repair.failure.json' if session_artifact else 'FRIDAY-INSTALL.native-bootstrap-repair.failure.json'),failure)
        except BaseException as secondary:remember_secondary(exc,secondary)
        raise


def main():
    started = time.monotonic()  # before parser/input IO; never reset on dispatch
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=('plan', 'install', 'check', 'dashboard-check', 'start', 'qualify', 'reconcile', 'resume-harness', 'resume-cli', 'continue-cli-segment', 'installed-cli', 'repair-installed-cli', 'repair-frontend-close', 'repair-native-bootstrap', 'repair-session-artifact'))
    parser.add_argument('--input', required=True, type=Path, help='Private pinned JSON, no credential values')
    parser.add_argument('--a0-plan', type=Path, help='Existing owned live native probe plan; never a readiness report')
    parser.add_argument('--a0-plan-sha256')
    args = parser.parse_args(); os.umask(0o077)
    sys.path.insert(0, str(ROOT))
    from scripts.dsh_prepare import StopUnconfirmed
    try:
        runtime_clock = installed_cli_clock() if args.phase in ('installed-cli','repair-installed-cli','repair-frontend-close','repair-native-bootstrap','repair-session-artifact') else None
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
        budget = (Budget(180,started=runtime_clock['started_mono'],deadline=runtime_clock['useful_deadline_mono'])
                  if runtime_clock else cli_segment_clock(admission) if admission else
                  (prepared[3] if prepared else Budget(value.get('seconds'), started=started)))
        budget.check()
        if args.phase == 'repair-session-artifact':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,session_artifact=True)
        elif args.phase == 'repair-native-bootstrap':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock)
        elif args.phase == 'repair-frontend-close':
            result = repair_frontend_close(value,args.input,clock=runtime_clock)
        elif args.phase == 'repair-installed-cli':
            result = repair_installed_cli(value,args.input,clock=runtime_clock)
        elif args.phase == 'installed-cli':
            result = installed_cli(value,args.input,clock=runtime_clock)
        elif args.phase == 'continue-cli-segment':
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
