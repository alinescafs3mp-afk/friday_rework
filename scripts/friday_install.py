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


def _source_runtime_module(name):
    """Share bounded source helpers without claiming native ``plugins``.

    project_plugin still validates every private module against its exact pin.
    """
    if name not in ('runtime_primitives', 'runtime_process',
                    'runtime_containment', 'runtime_observers'):
        raise ValueError('source_runtime_helper_required')
    alias = '_friday_install_validation_plugins'
    if alias not in sys.modules:
        package = importlib.util.module_from_spec(
            importlib.machinery.ModuleSpec(alias, loader=None, is_package=True))
        package.__path__ = [str(ROOT / 'plugins')]
        sys.modules[alias] = package
    if list(getattr(sys.modules[alias], '__path__', ())) != [str(ROOT / 'plugins')]:
        raise ValueError('foreign_validator_package')

    def check_paths():
        for key, loaded in tuple(sys.modules.items()):
            if not key.startswith(alias + '.'):
                continue
            relative = key[len(alias) + 1:].replace('.', '/')
            expected = ROOT / 'plugins' / relative
            expected = (expected / '__init__.py' if getattr(loaded, '__path__', None) is not None
                        else expected.with_suffix('.py'))
            if (not getattr(loaded, '__file__', None)
                    or Path(loaded.__file__).resolve() != expected
                    or getattr(getattr(loaded, '__spec__', None), 'origin', None) != str(expected)):
                raise ValueError('foreign_validator_module')
            if getattr(loaded, '__path__', None) is not None and list(loaded.__path__) != [str(expected.parent)]:
                raise ValueError('foreign_validator_package')
    check_paths()
    module = importlib.import_module(alias + '.friday_rework.' + name)
    check_paths()
    return module


if __name__ != '__main__':
    _primitives = _source_runtime_module('runtime_primitives')
    Refused, require, canonical, owned_file, unique, read_json, digest, pin = (
        getattr(_primitives, name) for name in
        ('Refused', 'require', 'canonical', 'owned_file', 'unique', 'read_json', 'digest', 'pin'))

class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Friday entry refused: phase=arguments reason=invalid_cli_arguments\n')




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
    require(set(product) == {'profile', 'inference', 'web', 'dashboard', 'accounts', 'runtime'} | (set(product) & {'a0_deployment','compression_inference','compression_multipass'}),
            'explicit_normal_product_required')
    if 'a0_deployment' in product:
        spec = importlib.util.spec_from_file_location('_friday_a0_profile_validator', ROOT / 'plugins/friday_rework/adapters/a0_profile.py')
        profile_validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile_validator)
        deployment = profile_validator.checked_profile(product['a0_deployment'])
        selected = product['inference']
        expected_key = 'FRIDAY_LLM_API_KEY'
        if (product.get('compression_inference') is not None
                and type(product['runtime']) is dict and set(product['runtime'])=={'enabled'}
                and product['runtime']['enabled'] is False):
            # Existing legacy A0 declarations remain inactive and byte-exact.
            # Their old27B chat is compared to the explicit preserved role.
            selected = product['compression_inference']
            expected_key = 'FRIDAY_COMPRESSION_API_KEY'
        chat = deployment['chat']
        require(chat['endpoint'] == selected['base_url'] and chat['model'] == selected['model']
                and chat['context_length'] == selected['context']
                and chat['max_output_tokens'] == selected['main_output']
                and selected['key_env'] == expected_key, 'a0_product_inference_profile_mismatch')
    if 'worker_install' in value:
        from scripts.worker_install import settings
        settings(value, cli_only=cli_only)
    build_config(**product['inference'], compression_inference=product.get('compression_inference'),
                 compression_multipass=product.get('compression_multipass'))
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
        if name == '.web_ui_build.lock':
            # Native main_web_build retains this empty advisory lock after a
            # normal dashboard build. Validate it, preserving its inode/bytes;
            # links, directories, payloads and world-writable modes refuse.
            require(owned_file(p) == b'' and stat.S_IMODE(p.stat().st_mode) in
                    (0o600, 0o644, 0o664), 'unexpected_native_web_build_lock')
            continue
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
    home, donors = spec_checked(value, cli_only=marker.get('completion_stage') in (CLI_STAGE,'TELEGRAM_ORDINARY'))
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
        if name == 'config.yaml' and marker.get('completion_stage') == 'TELEGRAM_ORDINARY':
            continue  # Checked below through the native semantic onboarding contract.
        require(digest(owned_file(home / name, private=True)) == sha, 'installed_profile_changed')
    expected_plugins = {name: sha for name, sha in value['project_files'].items()
                        if name.startswith('plugins/friday_rework/')}
    require(marker.get('plugin_files') == expected_plugins, 'installed_plugin_inventory_changed')
    for name, sha in expected_plugins.items():
        require(digest(owned_file(home / name, private=True)) == sha, 'installed_plugin_changed')
    effective = value
    if marker.get('completion_stage') == 'TELEGRAM_ORDINARY':
        native_packages(home/'hermes-agent')
        from hermes_cli.friday_ordinary_gateway import check
        from hermes_cli.friday_user_scope import authority
        with authority(home):
            check(home,role=False)
        return {'state':'ORDINARY_TELEGRAM_WORKERS_PENDING','ready':False,'effects':'NONE',
                'full_start_allowed':False,'workers_enabled':False,'runtime_acceptance':'NOT_GRANTED'}
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
    require(budget.call(read_json,home/MARKER).get('completion_stage') not in (CLI_STAGE,'TELEGRAM_ORDINARY'), 'cli_host_full_start_refused')
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
    require(phase in ("installed-cli", "repair-installed-cli", "repair-frontend-close", "repair-native-bootstrap", "repair-session-artifact", "repair-context-continuation", "repair-native-manager", "repair-readonly-schema-formatter", "repair-current12-readonly-fit", "repair-summary-fit", "repair-summary-budget", "repair-summary-completion", "repair-summary-visible"), "installed_cli_exact_phase_required")
    if phase in ("repair-installed-cli", "repair-frontend-close", "repair-native-bootstrap", "repair-session-artifact", "repair-context-continuation", "repair-native-manager", "repair-readonly-schema-formatter", "repair-current12-readonly-fit", "repair-summary-fit", "repair-summary-budget", "repair-summary-completion", "repair-summary-visible"):
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
    ordinary = phase == 'installed-cli' and request.get('schema') in ('friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')
    props='Id,InvocationID,ActiveState,SubState,MainPID,ControlPID,ControlGroup,RuntimeMaxUSec,TimeoutStopUSec,KillMode'
    if ordinary:
        props += ',ExecMainStartTimestampMonotonic'
    command=['/usr/bin/env','XDG_RUNTIME_DIR='+str(runtime),'DBUS_SESSION_BUS_ADDRESS=unix:path='+str(bus),
             '/usr/bin/systemctl','--user','show',unit,'--property='+props]
    text=run(command,ROOT,timeout=5,env=clean_environment(Path(request['home'])),
             deadline=clock['useful_deadline_mono'])[0]
    pairs=[r.split('=',1) for r in text.splitlines()]; observed=dict(pairs)
    require(re.fullmatch('[0-9a-f]{32}', observed.get('InvocationID',''))
            and len(pairs)==len(observed)==(11 if ordinary else 10) and observed == {'Id':unit,'InvocationID':observed['InvocationID'],
            'ActiveState':'active','SubState':'running','MainPID':str(clock['gnu_pid']),'ControlPID':'0',
            'ControlGroup':group,'RuntimeMaxUSec':'2min 28s','TimeoutStopUSec':'30s','KillMode':'control-group',
            **({'ExecMainStartTimestampMonotonic':observed.get('ExecMainStartTimestampMonotonic')} if ordinary else {})},
            'installed_cli_actual_native_unit_required')
    if ordinary:
        require(re.fullmatch(r'[1-9][0-9]{0,19}',observed['ExecMainStartTimestampMonotonic'])
                and abs(int(observed['ExecMainStartTimestampMonotonic'])/1000000-clock['started_mono']) < 0.2,
                'installed_cli_unit_main_birth_changed')
    version=run(['/usr/bin/gnutimeout','--version'],ROOT,timeout=3,
                env=clean_environment(Path(request['home'])),deadline=clock['useful_deadline_mono'])[0]
    require(version.startswith('timeout (GNU coreutils) '), 'installed_cli_genuine_gnu_required')
    return {'unit':unit,'invocation_id':observed['InvocationID'],'cgroup':group,
            'caps':dict(CLI_RUNTIME_CAPS),
            **({'unit_main_start_usec':int(observed['ExecMainStartTimestampMonotonic'])} if ordinary else {}),
            'self_stat':Path('/proc/self/stat').read_text(),
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


def cli_host_source_transition(request, transition_ref):
    """Bind reviewed HOST bytes while preserving the consumed native Source45 chain."""
    def exact(a, b):
        if type(a) is not type(b): return False
        if type(a) is dict: return set(a) == set(b) and all(exact(a[k],b[k]) for k in a)
        if type(a) is list: return len(a) == len(b) and all(exact(x,y) for x,y in zip(a,b))
        return a == b
    def load(ref):
        require(type(ref) is dict and set(ref) == {'path','sha256'}
                and type(ref['path']) is str and type(ref['sha256']) is str
                and re.fullmatch('[0-9a-f]{64}',ref['sha256']), 'cli_host_transition_pin_required')
        raw = owned_file(Path(ref['path']),private=True)
        require(digest(raw) == ref['sha256'], 'input_pin_changed')
        return cli_ordinary_failed_v6_json(raw)
    require(request.get('schema') == 'friday.installed-cli-request.v12', 'cli_host_transition_v12_required')
    proof = load(transition_ref)
    fields = {'schema','request','native_input','host_input','before_helper','after_helper',
              'marker','receipt','stamp','maintenance_intent','root_review'}
    require(type(proof) is dict and set(proof) == fields
            and proof['schema'] == 'friday.cli-host-source-transition.v1', 'cli_host_transition_fields_required')
    require(exact(load(proof['request']),request) and exact(proof['native_input'],request['repaired_input']),
            'cli_host_transition_request_changed')
    before = load(proof['native_input']); after = load(proof['host_input'])
    helper = 'scripts/friday_install.py'
    require(exact({k:v for k,v in before.items() if k != 'project_files'},
                  {k:v for k,v in after.items() if k != 'project_files'})
            and type(before['project_files']) is type(after['project_files']) is dict
            and set(before['project_files']) == set(after['project_files'])
            and exact({k:v for k,v in before['project_files'].items() if k != helper},
                      {k:v for k,v in after['project_files'].items() if k != helper}),
            'cli_host_transition_only_helper_required')
    require(proof['host_input']['path'] == str(ROOT.parent/'HOST-SOURCE-INPUT.json')
            and proof['before_helper']['path'] == str(Path(proof['native_input']['path']).parent/'project'/helper)
            and proof['after_helper']['path'] == str(ROOT/helper)
            and proof['before_helper']['sha256'] == before['project_files'][helper]
            and proof['after_helper']['sha256'] == after['project_files'][helper]
            and proof['before_helper']['sha256'] != proof['after_helper']['sha256'],
            'cli_host_transition_helper_binding_required')
    pin(proof['before_helper']); pin(proof['after_helper'])
    home = Path(request['home'])
    for field, name in (('marker',MARKER),('receipt','hermes-agent.source.json'),
                        ('stamp','hermes-agent/install-stamp.json'),('maintenance_intent',CLI_SUMMARY_VISIBLE_INTENT)):
        require(proof[field]['path'] == str(home/name), 'cli_host_transition_native_path_required')
        load(proof[field])
    marker = load(proof['marker']); receipt = load(proof['receipt']); stamp = load(proof['stamp'])
    intent = load(proof['maintenance_intent'])
    require(exact(marker['postinstall_source_input'],proof['native_input'])
            and marker['source_receipt_sha256'] == proof['receipt']['sha256']
            and len(receipt['layers']) == 45
            and exact(stamp['fridaySource'],{'baseTree':receipt['base_tree'],'layers':receipt['layers']})
            and intent['schema'] == 'friday.summary-visible-repair-intent.v1'
            and intent['state'] == 'CONSUMED_NO_RETRY'
            and exact(intent['request']['repaired_input'],proof['native_input'])
            and exact(marker['postinstall_summary_visible_repair']['intent'],proof['maintenance_intent']),
            'cli_host_transition_consumed45_required')
    review = load(proof['root_review'])
    bindings = {k:v for k,v in proof.items() if k not in {'schema','root_review'}}
    require(type(review) is dict and set(review) == {'schema','Source_Go','Binding_Go','Runtime_Go',
            'Resource_Go','Release_Go','bindings','independent_review'}
            and review['schema'] == 'friday.cli-host-source-transition-root-review.v1'
            and review['Source_Go'] is True and review['Binding_Go'] is True
            and review['Runtime_Go'] is review['Resource_Go'] is review['Release_Go'] is False
            and exact(review['bindings'],bindings), 'cli_host_transition_root_proof_required')
    independent = load(review['independent_review'])
    require(type(independent) is dict and set(independent) == {'schema','Source_Go','Binding_Go','bindings'}
            and independent['schema'] == 'friday.cli-host-source-transition-independent-review.v1'
            and independent['Source_Go'] is True and independent['Binding_Go'] is True
            and exact(independent['bindings'],bindings), 'cli_host_transition_independent_proof_required')
    # The corrected host validates every active project file before any runtime effects.
    spec_checked(after,cli_only=True)
    return after


def installed_cli(request, request_path, *, clock, host_source_transition=None):
    session_artifact = request.get('schema') == 'friday.installed-cli-request.v4'
    ordinary_readonly = request.get('schema') in ('friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')
    require(type(request) is dict and set(request)==({'schema','assignment','generation','home',
        'installation_input','repaired_input','historical_marker','native_launcher','history','unit','invocation_id','argv'} | ({'ordinary_readonly','job_id','partial_proof'} | ({'strategy_recovery'} if request.get('schema') == 'friday.installed-cli-request.v12' else set()) if ordinary_readonly else {'session_artifact'} if session_artifact else set()))
        and request['schema'] in ('friday.installed-cli-request.v1','friday.installed-cli-request.v2','friday.installed-cli-request.v3','friday.installed-cli-request.v4','friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12') and request['generation']==1
        and type(request['generation']) is int
        and re.fullmatch('[A-Za-z0-9-]{1,128}',request['assignment'])
        and request['invocation_id']=='OBSERVE_NATIVE_AT_ADMISSION', 'installed_cli_exact_request_required')
    from scripts.install_containment import Budget, Containment
    budget=Budget(180,started=clock['started_mono'],deadline=clock['useful_deadline_mono'])
    physical=budget.call(installed_cli_kernel,request,clock)
    frontend = request['schema'] != 'friday.installed-cli-request.v1'
    bootstrap_chain = request['schema'] in ('friday.installed-cli-request.v3','friday.installed-cli-request.v4','friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')
    original=read_json(pin(request['installation_input']));value=read_json(pin(request['repaired_input']))
    if host_source_transition is not None:
        value=budget.call(cli_host_source_transition,request,host_source_transition)
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
                ({'postinstall_session_artifact_repair'} if session_artifact or ordinary_readonly else set()) |
                ({'postinstall_context_continuation_repair'} if ordinary_readonly else set()) |
                ({'postinstall_native_manager_repair'} if 'postinstall_native_manager_repair' in marker else set()) |
                ({'postinstall_readonly_schema_formatter_repair'} if 'postinstall_readonly_schema_formatter_repair' in marker else set()) |
                ({'postinstall_current12_readonly_fit_repair'} if 'postinstall_current12_readonly_fit_repair' in marker else set()) |
                ({'postinstall_summary_fit_repair'} if 'postinstall_summary_fit_repair' in marker else set()) |
                ({'postinstall_summary_budget_repair'} if 'postinstall_summary_budget_repair' in marker else set()) |
                ({'postinstall_summary_completion_repair'} if 'postinstall_summary_completion_repair' in marker else set()) |
                ({'postinstall_summary_visible_repair'} if 'postinstall_summary_visible_repair' in marker else set())} ==
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
    if ordinary_readonly:
        require(request['ordinary_readonly'].get('schema') == {'friday.installed-cli-request.v5':'friday.cli-ordinary-readonly.v1','friday.installed-cli-request.v6':'friday.cli-ordinary-readonly.v2','friday.installed-cli-request.v7':'friday.cli-ordinary-readonly.v3','friday.installed-cli-request.v8':'friday.cli-ordinary-readonly.v4','friday.installed-cli-request.v9':'friday.cli-ordinary-readonly.v5','friday.installed-cli-request.v10':'friday.cli-ordinary-readonly.v6','friday.installed-cli-request.v11':'friday.cli-ordinary-readonly.v7','friday.installed-cli-request.v12':'friday.cli-ordinary-readonly.v8'}[request['schema']]
                and (request['schema'] != 'friday.installed-cli-request.v6' or 'postinstall_native_manager_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v7' or 'postinstall_readonly_schema_formatter_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v8' or 'postinstall_current12_readonly_fit_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v9' or 'postinstall_summary_fit_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v10' or 'postinstall_summary_budget_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v11' or 'postinstall_summary_completion_repair' in marker)
                and (request['schema'] != 'friday.installed-cli-request.v12' or 'postinstall_summary_visible_repair' in marker), 'cli_ordinary_new_question_source_required')
        expected = cli_ordinary_readonly_argv(home,request['ordinary_readonly'])
        require(request['job_id'] == cli_ordinary_job_id(home,request['ordinary_readonly']),
                'cli_ordinary_semantic_job_changed')
        budget.call(cli_ordinary_readonly_inputs,home,request['ordinary_readonly'])
        budget.call(cli_ordinary_readonly_artifact,home,request['ordinary_readonly'])
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
    require(len(full_receipt['layers'])==((45 if 'postinstall_summary_visible_repair' in marker else 44 if 'postinstall_summary_completion_repair' in marker else 43 if 'postinstall_summary_budget_repair' in marker else 42 if 'postinstall_summary_fit_repair' in marker else 41 if 'postinstall_current12_readonly_fit_repair' in marker else 40 if 'postinstall_readonly_schema_formatter_repair' in marker else 39 if 'postinstall_native_manager_repair' in marker else 38) if ordinary_readonly else 37 if session_artifact else 36 if bootstrap_chain else 35 if frontend else 34) and read_json(source/'install-stamp.json')['fridaySource']==
            {'baseTree':full_receipt['base_tree'],'layers':full_receipt['layers']},'installed_cli_full_stamp_required')
    custody=Containment(value['containment'],budget,clean_environment(home))
    repair_intent=read_json(home/CLI_REPAIR_INTENT)
    if bootstrap_chain:
        budget.call(validated_cli_repair_chain,home,marker,request)
        delta=read_json(pin(marker['postinstall_native_bootstrap_repair']['intent']))
        frontend_delta=read_json(pin(marker['postinstall_frontend_repair']['intent']))
        expected_previous=frontend_delta['request']['previous_input']
        if ordinary_readonly:
            repair = read_json(pin(marker['postinstall_summary_visible_repair' if request['schema'] == 'friday.installed-cli-request.v12' else 'postinstall_summary_completion_repair' if request['schema'] == 'friday.installed-cli-request.v11' else 'postinstall_summary_budget_repair' if request['schema'] == 'friday.installed-cli-request.v10' else 'postinstall_summary_fit_repair' if request['schema'] == 'friday.installed-cli-request.v9' else 'postinstall_current12_readonly_fit_repair' if request['schema'] == 'friday.installed-cli-request.v8' else 'postinstall_readonly_schema_formatter_repair' if request['schema'] == 'friday.installed-cli-request.v7' else 'postinstall_context_continuation_repair']['intent']))
            require((repair['request']['next_ordinary_readonly'] == request['ordinary_readonly'] if request['schema'] in ('friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12') else repair['request']['ordinary_readonly'] == cli_ordinary_readonly_baseline(request['ordinary_readonly']))
                    and repair['request']['partial_proof'] == request['partial_proof'], 'cli_ordinary_repair_scope_changed')
            if request['schema'] not in ('friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12'):
                budget.call(cli_context_previous_journey,repair['request'],home)
            jobs=home/'preparation/cli-runtime/jobs'
            if not jobs.exists():
                jobs.mkdir(mode=0o700)
            directory(jobs)
            job_path=jobs/(request['job_id']+'.intent.json')
            require(not job_path.exists() and not job_path.is_symlink(), 'cli_ordinary_job_consumed_no_retry')
        else:
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
    if host_source_transition is not None:
        require(budget.call(cli_host_source_transition,request,host_source_transition) == value,
                'cli_host_transition_changed_before_consumption')
    require(read_json(request_path)==request, 'installed_cli_request_changed')
    folder=home/'preparation/cli-runtime';folder.mkdir(mode=0o700,exist_ok=True);directory(folder)
    intent={'schema':'friday.installed-cli-invocation.v1','state':'CONSUMED_NOT_COMPLETE',
            'request':request,'clock':clock,'physical':physical,'history':request['history']}
    if ordinary_readonly:
        publish(job_path,{'schema':'friday.cli-ordinary-job-intent.v1','state':'CONSUMED_NO_RETRY',
                'job_id':request['job_id'],'request':request,'clock':clock},budget=budget)
    elif bootstrap_chain:
        publish(home/(CLI_SESSION_RUNTIME_INTENT if session_artifact else CLI_BOOTSTRAP_RUNTIME_INTENT),intent,budget=budget)
    elif frontend:
        publish(home/CLI_FRONTEND_RUNTIME_INTENT,intent,budget=budget)
    publish(folder/(request['unit']+'.intent.json'),intent,budget=budget)
    result=custody.run([str(launch),*expected],source,timeout=min(120,budget.check(reserve=1)),
                       log=folder/(request['unit']+'.native'))
    if ordinary_readonly:
        row,messages = budget.call(cli_ordinary_readonly_inputs,home,request['ordinary_readonly'],resumed=True)
        budget.call(cli_ordinary_readonly_artifact,home,request['ordinary_readonly'])
        baseline=set(request['ordinary_readonly']['baseline_message_ids'])
        appended=[m for m in messages if m['id'] not in baseline]
        require(result[1]['returncode'] == 0 and result[1]['timeout'] is False
                and row['end_reason'] == 'cli_close' and row['ended_at'] is not None
                and any(m['role']=='user' and m['content']==expected[-1] for m in appended)
                and any(m['role']=='tool' and m['tool_name']=='read_file'
                    and json.loads(m['content']).get('success') is True for m in appended)
                and appended[-1]['role']=='assistant' and type(appended[-1]['content']) is str
                and bool(appended[-1]['content'].strip())
                and not any(m['role']=='tool' and m['tool_name']!='read_file' for m in appended),
                'cli_ordinary_native_completion_required')
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
        return cli_ordinary_failed_v6_json(raw)
    def local(path):
        raw = read_owned(path, private=True)
        return cli_ordinary_failed_v6_json(raw), hashlib.sha256(raw).hexdigest()
    require(request['schema'] in ('friday.installed-cli-request.v1','friday.installed-cli-request.v2',
                                 'friday.installed-cli-request.v3','friday.installed-cli-request.v4',
                                 'friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12'), 'cli_runtime_supported_request_required')
    require(('postinstall_native_bootstrap_repair' in marker) ==
            (request['schema'] in ('friday.installed-cli-request.v3','friday.installed-cli-request.v4','friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12'))
            and ('postinstall_session_artifact_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v4','friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12'))
            and ('postinstall_context_continuation_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v5','friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12'))
            and ('postinstall_frontend_repair' in marker) == (request['schema'] != 'friday.installed-cli-request.v1'),
            'cli_runtime_supported_chain_required')
    require(request['schema'] not in ('friday.installed-cli-request.v6','friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12') or
            'postinstall_native_manager_repair' in marker, 'cli_ordinary_new_question_source_required')
    require(('postinstall_readonly_schema_formatter_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v7','friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')), 'cli_runtime_schema_formatter_chain_required')
    require(('postinstall_current12_readonly_fit_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v8','friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')), 'cli_runtime_current12_chain_required')
    require(('postinstall_summary_fit_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v9','friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')), 'cli_runtime_summary_fit_chain_required')
    require(('postinstall_summary_budget_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v10','friday.installed-cli-request.v11','friday.installed-cli-request.v12')), 'cli_runtime_summary_budget_chain_required')
    require(('postinstall_summary_visible_repair' in marker) == (request['schema'] == 'friday.installed-cli-request.v12'), 'cli_runtime_summary_visible_chain_required')
    require(('postinstall_summary_completion_repair' in marker) == (request['schema'] in ('friday.installed-cli-request.v11','friday.installed-cli-request.v12')), 'cli_runtime_summary_completion_chain_required')
    original = load(request['installation_input'])
    current_input = load(request['repaired_input'])
    require({k:v for k,v in original.items() if k != 'project_files'} ==
            {k:v for k,v in current_input.items() if k != 'project_files'}
            and current_input['home'] == str(home), 'cli_runtime_chain_input_changed')
    receipt, receipt_sha = local(home/'hermes-agent.source.json')
    stamp, _ = local(home/'hermes-agent/install-stamp.json')
    require(marker['source_receipt_sha256'] == receipt_sha and stamp['fridaySource'] ==
            {'baseTree':receipt['base_tree'],'layers':receipt['layers']}, 'cli_runtime_chain_source_changed')
    names41, newfiles41 = set(), set()
    if 'postinstall_current12_readonly_fit_repair' in marker:
        manifest41_path = Path(request['repaired_input']['path']).parent/'project/patches/hermes/installed-current12-readonly-fit-manifest.json'
        manifest41_raw = read_owned(manifest41_path)
        require(hashlib.sha256(manifest41_raw).hexdigest() == current_input['project_files']['patches/hermes/installed-current12-readonly-fit-manifest.json'], 'cli_runtime_current12_manifest_changed')
        names41, newfiles41 = cli_current12_manifest_scope(cli_ordinary_failed_v6_json(manifest41_raw))
    names42, newfiles42 = set(), set()
    if 'postinstall_summary_fit_repair' in marker:
        manifest42_path = Path(request['repaired_input']['path']).parent/'project'/CLI_SUMMARY_FIT_MANIFEST
        manifest42_raw = read_owned(manifest42_path)
        require(hashlib.sha256(manifest42_raw).hexdigest() == current_input['project_files'][CLI_SUMMARY_FIT_MANIFEST], 'cli_runtime_summary_fit_manifest_changed')
        names42, newfiles42 = cli_summary_fit_manifest_scope(cli_ordinary_failed_v6_json(manifest42_raw))
    names43 = set()
    if 'postinstall_summary_budget_repair' in marker:
        manifest43_path = Path(request['repaired_input']['path']).parent/'project'/CLI_SUMMARY_BUDGET_MANIFEST
        manifest43_raw = read_owned(manifest43_path)
        require(hashlib.sha256(manifest43_raw).hexdigest() == current_input['project_files'][CLI_SUMMARY_BUDGET_MANIFEST], 'cli_runtime_summary_budget_manifest_changed')
        names43, _ = cli_summary_budget_manifest_scope(cli_ordinary_failed_v6_json(manifest43_raw))
    names44 = set()
    names45,newfiles45 = set(),set()
    if 'postinstall_summary_visible_repair' in marker:
        manifest45_path = Path(request['repaired_input']['path']).parent/'project'/CLI_SUMMARY_VISIBLE_MANIFEST
        manifest45_raw = read_owned(manifest45_path)
        require(hashlib.sha256(manifest45_raw).hexdigest() == current_input['project_files'][CLI_SUMMARY_VISIBLE_MANIFEST], 'cli_runtime_summary_visible_manifest_changed')
        names45,newfiles45 = cli_summary_visible_manifest_scope(cli_ordinary_failed_v6_json(manifest45_raw))
    if 'postinstall_summary_completion_repair' in marker:
        manifest44_path = Path(request['repaired_input']['path']).parent/'project'/CLI_SUMMARY_COMPLETION_MANIFEST
        manifest44_raw = read_owned(manifest44_path)
        require(hashlib.sha256(manifest44_raw).hexdigest() == current_input['project_files'][CLI_SUMMARY_COMPLETION_MANIFEST], 'cli_runtime_summary_completion_manifest_changed')
        names44, _ = cli_summary_completion_manifest_scope(cli_ordinary_failed_v6_json(manifest44_raw))
    head = marker
    snapshots = {}
    for field, folder, token, schema, manifest_name, source_name, count, prior_token, prior_schema in (
        ('postinstall_summary_visible_repair','summary-visible-repair',CLI_SUMMARY_VISIBLE_INTENT,
         'friday.summary-visible-repair-intent.v1','installed-summary-visible-manifest.json',
         tuple(names45),45,CLI_SUMMARY_COMPLETION_INTENT,'friday.summary-completion-repair-intent.v1'),
        ('postinstall_summary_completion_repair','summary-completion-repair',CLI_SUMMARY_COMPLETION_INTENT,
         'friday.summary-completion-repair-intent.v1','installed-summary-completion-manifest.json',
         tuple(names44),44,CLI_SUMMARY_BUDGET_INTENT,'friday.summary-budget-repair-intent.v1'),
        ('postinstall_summary_budget_repair','summary-budget-repair',CLI_SUMMARY_BUDGET_INTENT,
         'friday.summary-budget-repair-intent.v1','installed-summary-budget-manifest.json',
         tuple(names43),43,CLI_SUMMARY_FIT_INTENT,'friday.summary-fit-repair-intent.v1'),
        ('postinstall_summary_fit_repair','summary-fit-repair',CLI_SUMMARY_FIT_INTENT,
         'friday.summary-fit-repair-intent.v1','installed-summary-fit-manifest.json',
         tuple(names42),42,CLI_CURRENT12_INTENT,'friday.current12-readonly-fit-repair-intent.v1'),
        ('postinstall_current12_readonly_fit_repair','current12-readonly-fit-repair','FRIDAY-INSTALL.current12-readonly-fit-repair.intent.json',
         'friday.current12-readonly-fit-repair-intent.v1','installed-current12-readonly-fit-manifest.json',
         tuple(names41),41,'FRIDAY-INSTALL.readonly-schema-formatter-repair.intent.json','friday.readonly-schema-formatter-repair-intent.v1'),
        ('postinstall_readonly_schema_formatter_repair','readonly-schema-formatter-repair','FRIDAY-INSTALL.readonly-schema-formatter-repair.intent.json',
         'friday.readonly-schema-formatter-repair-intent.v1','installed-readonly-schema-formatter-manifest.json',
         tuple(cli_readonly_schema_manifest_names()),40,'FRIDAY-INSTALL.native-manager-repair.intent.json','friday.native-manager-repair-intent.v1'),
        ('postinstall_native_manager_repair','native-manager-repair','FRIDAY-INSTALL.native-manager-repair.intent.json',
         'friday.native-manager-repair-intent.v1','installed-native-manager-manifest.json',
         'hermes_cli/friday_credential_admission.py',39,'FRIDAY-INSTALL.context-continuation-repair.intent.json',
         'friday.context-continuation-repair-intent.v1'),
        ('postinstall_context_continuation_repair','context-continuation-repair','FRIDAY-INSTALL.context-continuation-repair.intent.json',
         'friday.context-continuation-repair-intent.v1','installed-context-continuation-manifest.json',
         ('agent/bounded_context.py','agent/context_compressor.py','agent/turn_preflight_gate.py',
          'hermes_cli/friday_credential_admission.py','hermes_cli/friday_user_scope.py',
          'tests/agent/test_post_tool_context_fit.py'),38,
         'FRIDAY-INSTALL.session-artifact-repair.intent.json','friday.session-artifact-repair-intent.v1'),
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
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest(); manifest = cli_ordinary_failed_v6_json(manifest_raw)
        require(value['project_files'][manifest_relative] == manifest_sha and len(manifest['files']) == (len(names45) if count == 45 else len(names44) if count == 44 else len(names43) if count == 43 else len(names42) if count == 42 else len(names41) if count == 41 else len(cli_readonly_schema_manifest_names()) if count == 40 else 6 if count == 38 else 2 if count == 37 else 1),
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
            new_file = (count == 45 and name in newfiles45) or (count == 38 and name == 'tests/agent/test_post_tool_context_fit.py') or (count == 40 and name in cli_readonly_schema_new_files()) or (count == 41 and name in newfiles41) or (count == 42 and name in newfiles42)
            require((row['before_sha256'] is None and row.get('new_file') is True and row['mode'] == '100644' and name not in before['files']
                     if new_file else row['before_sha256'] == before['files'][name]['sha256'])
                    and receipt['files'][name] == {k:row[k] for k in ('sha256','bytes','mode')},
                    'cli_runtime_chain_receipt_changed')
            raw = read_owned(snapshots.get(name,home/'hermes-agent'/name))
            require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'],
                    'cli_runtime_chain_source_changed')
            if new_file:
                absence = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
                require(absence.get(str(home/'hermes-agent'/name)) == {'absent':True}
                        and not (base/'hermes-agent'/name).exists()
                        and not (base/'hermes-agent'/name).is_symlink(), 'cli_runtime_saved_absence_changed')
            elif count in (37,38,39,40,41,42,43,44,45):
                prior_source = base/'hermes-agent'/name
                raw = read_owned(prior_source,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['before_sha256'], 'cli_runtime_saved_source_changed')
                snapshots[name] = prior_source
        prior = load(r['previous_repair_intent'],home/prior_token)
        require(prior['schema'] == prior_schema and prior['state'] == 'CONSUMED_NO_RETRY'
                and prior['request']['repaired_input'] == r['previous_input']
                and prior['request']['installation_input'] == request['installation_input']
                and cli_historical_scope_closed(prior['clock'],'friday.installed-cli-clock.v1'), 'cli_runtime_prior_repair_changed')
        if count == 45:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_summary_visible_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in names-newfiles45)):
                row=saved[str(home/relative)];backup=base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'],
                        'cli_runtime_summary_visible_beforeimage_mode_changed')
                raw=read_owned(backup,private=True)
                require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                        'cli_runtime_summary_visible_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_summary_visible_old_intent_changed')
            cli_ordinary_previous_failed_v11_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v12'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['strategy_recovery'] == r['new_strategy_recovery']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_summary_visible_scope_changed')
            cli_summary_visible_recovery_contract(request['strategy_recovery'],request['ordinary_readonly'],source=home/'hermes-agent')
            request = {k:v for k,v in request.items() if k != 'strategy_recovery'}
            request = dict(request,schema='friday.installed-cli-request.v11',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 44:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            existing = names
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_summary_completion_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in existing)):
                row = saved[str(home/relative)]; backup = base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'], 'cli_runtime_summary_completion_beforeimage_mode_changed')
                raw = read_owned(backup,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'cli_runtime_summary_completion_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_summary_completion_old_intent_snapshot_changed')
            cli_ordinary_previous_failed_v10_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v11'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_summary_completion_history_scope_changed')
            request = dict(request,schema='friday.installed-cli-request.v10',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 43:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            existing = names
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_summary_budget_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in existing)):
                row = saved[str(home/relative)]; backup = base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'], 'cli_runtime_summary_budget_beforeimage_mode_changed')
                raw = read_owned(backup,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'cli_runtime_summary_budget_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_summary_budget_old_intent_snapshot_changed')
            cli_ordinary_previous_failed_v9_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v10'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_summary_budget_history_scope_changed')
            request = dict(request,schema='friday.installed-cli-request.v9',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 42:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            existing = names-newfiles42
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_summary_fit_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in existing)):
                row = saved[str(home/relative)]; backup = base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'], 'cli_runtime_summary_fit_beforeimage_mode_changed')
                raw = read_owned(backup,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'cli_runtime_summary_fit_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_summary_fit_old_intent_snapshot_changed')
            cli_ordinary_previous_failed_v8_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v9'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_summary_fit_history_scope_changed')
            request = dict(request,schema='friday.installed-cli-request.v8',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 41:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            existing = names-newfiles41
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_current12_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in existing)):
                row = saved[str(home/relative)]; backup = base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'], 'cli_runtime_current12_beforeimage_mode_changed')
                raw = read_owned(backup,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'cli_runtime_current12_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_current12_old_intent_snapshot_changed')
            cli_ordinary_previous_failed_v7_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v8'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_current12_history_scope_changed')
            request = dict(request,schema='friday.installed-cli-request.v7',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 40:
            saved = cli_ordinary_failed_v6_json(read_owned(home/'preparation'/folder/'beforeimages.json',private=True))
            existing = names-cli_readonly_schema_new_files()
            expected_saved = {str(home/n) for n in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token)} | {str(home/'hermes-agent'/n) for n in names}
            require(type(saved) is dict and set(saved) == expected_saved, 'cli_runtime_formatter_beforeimages_scope_changed')
            for relative in ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json',prior_token,*('hermes-agent/'+n for n in existing)):
                row = saved[str(home/relative)]; backup = base/relative
                require(type(row) is dict and set(row) == {'path','sha256','bytes','original_mode'}
                        and row['path'] == str(backup) and type(row['bytes']) is type(row['original_mode']) is int
                        and row['bytes'] >= 0 and stat.S_IMODE((home/relative).stat().st_mode) == row['original_mode'], 'cli_runtime_formatter_beforeimage_mode_changed')
                raw = read_owned(backup,private=True)
                require(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'cli_runtime_formatter_beforeimage_changed')
            require(saved[str(home/prior_token)]['sha256'] == r['previous_repair_intent']['sha256'], 'cli_runtime_formatter_old_intent_snapshot_changed')
            cli_ordinary_previous_failed_v6_journey(r,home)
            require(request['schema'] == 'friday.installed-cli-request.v7'
                    and request['ordinary_readonly'] == r['next_ordinary_readonly']
                    and request['partial_proof'] == r['partial_proof'], 'cli_runtime_formatter_history_scope_changed')
            request = dict(request,schema='friday.installed-cli-request.v6',ordinary_readonly=r['ordinary_readonly'])
            head, receipt = previous, before
            continue
        if count == 39:
            cli_ordinary_previous_failed_journey(r,home)
            require(request.get('schema') == 'friday.installed-cli-request.v6'
                    and r['next_ordinary_readonly'].get('schema') == 'friday.cli-ordinary-readonly.v2'
                    and request.get('ordinary_readonly') == r['next_ordinary_readonly']
                    and cli_ordinary_readonly_baseline(r['next_ordinary_readonly']) == r['ordinary_readonly']
                    and request.get('partial_proof') == r['partial_proof'],
                    'cli_runtime_manager_history_scope_changed')
            head, receipt = previous, before
            continue
        if count == 38:
            cli_context_previous_journey(r,home)
            require(request.get('partial_proof') == r['partial_proof']
                    and cli_ordinary_readonly_baseline(request.get('ordinary_readonly')) == r['ordinary_readonly'],
                    'cli_runtime_partial_proof_or_baseline_changed')
            head, receipt = previous, before
            continue
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



CLI_SUMMARY_VISIBLE_MANIFEST = 'patches/hermes/installed-summary-visible-manifest.json'
CLI_SUMMARY_VISIBLE_INTENT = 'FRIDAY-INSTALL.summary-visible-repair.intent.json'


def cli_summary_visible_manifest_scope(manifest):
    """Source45 preserves exact final strategy4 and adds admission plus one explicit hook."""
    import re
    rows = manifest['files']
    if type(rows) is dict:
        rows = [dict(row,path=name) for name,row in rows.items()]
    names = {'agent/bounded_context.py','agent/context_compressor.py','agent/auxiliary_client.py',
             'agent/bounded_summary_output.py','agent/turn_preflight_gate.py',
             'hermes_cli/friday_credential_admission.py'}
    newfiles = {'agent/bounded_summary_output.py'}
    require(type(rows) is list and len(rows) == len(names) and all(type(r) is dict for r in rows)
            and {r['path'] for r in rows} == names, 'cli_summary_visible_manifest_scope_required')
    for row in rows:
        new = row['path'] in newfiles
        require(row['mode'] == '100644' and type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256'])
                and (row['before_sha256'] is None and row.get('new_file') is True if new else
                     type(row['before_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['before_sha256'])
                     and row.get('new_file',False) is False), 'cli_summary_visible_afterimage_required')
    return names,newfiles


def cli_summary_visible_recovery_contract(recovery, binding, *, source=None):
    """Exact source and old closed failure authorize one explicit product manual operation."""
    import hashlib, re
    fields = {'schema','operation','strategy','component_result','proposal','old_failure','full_SQL',
              'raw_SQL_snapshot','session_id','message_ids','ineffective_count','recovery_deadline',
              'job_id','strategy_afterimages'}
    require(type(recovery) is dict and set(recovery) == fields
            and recovery['schema'] == 'friday.visible-summary-manual-recovery.v1'
            and recovery['operation'] == 'compress-force-once' and recovery['strategy'] == 'bounded_visible_json_v1'
            and recovery['session_id'] == binding['id']
            and recovery['message_ids'] == binding['baseline_message_ids'] == list(range(5,31))
            and binding['schema'] == 'friday.cli-ordinary-readonly.v8'
            and recovery['ineffective_count'] == 2 and type(recovery['ineffective_count']) is int
            and recovery['recovery_deadline'] is None
            and recovery['job_id'] == cli_ordinary_job_id(Path(binding['database']).parent,binding),
            'cli_summary_visible_exact_manual_operation_required')
    reader = globals().get('owned_file') or globals().get('read_owned')
    expected = {'component_result':('734dffe347b2b11ee595590e64191672d1a765deb45da315d2b0620296452794',51213),
                'proposal':('e5aa5e3d7b8a124a3d3d278978ae99333300a898ff2868045358c242c6a9c79b',4636),
                'old_failure':('8af36bccd5cea921242d5ba7be9a99e684861694e6c857bcb4132e3d937bda6a',4229),
                'full_SQL':('ed11e5c51b9ce10b7dddfbfa2089bbcf4881a2a1aa0c83d2f8cb6b78cf8e2485',91043),
                'raw_SQL_snapshot':('937a63275a067bff7173525c8d40531fe678b866a1fb54b1e7f2927d666f048d',2004)}
    for key,(sha,size) in expected.items():
        ref = recovery[key]
        require(type(ref) is dict and set(ref) == {'path','sha256','bytes'} and ref['sha256'] == sha
                and ref['bytes'] == size and type(ref['bytes']) is int, 'cli_summary_visible_recovery_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha, 'cli_summary_visible_recovery_pin_changed')
    payload = cli_ordinary_failed_v6_json(reader(Path(recovery['full_SQL']['path']),private=True))
    require(payload['row']['id'] == binding['id'] and payload['row']['compression_ineffective_count'] == 2
            and payload['row']['compression_recovery_deadline'] is None
            and [m['id'] for m in payload['messages']] == list(range(5,31)), 'cli_summary_visible_persisted_stop_changed')
    expected_after = {'agent/context_compressor.py':('172f4ac48d4f72f59a8ff49cc5c2936450e684844cc291aaccb7abb1bad965b0',348719),
                      'agent/bounded_context.py':('d04a60af7d259c5a9af72a25b81be3f2f21db8e2ee9854938c2a6b50dcf0a0c9',51075),
                      'agent/auxiliary_client.py':('b129f096d3f3d2eacd7878bb3a45034961d9be6eb28368099b52227ffe346ac0',437725),
                      'agent/bounded_summary_output.py':('70a786a2b62d365183376a1ca4d4cf141d6af7446b286cc5f222029cdb5d543b',7105)}
    require(recovery['strategy_afterimages'] == {n:{'sha256':s,'bytes':z} for n,(s,z) in expected_after.items()},
            'cli_summary_visible_strategy_afterimages_required')
    if source is not None:
        for name,(sha,size) in expected_after.items():
            raw = reader(Path(source)/name)
            require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha, 'cli_summary_visible_installed_strategy_changed')
    return recovery


def cli_ordinary_previous_failed_v11_journey(request, home):
    """Pin the independently accepted complete stopped V11; never renew its job or clock."""
    import hashlib, math, re
    home = Path(home); reader = globals().get('owned_file') or globals().get('read_owned')
    def load(ref):
        require(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','sha256','bytes'})
                and type(ref['path']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']), 'cli_ordinary_v11_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and ('bytes' not in ref or ref['bytes'] == len(raw)), 'cli_ordinary_v11_pin_changed')
        return cli_ordinary_failed_v6_json(raw)
    require(request['previous_ordinary_independent']['sha256'] ==
            '8af36bccd5cea921242d5ba7be9a99e684861694e6c857bcb4132e3d937bda6a', 'cli_ordinary_v11_root_acceptance_required')
    accepted = load(request['previous_ordinary_independent'])
    for role,key in (('actual_proof','previous_ordinary_qualified'),('custody','previous_ordinary_custody'),
                     ('complete_SQL_rows','previous_ordinary_sql')):
        require(request[key]['path'] == accepted[role]['path'] and request[key]['sha256'] == accepted[role]['sha256'],
                'cli_ordinary_v11_evidence_routing_changed')
    require(request['previous_ordinary_qualified'] == request['previous_ordinary_unchanged'], 'cli_ordinary_v11_one_proof_required')
    require(accepted['state'] == 'ACTUAL_V11_FAILED_SCOPE_AND_PRIOR_DATA_PRESERVATION_ACCEPTED_NO_RETRY'
            and accepted['retry_authorized'] is False and accepted['original180_custody_closed'] is True
            and all(accepted[k] is True for k in ('FailedExecutionObservation_Go','Cleanup_Go','CompletePriorSQLPreservation_Go'))
            and all(accepted[k] is False for k in ('ReadArtifact_Go','GroundedFinalAnswer_Go','Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v11_truth_required')
    for key in ('independent','stable_SQL_snapshot','actual_compression_log_slice','observed_candidate40411_independent_supplement'):
        load(accepted[key])
    proof=load(accepted['actual_proof']); custody=load(accepted['custody']); saved=load(accepted['complete_SQL_rows'])
    prior=load(proof['consumed_native_intent']); old=prior['request']; clock=prior['clock']
    require(prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v11' and old['home'] == request['home'] == str(home)
            and old['unit'] != request['unit'] and old['assignment'] != request['assignment']
            and old['ordinary_readonly'] == request['ordinary_readonly'] and old['repaired_input'] == request['previous_input']
            and old['installation_input'] == request['installation_input'] and old['partial_proof'] == request['partial_proof']
            and old['history'] == request['history'] == prior['history']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'), 'cli_ordinary_v11_old_scope_required')
    require(load(proof['request']) == old and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly'])
            and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly']), 'cli_ordinary_v11_old_semantics_changed')
    prefix='preparation/cli-runtime/';base=prefix+old['unit'];job=prefix+'jobs/'+old['job_id']+'.intent.json'
    inventory=request['previous_ordinary_runtime']
    require(set(inventory) == {base+s for s in ('.intent.json','.json','.stdout','.stderr','.native-owner.json')}|{job},
            'cli_ordinary_v11_inventory_required')
    for name,sha in inventory.items():
        require(hashlib.sha256(reader(home/name,private=True)).hexdigest() == sha, 'cli_ordinary_v11_inventory_changed')
    require(load(proof['consumed_semantic_job']) == {'schema':'friday.cli-ordinary-job-intent.v1','state':'CONSUMED_NO_RETRY',
            'job_id':old['job_id'],'request':old,'clock':clock}
            and not (home/(base+'.result.json')).exists() and not (home/(base+'.result.json')).is_symlink()
            and custody['clock'] == clock and custody['retry_authorized'] is False
            and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is True
            and clock['started_mono'] <= custody['closure_mono'] <= clock['deadline_mono'], 'cli_ordinary_v11_no_replay_required')
    new=request['next_ordinary_readonly'];cli_ordinary_readonly_baseline(new)
    mutable={'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
             'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v8' and new['baseline_message_ids'] == list(range(5,31))
            and new['append_high_water'] == 30 and new['artifact_bytes'] == 915
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in old['ordinary_readonly'].items() if k not in mutable}
            and cli_ordinary_job_id(home,new) != old['job_id'] and cli_ordinary_readonly_argv(home,new) != old['argv'],
            'cli_ordinary_v12_genuine_question_required')
    fingerprint=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable=lambda rows:[{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(saved['complete_actual_SELECT_STAR'] is saved['no_large_payload_elision'] is True
            and [m['id'] for m in saved['messages']] == list(range(5,31))
            and len(saved['other_messages']) == 4 and len(saved['other_sessions']) == 1
            and fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and saved['row']['compression_ineffective_count'] == 2 and saved['row']['compression_recovery_deadline'] is None,
            'cli_ordinary_v11_complete_persisted_stop_required')
    cli_summary_visible_recovery_contract(request['new_strategy_recovery'],new)
    return old

CLI_SUMMARY_COMPLETION_MANIFEST = 'patches/hermes/installed-summary-completion-manifest.json'
CLI_SUMMARY_COMPLETION_INTENT = 'FRIDAY-INSTALL.summary-completion-repair.intent.json'

CLI_SUMMARY_BUDGET_MANIFEST = 'patches/hermes/installed-summary-budget-manifest.json'
CLI_SUMMARY_BUDGET_INTENT = 'FRIDAY-INSTALL.summary-budget-repair.intent.json'

CLI_SUMMARY_FIT_MANIFEST = 'patches/hermes/installed-summary-fit-manifest.json'
CLI_SUMMARY_FIT_INTENT = 'FRIDAY-INSTALL.summary-fit-repair.intent.json'

CLI_CURRENT12_MANIFEST = 'patches/hermes/installed-current12-readonly-fit-manifest.json'
CLI_CURRENT12_INTENT = 'FRIDAY-INSTALL.current12-readonly-fit-repair.intent.json'

CLI_READONLY_SCHEMA_MANIFEST = 'patches/hermes/installed-readonly-schema-formatter-manifest.json'
CLI_READONLY_SCHEMA_INTENT = 'FRIDAY-INSTALL.readonly-schema-formatter-repair.intent.json'

CLI_MANAGER_MANIFEST = 'patches/hermes/installed-native-manager-manifest.json'
CLI_MANAGER_INTENT = 'FRIDAY-INSTALL.native-manager-repair.intent.json'

CLI_CONTEXT_MANIFEST = 'patches/hermes/installed-context-continuation-manifest.json'
CLI_CONTEXT_INTENT = 'FRIDAY-INSTALL.context-continuation-repair.intent.json'
CLI_CONTEXT_NEW_FILE = 'tests/agent/test_post_tool_context_fit.py'
CLI_CONTEXT_NAMES = {'agent/bounded_context.py','agent/context_compressor.py','agent/turn_preflight_gate.py',
                     'hermes_cli/friday_credential_admission.py','hermes_cli/friday_user_scope.py',CLI_CONTEXT_NEW_FILE}

def repair_native_bootstrap(request, request_path, *, clock, session_artifact=False, context_continuation=False, native_manager=False, readonly_schema_formatter=False, current12_readonly_fit=False, summary_fit=False, summary_budget=False, summary_completion=False, summary_visible=False):
    phase = "repair-summary-visible" if summary_visible else "repair-summary-completion" if summary_completion else "repair-summary-budget" if summary_budget else "repair-summary-fit" if summary_fit else "repair-current12-readonly-fit" if current12_readonly_fit else "repair-readonly-schema-formatter" if readonly_schema_formatter else "repair-native-manager" if native_manager else "repair-context-continuation" if context_continuation else "repair-session-artifact" if session_artifact else "repair-native-bootstrap"
    token = CLI_SUMMARY_VISIBLE_INTENT if summary_visible else CLI_SUMMARY_COMPLETION_INTENT if summary_completion else CLI_SUMMARY_BUDGET_INTENT if summary_budget else CLI_SUMMARY_FIT_INTENT if summary_fit else CLI_CURRENT12_INTENT if current12_readonly_fit else CLI_READONLY_SCHEMA_INTENT if readonly_schema_formatter else CLI_MANAGER_INTENT if native_manager else CLI_CONTEXT_INTENT if context_continuation else CLI_SESSION_INTENT if session_artifact else CLI_BOOTSTRAP_INTENT
    prior_token = CLI_SUMMARY_COMPLETION_INTENT if summary_visible else CLI_SUMMARY_BUDGET_INTENT if summary_completion else CLI_SUMMARY_FIT_INTENT if summary_budget else CLI_CURRENT12_INTENT if summary_fit else CLI_READONLY_SCHEMA_INTENT if current12_readonly_fit else CLI_MANAGER_INTENT if readonly_schema_formatter else CLI_CONTEXT_INTENT if native_manager else CLI_SESSION_INTENT if context_continuation else CLI_BOOTSTRAP_INTENT if session_artifact else CLI_FRONTEND_INTENT
    field = "postinstall_summary_visible_repair" if summary_visible else "postinstall_summary_completion_repair" if summary_completion else "postinstall_summary_budget_repair" if summary_budget else "postinstall_summary_fit_repair" if summary_fit else "postinstall_current12_readonly_fit_repair" if current12_readonly_fit else "postinstall_readonly_schema_formatter_repair" if readonly_schema_formatter else "postinstall_native_manager_repair" if native_manager else "postinstall_context_continuation_repair" if context_continuation else "postinstall_session_artifact_repair" if session_artifact else "postinstall_native_bootstrap_repair"
    folder_name = "summary-visible-repair" if summary_visible else "summary-completion-repair" if summary_completion else "summary-budget-repair" if summary_budget else "summary-fit-repair" if summary_fit else "current12-readonly-fit-repair" if current12_readonly_fit else "readonly-schema-formatter-repair" if readonly_schema_formatter else "native-manager-repair" if native_manager else "context-continuation-repair" if context_continuation else "session-artifact-repair" if session_artifact else "native-bootstrap-repair"
    count = 45 if summary_visible else 44 if summary_completion else 43 if summary_budget else 42 if summary_fit else 41 if current12_readonly_fit else 40 if readonly_schema_formatter else 39 if native_manager else 38 if context_continuation else 37 if session_artifact else 36
    schema = "friday.summary-visible-repair" if summary_visible else "friday.summary-completion-repair" if summary_completion else "friday.summary-budget-repair" if summary_budget else "friday.summary-fit-repair" if summary_fit else "friday.current12-readonly-fit-repair" if current12_readonly_fit else "friday.readonly-schema-formatter-repair" if readonly_schema_formatter else "friday.native-manager-repair" if native_manager else "friday.context-continuation-repair" if context_continuation else "friday.session-artifact-repair" if session_artifact else "friday.native-bootstrap-repair"
    require(sum((session_artifact,context_continuation,native_manager,readonly_schema_formatter,current12_readonly_fit,summary_fit,summary_budget,summary_completion,summary_visible)) <= 1, 'cli_repair_single_phase_required')
    fields={'schema','phase','assignment','generation','home','installation_input','previous_input',
            'repaired_input','original_marker','original_receipt','original_stamp','previous_repair_intent',
            'selected_python','native_launchers','history','previous_runtime','unit','invocation_id','previous_journey'}
    require(type(request) is dict and set(request) == fields | ({'new_strategy_recovery'} if summary_visible else set()) | ({'ordinary_readonly','next_ordinary_readonly','partial_proof','previous_ordinary_runtime','previous_ordinary_custody','previous_ordinary_unchanged','previous_ordinary_qualified','previous_ordinary_sql','previous_ordinary_independent'} if (readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) else {'ordinary_readonly','next_ordinary_readonly','partial_proof','previous_ordinary_runtime','previous_ordinary_custody','previous_ordinary_unchanged'} if native_manager else {'ordinary_readonly','partial_proof'} if context_continuation else {'session_artifact'} if session_artifact else set())
            and (not summary_visible or 'new_strategy_recovery' in request)
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
            and (not (session_artifact or context_continuation or native_manager or readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) or 'postinstall_native_bootstrap_repair' in marker)
            and (not (context_continuation or native_manager or readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) or 'postinstall_session_artifact_repair' in marker)
            and (not native_manager or 'postinstall_context_continuation_repair' in marker)
            and (not (readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) or 'postinstall_native_manager_repair' in marker)
            and (not (current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) or 'postinstall_readonly_schema_formatter_repair' in marker)
            and (not (summary_fit or summary_budget or summary_completion or summary_visible) or 'postinstall_current12_readonly_fit_repair' in marker)
            and (not (summary_budget or summary_completion or summary_visible) or 'postinstall_summary_fit_repair' in marker)
            and (not (summary_completion or summary_visible) or 'postinstall_summary_budget_repair' in marker)
            and (not summary_visible or 'postinstall_summary_completion_repair' in marker)
            and 'postinstall_frontend_repair' in marker
            and marker.get('runtime_ready') is False and marker.get('gateway_installed') is False
            and marker.get('native_frontends') == 'PENDING'
            and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
            and value['product']['runtime'] == {'enabled':False}
            and cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
            and cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1'),
            'frontend_previous_pending_history_required')
    budget.call(validated_cli_repair_chain,home,marker,dict(request, schema=('friday.installed-cli-request.v11' if summary_visible else 'friday.installed-cli-request.v10' if summary_completion else 'friday.installed-cli-request.v9' if summary_budget else 'friday.installed-cli-request.v8' if summary_fit else 'friday.installed-cli-request.v7' if current12_readonly_fit else 'friday.installed-cli-request.v6' if readonly_schema_formatter else 'friday.installed-cli-request.v5' if native_manager else 'friday.installed-cli-request.v4' if context_continuation else 'friday.installed-cli-request.v3' if session_artifact else 'friday.installed-cli-request.v2'),repaired_input=request['previous_input']))
    old=read_json(paths['previous_repair_intent'])
    require(old.get('schema') == ('friday.summary-completion-repair-intent.v1' if summary_visible else 'friday.summary-budget-repair-intent.v1' if summary_completion else 'friday.summary-fit-repair-intent.v1' if summary_budget else 'friday.current12-readonly-fit-repair-intent.v1' if summary_fit else 'friday.readonly-schema-formatter-repair-intent.v1' if current12_readonly_fit else 'friday.native-manager-repair-intent.v1' if readonly_schema_formatter else 'friday.context-continuation-repair-intent.v1' if native_manager else 'friday.session-artifact-repair-intent.v1' if context_continuation else 'friday.native-bootstrap-repair-intent.v1' if session_artifact else 'friday.frontend-close-repair-intent.v1')
            and old.get('state') == 'CONSUMED_NO_RETRY'
            and old['request']['repaired_input'] == request['previous_input']
            and old['request']['installation_input'] == request['installation_input']
            and old['request']['selected_python'] == request['selected_python']
            and cli_historical_scope_closed(old['clock'],'friday.installed-cli-clock.v1'), 'frontend_old_repair_consumed_required')
    budget.call(cli_repair_history,request,home)
    budget.call(cli_ordinary_previous_failed_v11_journey,request,home) if summary_visible else budget.call(cli_ordinary_previous_failed_v10_journey,request,home) if summary_completion else budget.call(cli_ordinary_previous_failed_v9_journey,request,home) if summary_budget else budget.call(cli_ordinary_previous_failed_v8_journey,request,home) if summary_fit else budget.call(cli_ordinary_previous_failed_v7_journey,request,home) if current12_readonly_fit else budget.call(cli_ordinary_previous_failed_v6_journey,request,home) if readonly_schema_formatter else budget.call(cli_ordinary_previous_failed_journey,request,home) if native_manager else budget.call(cli_context_previous_journey,request,home) if context_continuation else budget.call(cli_bootstrap_previous_journey,request,home,session_artifact=session_artifact)
    if readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible:
        budget.call(cli_ordinary_readonly_inputs,home,request['next_ordinary_readonly'])
        budget.call(cli_ordinary_readonly_artifact,home,request['next_ordinary_readonly'])
    if native_manager:
        require(request['next_ordinary_readonly'].get('schema') == 'friday.cli-ordinary-readonly.v2'
                and cli_ordinary_readonly_baseline(request['next_ordinary_readonly']) == request['ordinary_readonly']
                and cli_ordinary_job_id(home,request['next_ordinary_readonly']) !=
                    cli_ordinary_job_id(home,request['ordinary_readonly']), 'cli_ordinary_new_question_required')
        budget.call(cli_ordinary_readonly_inputs,home,request['next_ordinary_readonly'])
        budget.call(cli_ordinary_readonly_artifact,home,request['next_ordinary_readonly'])
    if context_continuation or native_manager:
        budget.call(cli_ordinary_readonly_inputs,home,request['ordinary_readonly'])
        budget.call(cli_ordinary_readonly_artifact,home,request['ordinary_readonly'])
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
            and ({slim(l)['manifest']:slim(l) for _,l in layers[:count-1]} ==
                 {r['manifest']:r for r in receipt['layers']} if (readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) else
                 [slim(l) for _,l in layers[:count-1]] == receipt['layers'])
            and layers[-1][1]['manifest'] == (CLI_SUMMARY_VISIBLE_MANIFEST if summary_visible else CLI_SUMMARY_COMPLETION_MANIFEST if summary_completion else CLI_SUMMARY_BUDGET_MANIFEST if summary_budget else CLI_SUMMARY_FIT_MANIFEST if summary_fit else CLI_CURRENT12_MANIFEST if current12_readonly_fit else CLI_READONLY_SCHEMA_MANIFEST if readonly_schema_formatter else CLI_MANAGER_MANIFEST if native_manager else CLI_CONTEXT_MANIFEST if context_continuation else CLI_SESSION_MANIFEST if session_artifact else CLI_BOOTSTRAP_MANIFEST), 'frontend_single_additive_overlay_required')
    layer=layers[-1][1]
    names41,newfiles41 = cli_summary_visible_manifest_scope(layer) if summary_visible else cli_summary_completion_manifest_scope(layer) if summary_completion else cli_summary_budget_manifest_scope(layer) if summary_budget else cli_summary_fit_manifest_scope(layer) if summary_fit else cli_current12_manifest_scope(layer) if current12_readonly_fit else (set(),set())
    names = names41 if current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible else cli_readonly_schema_manifest_names() if readonly_schema_formatter else {'hermes_cli/friday_credential_admission.py'} if native_manager else CLI_CONTEXT_NAMES if context_continuation else {'hermes_cli/friday_credential_admission.py','hermes_cli/friday_user_scope.py'} if session_artifact else {'hermes_cli/friday_credential_admission.py'}
    require(set(layer['files']) == names, 'frontend_exact_scope_required')
    for name,row in layer['files'].items():
        if row.get('new_file'):
            require(((context_continuation and name == CLI_CONTEXT_NEW_FILE) or (readonly_schema_formatter and name in cli_readonly_schema_new_files()) or ((current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible) and name in newfiles41)) and name not in receipt['files'] and row['before_sha256'] is None
                    and row['mode'] == '100644' and not (source/name).exists()
                    and not (source/name).is_symlink(), 'context_new_file_must_be_absent')
        else:
            require(row['mode'] == receipt['files'][name]['mode']
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
        preserved={**paths,**{name:source/name for name in names if not layer['files'][name].get('new_file')}}
        if readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible:
            for name in (newfiles41 if current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible else cli_readonly_schema_new_files()):
                saved[str(source/name)]={'absent':True}
        if context_continuation:
            saved[str(source/CLI_CONTEXT_NEW_FILE)]={'absent':True}
            budget.call(cli_ordinary_readonly_inputs,home,request['ordinary_readonly'])
            budget.call(cli_ordinary_readonly_artifact,home,request['ordinary_readonly'])
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
            if not layer['files'][name].get('new_file'):
                cli_repair_bytes(dest,owned_file(source/name),budget,mode=0o600)
        git(staging,['apply','--check','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        git(staging,['apply','--whitespace=nowarn','-'],SourceBudget(budget.deadline),data=layer['patch'])
        if summary_completion or summary_visible:
            for name,row in layer['files'].items():
                (staging/name).chmod(int(row['mode'],8)&0o777)
        staged_outputs={}
        for name,row in layer['files'].items():
            raw=owned_file(staging/name)
            require(digest(raw) == row['sha256'] and len(raw) == row['bytes'], 'frontend_overlay_output_changed')
            if summary_completion or summary_visible:
                require(stat.S_IMODE((staging/name).stat().st_mode) == int(row['mode'],8)&0o777
                        and (row.get('new_file') or stat.S_IMODE((source/name).stat().st_mode) == saved[str(source/name)]['original_mode']),
                        'frontend_overlay_mode_changed')
            staged_outputs[name]=raw
        updated=json.loads(json.dumps(receipt))
        for name,row in layer['files'].items():
            raw=staged_outputs[name]
            stage='publish_source'
            if row.get('new_file'):
                cli_repair_bytes(source/name,raw,budget,mode=0o644)
            else:
                cli_repair_replace(source/name,raw,row['before_sha256'],budget,
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
        budget.call(cli_ordinary_previous_failed_v11_journey,request,home) if summary_visible else budget.call(cli_ordinary_previous_failed_v10_journey,request,home) if summary_completion else budget.call(cli_ordinary_previous_failed_v9_journey,request,home) if summary_budget else budget.call(cli_ordinary_previous_failed_v8_journey,request,home) if summary_fit else budget.call(cli_ordinary_previous_failed_v7_journey,request,home) if current12_readonly_fit else budget.call(cli_ordinary_previous_failed_v6_journey,request,home) if readonly_schema_formatter else budget.call(cli_ordinary_previous_failed_journey,request,home) if native_manager else budget.call(cli_context_previous_journey,request,home) if context_continuation else budget.call(cli_bootstrap_previous_journey,request,home,session_artifact=session_artifact)
        for path in preserved.values():
            require(digest(owned_file(saved[str(path)]['path'],private=True)) == saved[str(path)]['sha256'],
                    'frontend_custody_changed')
        require(digest(owned_file(home/prior_token,private=True)) == request['previous_repair_intent']['sha256'],
                'frontend_previous_intent_changed')
        budget.call(installed_cli_kernel,request,clock,phase=phase)
        require(read_json(request_path) == request, 'frontend_request_changed')
        if readonly_schema_formatter or current12_readonly_fit or summary_fit or summary_budget or summary_completion or summary_visible:
            budget.call(cli_ordinary_readonly_inputs,home,request['next_ordinary_readonly'])
            budget.call(cli_ordinary_readonly_artifact,home,request['next_ordinary_readonly'])
        if native_manager:
            require(cli_ordinary_readonly_baseline(request['next_ordinary_readonly']) == request['ordinary_readonly'],
                    'cli_ordinary_new_question_required')
            budget.call(cli_ordinary_readonly_inputs,home,request['next_ordinary_readonly'])
            budget.call(cli_ordinary_readonly_artifact,home,request['next_ordinary_readonly'])
        if context_continuation or native_manager:
            budget.call(cli_ordinary_readonly_inputs,home,request['ordinary_readonly'])
            budget.call(cli_ordinary_readonly_artifact,home,request['ordinary_readonly'])
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
        try:publish(home/('FRIDAY-INSTALL.summary-visible-repair.failure.json' if summary_visible else 'FRIDAY-INSTALL.summary-completion-repair.failure.json' if summary_completion else 'FRIDAY-INSTALL.summary-budget-repair.failure.json' if summary_budget else 'FRIDAY-INSTALL.summary-fit-repair.failure.json' if summary_fit else 'FRIDAY-INSTALL.current12-readonly-fit-repair.failure.json' if current12_readonly_fit else 'FRIDAY-INSTALL.readonly-schema-formatter-repair.failure.json' if readonly_schema_formatter else 'FRIDAY-INSTALL.native-manager-repair.failure.json' if native_manager else 'FRIDAY-INSTALL.context-continuation-repair.failure.json' if context_continuation else 'FRIDAY-INSTALL.session-artifact-repair.failure.json' if session_artifact else 'FRIDAY-INSTALL.native-bootstrap-repair.failure.json'),failure)
        except BaseException as secondary:remember_secondary(exc,secondary)
        raise



def cli_readonly_schema_new_files():
    return {'tests/agent/test_bounded_protected_formatter.py','tests/agent/test_ordinary_readonly_schemas.py'}


def cli_readonly_schema_manifest_names():
    return {'agent/agent_init.py','agent/turn_request_assembly.py','agent/bounded_context.py',
            'hermes_cli/friday_credential_admission.py'} | cli_readonly_schema_new_files()


def cli_ordinary_failed_v6_json(raw):
    """History roles choose strict JSON; file suffixes carry no authority."""
    import json, math
    def unique(pairs):
        result = {}
        for key,value in pairs:
            require(key not in result, 'cli_ordinary_v6_duplicate_json_key')
            result[key] = value
        return result
    def finite(text):
        value = float(text)
        require(math.isfinite(value), 'cli_ordinary_v6_nonfinite_json_number')
        return value
    def constant(text):
        require(False, 'cli_ordinary_v6_nonfinite_json_number')
    return json.loads(raw,object_pairs_hook=unique,parse_float=finite,parse_constant=constant)


def cli_current12_manifest_scope(manifest):
    """Final pinned additive41 declares its payload; preparation pins no candidate."""
    import re
    allowed = {'agent/agent_init.py','agent/bounded_context.py','agent/system_prompt.py','agent/turn_context.py',
               'agent/turn_request_assembly.py','hermes_cli/friday_credential_admission.py',
               'tests/agent/test_bounded_protected_formatter.py','tests/agent/test_ordinary_readonly_schemas.py',
               'tests/agent/test_ordinary_readonly_prompt_metadata.py'}
    required = {'agent/bounded_context.py','agent/system_prompt.py','agent/turn_context.py',
                'agent/turn_request_assembly.py','hermes_cli/friday_credential_admission.py',
                'tests/agent/test_ordinary_readonly_prompt_metadata.py'}
    rows = manifest['files']
    if type(rows) is dict:
        rows = [dict(row,path=name) for name,row in rows.items()]
    require(type(rows) is list and rows and all(type(row) is dict for row in rows), 'cli_current12_manifest_rows_required')
    names = {row['path'] for row in rows}
    require(len(names) == len(rows) and required <= names <= allowed, 'cli_current12_manifest_scope_required')
    newfiles = {'tests/agent/test_ordinary_readonly_prompt_metadata.py'}
    for row in rows:
        is_new = row['path'] in newfiles
        require(row['mode'] == '100644' and type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256'])
                and 'before_sha256' in row
                and (row['before_sha256'] is None and row.get('new_file') is True if is_new else
                    type(row['before_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['before_sha256'])
                    and row.get('new_file',False) is False), 'cli_current12_manifest_beforeimage_required')
    return names,newfiles


def cli_summary_completion_manifest_scope(manifest):
    """Source44 replaces the accepted summary-completion budget3 and the synchronized native admission."""
    rows = manifest['files']
    if type(rows) is dict:
        rows = [dict(row,path=name) for name,row in rows.items()]
    names = {'agent/bounded_context.py','agent/context_compressor.py','agent/conversation_compression.py',
             'hermes_cli/friday_credential_admission.py'}
    require(type(rows) is list and len(rows) == 4 and all(type(row) is dict for row in rows)
            and {row['path'] for row in rows} == names, 'cli_summary_completion_manifest_scope_required')
    for row in rows:
        require(row['mode'] == '100644' and type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is type(row['before_sha256']) is str
                and re.fullmatch('[0-9a-f]{64}',row['sha256'])
                and re.fullmatch('[0-9a-f]{64}',row['before_sha256'])
                and row.get('new_file',False) is False, 'cli_summary_completion_existing_afterimage_required')
    return names,set()


def cli_summary_budget_manifest_scope(manifest):
    """Source43 replaces the accepted budget3 and the synchronized native admission."""
    rows = manifest['files']
    if type(rows) is dict:
        rows = [dict(row,path=name) for name,row in rows.items()]
    names = {'agent/bounded_context.py','agent/context_compressor.py','agent/conversation_compression.py',
             'hermes_cli/friday_credential_admission.py'}
    require(type(rows) is list and len(rows) == 4 and all(type(row) is dict for row in rows)
            and {row['path'] for row in rows} == names, 'cli_summary_budget_manifest_scope_required')
    for row in rows:
        require(row['mode'] == '100644' and type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is type(row['before_sha256']) is str
                and re.fullmatch('[0-9a-f]{64}',row['sha256'])
                and re.fullmatch('[0-9a-f]{64}',row['before_sha256'])
                and row.get('new_file',False) is False, 'cli_summary_budget_existing_afterimage_required')
    return names,set()


def cli_ordinary_previous_failed_v10_journey(request, home):
    """Consume no old job: accept only exact reviewed failed V10 custody and a distinct V11."""
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    def readpin(ref, expected=None):
        require(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','sha256','bytes'})
                and type(ref['path']) is str and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
                'cli_ordinary_v10_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and ('bytes' not in ref or type(ref['bytes']) is int and ref['bytes'] == len(raw)),
                'cli_ordinary_v10_history_pin_changed')
        return raw
    def load(ref, expected=None):
        return cli_ordinary_failed_v6_json(readpin(ref,expected))
    def same(ref, expected):
        require(ref['path'] == expected['path'] and ref['sha256'] == expected['sha256'],
                'cli_ordinary_v10_evidence_routing_changed')
        return load(ref)
    require(request['previous_ordinary_independent']['sha256'] ==
            'cb3ddfaaf57085e75f22c3e76148f366c91c8c69d3e2e504f89cc3c91d7bd15d',
            'cli_ordinary_v10_exact_root_acceptance_required')
    proof = load(request['previous_ordinary_qualified'])
    same(proof['custody'],request['previous_ordinary_custody'])
    require(request['previous_ordinary_qualified'] == request['previous_ordinary_unchanged'],
            'cli_ordinary_v10_one_actual_proof_required')
    saved = same(proof['complete_SQL_rows'],request['previous_ordinary_sql'])
    custody = load(request['previous_ordinary_custody'])
    accepted = load(request['previous_ordinary_independent'])
    same(accepted['actual_proof'],request['previous_ordinary_qualified'])
    same(accepted['custody'],request['previous_ordinary_custody'])
    same(accepted['complete_SQL_rows'],request['previous_ordinary_sql'])
    require(accepted['independent']['sha256'] ==
            '65f1a53cd1b331942d428373127dc8c63af400633977069127d0110d1df469b1',
            'cli_ordinary_v10_exact_independent_acceptance_required')
    review = load(accepted['independent'])
    require(accepted['schema'] == 'friday.actual-v10-failed-root-acceptance.v1'
            and accepted['state'] == 'ACTUAL_V10_FAILED_SCOPE_AND_DATA_PRESERVATION_ACCEPTED_NO_RETRY'
            and review['schema'] == 'friday.actual-v10-failure-complete-preservation-independent-review.v1'
            and review['state'] == 'CLOSED_V10_FAILED_EXECUTION_AND_COMPLETE_PRIOR_SQL_PRESERVATION_ACCEPTED_NO_RETRY'
            and all(v[k] is True for v in (accepted,review) for k in
                ('FailedExecutionObservation_Go','Cleanup_Go','CompletePriorSQLPreservation_Go'))
            and all(v[k] is False for v in (accepted,review) for k in
                ('GroundedFinalAnswer_Go','ReadArtifact_Go','retry_authorized'))
            and accepted['namespace_init_exit_verified'] == review['native']['namespace_init_exit'] == 'UNKNOWN'
            and all(v[k] == 'UNKNOWN' for v in (proof,accepted,review['failure']) for k in
                ('model_call_count','main_model_call_count','auxiliary_model_call_count'))
            and all(v[k] is False for v in (proof,accepted,review) for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v10_failed_acceptance_truth_required')
    for ref in review['evidence'].values():
        load(ref)
    same(review['evidence']['root_closed'],request['previous_ordinary_qualified'])
    snapshot = same(accepted['stable_SQL_snapshot'],proof['SQL_snapshot'])
    same(saved['SQL_snapshot'],proof['SQL_snapshot'])
    compression = load(accepted['compression_observation'])
    same(review['evidence']['compression_slice'],accepted['compression_observation'])
    grounded = same(review['evidence']['grounded_input'],proof['actual_grounded_review_input'])
    same(grounded['complete_SQL_rows'],request['previous_ordinary_sql'])
    require(snapshot['state'] == 'NEW_STABLE_OWNED_POST_V10_DB_WAL_SHM_COPY'
            and snapshot['live_SQLite_opened'] is snapshot['retry_authorized'] is False
            and set(snapshot['files']) == set(snapshot['original_raw_pins']) == {'state.db','state.db-wal','state.db-shm'},
            'cli_ordinary_v10_stable_sql_snapshot_required')
    for name,ref in snapshot['files'].items():
        original = snapshot['original_raw_pins'][name]
        require(ref['path'] == str(Path(proof['SQL_snapshot']['path']).parent/'POST-V10-READONLY-SQLITE-SNAPSHOT'/name)
                and original['path'] == str(home/name) and ref['sha256'] == original['sha256']
                and ref['bytes'] == original['bytes']
                and type(ref['bytes']) is int and ref['bytes'] > 0
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
                'cli_ordinary_v10_sql_copy_routing_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256'],
                'cli_ordinary_v10_sql_copy_changed')
    require(proof['state'] == 'REAL_INSTALLED_V10_PARTIAL_OR_FAIL_CUSTODY_CLOSED_NO_RETRY'
            and proof['retry_authorized'] is False and proof['native_result'] is None
            and accepted['native_result'] is None and accepted['read_count'] == 0
            and proof['persisted_exact_full_read_count'] == 0
            and all(proof['checks'][k] is False for k in ('new_final_answer','native_result_present',
                'exact_saved_artifact_full_read','read_file_success','native_exit0','native_namespace_exit_verified',
                'fresh_read_after_distinct_v10_question','fresh_substantive_final_after_full_read'))
            and all(proof['checks'][k] is True for k in ('artifact_unchanged','all_foreign_rows_unchanged',
                'complete_ordered_own_rows','immutable_prior_payload','new_exact_question','only_read_file_calls',
                'only_read_file_tools','tool_calls_linked','persisted_cli_close','original_custody_inside_native180',
                'actual_native_budget_not_rebased','read_only_final_qualification_within30',
                'complete_original20_payload_unchanged','native_no_timeout_reaped'))
            and review['independent_SQL']['exact_full_read_sql_ids'] == []
            and review['independent_SQL']['new_read_or_tool'] is review['independent_SQL']['new_substantive_final'] is False
            and review['independent_SQL']['new_failed_turn_sql_id'] == grounded['final_sql_id'] == 28
            and review['independent_SQL']['own_ids'] == list(range(5,29))
            and grounded['exact_full_read_sql_ids'] == [],
            'cli_ordinary_v10_no_read_final_or_retry_required')
    cause = review['failure']; unknowns = review['unknowns_retained']
    require(cause['logged_request_conservative_estimate'] == 42153 and cause['input_budget'] == 35840
            and cause['finish_reason'] == 'length' and cause['commit_status'] == 'aborted'
            and cause['telemetry_aux_output_reservation'] == 600
            and cause['new_read_and_architecture_answer'] is False
            and all(cause[k] == 'UNKNOWN' for k in ('actual_HTTP_max_tokens',
                'actual_summary_content_and_reasoning_tokens','actual_model_summary_fidelity','FieldSourceTokenizationFit'))
            and unknowns['actual_HTTP_max_tokens'] == unknowns['actual_reasoning_tokens'] ==
                unknowns['actual_summary_content'] == 'NOT_CAPTURED/UNKNOWN'
            and unknowns['actual_model_summary_fidelity'] == unknowns['namespace_init_exit'] == 'UNKNOWN'
            and accepted['actual_HTTP_max_tokens'] == accepted['actual_summary_reasoning_tokens'] == 'NOT_CAPTURED'
            and accepted['summary_fidelity'] == 'NOT_ACCEPTED'
            and compression['schema'] == 'friday.actual-v10-compression-failure-log-slice.v1'
            and compression['state'] == 'REAL_RUNTIME_LOG_OBSERVATION_NOT_REQUEST_CAPTURE_OR_FIDELITY_ACCEPTANCE'
            and compression['retry_authorized'] is False
            and compression['summary_commit'] == 'ABORTED_LENGTH_NO_PARTIAL_SUMMARY_ACCEPTED'
            and compression['actual_HTTP_max_tokens'] == compression['actual_summary_content_and_reasoning_tokens'] == 'NOT_CAPTURED'
            and compression['model_call_counts'] == 'UNKNOWN'
            and compression['telemetry']['commit_status'] == 'aborted'
            and compression['telemetry']['aux_output_reservation'] == 600,
            'cli_ordinary_v10_observed_truncation_not_http_capture_required')
    prior = load(proof['consumed_native_intent']); old = prior['request']; clock = prior['clock']
    require(prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v10'
            and old['home'] == request['home'] == str(home)
            and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',old['unit'])
            and old['unit'] != request['unit'] and old['assignment'] != request['assignment']
            and cli_ordinary_job_id(home,request['next_ordinary_readonly']) != old['job_id']
            and cli_ordinary_readonly_argv(home,request['next_ordinary_readonly']) != old['argv']
            and old['installation_input'] == request['installation_input']
            and old['repaired_input'] == request['previous_input']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and old['history'] == prior['history'] == request['history']
            and old['partial_proof'] == request['partial_proof']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'),
            'cli_ordinary_v10_consumed_closed_scope_required')
    require(load(proof['request']) == old and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly'])
            and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly']),
            'cli_ordinary_v10_consumed_semantics_changed')
    for key in ('installation_input','repaired_input','partial_proof'):
        load(old[key])
    require(set(old['history']) == {'FRIDAY-INSTALL.cli-host.intent.json',
            'FRIDAY-INSTALL.cli-segment.intent.json','FRIDAY-INSTALL.json.original-cli-segment'},
            'cli_ordinary_v10_historical_inventory_required')
    for name,sha in old['history'].items():
        require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha)
                and hashlib.sha256(reader(home/name,private=True)).hexdigest() == sha,
                'cli_ordinary_v10_historical_inventory_changed')
    prefix = 'preparation/cli-runtime/'; base = prefix+old['unit']
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    job = prefix+'jobs/'+old['job_id']+'.intent.json'
    inventory = request['previous_ordinary_runtime']
    require(type(inventory) is dict and set(inventory) == {base+s for s in suffixes}|{job},
            'cli_ordinary_v10_inventory_required')
    for name,sha in inventory.items():
        require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha)
                and hashlib.sha256(reader(home/name,private=True)).hexdigest() == sha,
                'cli_ordinary_v10_inventory_changed')
    for role,name in (('consumed_native_intent',base+'.intent.json'),('native_observation',base+'.json'),
                      ('consumed_semantic_job',job)):
        require(proof[role]['path'] == str(home/name) and proof[role]['sha256'] == inventory[name],
                'cli_ordinary_v10_runtime_routing_changed')
    require(load(proof['consumed_semantic_job']) == {'schema':'friday.cli-ordinary-job-intent.v1',
            'state':'CONSUMED_NO_RETRY','job_id':old['job_id'],'request':old,'clock':clock}
            and not (home/(base+'.result.json')).exists() and not (home/(base+'.result.json')).is_symlink(),
            'cli_ordinary_v10_no_replay_required')
    observed = load(proof['native_observation']); native = load(custody['native_return'])
    for name in ('stdout','stderr'):
        readpin(native[name],Path(proof['request']['path']).parent/('UNIT.'+name))
    owner = cli_ordinary_failed_v6_json(reader(home/(base+'.native-owner.json'),private=True))
    require(type(observed['argv']) is list and len(observed['argv']) == 16+len(old['argv'])
            and observed['argv'][:2] == ['/usr/bin/bwrap','--json-status-fd']
            and observed['argv'][3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',str(home/'hermes-agent/.hermes/bin/hermes')]
            and observed['argv'][16:] == old['argv']
            and owner['boot_id'] == clock['boot_id'] and owner['pid'] == 1 and type(owner['pid']) is int
            and type(owner['starttime_ticks']) is int and owner['starttime_ticks'] >= observed['starttime_ticks']
            and re.fullmatch(r'pid:\[[0-9]+\]',owner['pid_namespace'])
            and all(type(observed[k+'_bytes']) is int
                    and observed[k+'_bytes'] == len(reader(home/(base+'.'+k),private=True))
                    and observed[k+'_sha256'] == inventory[base+'.'+k] for k in ('stdout','stderr')),
            'cli_ordinary_v10_native_observation_changed')
    require(observed['returncode'] == 1 and type(observed['returncode']) is int
            and observed['reaped'] is True and observed['timeout'] is False
            and native['returncode'] == 2 and type(native['returncode']) is int
            and native['unit'] == old['unit'] and native['reaped'] is True and native['timed_out'] is False
            and custody['state'] == 'VERIFIED_OWN_CUSTODY_CLOSED' and custody['clock'] == clock
            and custody['retry_authorized'] is False and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is True
            and custody['unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and type(custody['closure_mono']) in (int,float) and math.isfinite(custody['closure_mono'])
            and clock['started_mono'] <= custody['closure_mono'] <= clock['deadline_mono'],
            'cli_ordinary_v10_custody_changed')
    require(observed['elapsed_seconds'] == review['native']['child_elapsed_seconds'] == 34.873
            and native['elapsed_seconds'] == review['native']['root_elapsed_seconds']
            and native['elapsed_seconds'] == accepted['actual_native_root_elapsed_seconds'] == 37.12460862900116
            and review['custody']['saved_four_births'] == custody['own_births']
            and review['custody']['saved_unit'] == custody['unit']
            and proof['all_qualification_within_original180'] is False
            and 0 <= proof['read_only_final_qualification_seconds'] <= 30
            and review['final_readonly_qualification']['after_same_original180_expired'] is True
            and review['final_readonly_qualification']['seconds'] == proof['read_only_final_qualification_seconds'],
            'cli_ordinary_v10_original_native_clock_truth_required')
    births = custody['own_births']
    require(type(births) is list and len(births) == 4
            and {b['name'] for b in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(type(b['pid']) is type(b['birth_ticks']) is int and b['pid'] > 1
                    and b['birth_ticks'] > 0 and b['same_birth_alive'] is False for b in births),
            'cli_ordinary_v10_births_changed')
    born = {b['name']:b for b in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) == (observed['pid'],observed['starttime_ticks'])
            and prior['physical']['caps'] == CLI_RUNTIME_CAPS and prior['physical']['unit'] == old['unit'],
            'cli_ordinary_v10_birth_binding_changed')
    new = request['next_ordinary_readonly']; oldbinding = old['ordinary_readonly']
    cli_ordinary_readonly_baseline(new)
    mutable = {'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
               'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v7'
            and new['question'] != oldbinding['question'] and new['purpose'] != oldbinding['purpose']
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in oldbinding.items() if k not in mutable}
            and oldbinding['schema'] == 'friday.cli-ordinary-readonly.v6'
            and oldbinding['baseline_message_ids'] == list(range(5,27))
            and new['baseline_message_ids'] == list(range(5,29)) and new['append_high_water'] == 28
            and new['artifact_bytes'] == 915 and cli_ordinary_job_id(home,new) != old['job_id'],
            'cli_ordinary_v11_genuine_new_baseline_required')
    require(saved['complete_actual_SELECT_STAR'] is saved['no_large_payload_elision'] is True
            and [m['id'] for m in saved['messages']] == list(range(5,29))
            and all(type(m[k]) is int and m[k] in (0,1) for m in saved['messages'] for k in ('active','compacted'))
            and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp'])
                    and 0 <= m['timestamp'] <= 4200000000 for m in saved['messages'])
            and saved['row']['end_reason'] == 'cli_close' and type(saved['row']['ended_at']) in (int,float)
            and math.isfinite(saved['row']['ended_at']) and saved['row']['ended_at'] > 0
            and {k:saved['row'][k] for k in new['identity']} == new['identity'],
            'cli_ordinary_v10_complete_sql_required')
    fingerprint = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:22])) == oldbinding['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:4])) == new['stable_messages_sha256']
            and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in saved['messages'][:4]]) == new['initial_lifecycle_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256']
            and max(m['id'] for m in saved['messages']+saved['other_messages']) == 28,
            'cli_ordinary_v10_saved_payload_changed')
    earlier = load(review['evidence']['v9_baseline'])
    require(saved['messages'][:22] == earlier['messages']
            and saved['other_messages'] == earlier['other_messages']
            and saved['other_sessions'] == earlier['other_sessions']
            and len(saved['other_messages']) == 4 and len(saved['other_sessions']) == 1
            and review['independent_SQL']['prior22_fullcolumns_exactly_preserved'] is True
            and review['independent_SQL']['foreign_allcolumns_exactly_preserved'] is True,
            'cli_ordinary_v10_complete_prior_payload_changed')
    tail = saved['messages'][-2:]
    require([m['id'] for m in tail] == [27,28] and [m['role'] for m in tail] == ['user','assistant']
            and tail[0]['content'] == old['argv'][-1]
            and tail[1]['content'] == 'Your request was not processed. Send it again if you still want me to carry it out.'
            and tail[1]['display_kind'] == 'failed_turn'
            and all(m['tool_calls'] is m['tool_name'] is m['tool_call_id'] is None for m in tail)
            and cli_ordinary_failed_v6_json(tail[1]['display_metadata'])['error'] ==
                'bounded_context: conservative byte estimate 42153 exceeds input budget 35840; tokenizer fit is unverified',
            'cli_ordinary_v10_saved_transport_placeholder_required')
    artifact = reader(Path(new['output']),private=True)
    require(len(artifact) == new['artifact_bytes'] == 915
            and hashlib.sha256(artifact).hexdigest() == new['artifact_sha256']
            and review['independent_SQL']['artifact'] == {'path':new['output'],'bytes':915,'sha256':new['artifact_sha256']}
            and review['independent_SQL']['BLOBs_complete'] is True,
            'cli_ordinary_v10_saved_artifact_and_blob_changed')
    return old


def cli_ordinary_previous_failed_v9_journey(request, home):
    """Consume no old job: accept only exact reviewed failed V9 custody and a distinct V10."""
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    def load(ref, expected=None):
        require(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','sha256','bytes'})
                and type(ref['path']) is str and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
                'cli_ordinary_v9_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and ('bytes' not in ref or type(ref['bytes']) is int and ref['bytes'] == len(raw)),
                'cli_ordinary_v9_history_pin_changed')
        return cli_ordinary_failed_v6_json(raw)
    def same(ref, expected):
        require(ref['path'] == expected['path'] and ref['sha256'] == expected['sha256'],
                'cli_ordinary_v9_evidence_routing_changed')
        return load(ref)
    require(request['previous_ordinary_independent']['sha256'] ==
            'cdcb84c3dce0a1a8cf7ab5cda32777496a00345c13268345e18bf1b295ab4bf9',
            'cli_ordinary_v9_exact_root_acceptance_required')
    proof = load(request['previous_ordinary_qualified'])
    same(proof['custody'],request['previous_ordinary_custody'])
    require(request['previous_ordinary_qualified'] == request['previous_ordinary_unchanged'],
            'cli_ordinary_v9_one_actual_proof_required')
    saved = same(proof['complete_SQL_rows'],request['previous_ordinary_sql'])
    custody = load(request['previous_ordinary_custody'])
    accepted = load(request['previous_ordinary_independent'])
    same(accepted['actual_proof'],request['previous_ordinary_qualified'])
    same(accepted['custody'],request['previous_ordinary_custody'])
    same(accepted['complete_SQL_rows'],request['previous_ordinary_sql'])
    review = load(accepted['independent'])
    require(accepted['schema'] == 'friday.actual-v9-failed-root-acceptance.v1'
            and accepted['state'] == 'ACTUAL_V9_FAILED_SCOPE_AND_DATA_PRESERVATION_ACCEPTED_NO_RETRY'
            and review['schema'] == 'friday.actual-v9-failed-execution-independent-acceptance.v1'
            and review['state'] == 'ACTUAL_V9_FAILED_EXECUTION_CUSTODY_AND_COMPLETE_PRIOR_SQL_PRESERVATION_ACCEPTED_CONSUMED_NO_RETRY'
            and all(v[k] is True for v in (accepted,review) for k in
                ('FailedExecutionObservation_Go','Cleanup_Go','CompletePriorSQLPreservation_Go'))
            and accepted['GroundedFinalAnswer_Go'] is accepted['ReadArtifact_Go'] is False
            and accepted['retry_authorized'] is review['retry_authorized'] is False
            and accepted['model_call_count'] == accepted['namespace_init_exit_verified'] == 'UNKNOWN'
            and review['actual_native']['native_namespace_init_exit_verified'] == 'UNKNOWN'
            and all(v[k] is False for v in (proof,accepted,review) for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v9_failed_acceptance_truth_required')
    for role,leaf in (('request','REQUEST.json'),('custody','ROOT-REAL-V9-IMMEDIATE-CUSTODY-WITNESS.json'),
                      ('complete_SQL_rows','POST-REAL-READONLY-SESSION-ROWS.json'),
                      ('SQL_snapshot','POST-V9-STABLE-SQLITE-COPY.json')):
        same(review['pins'][leaf],proof[role])
    same(review['pins']['ROOT-REAL-V9-READONLY-NEW-QUESTION-CUSTODY-CLOSED.json'],request['previous_ordinary_qualified'])
    for role,name in (('consumed_native_intent','consumed_intent'),('native_observation','observation')):
        same(review['native_pins'][name],proof[role])
    snapshot = same(accepted['stable_SQL_snapshot'],proof['SQL_snapshot'])
    same(saved['SQL_snapshot'],proof['SQL_snapshot'])
    require(proof['state'] == 'REAL_INSTALLED_V9_PARTIAL_OR_FAIL_CUSTODY_CLOSED_NO_RETRY'
            and proof['retry_authorized'] is False and proof['native_result'] is None
            and proof['persisted_exact_full_read_count'] == 0
            and all(proof['checks'][k] is False for k in ('new_final_answer','native_result_present',
                'exact_saved_artifact_full_read','read_file_success','native_exit0','native_namespace_exit_verified'))
            and all(proof['checks'][k] is True for k in ('artifact_unchanged','all_foreign_rows_unchanged',
                'complete_ordered_own_rows','immutable_prior_payload','new_exact_question','only_read_file_calls',
                'only_read_file_tools','tool_calls_linked','persisted_cli_close','original_custody_inside_native180',
                'actual_native_budget_not_rebased','read_only_final_qualification_within30'))
            and proof['model_call_count'] == proof['main_model_call_count'] == proof['auxiliary_model_call_count'] == 'UNKNOWN'
            and review['actual_grounding'] == {'grounded_final_present':False,
                'independent_grounded_answer_acceptance':'NOT_APPLICABLE_NO_SUBSTANTIVE_ANSWER',
                'native_result_present':False,'new_read_file_called':False,'new_read_file_success':False,
                'persisted_exact_full_read_count':0,'placeholder_sql_id':26},
            'cli_ordinary_v9_no_read_final_or_retry_required')
    cause = review['cause_and_next_direct_check']
    require(cause['auxiliary_summary_precommit_wire_bytes'] == 43437
            and cause['original_input_budget'] == 35840 and cause['fallback_existing_request_bytes'] == 41314
            and cause['auxiliary_refused_before_commit'] is cause['saved_conversation_rows_unchanged'] is True
            and all(cause[k] == 'UNKNOWN' for k in ('model_call_count','main_model_call_count','auxiliary_model_call_count',
                'actual_model_summary_fidelity','FieldSourceTokenizationFit')),
            'cli_ordinary_v9_proposed_wire_not_measured_http_required')
    prior = load(proof['consumed_native_intent']); old = prior['request']; clock = prior['clock']
    require(prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v9'
            and old['home'] == request['home'] == str(home)
            and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',old['unit'])
            and old['unit'] != request['unit'] and old['assignment'] != request['assignment']
            and old['installation_input'] == request['installation_input']
            and old['repaired_input'] == request['previous_input']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and old['history'] == prior['history'] == request['history']
            and old['partial_proof'] == request['partial_proof']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'),
            'cli_ordinary_v9_consumed_closed_scope_required')
    require(load(proof['request']) == old and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly'])
            and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly']),
            'cli_ordinary_v9_consumed_semantics_changed')
    prefix = 'preparation/cli-runtime/'; base = prefix+old['unit']
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    job = prefix+'jobs/'+old['job_id']+'.intent.json'
    inventory = request['previous_ordinary_runtime']
    require(type(inventory) is dict and set(inventory) == {base+s for s in suffixes}|{job},
            'cli_ordinary_v9_inventory_required')
    for name,sha in inventory.items():
        require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha)
                and hashlib.sha256(reader(home/name,private=True)).hexdigest() == sha,
                'cli_ordinary_v9_inventory_changed')
    for role,name in (('consumed_native_intent',base+'.intent.json'),('native_observation',base+'.json'),
                      ('consumed_semantic_job',job)):
        require(proof[role]['path'] == str(home/name) and proof[role]['sha256'] == inventory[name],
                'cli_ordinary_v9_runtime_routing_changed')
    require(load(proof['consumed_semantic_job']) == {'schema':'friday.cli-ordinary-job-intent.v1',
            'state':'CONSUMED_NO_RETRY','job_id':old['job_id'],'request':old,'clock':clock}
            and not (home/(base+'.result.json')).exists() and not (home/(base+'.result.json')).is_symlink(),
            'cli_ordinary_v9_no_replay_required')
    observed = load(proof['native_observation']); native = load(custody['native_return'])
    owner = cli_ordinary_failed_v6_json(reader(home/(base+'.native-owner.json'),private=True))
    require(type(observed['argv']) is list and len(observed['argv']) == 16+len(old['argv'])
            and observed['argv'][:2] == ['/usr/bin/bwrap','--json-status-fd']
            and observed['argv'][3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',str(home/'hermes-agent/.hermes/bin/hermes')]
            and observed['argv'][16:] == old['argv']
            and owner['boot_id'] == clock['boot_id'] and owner['pid'] == 1 and type(owner['pid']) is int
            and type(owner['starttime_ticks']) is int and owner['starttime_ticks'] >= observed['starttime_ticks']
            and re.fullmatch(r'pid:\[[0-9]+\]',owner['pid_namespace'])
            and all(type(observed[k+'_bytes']) is int
                    and observed[k+'_bytes'] == len(reader(home/(base+'.'+k),private=True))
                    and observed[k+'_sha256'] == inventory[base+'.'+k] for k in ('stdout','stderr')),
            'cli_ordinary_v9_native_observation_changed')
    require(observed['returncode'] == 1 and type(observed['returncode']) is int
            and observed['reaped'] is True and observed['timeout'] is False
            and native['returncode'] == 2 and type(native['returncode']) is int
            and native['unit'] == old['unit'] and native['reaped'] is True and native['timed_out'] is False
            and custody['state'] == 'VERIFIED_OWN_CUSTODY_CLOSED' and custody['clock'] == clock
            and custody['retry_authorized'] is False and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is True
            and custody['unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and type(custody['closure_mono']) in (int,float) and math.isfinite(custody['closure_mono'])
            and clock['started_mono'] <= custody['closure_mono'] <= clock['deadline_mono'],
            'cli_ordinary_v9_custody_changed')
    require(observed['elapsed_seconds'] == review['actual_native']['child_elapsed_seconds'] == 63.242
            and native['elapsed_seconds'] == review['actual_native']['caller_elapsed_seconds']
            and 65.402 <= native['elapsed_seconds'] < 65.403
            and review['actual_native']['original_clock'] == clock
            and review['actual_native']['own_four_births'] == custody['own_births']
            and review['actual_native']['unit'] == custody['unit']
            and proof['all_qualification_within_original180'] is False
            and 0 <= proof['read_only_final_qualification_seconds'] <= 30
            and review['qualification_timing']['same_original180_not_renewed'] is True
            and review['qualification_timing']['read_only_final_seconds'] == proof['read_only_final_qualification_seconds'],
            'cli_ordinary_v9_original_native_clock_truth_required')
    births = custody['own_births']
    require(type(births) is list and len(births) == 4
            and {b['name'] for b in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(type(b['pid']) is type(b['birth_ticks']) is int and b['pid'] > 1
                    and b['birth_ticks'] > 0 and b['same_birth_alive'] is False for b in births),
            'cli_ordinary_v9_births_changed')
    born = {b['name']:b for b in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) == (observed['pid'],observed['starttime_ticks'])
            and prior['physical']['caps'] == CLI_RUNTIME_CAPS and prior['physical']['unit'] == old['unit'],
            'cli_ordinary_v9_birth_binding_changed')
    new = request['next_ordinary_readonly']; oldbinding = old['ordinary_readonly']
    cli_ordinary_readonly_baseline(new)
    mutable = {'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
               'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v6'
            and new['question'] != oldbinding['question'] and new['purpose'] != oldbinding['purpose']
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in oldbinding.items() if k not in mutable}
            and oldbinding['baseline_message_ids'] == list(range(5,25))
            and new['baseline_message_ids'] == list(range(5,27)) and new['append_high_water'] == 26
            and new['artifact_bytes'] == 915 and cli_ordinary_job_id(home,new) != old['job_id'],
            'cli_ordinary_v10_genuine_new_baseline_required')
    require(saved['complete_actual_SELECT_STAR'] is saved['no_large_payload_elision'] is True
            and [m['id'] for m in saved['messages']] == list(range(5,27))
            and all(type(m[k]) is int and m[k] in (0,1) for m in saved['messages'] for k in ('active','compacted'))
            and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp'])
                    and 0 <= m['timestamp'] <= 4200000000 for m in saved['messages'])
            and saved['row']['end_reason'] == 'cli_close' and type(saved['row']['ended_at']) in (int,float)
            and math.isfinite(saved['row']['ended_at']) and saved['row']['ended_at'] > 0
            and {k:saved['row'][k] for k in new['identity']} == new['identity'],
            'cli_ordinary_v9_complete_sql_required')
    fingerprint = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:20])) == oldbinding['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:4])) == new['stable_messages_sha256']
            and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in saved['messages'][:4]]) == new['initial_lifecycle_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256']
            and max(m['id'] for m in saved['messages']+saved['other_messages']) == 26,
            'cli_ordinary_v9_saved_payload_changed')
    tail = saved['messages'][-2:]
    require([m['id'] for m in tail] == [25,26] and [m['role'] for m in tail] == ['user','assistant']
            and tail[0]['content'] == old['argv'][-1]
            and tail[1]['content'] == 'Your request was not processed. Send it again if you still want me to carry it out.'
            and tail[1]['display_kind'] == 'failed_turn'
            and all(m['tool_calls'] is m['tool_name'] is m['tool_call_id'] is None for m in tail)
            and cli_ordinary_failed_v6_json(tail[1]['display_metadata'])['error'] ==
                'bounded_context: conservative byte estimate 41314 exceeds input budget 35840; tokenizer fit is unverified',
            'cli_ordinary_v9_saved_transport_placeholder_required')
    artifact = reader(Path(new['output']),private=True)
    require(len(artifact) == new['artifact_bytes'] == 915
            and hashlib.sha256(artifact).hexdigest() == new['artifact_sha256']
            and review['complete_SQL']['artifact'] == {'path':new['output'],'bytes':915,'sha256':new['artifact_sha256']}
            and review['complete_SQL']['all_SQL_payload_and_BLOB_unchanged'] is True,
            'cli_ordinary_v9_saved_artifact_and_blob_changed')
    return old

def cli_summary_fit_manifest_scope(manifest):
    """Additive42 afterimages are supplied only after native source acceptance."""
    required = {'agent/bounded_context.py','agent/context_compressor.py',
                'agent/conversation_loop.py','agent/auxiliary_client.py',
                'agent/conversation_compression.py','agent/turn_api_request.py',
                'agent/turn_request_assembly.py','hermes_cli/friday_credential_admission.py',
                'hermes_cli/friday_dashboard_owner.py'}
    tests = {'tests/agent/test_summary_fit_precommit.py'}
    rows = manifest['files']
    if type(rows) is dict:
        rows = [dict(row,path=name) for name,row in rows.items()]
    require(type(rows) is list and rows and all(type(row) is dict for row in rows),
            'cli_summary_fit_manifest_rows_required')
    names = {row['path'] for row in rows}
    require(len(names) == len(rows) and required <= names <= required|tests,
            'cli_summary_fit_manifest_scope_required')
    newfiles = names & tests
    for row in rows:
        require(row['mode'] == '100644' and type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256'])
                and 'before_sha256' in row
                and (row['before_sha256'] is None and row.get('new_file') is True if row['path'] in newfiles else
                    type(row['before_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['before_sha256'])
                    and row.get('new_file',False) is False), 'cli_summary_fit_manifest_beforeimage_required')
    return names,newfiles


def cli_ordinary_previous_failed_v8_journey(request, home):
    """Consume no old job: accept only witnessed V8 partial custody and a new V9."""
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    def load(ref, expected=None):
        require(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','sha256','bytes'})
                and type(ref['path']) is str and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
                'cli_ordinary_v8_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and ('bytes' not in ref or type(ref['bytes']) is int and ref['bytes'] == len(raw)),
                'cli_ordinary_v8_history_pin_changed')
        return cli_ordinary_failed_v6_json(raw)
    def same(ref, expected):
        require(ref['path'] == expected['path'] and ref['sha256'] == expected['sha256'],
                'cli_ordinary_v8_evidence_routing_changed')
        return load(ref)
    proof = load(request['previous_ordinary_qualified'])
    same(proof['custody'],request['previous_ordinary_custody'])
    require(request['previous_ordinary_qualified'] == request['previous_ordinary_unchanged'],
            'cli_ordinary_v8_one_actual_proof_required')
    saved = same(proof['complete_SQL_rows'],request['previous_ordinary_sql'])
    custody = load(request['previous_ordinary_custody'])
    accepted = load(request['previous_ordinary_independent'])
    same(accepted['actual_proof'],request['previous_ordinary_qualified'])
    review = load(accepted['review'])
    require(accepted['schema'] == 'friday.actual-v8-partial-root-acceptance.v1'
            and accepted['PartialRead_Go'] is accepted['Cleanup_Go'] is True
            and accepted['GroundedFinalAnswer_Go'] is False
            and accepted['model_call_count'] == accepted['namespace_init_exit_verified'] == 'UNKNOWN'
            and review['schema'] == 'friday.v8-actual-partial-independent-review.v1'
            and review['state'] == 'EXACT_ACTUAL_V8_READ_AND_CUSTODY_PARTIAL_ACCEPTED_NO_FINAL_NO_RETRY'
            and review['PartialRead_Go'] is review['Cleanup_Go'] is True
            and review['GroundedFinalAnswer_Go'] is review['retry_authorized'] is False
            and all(v[k] is False for v in (proof,accepted,review) for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v8_partial_acceptance_truth_required')
    for role in ('request','custody','complete_SQL_rows','consumed_native_intent',
                 'consumed_semantic_job','native_observation'):
        same({k:review['pins'][role][k] for k in ('path','sha256','bytes')},proof[role])
    require(proof['state'] == 'REAL_INSTALLED_V8_PARTIAL_OR_FAIL_CUSTODY_CLOSED_NO_RETRY'
            and proof['retry_authorized'] is False and proof['native_result'] is None
            and proof['checks']['new_final_answer'] is proof['checks']['native_result_present'] is False
            and all(proof['checks'][k] is True for k in ('artifact_unchanged','all_foreign_rows_unchanged',
                'complete_ordered_own_rows','immutable_prior_payload','new_exact_question','only_read_file_calls',
                'only_read_file_tools','read_file_success','tool_calls_linked','persisted_cli_close')),
            'cli_ordinary_v8_no_final_or_retry_required')
    prior = load(proof['consumed_native_intent']); old = prior['request']; clock = prior['clock']
    require(prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v8'
            and old['home'] == request['home'] == str(home)
            and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',old['unit'])
            and old['unit'] != request['unit'] and old['assignment'] != request['assignment']
            and old['installation_input'] == request['installation_input']
            and old['repaired_input'] == request['previous_input']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and old['history'] == prior['history'] == request['history']
            and old['partial_proof'] == request['partial_proof']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'),
            'cli_ordinary_v8_consumed_closed_scope_required')
    require(load(proof['request']) == old and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly'])
            and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly']),
            'cli_ordinary_v8_consumed_semantics_changed')
    prefix = 'preparation/cli-runtime/'; base = prefix+old['unit']
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    job = prefix+'jobs/'+old['job_id']+'.intent.json'
    inventory = request['previous_ordinary_runtime']
    require(type(inventory) is dict and set(inventory) == {base+s for s in suffixes}|{job},
            'cli_ordinary_v8_inventory_required')
    for name,sha in inventory.items():
        require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha)
                and hashlib.sha256(reader(home/name,private=True)).hexdigest() == sha,
                'cli_ordinary_v8_inventory_changed')
    for role,name in (('consumed_native_intent',base+'.intent.json'),('native_observation',base+'.json'),
                      ('consumed_semantic_job',job)):
        require(proof[role]['path'] == str(home/name) and proof[role]['sha256'] == inventory[name],
                'cli_ordinary_v8_runtime_routing_changed')
    require(load(proof['consumed_semantic_job']) == {'schema':'friday.cli-ordinary-job-intent.v1',
            'state':'CONSUMED_NO_RETRY','job_id':old['job_id'],'request':old,'clock':clock}
            and not (home/(base+'.result.json')).exists() and not (home/(base+'.result.json')).is_symlink(),
            'cli_ordinary_v8_no_replay_required')
    observed = load(proof['native_observation']); native = load(custody['native_return'])
    owner = cli_ordinary_failed_v6_json(reader(home/(base+'.native-owner.json'),private=True))
    require(type(observed['argv']) is list and len(observed['argv']) == 16+len(old['argv'])
            and observed['argv'][:2] == ['/usr/bin/bwrap','--json-status-fd']
            and observed['argv'][3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',str(home/'hermes-agent/.hermes/bin/hermes')]
            and observed['argv'][16:] == old['argv']
            and owner['boot_id'] == clock['boot_id'] and owner['pid'] == 1 and type(owner['pid']) is int
            and type(owner['starttime_ticks']) is int and owner['starttime_ticks'] >= observed['starttime_ticks']
            and re.fullmatch(r'pid:\[[0-9]+\]',owner['pid_namespace'])
            and all(type(observed[k+'_bytes']) is int
                    and observed[k+'_bytes'] == len(reader(home/(base+'.'+k),private=True))
                    and observed[k+'_sha256'] == inventory[base+'.'+k] for k in ('stdout','stderr')),
            'cli_ordinary_v8_native_observation_changed')
    require(observed['returncode'] == 1 and type(observed['returncode']) is int
            and observed['reaped'] is True and observed['timeout'] is False
            and native['returncode'] == 2 and type(native['returncode']) is int
            and native['unit'] == old['unit'] and native['reaped'] is True and native['timed_out'] is False
            and custody['state'] == 'VERIFIED_OWN_CUSTODY_CLOSED' and custody['clock'] == clock
            and custody['retry_authorized'] is False and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is True
            and custody['unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and type(custody['closure_mono']) in (int,float) and math.isfinite(custody['closure_mono'])
            and clock['started_mono'] <= custody['closure_mono'] <= clock['deadline_mono'],
            'cli_ordinary_v8_custody_changed')
    births = custody['own_births']
    require(type(births) is list and len(births) == 4
            and {b['name'] for b in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(type(b['pid']) is type(b['birth_ticks']) is int and b['pid'] > 1
                    and b['birth_ticks'] > 0 and b['same_birth_alive'] is False for b in births),
            'cli_ordinary_v8_births_changed')
    born = {b['name']:b for b in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) == (observed['pid'],observed['starttime_ticks'])
            and prior['physical']['caps'] == CLI_RUNTIME_CAPS and prior['physical']['unit'] == old['unit'],
            'cli_ordinary_v8_birth_binding_changed')
    new = request['next_ordinary_readonly']; oldbinding = old['ordinary_readonly']
    cli_ordinary_readonly_baseline(new)
    mutable = {'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
               'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v5'
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in oldbinding.items() if k not in mutable}
            and oldbinding['baseline_message_ids'] == list(range(5,17))
            and new['baseline_message_ids'] == list(range(5,25)) and new['append_high_water'] == 24
            and new['artifact_bytes'] == 915 and cli_ordinary_job_id(home,new) != old['job_id'],
            'cli_ordinary_v9_genuine_new_baseline_required')
    require(saved['complete_actual_SELECT_STAR'] is saved['no_large_payload_elision'] is True
            and [m['id'] for m in saved['messages']] == list(range(5,25))
            and all(type(m[k]) is int and m[k] in (0,1) for m in saved['messages'] for k in ('active','compacted'))
            and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp'])
                    and 0 <= m['timestamp'] <= 4200000000 for m in saved['messages'])
            and saved['row']['end_reason'] == 'cli_close' and type(saved['row']['ended_at']) in (int,float)
            and math.isfinite(saved['row']['ended_at']) and saved['row']['ended_at'] > 0
            and {k:saved['row'][k] for k in new['identity']} == new['identity'],
            'cli_ordinary_v8_complete_sql_required')
    fingerprint = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:12])) == oldbinding['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:4])) == new['stable_messages_sha256']
            and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in saved['messages'][:4]]) == new['initial_lifecycle_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256']
            and max(m['id'] for m in saved['messages']+saved['other_messages']) == 24,
            'cli_ordinary_v8_saved_payload_changed')
    tail = saved['messages'][-3:]
    require([m['role'] for m in tail] == ['user','assistant','tool'] and tail[0]['content'] == old['argv'][-1]
            and tail[1]['content'] == '' and tail[2]['tool_name'] == 'read_file', 'cli_ordinary_v8_saved_tail_changed')
    calls = cli_ordinary_failed_v6_json(tail[1]['tool_calls'])
    require(type(calls) is list and len(calls) == 1 and calls[0]['type'] == 'function'
            and calls[0]['function']['name'] == 'read_file'
            and cli_ordinary_failed_v6_json(calls[0]['function']['arguments']) == {'path':new['output']}
            and tail[2]['tool_call_id'] == calls[0]['id'], 'cli_ordinary_v8_saved_tool_binding_changed')
    artifact = reader(Path(new['output']),private=True); tool = cli_ordinary_failed_v6_json(tail[2]['content'])
    require(len(artifact) == new['artifact_bytes'] and hashlib.sha256(artifact).hexdigest() == new['artifact_sha256']
            and tool['success'] is tool['readonly'] is True and tool['path'] == new['output']
            and tool['content'] == artifact.decode('utf-8').rstrip('\n'), 'cli_ordinary_v8_saved_artifact_changed')
    return old


def cli_ordinary_previous_failed_v7_journey(request, home):
    """A partial consumed V7 is history; only a distinct pinned V8 may follow."""
    import hashlib, json, math, re
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    if reader is None:
        from hermes_cli.friday_dashboard_owner import read_owned as reader
    def pin(ref, expected=None, *, role='json', sized=False):
        require(type(ref) is dict and set(ref) == ({'path','sha256','bytes'} if sized else {'path','sha256'})
                and type(ref['path']) is str and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256'])
                and role in ('json','stdout','stderr')
                and (role == 'json' or expected is not None and str(expected).endswith('.'+role)),
                'cli_ordinary_v7_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and (not sized or type(ref['bytes']) is int and ref['bytes'] == len(raw)
                     and (ref['bytes'] >= 0 if role in ('stdout','stderr') else ref['bytes'] > 0)),
                'cli_ordinary_v7_history_pin_changed')
        return cli_ordinary_failed_v6_json(raw) if role == 'json' else raw
    def sized(ref, path, sha, length):
        require(type(ref) is dict and set(ref) == {'path','sha256','bytes'}
                and type(ref['bytes']) is int and ref == {'path':str(path),'sha256':sha,'bytes':length},
                'cli_ordinary_v7_witness_ref_changed')
    inventory = request['previous_ordinary_runtime']; prefix = 'preparation/cli-runtime/'
    require(type(inventory) is dict and len(inventory) == 6, 'cli_ordinary_v7_inventory_required')
    candidates = [name[len(prefix):-len('.intent.json')] for name in inventory
                  if type(name) is str and name.startswith(prefix) and '/' not in name[len(prefix):]
                  and name.endswith('.service.intent.json')]
    require(len(candidates) == 1 and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',candidates[0]),
            'cli_ordinary_v7_unit_required')
    unit = candidates[0]; base = prefix+unit
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    blobs = {}
    for suffix in suffixes:
        require(base+suffix in inventory, 'cli_ordinary_v7_inventory_required')
        role = 'stdout' if suffix == '.stdout' else 'stderr' if suffix == '.stderr' else 'json'
        blobs[suffix] = pin({'path':str(home/(base+suffix)),'sha256':inventory[base+suffix]},home/(base+suffix),role=role)
    prior = blobs['.intent.json']; old = prior['request']; clock = prior['clock']
    require(type(prior) is dict and set(prior) == {'schema','state','request','clock','physical','history'}
            and prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v7' and old['home'] == request['home'] == str(home)
            and old['unit'] == unit != request['unit'] and old['assignment'] != request['assignment']
            and old['repaired_input'] == request['previous_input'] and old['installation_input'] == request['installation_input']
            and old['history'] == prior['history'] == request['history'] and old['partial_proof'] == request['partial_proof']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'), 'cli_ordinary_v7_closed_scope_required')
    require(type(old['job_id']) is str and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly'])
            and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly']), 'cli_ordinary_v7_consumed_semantics_changed')
    job = prefix+'jobs/'+old['job_id']+'.intent.json'
    require(set(inventory) == {base+s for s in suffixes}|{job}, 'cli_ordinary_v7_inventory_required')
    job_value = pin({'path':str(home/job),'sha256':inventory[job]},home/job)
    require(job_value == {'schema':'friday.cli-ordinary-job-intent.v1','state':'CONSUMED_NO_RETRY',
            'job_id':old['job_id'],'request':old,'clock':clock}, 'cli_ordinary_v7_job_changed')
    result = home/(base+'.result.json')
    require(not result.exists() and not result.is_symlink(), 'cli_ordinary_v7_result_must_remain_absent')
    observed = blobs['.json']; argv = observed['argv']
    require(type(argv) is list and all(type(a) is str for a in argv)
            and len(argv) == 16+len(old['argv']) and argv[:2] == ['/usr/bin/bwrap','--json-status-fd']
            and re.fullmatch('[1-9][0-9]{0,9}',argv[2]) and 3 <= int(argv[2]) <= 2147483647
            and argv[3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',str(home/'hermes-agent/.hermes/bin/hermes')]
            and argv[16:] == old['argv'] and type(observed['returncode']) is int and observed['returncode'] == 1
            and observed['reaped'] is True and observed['timeout'] is False and observed['reason'] == 'command_nonzero_exit'
            and type(observed['elapsed_seconds']) in (int,float) and math.isfinite(observed['elapsed_seconds'])
            and observed['elapsed_seconds'] > 0 and type(observed['pid']) is type(observed['starttime_ticks']) is int
            and 1 < observed['pid'] <= 2147483647 and observed['starttime_ticks'] > 0
            and all(type(observed[k+'_bytes']) is int and observed[k+'_bytes'] == len(blobs['.'+k])
                    and observed[k+'_sha256'] == hashlib.sha256(blobs['.'+k]).hexdigest() for k in ('stdout','stderr')),
            'cli_ordinary_v7_observation_changed')
    owner = blobs['.native-owner.json']
    require(type(owner) is dict and set(owner) == {'boot_id','pid','pid_namespace','starttime_ticks'}
            and owner['boot_id'] == clock['boot_id'] and type(owner['pid']) is int and owner['pid'] == 1
            and type(owner['starttime_ticks']) is int and owner['starttime_ticks'] > observed['starttime_ticks']
            and type(owner['pid_namespace']) is str and re.fullmatch(r'pid:\[[0-9]+\]',owner['pid_namespace']),
            'cli_ordinary_v7_native_owner_changed')
    custody = pin(request['previous_ordinary_custody']); failed = pin(request['previous_ordinary_unchanged'])
    qualified = pin(request['previous_ordinary_qualified']); saved = pin(request['previous_ordinary_sql'])
    independent = pin(request['previous_ordinary_independent'])
    raw_intent = reader(home/(base+'.intent.json'),private=True)
    sized(custody['native_intent'],home/(base+'.intent.json'),inventory[base+'.intent.json'],len(raw_intent))
    native = pin(custody['native_return'],sized=True)
    require(native['unit'] == unit and type(native['returncode']) is int and native['returncode'] == 2
            and native['reaped'] is True and native['timed_out'] is False
            and type(native['elapsed_seconds']) in (int,float) and math.isfinite(native['elapsed_seconds'])
            and native['elapsed_seconds'] >= observed['elapsed_seconds'], 'cli_ordinary_v7_native_return_changed')
    for role in ('stdout','stderr'):
        pin(native[role],Path(custody['native_return']['path']).parent/('UNIT.'+role),role=role,sized=True)
    physical = prior['physical']
    require(physical['unit'] == unit and physical['caps'] == {'memory.max':'2147483648','memory.swap.max':'0','pids.max':'128','cpu.max':'200000 100000'}
            and type(physical['unit_main_start_usec']) is int and physical['unit_main_start_usec'] > 0
            and abs(physical['unit_main_start_usec']/1000000-clock['started_mono']) < 0.2
            and type(physical['invocation_id']) is str and re.fullmatch('[0-9a-f]{32}',physical['invocation_id'])
            and physical['cgroup'].endswith('/'+unit), 'cli_ordinary_v7_physical_history_changed')
    witness = custody['closure_witness_mono']
    require(custody['state'] == 'VERIFIED_OWN_CUSTODY_CLOSED' and custody['clock'] == clock
            and type(witness) in (int,float) and math.isfinite(witness)
            and clock['started_mono'] <= witness <= clock['deadline_mono']
            and custody['unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is custody['no_retry_authorized'] is True,
            'cli_ordinary_v7_custody_changed')
    births = custody['known_own_births']
    require(type(births) is list and len(births) == 4 and {b['name'] for b in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(set(b) == {'name','pid','birth_ticks','same_birth_alive'} and type(b['pid']) is type(b['birth_ticks']) is int
                    and 1 < b['pid'] <= 2147483647 and b['birth_ticks'] > 0 and b['same_birth_alive'] is False for b in births),
            'cli_ordinary_v7_births_changed')
    born = {b['name']:b for b in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) == (observed['pid'],observed['starttime_ticks']),
            'cli_ordinary_v7_birth_binding_changed')
    sized(failed['custody'],request['previous_ordinary_custody']['path'],request['previous_ordinary_custody']['sha256'],len(reader(Path(request['previous_ordinary_custody']['path']),private=True)))
    sized(failed['native_observation'],home/(base+'.json'),inventory[base+'.json'],len(reader(home/(base+'.json'),private=True)))
    sized(failed['consumed_semantic_job'],home/job,inventory[job],len(reader(home/job,private=True)))
    require(failed['state'] == 'REAL_INSTALLED_READONLY_NEW_QUESTION_PARTIAL_OR_FAIL_CUSTODY_CLOSED'
            and failed['new_V7_retry_authorized'] is False
            and all(failed[k] is False for k in ('old_V4_retry_authorized','old_V5_retry_authorized','old_V6_retry_authorized'))
            and failed['native_result'] is None and failed['checks']['artifact_unchanged'] is True
            and failed['checks']['immutable_old_and_foreign_SQL_payload'] is True
            and failed['checks']['old_V4_V5_V6_suffixes_consumed_result_absence_preserved'] is True,
            'cli_ordinary_v7_failed_custody_truth_required')
    sized(qualified['original_root_proof'],request['previous_ordinary_unchanged']['path'],request['previous_ordinary_unchanged']['sha256'],len(reader(Path(request['previous_ordinary_unchanged']['path']),private=True)))
    sized(qualified['same_boot_custody_witness'],request['previous_ordinary_custody']['path'],request['previous_ordinary_custody']['sha256'],len(reader(Path(request['previous_ordinary_custody']['path']),private=True)))
    sized(qualified['same_original_job_consumed_no_retry'],home/job,inventory[job],len(reader(home/job,private=True)))
    require(qualified['state'] == 'REAL_V7_PARTIAL_READ_FILE_SUCCEEDED_FINAL_ANSWER_BLOCKED_NO_RETRY'
            and qualified['model_call_count'] == 'UNKNOWN'
            and qualified['namespace_exit_verified'] == 'UNKNOWN_missing_final_result_field'
            and type(qualified['native_returncode']) is int and qualified['native_returncode'] == native['returncode'] == 2
            and qualified['new_V7_retry_authorized'] is qualified['old_V4_V5_V6_retry_authorized'] is False
            and qualified['checks'] == {'new_exact_question':True,'new_final_answer':False,'only_read_file_calls':True,
                'only_read_file_tools':True,'persisted_cli_close':True,'read_file_success':True,'tool_calls_linked':True}
            and qualified['query_sha256'] == hashlib.sha256(old['argv'][-1].encode()).hexdigest()
            and qualified['exact_full_query_utf8_bytes'] == len(old['argv'][-1].encode())
            and qualified['runtime_guard'] == {'conservative_byte_estimate':38840,'final_answer':'ABSENT',
                'input_budget':35840,'tokenizer_fit':'UNVERIFIED'}
            and all(v[k] is False for v in (failed,qualified,independent) for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v7_partial_not_success_required')
    sized(independent['qualified_partial'],request['previous_ordinary_qualified']['path'],request['previous_ordinary_qualified']['sha256'],len(reader(Path(request['previous_ordinary_qualified']['path']),private=True)))
    require(independent['FailedV7_Custody_Go'] is True and independent['V7_retry_authorized'] is False,
            'cli_ordinary_v7_independent_custody_required')
    reviewed = pin(independent['independent'],sized=True)
    require(reviewed['state'] == 'EXACT7_PUBLICATION_ACCEPTED_FAILED_V7_CUSTODY_DISTINCT'
            and reviewed['schema'] == 'friday.exact7.publication-independent-review.v1'
            and reviewed['FailedV7_Custody_Go'] is True and reviewed['V7_Go'] is False
            and reviewed['actual_effects'] is False and reviewed['failed_checks'] == []
            and all(reviewed[k] is False for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v7_independent_review_truth_required')
    evidence = pin(reviewed['evidence'],sized=True)
    require(type(evidence['checks']) is dict and evidence['checks'] and all(value is True for value in evidence['checks'].values())
            and evidence['sameboot_failed_custody_independently_verified'] is True
            and evidence['actual_SQL_opens'] == evidence['protected_PID_probes'] == 0
            and evidence['actual_effects'] is False and evidence['boot_changed_no_old_probe'] is True
            and evidence['original_failed_V7_custody_remaining_seconds'] > 0,
            'cli_ordinary_v7_independent_evidence_required')
    new = request['next_ordinary_readonly']; oldbinding = old['ordinary_readonly']
    cli_ordinary_readonly_baseline(new)
    mutable = {'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
               'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v4'
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in oldbinding.items() if k not in mutable}
            and oldbinding['baseline_message_ids'] == list(range(5,14)) and new['baseline_message_ids'] == list(range(5,17))
            and new['append_high_water'] == 16 and cli_ordinary_job_id(home,new) != old['job_id'],
            'cli_ordinary_v8_genuine_new_baseline_required')
    require(type(saved) is dict and set(saved) == {'row','messages','other_sessions','other_messages','append_high_water'}
            and all(type(m[k]) is int and m[k] in (0,1) for m in saved['messages'] for k in ('active','compacted'))
            and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp']) and 0 <= m['timestamp'] <= 4200000000 for m in saved['messages'])
            and type(saved['row']['started_at']) in (int,float) and math.isfinite(saved['row']['started_at']) and saved['row']['started_at'] > 0
            and type(saved['row']['ended_at']) in (int,float) and math.isfinite(saved['row']['ended_at']) and saved['row']['ended_at'] > 0
            and {k:saved['row'][k] for k in new['identity']} == new['identity'], 'cli_ordinary_v7_sql_domains_changed')
    fingerprint = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and [m['id'] for m in saved['messages']] == new['baseline_message_ids']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:9])) == oldbinding['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:4])) == new['stable_messages_sha256']
            and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in saved['messages'][:4]]) == new['initial_lifecycle_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256'] and saved['append_high_water'] == 16
            and saved['row']['end_reason'] == 'cli_close' and saved['row']['ended_at'] is not None
            and [m['role'] for m in saved['messages'][-3:]] == ['user','assistant','tool']
            and saved['messages'][-3]['content'] == old['argv'][-1]
            and saved['messages'][-2]['content'] == ''
            and saved['messages'][-2]['tool_calls'] is not None
            and saved['messages'][-1]['tool_name'] == 'read_file',
            'cli_ordinary_v7_saved_sql_changed')
    calls = cli_ordinary_failed_v6_json(saved['messages'][-2]['tool_calls'])
    require(type(calls) is list and len(calls) == 1 and calls[0]['type'] == 'function'
            and calls[0]['function']['name'] == 'read_file'
            and cli_ordinary_failed_v6_json(calls[0]['function']['arguments']) == {'path':new['output']}
            and saved['messages'][-1]['tool_call_id'] == calls[0]['id'], 'cli_ordinary_v7_saved_tool_binding_changed')
    tool = cli_ordinary_failed_v6_json(saved['messages'][-1]['content'])
    artifact = reader(Path(new['output']),private=True)
    require(len(artifact) == new['artifact_bytes'] and hashlib.sha256(artifact).hexdigest() == new['artifact_sha256']
            and tool['success'] is True and tool['readonly'] is True and tool['path'] == new['output']
            and type(tool['content']) is str and tool['content'] == artifact.decode('utf-8').rstrip('\n'),
            'cli_ordinary_v7_saved_artifact_changed')
    return old


def cli_ordinary_previous_failed_v6_journey(request, home):
    """A failed consumed V6 is history; only a distinct pinned V7 may follow."""
    import hashlib, json, math, re
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    if reader is None:
        from hermes_cli.friday_dashboard_owner import read_owned as reader
    def pin(ref, expected=None, *, role='json', sized=False):
        require(type(ref) is dict and set(ref) == ({'path','sha256','bytes'} if sized else {'path','sha256'})
                and type(ref['path']) is str and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256'])
                and role in ('json','stdout','stderr')
                and (role == 'json' or expected is not None and str(expected).endswith('.'+role)),
                'cli_ordinary_v6_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(len(raw) <= 64*1024*1024 and hashlib.sha256(raw).hexdigest() == ref['sha256']
                and (not sized or type(ref['bytes']) is int and ref['bytes'] == len(raw)
                     and (ref['bytes'] >= 0 if role in ('stdout','stderr') else ref['bytes'] > 0)),
                'cli_ordinary_v6_history_pin_changed')
        return cli_ordinary_failed_v6_json(raw) if role == 'json' else raw
    def sized(ref, path, sha, length):
        require(type(ref) is dict and set(ref) == {'path','sha256','bytes'}
                and type(ref['bytes']) is int and ref == {'path':str(path),'sha256':sha,'bytes':length},
                'cli_ordinary_v6_witness_ref_changed')
    inventory = request['previous_ordinary_runtime']; prefix = 'preparation/cli-runtime/'
    require(type(inventory) is dict and len(inventory) == 6, 'cli_ordinary_v6_inventory_required')
    candidates = [name[len(prefix):-len('.intent.json')] for name in inventory
                  if type(name) is str and name.startswith(prefix) and '/' not in name[len(prefix):]
                  and name.endswith('.service.intent.json')]
    require(len(candidates) == 1 and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',candidates[0]),
            'cli_ordinary_v6_unit_required')
    unit = candidates[0]; base = prefix+unit
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    blobs = {}
    for suffix in suffixes:
        require(base+suffix in inventory, 'cli_ordinary_v6_inventory_required')
        role = 'stdout' if suffix == '.stdout' else 'stderr' if suffix == '.stderr' else 'json'
        blobs[suffix] = pin({'path':str(home/(base+suffix)),'sha256':inventory[base+suffix]},home/(base+suffix),role=role)
    prior = blobs['.intent.json']; old = prior['request']; clock = prior['clock']
    require(type(prior) is dict and set(prior) == {'schema','state','request','clock','physical','history'}
            and prior['schema'] == 'friday.installed-cli-invocation.v1' and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v6' and old['home'] == request['home'] == str(home)
            and old['unit'] == unit != request['unit'] and old['assignment'] != request['assignment']
            and old['repaired_input'] == request['previous_input'] and old['installation_input'] == request['installation_input']
            and old['history'] == prior['history'] == request['history'] and old['partial_proof'] == request['partial_proof']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'), 'cli_ordinary_v6_closed_scope_required')
    require(type(old['job_id']) is str and old['job_id'] == cli_ordinary_job_id(home,old['ordinary_readonly'])
            and old['argv'] == cli_ordinary_readonly_argv(home,old['ordinary_readonly']), 'cli_ordinary_v6_consumed_semantics_changed')
    job = prefix+'jobs/'+old['job_id']+'.intent.json'
    require(set(inventory) == {base+s for s in suffixes}|{job}, 'cli_ordinary_v6_inventory_required')
    job_value = pin({'path':str(home/job),'sha256':inventory[job]},home/job)
    require(job_value == {'schema':'friday.cli-ordinary-job-intent.v1','state':'CONSUMED_NO_RETRY',
            'job_id':old['job_id'],'request':old,'clock':clock}, 'cli_ordinary_v6_job_changed')
    result = home/(base+'.result.json')
    require(not result.exists() and not result.is_symlink(), 'cli_ordinary_v6_result_must_remain_absent')
    observed = blobs['.json']; argv = observed['argv']
    require(type(argv) is list and all(type(a) is str for a in argv)
            and len(argv) == 16+len(old['argv']) and argv[:2] == ['/usr/bin/bwrap','--json-status-fd']
            and re.fullmatch('[1-9][0-9]{0,9}',argv[2]) and 3 <= int(argv[2]) <= 2147483647
            and argv[3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',str(home/'hermes-agent/.hermes/bin/hermes')]
            and argv[16:] == old['argv'] and type(observed['returncode']) is int and observed['returncode'] == 1
            and observed['reaped'] is True and observed['timeout'] is False and observed['reason'] == 'command_nonzero_exit'
            and type(observed['elapsed_seconds']) in (int,float) and math.isfinite(observed['elapsed_seconds'])
            and observed['elapsed_seconds'] > 0 and type(observed['pid']) is type(observed['starttime_ticks']) is int
            and 1 < observed['pid'] <= 2147483647 and observed['starttime_ticks'] > 0
            and all(type(observed[k+'_bytes']) is int and observed[k+'_bytes'] == len(blobs['.'+k])
                    and observed[k+'_sha256'] == hashlib.sha256(blobs['.'+k]).hexdigest() for k in ('stdout','stderr')),
            'cli_ordinary_v6_observation_changed')
    owner = blobs['.native-owner.json']
    require(type(owner) is dict and set(owner) == {'boot_id','pid','pid_namespace','starttime_ticks'}
            and owner['boot_id'] == clock['boot_id'] and type(owner['pid']) is int and owner['pid'] == 1
            and type(owner['starttime_ticks']) is int and owner['starttime_ticks'] > observed['starttime_ticks']
            and type(owner['pid_namespace']) is str and re.fullmatch(r'pid:\[[0-9]+\]',owner['pid_namespace']),
            'cli_ordinary_v6_native_owner_changed')
    custody = pin(request['previous_ordinary_custody']); failed = pin(request['previous_ordinary_unchanged'])
    qualified = pin(request['previous_ordinary_qualified']); saved = pin(request['previous_ordinary_sql'])
    independent = pin(request['previous_ordinary_independent'])
    raw_intent = reader(home/(base+'.intent.json'),private=True)
    sized(custody['native_intent'],home/(base+'.intent.json'),inventory[base+'.intent.json'],len(raw_intent))
    native = pin(custody['native_return'],sized=True)
    require(native['unit'] == unit and type(native['returncode']) is int and native['returncode'] == 2
            and native['reaped'] is True and native['timed_out'] is False
            and type(native['elapsed_seconds']) in (int,float) and math.isfinite(native['elapsed_seconds'])
            and native['elapsed_seconds'] >= observed['elapsed_seconds'], 'cli_ordinary_v6_native_return_changed')
    for role in ('stdout','stderr'):
        pin(native[role],Path(custody['native_return']['path']).parent/('UNIT.'+role),role=role,sized=True)
    physical = prior['physical']
    require(physical['unit'] == unit and physical['caps'] == {'memory.max':'2147483648','memory.swap.max':'0','pids.max':'128','cpu.max':'200000 100000'}
            and type(physical['unit_main_start_usec']) is int and physical['unit_main_start_usec'] > 0
            and abs(physical['unit_main_start_usec']/1000000-clock['started_mono']) < 0.2
            and type(physical['invocation_id']) is str and re.fullmatch('[0-9a-f]{32}',physical['invocation_id'])
            and physical['cgroup'].endswith('/'+unit), 'cli_ordinary_v6_physical_history_changed')
    witness = custody['closure_witness_mono']
    require(custody['state'] == 'VERIFIED_OWN_CUSTODY_CLOSED' and custody['clock'] == clock
            and type(witness) in (int,float) and math.isfinite(witness)
            and clock['started_mono'] <= witness <= clock['deadline_mono']
            and custody['unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is custody['no_retry_authorized'] is True,
            'cli_ordinary_v6_custody_changed')
    births = custody['known_own_births']
    require(type(births) is list and len(births) == 4 and {b['name'] for b in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(set(b) == {'name','pid','birth_ticks','same_birth_alive'} and type(b['pid']) is type(b['birth_ticks']) is int
                    and 1 < b['pid'] <= 2147483647 and b['birth_ticks'] > 0 and b['same_birth_alive'] is False for b in births),
            'cli_ordinary_v6_births_changed')
    born = {b['name']:b for b in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) == (observed['pid'],observed['starttime_ticks']),
            'cli_ordinary_v6_birth_binding_changed')
    sized(failed['custody'],request['previous_ordinary_custody']['path'],request['previous_ordinary_custody']['sha256'],len(reader(Path(request['previous_ordinary_custody']['path']),private=True)))
    sized(failed['native_observation'],home/(base+'.json'),inventory[base+'.json'],len(reader(home/(base+'.json'),private=True)))
    sized(failed['consumed_semantic_job'],home/job,inventory[job],len(reader(home/job,private=True)))
    require(failed['state'] == 'REAL_INSTALLED_READONLY_NEW_QUESTION_PARTIAL_OR_FAIL_CUSTODY_CLOSED'
            and failed['new_V6_retry_authorized'] is failed['old_V4_retry_authorized'] is failed['old_V5_retry_authorized'] is False
            and failed['native_result'] is None and failed['checks']['artifact_unchanged'] is True
            and failed['checks']['immutable_old_and_foreign_SQL_payload'] is True
            and failed['checks']['old_V4_V5_suffixes_consumed_result_absence_preserved'] is True
            and qualified['state'] == 'REAL_V6_FAIL_CONTEXT_FORMATTER_PROTECTED_ROWS_NOT_A_SUCCESSFUL_ANSWER'
            and qualified['assistant_display_kind'] == 'failed_turn' and qualified['successful_user_answer'] is False
            and qualified['model_calls'] == 'UNKNOWN from saved observations; do not infer zero or completed answer'
            and qualified['job_retry_authorized'] is False and qualified['no_timeout_reaped'] is True
            and type(qualified['child_returncode']) is type(qualified['native_returncode']) is int
            and qualified['child_returncode'] == 1 and qualified['native_returncode'] == 2
            and qualified['child_elapsed_seconds'] == observed['elapsed_seconds']
            and all(v[k] is False for v in (failed,qualified,independent) for k in ('Runtime_Go','Resource_Go','Release_Go')),
            'cli_ordinary_v6_failed_turn_required')
    require(independent['state'] == 'INDEPENDENT_FAILED_CUSTODY_HISTORY_VERIFIED'
            and independent['Failure_Custody_Go'] is True
            and independent['exact_Rootproof_sha256'] == request['previous_ordinary_unchanged']['sha256']
            and independent['exact_custody_witness_sha256'] == request['previous_ordinary_custody']['sha256']
            and independent['exact_qualified_outcome_sha256'] == request['previous_ordinary_qualified']['sha256'],
            'cli_ordinary_v6_independent_custody_required')
    require(independent['failed_turn_verified'] is independent['no_retry_authorized'] is independent['old_and_foreign_SQL_artifact_preserved'] is True
            and type(independent['failed_checks']) is list and independent['failed_checks'] == [], 'cli_ordinary_v6_independent_truth_required')
    evidence = pin(independent['evidence'],sized=True)
    require(type(evidence['checks']) is dict and evidence['checks'] and all(value is True for value in evidence['checks'].values())
            and evidence['message_diffs'] == evidence['foreign_session_diffs'] == evidence['post_snapshot_diffs'] == []
            and evidence['current_known_births_all_gone'] is evidence['current_old_cgroup_absent'] is True
            and evidence['current_unit'] == {'ActiveState':'failed','ControlGroup':'','MainPID':'0'}
            and {row['item'] for row in evidence['V6_inventory']} == set(inventory)
            and all(row['exact'] is True for row in evidence['V6_inventory']), 'cli_ordinary_v6_independent_evidence_required')
    pin(evidence['copied_SQL_rows'],sized=True)
    new = request['next_ordinary_readonly']; oldbinding = old['ordinary_readonly']
    cli_ordinary_readonly_baseline(new)
    mutable = {'schema','question','purpose','row_sha256','messages_sha256','baseline_message_ids',
               'baseline_stable_messages_sha256','append_high_water','initial_lifecycle_sha256'}
    require(new['schema'] == 'friday.cli-ordinary-readonly.v3'
            and {k:v for k,v in new.items() if k not in mutable} == {k:v for k,v in oldbinding.items() if k not in mutable}
            and oldbinding['baseline_message_ids'] == list(range(5,12)) and new['baseline_message_ids'] == list(range(5,14))
            and new['append_high_water'] == 13 and cli_ordinary_job_id(home,new) != old['job_id'],
            'cli_ordinary_v7_genuine_new_baseline_required')
    require(all(type(m[k]) is int and m[k] in (0,1) for m in saved['messages'] for k in ('active','compacted'))
            and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp']) and 0 <= m['timestamp'] <= 4200000000 for m in saved['messages'])
            and type(saved['row']['started_at']) in (int,float) and math.isfinite(saved['row']['started_at']) and saved['row']['started_at'] > 0
            and type(saved['row']['ended_at']) in (int,float) and math.isfinite(saved['row']['ended_at']) and saved['row']['ended_at'] > 0
            and {k:saved['row'][k] for k in new['identity']} == new['identity'], 'cli_ordinary_v6_sql_domains_changed')
    fingerprint = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
    require(type(saved) is dict and set(saved) == {'row','messages','other_sessions','other_messages','append_high_water'}
            and fingerprint(saved['row']) == new['row_sha256'] and fingerprint(saved['messages']) == new['messages_sha256']
            and [m['id'] for m in saved['messages']] == new['baseline_message_ids']
            and fingerprint(stable(saved['messages'])) == new['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:7])) == oldbinding['baseline_stable_messages_sha256']
            and fingerprint(stable(saved['messages'][:4])) == new['stable_messages_sha256']
            and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in saved['messages'][:4]]) == new['initial_lifecycle_sha256']
            and fingerprint(saved['other_sessions']) == new['other_sessions_sha256']
            and fingerprint(saved['other_messages']) == new['other_messages_sha256'] and saved['append_high_water'] == 13
            and saved['row']['end_reason'] == 'cli_close' and saved['row']['ended_at'] is not None
            and saved['messages'][-2]['role'] == 'user' and saved['messages'][-2]['content'] == old['argv'][-1]
            and saved['messages'][-1]['role'] == 'assistant' and saved['messages'][-1]['display_kind'] == 'failed_turn'
            and cli_ordinary_failed_v6_json(saved['messages'][-1]['display_metadata'])['error'] == qualified['cause'],
            'cli_ordinary_v6_saved_sql_changed')
    return old


def cli_ordinary_previous_failed_journey(request, home):
    """Pinned failed V5 grants no retry, budget renewal, or runtime authority."""
    import hashlib, json, math, re
    home = Path(home)
    reader = globals().get('owned_file') or globals().get('read_owned')
    if reader is None:
        from hermes_cli.friday_dashboard_owner import read_owned as reader

    def raw_pin(ref, expected=None, *, role, sized=False):
        require(type(ref) is dict and set(ref) == ({'path','sha256','bytes'} if sized else {'path','sha256'})
                and type(ref['path']) is str
                and (expected is None or ref['path'] == str(expected))
                and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
                'cli_ordinary_history_pin_required')
        raw = reader(Path(ref['path']),private=True)
        require(hashlib.sha256(raw).hexdigest() == ref['sha256']
                and (not sized or type(ref['bytes']) is int
                     and 0 < ref['bytes'] <= 64*1024*1024 and len(raw) == ref['bytes']),
                'cli_ordinary_history_pin_changed')
        require(role in ('json','stdout','stderr')
                and (role == 'json' or expected is not None
                     and str(expected).endswith('.'+role)),
                'cli_ordinary_history_role_required')
        if role == 'json':
            strict_json(raw)
        return raw

    def strict_json(raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'cli_ordinary_history_duplicate_json_key')
                result[key] = value
            return result
        def constant(value):
            require(False, 'cli_ordinary_history_nonfinite_json_number')
        def finite_float(value):
            result = float(value)
            require(math.isfinite(result), 'cli_ordinary_history_nonfinite_json_number')
            return result
        return json.loads(raw,object_pairs_hook=unique,parse_constant=constant,parse_float=finite_float)

    def sized_ref(ref, path, digest, length, code):
        require(type(ref) is dict and set(ref) == {'path','sha256','bytes'}
                and type(ref['path']) is str and type(ref['sha256']) is str
                and type(ref['bytes']) is int and 0 < ref['bytes'] <= 64*1024*1024
                and ref == {'path':str(path),'sha256':digest,'bytes':length}, code)

    inventory = request['previous_ordinary_runtime']; prefix = 'preparation/cli-runtime/'
    require(type(inventory) is dict and len(inventory) == 5,
            'cli_ordinary_failed_inventory_required')
    candidates = [name[len(prefix):-len('.intent.json')] for name in inventory
                  if type(name) is str and name.startswith(prefix)
                  and '/' not in name[len(prefix):] and name.endswith('.service.intent.json')]
    require(len(candidates) == 1 and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',candidates[0]),
            'cli_ordinary_previous_unit_required')
    unit = candidates[0]; base = prefix+unit
    suffixes = ('.intent.json','.json','.stdout','.stderr')
    blobs = {}
    for suffix in suffixes:
        name = base+suffix
        require(name in inventory, 'cli_ordinary_failed_inventory_required')
        blobs[suffix] = raw_pin({'path':str(home/name),'sha256':inventory[name]},home/name,role=('stdout' if suffix == '.stdout' else
                                      'stderr' if suffix == '.stderr' else 'json'))
    prior = strict_json(blobs['.intent.json']); old = prior['request']; clock = prior['clock']
    require(set(prior) == {'schema','state','request','clock','history','physical'}
            and prior['schema'] == 'friday.installed-cli-invocation.v1'
            and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and old['schema'] == 'friday.installed-cli-request.v5'
            and old['home'] == request['home'] == str(home)
            and old['unit'] == unit and unit != request['unit']
            and old['assignment'] != request['assignment']
            and old['repaired_input'] == request['previous_input']
            and old['installation_input'] == request['installation_input']
            and old['history'] == prior['history'] == request['history']
            and old['ordinary_readonly'] == request['ordinary_readonly']
            and old['partial_proof'] == request['partial_proof']
            and 'session_artifact' not in old
            and cli_historical_scope_closed(clock,'friday.installed-cli-clock.v1'),
            'cli_ordinary_closed_v5_required')
    require(type(old['job_id']) is str and re.fullmatch('[0-9a-f]{64}',old['job_id']),
            'cli_ordinary_previous_job_required')
    job_name = prefix+'jobs/'+old['job_id']+'.intent.json'
    require(set(inventory) == {base+s for s in suffixes}|{job_name},
            'cli_ordinary_failed_inventory_required')
    job_raw = raw_pin({'path':str(home/job_name),'sha256':inventory[job_name]},home/job_name,role='json')
    require(strict_json(job_raw) == {'schema':'friday.cli-ordinary-job-intent.v1',
            'state':'CONSUMED_NO_RETRY','job_id':old['job_id'],'request':old,'clock':clock},
            'cli_ordinary_previous_job_changed')
    cli_ordinary_job_consumed(home,old,clock)
    for suffix in ('.native-owner.json','.result.json'):
        path = home/(base+suffix)
        require(not path.exists() and not path.is_symlink(), 'cli_ordinary_failed_absence_changed')

    custody_raw = raw_pin(request['previous_ordinary_custody'],role='json')
    custody = strict_json(custody_raw)
    for field,suffix in (('native_intent','.intent.json'),('native_observation','.json'),('native_stderr','.stderr')):
        ref = custody[field]
        sized_ref(ref,home/(base+suffix),inventory[base+suffix],len(blobs[suffix]),
                  'cli_ordinary_custody_artifact_changed')
    sized_ref(custody['consumed_semantic_job'],home/job_name,inventory[job_name],len(job_raw),
              'cli_ordinary_custody_job_changed')
    observed = strict_json(blobs['.json'])
    argv = observed['argv']
    require(type(argv) is list and all(type(arg) is str for arg in argv)
            and type(old['argv']) is list and all(type(arg) is str for arg in old['argv'])
            and len(argv) == 16+len(old['argv'])
            and argv[:2] == ['/usr/bin/bwrap','--json-status-fd']
            and re.fullmatch('[1-9][0-9]{0,9}',argv[2])
            and 3 <= int(argv[2]) <= 2147483647
            and argv[3:16] == ['--unshare-pid','--die-with-parent','--new-session','--as-pid-1',
                '--bind','/','/','--dev','/dev','--proc','/proc','--',
                str(home/'hermes-agent/.hermes/bin/hermes')]
            and argv[16:] == old['argv'], 'cli_ordinary_failed_observation_changed')
    require(type(observed['returncode']) is type(custody['child_returncode']) is int
            and observed['returncode'] == custody['child_returncode'] == 1
            and type(observed['pid']) is type(observed['starttime_ticks']) is int
            and 1 < observed['pid'] <= 2147483647 and observed['starttime_ticks'] > 0
            and all(type(observed[k]) is int and observed[k] >= 0 for k in ('stdout_bytes','stderr_bytes'))
            and type(observed['elapsed_seconds']) in (int,float)
            and type(custody['child_elapsed_seconds']) in (int,float)
            and math.isfinite(observed['elapsed_seconds']) and observed['elapsed_seconds'] > 0
            and math.isfinite(custody['child_elapsed_seconds']) and custody['child_elapsed_seconds'] > 0
            and observed['reaped'] is custody['child_reaped'] is True
            and observed['timeout'] is custody['child_timeout'] is False
            and observed['reason'] == 'command_nonzero_exit'
            and observed['elapsed_seconds'] == custody['child_elapsed_seconds']
            and observed['stdout_bytes'] == len(blobs['.stdout']) == 0
            and observed['stderr_bytes'] == len(blobs['.stderr'])
            and observed['stdout_sha256'] == hashlib.sha256(blobs['.stdout']).hexdigest()
            and observed['stderr_sha256'] == hashlib.sha256(blobs['.stderr']).hexdigest()
            and observed['argv'][-len(old['argv']):] == old['argv'],
            'cli_ordinary_failed_observation_changed')
    terminal = custody['unit']; physical = prior['physical']
    require(type(physical['unit_main_start_usec']) is int and physical['unit_main_start_usec'] > 0
            and type(custody['native_returncode']) is int
            and terminal == {'ActiveState':'failed','SubState':'failed','MainPID':'0','ControlGroup':'',
            'Result':'exit-code','ExecMainStartTimestampMonotonic':str(physical['unit_main_start_usec'])}
            and physical['unit'] == unit
            and custody['state'] == 'REAL_V5_NATIVE_ADMISSION_FAILED_CUSTODY_CLOSED'
            and custody['cause'] == 'friday_credential_cli_ordinary_current_native_unit_changed'
            and custody['original_clock'] == clock
            and cli_historical_scope_closed(custody['original_clock'],'friday.installed-cli-clock.v1') and custody['native_returncode'] == 2
            and custody['retry_authorized'] is False
            and custody['Runtime_Go'] is custody['Resource_Go'] is custody['Release_Go'] is False
            and custody['native_result_absent'] is custody['cgroup_gone_or_empty'] is custody['heavy_flock_returned'] is True
            and type(custody['model_calls_observed']) is int and custody['model_calls_observed'] == 0,
            'cli_ordinary_failed_custody_required')
    births = custody['known_own_births']
    require(type(births) is list and len(births) == 4
            and {row['name'] for row in births} == {'self','GNU','systemd-run-client','bwrap-monitor'}
            and all(set(row) == {'name','pid','birth_ticks','same_birth_alive'}
                    and type(row['pid']) is int and 1 < row['pid'] <= 2147483647
                    and type(row['birth_ticks']) is int and row['birth_ticks'] > 0
                    and row['same_birth_alive'] is False for row in births),
            'cli_ordinary_failed_births_required')
    born = {row['name']:row for row in births}
    require((born['GNU']['pid'],born['GNU']['birth_ticks']) == (clock['gnu_pid'],clock['gnu_starttime_ticks'])
            and (born['bwrap-monitor']['pid'],born['bwrap-monitor']['birth_ticks']) ==
                (observed['pid'],observed['starttime_ticks']), 'cli_ordinary_failed_birth_binding_changed')
    raw_pin(custody['Root_initial_checker_negative'],role='json',sized=True)
    # These are witness timestamps within original180, never a renewed budget.
    witness = custody['closure_witness_mono']
    require(type(witness) in (int,float) and math.isfinite(witness)
            and clock['started_mono'] <= witness <= clock['deadline_mono']
            and type(custody['original180_remaining_seconds']) in (int,float)
            and math.isfinite(custody['original180_remaining_seconds'])
            and custody['original180_remaining_seconds'] >= 0
            and math.isclose(custody['original180_remaining_seconds'],clock['deadline_mono']-witness,
                             rel_tol=0,abs_tol=0.01), 'cli_ordinary_original180_witness_changed')
    unchanged = strict_json(raw_pin(request['previous_ordinary_unchanged'],role='json'))
    sized_ref(unchanged['custody'],request['previous_ordinary_custody']['path'],
              request['previous_ordinary_custody']['sha256'],len(custody_raw),
              'cli_ordinary_unchanged_data_required')
    require(unchanged['state'] == 'BASELINE_SQL_ARTIFACT_OLD_V4_UNCHANGED_VERIFIED'
            and unchanged['Root_helper_argument_correction_only'] is True
            and unchanged['artifact_unchanged'] is unchanged['baseline_SQL_payload_and_lifecycle_unchanged'] is True
            and unchanged['old_V4_five_suffixes_consumed_result_absence_unchanged'] is True
            and unchanged['no_runtime_retry_authorized'] is True
            and type(unchanged['checked_monotonic']) in (int,float)
            and math.isfinite(unchanged['checked_monotonic'])
            and witness <= unchanged['checked_monotonic'] <= clock['deadline_mono']
            and type(unchanged['original180_remaining_seconds']) in (int,float)
            and math.isfinite(unchanged['original180_remaining_seconds'])
            and unchanged['original180_remaining_seconds'] >= 0
            and math.isclose(unchanged['original180_remaining_seconds'],
                             clock['deadline_mono']-unchanged['checked_monotonic'],rel_tol=0,abs_tol=1e-6),
            'cli_ordinary_unchanged_data_required')
    # Re-read the original V4 proof and five artifacts; no reinterpretation of V4.
    v4 = strict_json(raw_pin(old['partial_proof'],role='json'))
    require(v4['state'] == 'REAL_NATIVE_V4_PARTIAL_ARTIFACT_CONTEXT_FAIL_CUSTODY_CLOSED_NO_RETRY'
            and v4['retry_authorized'] is v4['narrow_journey_accepted'] is v4['full_Runtime_Go'] is False
            and cli_historical_scope_closed(v4['clock'],'friday.installed-cli-clock.v1'),
            'cli_ordinary_old_v4_closed_required')
    refs = v4['native_artifacts']
    v4_suffixes = (*suffixes,'.native-owner.json')
    require(type(refs) is dict and set(refs) == set(v4_suffixes), 'cli_ordinary_old_v4_inventory_required')
    v4_intent = strict_json(raw_pin(refs['.intent.json'],role='json',sized=True)); v4_unit = v4_intent['request']['unit']
    require(re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',v4_unit)
            and v4_intent['state'] == 'CONSUMED_NOT_COMPLETE'
            and v4_intent['request']['schema'] == 'friday.installed-cli-request.v4'
            and v4_intent['clock'] == v4['clock'], 'cli_ordinary_old_v4_intent_changed')
    for suffix in v4_suffixes:
        raw_pin(refs[suffix],home/(prefix+v4_unit+suffix),
                role=('stdout' if suffix == '.stdout' else
                      'stderr' if suffix == '.stderr' else 'json'),sized=True)
    path = home/(prefix+v4_unit+'.result.json')
    require(not path.exists() and not path.is_symlink(), 'cli_ordinary_old_v4_result_must_remain_absent')
    return old



def cli_context_previous_journey(request, home):
    """Preserve the consumed failed V4 journey, including its absent result."""
    read_owned = owned_file
    import hashlib, re
    home = Path(home)
    def load(ref, expected=None):
        require(type(ref) is dict and set(ref) == {'path','sha256'}
                and (expected is None or ref['path'] == str(expected)), 'cli_context_history_pin_required')
        raw = read_owned(Path(ref['path']),private=True)
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'cli_context_history_pin_changed')
        return json.loads(raw)
    prior = load(request['previous_journey'],home/'FRIDAY-INSTALL.session-artifact-journey.intent.json')
    require(prior['schema'] == 'friday.installed-cli-invocation.v1'
            and prior['state'] == 'CONSUMED_NOT_COMPLETE'
            and prior['request']['schema'] == 'friday.installed-cli-request.v4'
            and prior['request']['repaired_input'] == request['previous_input']
            and prior['request']['installation_input'] == request['installation_input']
            and cli_historical_scope_closed(prior['clock'],'friday.installed-cli-clock.v1'),
            'cli_context_closed_v4_required')
    unit = prior['request']['unit']; prefix = 'preparation/cli-runtime/'
    require(type(unit) is str and re.fullmatch(r'friday-rework-cli-runtime-[A-Za-z0-9-]+\.service',unit),
            'cli_context_previous_unit_required')
    suffixes = ('.intent.json','.json','.stdout','.stderr','.native-owner.json')
    inventory = request['previous_runtime']
    require(type(inventory) is dict and set(inventory) == {prefix+unit+s for s in suffixes},
            'cli_context_failed_inventory_required')
    observed = {}
    for suffix in suffixes:
        name = prefix+unit+suffix; raw = read_owned(home/name,private=True)
        require(hashlib.sha256(raw).hexdigest() == inventory[name], 'cli_context_failed_inventory_changed')
        observed[suffix] = {'path':str(home/name),'bytes':len(raw),'sha256':inventory[name]}
        if suffix == '.intent.json':
            require(json.loads(raw) == prior, 'cli_context_consumed_v4_changed')
    result = home/(prefix+unit+'.result.json')
    require(not result.exists() and not result.is_symlink(), 'cli_context_failed_result_must_remain_absent')
    proof = load(request['partial_proof'])
    require(proof['state'] == 'REAL_NATIVE_V4_PARTIAL_ARTIFACT_CONTEXT_FAIL_CUSTODY_CLOSED_NO_RETRY'
            and proof['clock'] == prior['clock'] and proof['native_artifacts'] == observed
            and proof['native_child_exit'] == 1 and proof['root_entry_exit'] == 2
            and proof['reaped'] is True and proof['timeout'] is False
            and proof['known_GNU_self_bwrap_births_gone'] is True
            and proof['native_cgroup_gone_or_empty'] is True
            and proof['shared_heavy_flock_returned'] is True
            and proof['native_result_absent_due_to_child_exit1'] is True
            and proof['retry_authorized'] is False and proof['narrow_journey_accepted'] is False
            and proof['full_Runtime_Go'] is False,
            'cli_context_closed_partial_proof_required')
    binding = request['ordinary_readonly']
    require(proof['artifact'] == {'path':binding['output'],'bytes':binding['artifact_bytes'],
                    'sha256':binding['artifact_sha256']}
            and prior['request']['session_artifact']['id'] == binding['id']
            and prior['request']['session_artifact']['identity'] == binding['identity']
            and prior['request']['session_artifact']['stable_messages_sha256'] == binding['stable_messages_sha256']
            and prior['request']['session_artifact']['message_ids'] == binding['message_ids'],
            'cli_context_original_session_changed')
    return prior


def cli_ordinary_readonly_baseline(binding):
    """A next question adds caller authority without changing historical data."""
    require(type(binding) is dict, 'cli_ordinary_question_binding_required')
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v1':
        require('question' not in binding and 'purpose' not in binding,
                'cli_ordinary_question_binding_required')
        return binding
    require(binding.get('schema') in ('friday.cli-ordinary-readonly.v2','friday.cli-ordinary-readonly.v3','friday.cli-ordinary-readonly.v4','friday.cli-ordinary-readonly.v5','friday.cli-ordinary-readonly.v6','friday.cli-ordinary-readonly.v7','friday.cli-ordinary-readonly.v8')
            and type(binding.get('question')) is str and type(binding.get('purpose')) is str,
            'cli_ordinary_question_binding_required')
    question, purpose = binding['question'], binding['purpose']
    try:
        question_bytes, purpose_bytes = question.encode('utf-8'), purpose.encode('utf-8')
    except UnicodeError:
        require(False, 'cli_ordinary_question_utf8_required')
    require(0 < len(question_bytes) <= 2048 and 0 < len(purpose_bytes) <= 128
            and '\x00' not in question and '\x00' not in purpose,
            'cli_ordinary_question_utf8_required')
    declared = ('Какой один следующий шаг реализации диспетчеризации задач от Hermes к DeepSeek Harness следует подготовить по сохранённому резюме? Назови вход, ожидаемый результат воркера и проверку локального endpoint без облачного fallback; если резюме не задаёт детали, явно обозначь предположение.', 'next-local-worker-dispatch-implementation-step') if binding['schema'] == 'friday.cli-ordinary-readonly.v2' else ('Какие обязательные возможности Пятницы перечислены в сохранённом резюме и какие ограничения или неподтверждённые результаты там отмечены? Отдели требования от уже выполненного; не дополняй сведения догадками.', 'extract-required-capabilities-and-limits-from-saved-artifact')
    if binding['schema'] == 'friday.cli-ordinary-readonly.v4':
        declared = ('По сохранённому файлу составь таблицу: требование Пятницы / уже сделано / ещё не подтверждено. Включи только факты файла, укажи ограничения. Ответь по-русски.', 'build-evidence-status-table-from-saved-artifact')
    if binding['schema'] == 'friday.cli-ordinary-readonly.v5':
        declared = ('По сохранённому файлу назови один ещё не подтверждённый результат Пятницы и проверку, которая его подтвердит. Используй только факты файла; если проверка не задана, прямо укажи это. Ответь по-русски.', 'verify-one-unconfirmed-result-from-saved-artifact')
    if binding['schema'] == 'friday.cli-ordinary-readonly.v8':
        require((question,purpose) == ('По сохранённому файлу укажи репозиторий и ветку публикации Пятницы. Затем объясни, что файл подтверждает о приёмке продукта и сохранении прежней Friday. Отдели требования от подтверждённой реализации, не делай выводов вне файла и ответь кратко по-русски.','verify-saved-publication-and-product-acceptance-boundaries')
                and question.strip() == question and purpose.strip() == purpose, 'cli_ordinary_distinct_v12_question_required')
    elif binding['schema'] == 'friday.cli-ordinary-readonly.v7':
        require((question,purpose) == ('По сохранённому файлу перечисли обязательные пользовательские интерфейсы Пятницы и ограничение на использование облачных моделей. Отдели требования от подтверждённой реализации; не добавляй сведений вне файла. Ответь кратко по-русски.', 'list-saved-user-interfaces-local-inference-and-implementation-boundary')
                and question.strip() == question and purpose.strip() == purpose
                and re.fullmatch('[a-z][a-z0-9-]{1,127}',purpose), 'cli_ordinary_distinct_v11_question_required')
    elif binding['schema'] == 'friday.cli-ordinary-readonly.v6':
        require((question,purpose) == ('Кратко изложи архитектуру Пятницы из сохранённого файла и отдели названные компоненты от состояния приёмки. Используй только факты файла; явно укажи, принята ли Пятница как продукт. Ответь по-русски.', 'summarize-architecture-and-acceptance-boundary-from-saved-artifact')
                and question.strip() == question and purpose.strip() == purpose
                and re.fullmatch('[a-z][a-z0-9-]{1,127}',purpose), 'cli_ordinary_distinct_v10_question_required')
    else:
        require((question,purpose) == declared, 'cli_ordinary_declared_new_question_required')
    return {**{k:v for k,v in binding.items() if k not in {'question','purpose','schema'}},
            'schema':'friday.cli-ordinary-readonly.v1'}


def cli_ordinary_readonly_inputs(home, binding, *, resumed=False):
    """Lossless post-partial payload with legal mutable native lifecycle."""
    binding = cli_ordinary_readonly_baseline(binding)
    import sqlite3, hashlib, math, re
    home = Path(home)
    fields = {'schema','id','database','row_sha256','messages_sha256','stable_messages_sha256',
              'initial_lifecycle_sha256','message_ids','identity','output','max_bytes',
              'baseline_message_ids','baseline_stable_messages_sha256','append_high_water',
              'other_sessions_sha256','other_messages_sha256','artifact_sha256','artifact_bytes'}
    require(type(binding) is dict and set(binding) == fields
            and binding['schema'] == 'friday.cli-ordinary-readonly.v1'
            and type(binding['id']) is str and re.fullmatch(r'[0-9]{8}_[0-9]{6}_[0-9a-f]{6}',binding['id'])
            and binding['database'] == str(home/'state.db')
            and binding['output'] == str(home/'user-artifacts/session-followup.txt')
            and binding['max_bytes'] == 8192 and type(binding['max_bytes']) is int
            and type(binding['artifact_bytes']) is int
            and 0 < binding['artifact_bytes'] <= binding['max_bytes']
            and type(binding['artifact_sha256']) is str
            and re.fullmatch('[0-9a-f]{64}',binding['artifact_sha256'])
            and type(binding['message_ids']) is list and len(binding['message_ids']) == 4
            and all(type(n) is int and n > 0 for n in binding['message_ids'])
            and binding['message_ids'] == sorted(set(binding['message_ids']))
            and type(binding['baseline_message_ids']) is list
            and 4 < len(binding['baseline_message_ids']) < 65
            and all(type(n) is int and n > 0 for n in binding['baseline_message_ids'])
            and binding['baseline_message_ids'] == sorted(set(binding['baseline_message_ids']))
            and binding['baseline_message_ids'][:4] == binding['message_ids']
            and type(binding['append_high_water']) is int
            and binding['append_high_water'] >= max(binding['baseline_message_ids'])
            and all(type(binding[k]) is str and re.fullmatch('[0-9a-f]{64}',binding[k]) for k in
                ('row_sha256','messages_sha256','stable_messages_sha256','initial_lifecycle_sha256',
                 'baseline_stable_messages_sha256','other_sessions_sha256','other_messages_sha256')),
            'cli_ordinary_readonly_scope_required')
    path = home/'state.db'; st = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
            and st.st_nlink == 1 and not st.st_mode & 0o077, 'cli_session_owned_database_required')
    for suffix in ('-wal','-shm'):
        side = path.with_name(path.name+suffix)
        if side.exists() or side.is_symlink():
            ss = side.lstat()
            require(side.resolve() == side and stat.S_ISREG(ss.st_mode) and ss.st_uid == os.getuid()
                    and ss.st_nlink == 1 and not ss.st_mode & 0o077, 'cli_session_owned_database_required')
    fingerprint = lambda value: hashlib.sha256(json.dumps(value,sort_keys=True,
                separators=(',',':'),ensure_ascii=False,default=lambda b:{'sqlite_blob_hex':b.hex()}).encode()).hexdigest()
    connection = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0.2)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
        found = connection.execute('SELECT * FROM sessions WHERE id=?',(binding['id'],)).fetchone()
        require(found is not None, 'cli_session_missing'); row = dict(found)
        keys = {'id','source','created_source','user_id','origin_json','profile_name','cwd','model',
                'billing_provider','billing_base_url','parent_session_id'}
        require(type(binding['identity']) is dict and set(binding['identity']) == keys
                and {k:row[k] for k in keys} == binding['identity']
                and row['source'] == row['created_source'] == 'cli' and row['profile_name'] == 'default'
                and row['user_id'] is None and row['origin_json'] is None and row['parent_session_id'] is None
                and row['cwd'] == str(home/'hermes-agent') and row['model'] == 'dispatcher'
                and row['billing_provider'] == 'custom' and not row['archived'] and not row['hidden'],
                'cli_session_foreign_identity')
        native_time = lambda value: type(value) in (int,float) and math.isfinite(value) and value > 0
        # Native end stamps both fields; reopen clears both. Reasons are native
        # writer strings, not a closed enum of the current CLI's known reasons.
        require(native_time(row['started_at'])
                and ((row['ended_at'] is None and row['end_reason'] is None)
                    or (native_time(row['ended_at']) and type(row['end_reason']) is str)),
                'cli_ordinary_session_lifecycle_invalid')
        require(resumed or (fingerprint(row) == binding['row_sha256']
                and row['ended_at'] is not None), 'cli_ordinary_baseline_row_changed')
        messages = [dict(r) for r in connection.execute(
            'SELECT * FROM messages WHERE session_id=? ORDER BY id LIMIT 65',(binding['id'],))]
        # Apply the domains before excluding flags from immutable payload pins,
        # including newly appended rows. Message writers allow epoch zero.
        require(all(type(m[k]) is int and m[k] in (0,1)
                    for m in messages for k in ('active','compacted'))
                and all(type(m['timestamp']) in (int,float) and math.isfinite(m['timestamp'])
                    and 0 <= m['timestamp'] <= 4200000000 for m in messages),
                'cli_ordinary_message_lifecycle_invalid')
        count = len(binding['baseline_message_ids']); prior = messages[:count]
        stable = lambda rows: [{k:v for k,v in m.items() if k not in {'active','compacted'}} for m in rows]
        require(len(messages) < 65 and [m['id'] for m in prior] == binding['baseline_message_ids']
                and fingerprint(stable(prior)) == binding['baseline_stable_messages_sha256']
                and fingerprint(stable(prior[:4])) == binding['stable_messages_sha256']
                and all(m['id'] > binding['append_high_water'] for m in messages[count:])
                and (resumed or (len(messages) == count and fingerprint(messages) == binding['messages_sha256']
                    and fingerprint([{k:m[k] for k in ('id','active','compacted')} for m in prior[:4]]) ==
                        binding['initial_lifecycle_sha256'])), 'cli_ordinary_history_changed')
        other_sessions = [dict(r) for r in connection.execute('SELECT * FROM sessions WHERE id<>? ORDER BY id',(binding['id'],))]
        other_messages = [dict(r) for r in connection.execute('SELECT * FROM messages WHERE session_id<>? ORDER BY id',(binding['id'],))]
        require(fingerprint(other_sessions) == binding['other_sessions_sha256']
                and fingerprint(other_messages) == binding['other_messages_sha256'], 'cli_ordinary_other_session_changed')
        high = connection.execute('SELECT COALESCE(MAX(id),0) FROM messages').fetchone()[0]
        require(resumed or high == binding['append_high_water'], 'cli_ordinary_append_baseline_changed')
        return row,messages
    finally:
        connection.close()


def cli_ordinary_readonly_artifact(home, binding):
    """Verify bytes through an owned parent and file descriptor, without fallback."""
    import hashlib
    path = Path(binding['output']); parent = Path(home)/'user-artifacts'
    require(path == parent/'session-followup.txt' and parent.resolve() == parent,
            'cli_ordinary_artifact_escape')
    directory = os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        pst = os.fstat(directory); named_parent = parent.lstat()
        require(stat.S_ISDIR(pst.st_mode) and pst.st_uid == os.getuid() and not pst.st_mode & 0o077
                and (pst.st_dev,pst.st_ino) == (named_parent.st_dev,named_parent.st_ino),
                'cli_ordinary_parent_changed')
        fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
                    and not before.st_mode & 0o077 and before.st_size == binding['artifact_bytes']
                    and 0 < before.st_size <= binding['max_bytes'], 'cli_ordinary_artifact_invalid')
            data = os.read(fd,binding['max_bytes']+1); after = os.fstat(fd)
            named = os.stat(path.name,dir_fd=directory,follow_symlinks=False)
            require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
                    (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    and (after.st_dev,after.st_ino) == (named.st_dev,named.st_ino)
                    and len(data) == binding['artifact_bytes']
                    and hashlib.sha256(data).hexdigest() == binding['artifact_sha256'],
                    'cli_ordinary_artifact_changed')
            data.decode('utf-8')
            named_parent = parent.lstat()
            require((pst.st_dev,pst.st_ino) == (named_parent.st_dev,named_parent.st_ino),
                    'cli_ordinary_parent_changed')
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def cli_ordinary_readonly_argv(home, binding):
    cli_ordinary_readonly_baseline(binding)
    if binding.get('schema') in ('friday.cli-ordinary-readonly.v2','friday.cli-ordinary-readonly.v3','friday.cli-ordinary-readonly.v4','friday.cli-ordinary-readonly.v5','friday.cli-ordinary-readonly.v6','friday.cli-ordinary-readonly.v7','friday.cli-ordinary-readonly.v8'):
        query = ('Прочитай существующий файл '+binding['output']+' инструментом read_file. '
                 +binding['question']+' Дай краткий ответ; не изменяй файлы и не вызывай другие инструменты.')
        return ['-p','default','--cli','chat','--oneshot','-t','file','--run-budget','90',
                '--max-turns','4','--resume',binding['id'],'--no-restore-cwd','-q',query]
    query = ('Прочитай существующий файл '+binding['output']+
             ' инструментом read_file. По сохранённому резюме объясни, как разделены роли Hermes, '
             'DeepSeek Harness и Agent Zero и почему они нужны вместе. Дай краткий ответ.')
    return ['-p','default','--cli','chat','--oneshot','-t','file','--run-budget','90',
            '--max-turns','4','--resume',binding['id'],'--no-restore-cwd','-q',query]


def cli_ordinary_job_id(home, binding):
    import hashlib
    cli_ordinary_readonly_baseline(binding)
    semantic = {'schema':'friday.cli-ordinary-readonly-job.v1','session':binding['identity'],
                'artifact':{'path':binding['output'],'sha256':binding['artifact_sha256']},
                'query':cli_ordinary_readonly_argv(home,binding)[-1],
                'effects':['read_file_pinned_existing_artifact','native_final_answer_and_session_append']}
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v2':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v2',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v3':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v3',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v4':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v4',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v5':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v5',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v6':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v6',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v7':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v7',
                        question=binding['question'],purpose=binding['purpose'],binding=binding)
    if binding.get('schema') == 'friday.cli-ordinary-readonly.v8':
        semantic.update(schema='friday.cli-ordinary-readonly-job.v8',
                        question=binding['question'],purpose=binding['purpose'],binding=binding,
                        operation='bounded-visible-json-v1-manual-compress-force-once')
    return hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def cli_ordinary_job_consumed(home, request, clock):
    read_owned = owned_file
    job = cli_ordinary_job_id(home,request['ordinary_readonly'])
    require(request.get('job_id') == job and 'session_artifact' not in request
            and request['argv'] == cli_ordinary_readonly_argv(home,request['ordinary_readonly']),
            'cli_ordinary_semantic_job_changed')
    token = Path(home)/'preparation/cli-runtime/jobs'/(job+'.intent.json')
    require(json.loads(read_owned(token,private=True)) == {
            'schema':'friday.cli-ordinary-job-intent.v1','state':'CONSUMED_NO_RETRY',
            'job_id':job,'request':request,'clock':clock}, 'cli_ordinary_consumed_job_changed')

def main():
    started = time.monotonic()  # before parser/input IO; never reset on dispatch
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=('plan', 'install', 'check', 'dashboard-check', 'start', 'qualify', 'activate-telegram', 'update-telegram', 'prepare-ordinary-workers', 'recover-ordinary-worker-keyless', 'register-ordinary-a0', 'start-telegram', 'rollback-telegram', 'reconcile', 'resume-harness', 'resume-cli', 'continue-cli-segment', 'installed-cli', 'repair-installed-cli', 'repair-frontend-close', 'repair-native-bootstrap', 'repair-session-artifact', 'repair-context-continuation','repair-native-manager','repair-readonly-schema-formatter','repair-current12-readonly-fit','repair-summary-fit','repair-summary-budget','repair-summary-completion','repair-summary-visible'))
    parser.add_argument('--input', required=True, type=Path, help='Private pinned JSON, no credential values')
    parser.add_argument('--a0-plan', type=Path, help='Existing owned live native probe plan; never a readiness report')
    parser.add_argument('--a0-plan-sha256')
    parser.add_argument('--host-source-transition',type=Path)
    parser.add_argument('--host-source-transition-sha256')
    args = parser.parse_args(); os.umask(0o077)
    sys.path.insert(0, str(ROOT))
    global Refused, require, canonical, owned_file, unique, read_json, digest, pin
    primitives = _source_runtime_module('runtime_primitives')
    Refused, require, canonical, owned_file, unique, read_json, digest, pin = (
        getattr(primitives, name) for name in
        ('Refused', 'require', 'canonical', 'owned_file', 'unique', 'read_json', 'digest', 'pin'))
    from scripts.dsh_prepare import StopUnconfirmed
    try:
        runtime_clock = installed_cli_clock() if args.phase in ('installed-cli','repair-installed-cli','repair-frontend-close','repair-native-bootstrap','repair-session-artifact','repair-context-continuation','repair-native-manager','repair-readonly-schema-formatter','repair-current12-readonly-fit','repair-summary-fit','repair-summary-budget','repair-summary-completion','repair-summary-visible') else None
        if args.phase == 'register-ordinary-a0':
            from scripts.friday_ordinary_a0_registration import registration_clock
            runtime_clock = registration_clock()
        raw = owned_file(args.input, private=True)
        require((args.host_source_transition is None) == (args.host_source_transition_sha256 is None)
                and (args.host_source_transition is None or args.phase == 'installed-cli'),
                'cli_host_transition_arguments_required')
        host_transition = None if args.host_source_transition is None else {
            'path':str(args.host_source_transition),'sha256':args.host_source_transition_sha256}
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
        if args.phase == 'activate-telegram':
            from scripts.friday_ordinary_install import activate
            result = activate(value,args.input,budget)
        elif args.phase == 'prepare-ordinary-workers':
            from scripts.friday_ordinary_install import prepare_workers
            result = prepare_workers(value,args.input,budget)
        elif args.phase == 'recover-ordinary-worker-keyless':
            from scripts.friday_worker_preparation import recover_keyless
            result = recover_keyless(value,args.input,budget)
        elif args.phase == 'register-ordinary-a0':
            from scripts.friday_ordinary_a0_registration import register
            result = register(value,args.input,clock=runtime_clock)
        elif args.phase == 'update-telegram':
            from scripts.friday_ordinary_install import update
            result = update(value,args.input,budget)
        elif args.phase == 'rollback-telegram':
            from scripts.friday_ordinary_install import rollback
            result = rollback(value,budget)
        elif args.phase == 'start-telegram':
            from scripts.friday_ordinary_install import start
            result = start(value,args.input,sha,budget)
        elif args.phase == 'repair-summary-visible':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,summary_visible=True)
        elif args.phase == 'repair-summary-completion':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,summary_completion=True)
        elif args.phase == 'repair-summary-budget':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,summary_budget=True)
        elif args.phase == 'repair-summary-fit':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,summary_fit=True)
        elif args.phase == 'repair-current12-readonly-fit':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,current12_readonly_fit=True)
        elif args.phase == 'repair-readonly-schema-formatter':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,readonly_schema_formatter=True)
        elif args.phase == 'repair-native-manager':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,native_manager=True)
        elif args.phase == 'repair-context-continuation':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,context_continuation=True)
        elif args.phase == 'repair-session-artifact':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock,session_artifact=True)
        elif args.phase == 'repair-native-bootstrap':
            result = repair_native_bootstrap(value,args.input,clock=runtime_clock)
        elif args.phase == 'repair-frontend-close':
            result = repair_frontend_close(value,args.input,clock=runtime_clock)
        elif args.phase == 'repair-installed-cli':
            result = repair_installed_cli(value,args.input,clock=runtime_clock)
        elif args.phase == 'installed-cli':
            result = installed_cli(value,args.input,clock=runtime_clock,host_source_transition=host_transition)
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
