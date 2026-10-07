#!/usr/bin/env python3
"""Native install completion; internal entry, explicit input and owned source."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def profile_write(home, spec):
    from tools.configure_product import compose_product
    bundle = compose_product(spec)
    from hermes_cli.friday_dashboard_tls import declared_settings
    declared_settings(home, bundle['contract']['native_dashboard'])
    from hermes_cli.config import atomic_config_write, config_write_transaction, DEFAULT_SOUL_MD
    from scripts.friday_install import require, publish, owned_file
    require(not (home / 'config.yaml').exists() and not (home / 'config.yaml').is_symlink(),
            'existing_profile_config_not_replaced')
    require(not (home / 'FRIDAY-PROFILE.json').exists() and not (home / 'FRIDAY-PROFILE.json').is_symlink(),
            'existing_profile_identity_not_replaced')
    runtime = spec['runtime']
    from plugins.friday_rework.host_runtime import configured_runtimes
    require(all(r['runtime_home'] == str(home) for r in configured_runtimes(runtime).values()),
            'foreign_worker_home')
    soul = home / 'SOUL.md'
    if soul.exists() or soul.is_symlink():
        require(owned_file(soul, private=True) == DEFAULT_SOUL_MD.encode(),
                'existing_custom_persona_not_replaced')
    staged = home / 'SOUL.md.friday'
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(bundle['soul']); f.flush(); os.fsync(f.fileno())
    # Config/module initialization can seed the native default before writing.
    # Only that exact seed in this fresh installation is replaced; owner text
    # and an interrupted already-published Friday identity remain untouched.
    os.replace(staged, soul)
    with config_write_transaction(home / 'config.yaml'):
        atomic_config_write(home / 'config.yaml', bundle['config'])
    publish(home / 'FRIDAY-PROFILE.json', bundle['contract'])
    return bundle


def dashboard_source_check(home):
    """Installed actual native consumer; reads source/stamp, never credentials."""
    from types import ModuleType
    from scripts.friday_install import owned_file, read_json, digest, require
    source = home / 'hermes-agent'
    path = source / 'hermes_cli/friday_dashboard_owner.py'
    receipt = read_json(home / 'hermes-agent.source.json')
    raw = owned_file(path)
    row = receipt['files']['hermes_cli/friday_dashboard_owner.py']
    require(digest(raw) == row['sha256'] and len(raw) == row['bytes'],
            'native_dashboard_source_code_changed')
    # Execute those exact validated bytes, not a second path read after checking.
    module = ModuleType('_friday_dashboard_source_check')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    identity = module.declared(home, source=source)
    return {'state': 'SOURCE_OWNERSHIP_VERIFIED_RUNTIME_NOT_RUN', 'ready': False,
            'identity': identity, 'credentials_checked': False}


def host_owner(record, home, profile, *, dashboard=None):
    """Policy for actual native records, used before/final ownership checks.

    A matching record is still not an observation of HTTP/auth/source identity.
    The native probe and process/install checks remain required by integration.
    """
    from scripts.friday_install import require
    require(record.home == str(home) and profile in record.profiles
            and record.start_time is not None and record.protocol_version == 1,
            'foreign_or_unproved_native_host_owner')
    if dashboard is not None:
        require(record.host == dashboard['host'] and record.port == dashboard['port'],
                'foreign_dashboard_authority')
    return True


def native_profile_check(bundle, home, *, records=()):
    """Read-only real config/auth/scope validation; inspect no secret values."""
    from scripts.friday_install import require
    from hermes_constants import get_hermes_home
    from hermes_cli.web_server import should_require_dashboard_auth
    from urllib.parse import urlsplit
    require(get_hermes_home() == home, 'native_home_mismatch')
    config = bundle['config']; contract = bundle['contract']; dash = contract['native_dashboard']
    require(config['dashboard'].get('require_auth') is True
            and should_require_dashboard_auth(dash['host'], frozenset({urlsplit(dash['public_url']).hostname}),
                                              require_auth=config['dashboard']['require_auth']),
            'native_dashboard_auth_off')
    from hermes_cli.friday_dashboard_tls import declared_settings
    require(config['dashboard'].get('tls') == dash.get('tls'), 'dashboard_tls_config_contract_mismatch')
    declared_settings(home, dash)
    require(config['fallback_providers'] == [] and config['fallback_model'] == {},
            'model_fallback_refused')
    require('dashboard_auth/basic' in config['plugins']['enabled']
            and 'friday_rework' in config['plugins']['enabled'], 'mandatory_native_plugins_missing')
    require(config['dashboard']['basic_auth']['username'] == dash['operator']['user_id']
            and dash['operator']['provider'] == 'basic' and dash['operator']['org_id'] == '',
            'native_operator_identity_mismatch')
    require(config['web']['backend'] == config['web']['search_backend'] == config['web']['extract_backend'] == 'exa'
            and config['web']['keyless_rescue'] is False and type(config['web']['keyless_fallback']) is bool
            and config['web']['provider_tier']['exa'] == ('free' if config['web']['keyless_fallback'] else 'paid')
            and 'web/exa' in config['plugins']['enabled'],
            'mandatory_web_route_missing')
    for record in records:
        host_owner(record, home, contract['profile'],
                   dashboard=dash if record.role == 'serve' else None)
    return {'state': 'TEMPLATE_INCOMPLETE', 'ready': False, 'credentials_checked': False}


def install_stamp(receipt):
    from scripts.write_install_stamp import build_stamp
    stamp = build_stamp(update_mechanism='external', commit=receipt['commit'], dirty=True,
                        branch='friday-rework', source='local', distribution='friday-rework')
    stamp['fridaySource'] = {'baseTree': receipt['base_tree'], 'layers': receipt['layers']}
    return stamp


def stage_dashboard_tls(value, home):
    from scripts.friday_install import dashboard_tls_inputs, require, directory
    inputs = dashboard_tls_inputs(value, home)
    if not inputs:
        return
    folder = home / 'dashboard-tls'
    require(not folder.exists() and not folder.is_symlink(), 'existing_dashboard_tls_not_adopted')
    folder.mkdir(mode=0o700); directory(folder)
    for key, data in inputs.items():
        path = home / value['product']['dashboard']['tls'][key]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    from hermes_cli.friday_dashboard_tls import checked
    dash = value['product']['dashboard']
    checked(home, dash['tls'], dash['host'], dash['port'], dash['public_url'])


def complete(value, home, receipt):
    from scripts.friday_install import require, owned_file, digest, publish
    from hermes_constants import get_hermes_home
    require(get_hermes_home() == home, 'foreign_native_home')
    source = home / 'hermes-agent'
    # Only the native PM selected generation and this installation may publish
    # commands. Publication is local; expose_cli/user PATH is never called.
    from pm.paths import repo_root
    from pm.environments import owning_home_root, project_python
    require(repo_root() == source and Path(sys.executable) == project_python(source)
            and owning_home_root(source) in (None, home), 'native_pm_install_owner_mismatch')
    require(not (source / '.git').exists(), 'exported_full_patched_source_required')
    from tools.configure_product import compose_product
    stage_dashboard_tls(value, home)
    bundle = compose_product(value['product'])
    from gateway.host_rendezvous import read_record, record_is_stale
    records = tuple(r for role in ('serve', 'gateway')
                    if (r := read_record(role, include_stale=True)) is not None and not record_is_stale(r))
    native_profile_check(bundle, home, records=records)
    from hermes_cli.source_build import (source_build_env, prepare_source_dependencies,
                                         build_source_tui, build_source_web, source_product_current)
    env = source_build_env(explicit=True)
    prepare_source_dependencies(source, ('ui-tui', 'web'), env=env, explicit=True)
    build_source_tui(source, env=env); build_source_web(source, env=env)
    require(source_product_current(source, 'tui', source / 'ui-tui/dist')
            and source_product_current(source, 'web', source / 'hermes_cli/web_dist'),
            'native_frontend_freshness_not_verified')
    from hermes_cli._launchers import ensure_install_launchers, ENTRY_POINTS
    written = ensure_install_launchers(source, source / '.hermes/bin')
    require(len(written) == len(ENTRY_POINTS), 'native_launcher_publication_failed')
    # Truthful upstream base plus overlays; never claim a clean upstream build.
    publish(source / 'install-stamp.json', install_stamp(receipt))
    target = home / 'plugins/friday_rework'
    require(not target.exists() and not target.is_symlink(), 'existing_plugin_not_adopted')
    target.parent.mkdir(mode=0o700, exist_ok=True)
    from scripts.friday_install import directory
    directory(target.parent)
    shutil.copytree(ROOT / 'plugins/friday_rework', target)
    for name, sha in value['project_files'].items():
        prefix = 'plugins/friday_rework/'
        if name.startswith(prefix):
            p = target / name[len(prefix):]
            require(digest(owned_file(p)) == sha, 'installed_plugin_source_changed')
            os.chmod(p, 0o600)
    for path in target.rglob('*'):
        if path.is_dir():
            os.chmod(path, 0o700)
    stage_worker_runtime(value, home)
    bundle = profile_write(home, value['product'])
    return native_profile_check(bundle, home)



def stage_worker_runtime(value, home):
    """Normal installation ships exact source; no live launcher overwrite/grant."""
    from scripts.friday_install import directory,require,owned_file,digest
    destination = home / 'worker-runtime-source'
    require(not destination.exists() and not destination.is_symlink(), 'existing_worker_source_not_adopted')
    names = ('scripts/a0_runtime.py','scripts/rootless_docker_launch.py',
             'plugins/friday_rework/adapters/a0_profile.py','plugins/friday_rework/adapters/a0_web.py')
    payload = {}
    for name in names:
        require(name in value['project_files'], 'worker_runtime_source_not_pinned')
        data = owned_file(ROOT/name)
        require(digest(data)==value['project_files'][name], 'worker_runtime_source_changed')
        payload[name]=data
    destination.mkdir(mode=0o700);directory(destination)
    for name,data in payload.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
    return destination

def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=('install', 'start'))
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--deadline', required=True, type=float, help='Inherited original monotonic deadline')
    args = parser.parse_args()
    # Validate stdlib-only ownership and pins before importing installed code.
    sys.path.insert(0, str(ROOT))
    from scripts.friday_install import spec_checked, read_json, composition_checked, directory
    value = read_json(args.input)
    from scripts.install_containment import Budget
    budget = Budget(value.get('seconds'), started=started, deadline=args.deadline)
    home, donors = budget.call(spec_checked, value); budget.call(directory, home)
    from scripts.friday_install import MARKER, digest, owned_file, require, partial_claim
    if args.phase == 'install':
        require(read_json(home / MARKER) == partial_claim(digest(owned_file(args.input, private=True)), budget),
                'fresh_install_claim_required')
    else:
        from scripts.friday_install import inspect
        budget.call(inspect, value, digest(owned_file(args.input, private=True)))
    source = home / 'hermes-agent'; receipt = read_json(home / 'hermes-agent.source.json')
    budget.call(composition_checked, value, source, receipt, donors['hermes'])
    sys.path.insert(0, str(source))
    import tools, plugins, scripts
    # A cached project namespace must never stand in for the verified native
    # regular package. Native __init__ executes before adding project modules.
    for package in (tools, plugins):
        expected = source / package.__name__ / '__init__.py'
        require(Path(package.__file__ or '').resolve() == expected
                and list(package.__path__) == [str(expected.parent)],
                'native_package_provenance_required')
        package.__path__.append(str(ROOT / package.__name__))
    scripts.__path__.append(str(source / 'scripts'))
    if args.phase == 'start':
        from scripts.friday_start import start
        from scripts.dsh_prepare import StopUnconfirmed
        try:
            budget.call(start, value, budget)
        except StopUnconfirmed:
            parser.exit(3, 'STOP_UNCONFIRMED: native service ownership requires reconciliation; do not retry\n')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            parser.exit(2, 'Friday native start refused: mandatory native admission is incomplete\n')
        raise RuntimeError('native foreground ownership was not transferred')
    result = budget.call(complete, value, home, receipt)
    payload = json.dumps(result, sort_keys=True)
    budget.check()
    print(payload, flush=True)
    budget.check()


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    from scripts.dsh_prepare import StopUnconfirmed
    try:
        main()
    except StopUnconfirmed:
        print('STOP_UNCONFIRMED: native operation requires ownership reconciliation', file=sys.stderr)
        sys.exit(3)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        print('Friday native operation refused: owned inputs and admission required', file=sys.stderr)
        sys.exit(2)
