#!/usr/bin/env python3
"""Finite Friday composition over native preparers, PM and launchers.

Installation is an explicit effectful operator action. Planning and inspection
never install dependencies, read credentials or grant worker admission.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
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


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


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


def directory(path):
    p = canonical(str(path)); info = p.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'owned_private_directory_required')
    return p


def spec_checked(value):
    fields = {'home', 'bootstrap_python', 'hermes_donor', 'hermes_prepare',
              'sources_lock', 'dsh_donor', 'a0_donor', 'product', 'project_files', 'seconds'}
    require(isinstance(value, dict) and set(value) == fields, 'explicit_install_fields_required')
    home = canonical(value['home']); directory(home.parent)
    require(home != Path.home() / '.hermes' and home != ROOT
            and not ROOT.is_relative_to(home), 'separate_product_home_required')
    require(type(value['seconds']) is int and 30 <= value['seconds'] <= 7200,
            'finite_install_budget_required')
    for key in ('bootstrap_python', 'hermes_prepare', 'sources_lock'):
        pin(value[key])
    for key in ('hermes_donor', 'dsh_donor', 'a0_donor'):
        canonical(value[key])
    require(canonical(value['dsh_donor']) == home / 'harness', 'owned_harness_destination_required')
    files = value['project_files']
    require(isinstance(files, dict) and files, 'reviewed_project_inventory_required')
    required = {'scripts/friday_install.py', 'scripts/friday_native.py',
                'scripts/dsh_prepare.py', 'scripts/a0_prepare.py',
                'tools/configure_product.py', 'tools/configure_local_test.py',
                'tools/web_profile.py', 'config/SOUL.md', 'config/RESEARCH.md'}
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
    product = value['product']
    require(isinstance(product, dict) and product.get('profile') == 'default',
            'native_default_receiving_home_required')
    require(isinstance(product.get('dashboard'), dict)
            and set(product['dashboard']) == {'host', 'port', 'public_url', 'operator'},
            'explicit_dashboard_authority_required')
    # Reuse the existing pure local/capacity validator before any install
    # effects. Full native profile/provider/auth consumption happens later.
    from tools.configure_local_test import build_config
    from tools.web_profile import hermes_web_config
    require(set(product) == {'profile', 'inference', 'web', 'dashboard', 'accounts', 'runtime'},
            'explicit_normal_product_required')
    build_config(**product['inference'])
    require(product['web'].get('profile') == 'exa-paid'
            and set(product['web']) == {'profile', 'extract_char_limit', 'extract_timeout'}
            and all(product['web'][k] is not None for k in ('extract_char_limit', 'extract_timeout')),
            'mandatory_scoped_web_required')
    hermes_web_config(**product['web'])
    dash = product['dashboard']; ipaddress.ip_address(dash['host'])
    require(type(dash['port']) is int and 1 <= dash['port'] <= 65535, 'explicit_dashboard_port_required')
    public = urlsplit(dash['public_url'])
    require(public.scheme == 'https' and public.hostname and public.username is None
            and public.password is None and public.port == dash['port']
            and public.path in ('', '/') and not public.query and not public.fragment,
            'protected_dashboard_public_authority_required')
    lock = json.loads(owned_file(pin(value['sources_lock'])))
    donors = {r['id']: r for r in lock['repositories']}
    require({'hermes', 'dsh', 'a0'}.issubset(donors), 'complete_donor_pins_required')
    return home, donors


def commands(value):
    """Generate native argv; no custom PM flags or replacement service backend."""
    home, _ = spec_checked(value); source = home / 'hermes-agent'
    python = value['bootstrap_python']['path']; helper = str(ROOT / 'scripts/friday_native.py')
    launcher = str(source / '.hermes/bin/hermes')
    return {
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


def publish(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install(value, input_path):
    """Future operator flow. Failed partial installs require reconciliation."""
    home, donors = spec_checked(value); argv = commands(value)
    raw = owned_file(input_path, private=True)
    require(json.loads(raw, object_pairs_hook=unique) == value, 'install_input_changed')
    input_hash = digest(raw)
    if home.exists():
        directory(home)
        marker = read_json(home / MARKER)
        require(marker.get('schema') == SCHEMA and marker.get('input_sha256') == input_hash,
                'foreign_existing_install_not_adopted')
        require(marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE',
                'partial_install_requires_reconciliation')
        return inspect(value, input_hash)
    # Exact exclusive claim, before preparers or PM write anything. No reset,
    # recursive chmod, overwrite, rollback or adoption on a subsequent failure.
    home.mkdir(mode=0o700)
    publish(home / MARKER, {'schema': SCHEMA, 'state': 'PARTIAL', 'input_sha256': input_hash})
    from scripts.dsh_prepare import run
    deadline = time.monotonic() + value['seconds']
    def execute(command, cwd, timeout=1800):
        remaining = int(deadline - time.monotonic())
        require(remaining > 0, 'original_install_budget_exhausted')
        return run(command, cwd, timeout=min(timeout, remaining), env=clean_environment(home))[0]
    execute(argv['compose'], ROOT, 130)
    source = home / 'hermes-agent'; receipt_path = home / 'hermes-agent.source.json'
    receipt = read_json(receipt_path); composition_checked(value, source, receipt, donors['hermes'])
    for phase in ('tools', 'dependencies'):
        execute(argv[phase], source)
    # Native PM selected interpreter; never substitute an unrelated venv.
    expression = 'from pm.environments import project_python; from pathlib import Path; print(project_python(Path.cwd()))'
    selected = execute([value['bootstrap_python']['path'], '-B', '-c', expression], source, 15)
    # Native venv executables may be symlinks to the selected store Python.
    # The native completion entry verifies project_python before imports/build.
    require(Path(selected).is_absolute() and Path(selected).is_file(), 'native_pm_python_missing')
    execute([selected, '-B', str(ROOT / 'scripts/friday_native.py'), 'install',
             '--input', str(input_path)], source)
    for command in argv['harness']:
        execute(command, ROOT)
    execute(argv['a0_inventory'], ROOT, 120)
    composition_checked(value, source, receipt, donors['hermes'])
    # Native source receipt and original input bind this finite installation.
    # A native PM/build success cannot grant the absent A0/web/kernel boundary.
    marker = {'schema': SCHEMA, 'state': 'INSTALLED_TEMPLATE_INCOMPLETE',
              'input_sha256': input_hash, 'source_receipt_sha256': digest(owned_file(receipt_path)),
              'home': str(home), 'source': str(source), 'runtime_ready': False,
              'gateway_installed': False, 'remaining': gaps()}
    marker['profile_files'] = {name: digest(owned_file(home / name, private=True))
                               for name in ('config.yaml', 'SOUL.md', 'FRIDAY-PROFILE.json')}
    marker['plugin_files'] = {name: sha for name, sha in value['project_files'].items()
                              if name.startswith('plugins/friday_rework/')}
    pending = home / (MARKER + '.completed')
    publish(pending, marker)
    # Exact private claim only: no overwrite of an arbitrary existing home.
    require(read_json(home / MARKER) == {'schema': SCHEMA, 'state': 'PARTIAL',
                                       'input_sha256': input_hash}, 'install_claim_changed')
    os.replace(pending, home / MARKER)
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return marker


def gaps():
    return ['A0 portable image/toolchain preparation is absent; fixed deployment needs separately admitted kernel/resources',
            'Current product compiler refuses an A0 useful-web runtime and cannot configure both workers',
            'Native Dashboard boundary requires independent source review and actual authenticated startup/attach acceptance',
            'Protected credential provisioning, actual account ownership, PM/build realization and all six live journeys require independent acceptance']


def inspect(value, input_hash):
    home, donors = spec_checked(value); directory(home)
    marker = read_json(home / MARKER)
    require(marker.get('schema') == SCHEMA and marker.get('home') == str(home)
            and marker.get('input_sha256') == input_hash
            and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE', 'foreign_or_partial_install')
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
    return {'state': 'TEMPLATE_INCOMPLETE', 'ready': False, 'home': str(home),
            'effects': 'NONE', 'remaining': gaps()}


def start(value, input_hash):
    # This candidate deliberately has no grant-converting switch. Calling a
    # source renderer "READY" or providing a receipt alone cannot launch it.
    inspect(value, input_hash)
    # A0/web/kernel admission is still absent. The Dashboard is now guarded at
    # its native CLI and pre-bind host lock, not by a check-then-launch wrapper.
    raise ValueError('mandatory_a0_web_kernel_and_final_native_dashboard_owner_not_admitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=('plan', 'install', 'check', 'dashboard-check', 'start'))
    parser.add_argument('--input', required=True, type=Path, help='Private pinned JSON, no credential values')
    args = parser.parse_args(); os.umask(0o077)
    sys.path.insert(0, str(ROOT))
    try:
        raw = owned_file(args.input, private=True)
        value = json.loads(raw, object_pairs_hook=unique); sha = digest(raw)
        if args.phase == 'plan':
            result = {'state': 'PLANNED_NOT_EXECUTED', 'ready': False,
                      'commands': commands(value), 'remaining': gaps()}
        elif args.phase == 'install':
            result = install(value, args.input)
        elif args.phase == 'check':
            result = inspect(value, sha)
        elif args.phase == 'dashboard-check':
            inspect(value, sha)
            from scripts.friday_native import dashboard_source_check
            result = dashboard_source_check(Path(value['home']))
        else:
            result = start(value, sha)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        # Native errors/inputs can contain credentials: print no exception body.
        parser.exit(2, 'Friday entry refused: pinned inputs, owned fresh installation and admitted native dependencies required\n')
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
