"""Remaining native installer preparation for an existing ordinary receiver.

The new request owns one finite attempt. Native reports stay in its exclusive
directory; existing attempts, users, hosts and qualification remain untouched.
"""
from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import resource
import time
from pathlib import Path

from scripts import friday_install as f
from scripts import friday_ordinary_install as ordinary

SCHEMA = 'friday.ordinary-worker-preparation.v1'
NAMES = {'source': 'dsh-source.json', 'toolchain': 'dsh-toolchain.json',
         'build': 'dsh-build.json', 'smoke': 'dsh-smoke.json',
         'inventory': 'dsh-build-inventory.json', 'a0': 'a0.json'}
BUILD_FIELDS = {'memory_bytes', 'swap_bytes', 'cpu_percent', 'tasks', 'affinity',
                'fsize_bytes', 'core_bytes', 'seconds', 'cleanup_seconds'}

KEYLESS_RECOVERY_SCHEMA = 'friday.ordinary-worker-keyless-recovery.v1'
KEYLESS_RECOVERY_FIELDS = {'schema', 'recovery_id', 'seconds', 'home', 'profile', 'binding',
    'generation', 'transition', 'installed_input', 'recovery_input', 'root_marker', 'source_receipt',
    'stamp', 'root_configuration', 'root_profile', 'native_unit', 'onboarding', 'user_marker',
    'configuration', 'access_state', 'attachment', 'preparations', 'reports', 'history',
    'failure', 'closed_failure', 'qualification_files'}
KEYLESS_FAILED_FILES = {'failure.json', 'dsh-safety/inputs/bootstrap.py',
    'dsh-safety/inputs/web-network.mjs', 'dsh-safety/inputs/web-ca.pem'}


def _keyless_request(request):
    """This operation is a new maintenance transition, never a setup retry."""
    f.require(type(request) is dict and set(request) == KEYLESS_RECOVERY_FIELDS
        and request['schema'] == KEYLESS_RECOVERY_SCHEMA
        and type(request['recovery_id']) is str
        and re.fullmatch('[A-Za-z0-9_-]{1,64}', request['recovery_id'])
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180
        and type(request['generation']) is int and request['generation'] == 1
        and request['transition'] == 'NEW_PRODUCT_MAINTENANCE_NO_RUNTIME_AUTHORITY'
        and type(request['profile']) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', request['profile'])
        and request['profile'] != 'default'
        and type(request['binding']) is dict
        and request['binding'].get('runtime_profile') == request['profile']
        and type(request['preparations']) is dict and set(request['preparations']) == {'dsh', 'a0'}
        and type(request['reports']) is dict and set(request['reports']) == set(NAMES)
        and type(request['history']) is list
        and type(request['qualification_files']) is dict
        and set(request['qualification_files']) == KEYLESS_FAILED_FILES
        and all(type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha)
                for sha in request['qualification_files'].values()),
        'ordinary_keyless_explicit_recovery_request_required')


def _keyless_failed_tree(request, profile_home, *, folder=None):
    """Accept only the demonstrated failure before any native setup branch."""
    folder = profile_home / 'workers/qualification' if folder is None else folder
    f.directory(folder)
    expected_dirs = {'dsh-safety', 'dsh-safety/home', 'dsh-safety/workspace', 'dsh-safety/inputs'}
    files = {}; directories = {}
    for path in [folder, *folder.rglob('*')]:
        f.require(not path.is_symlink(), 'ordinary_keyless_failed_tree_link_refused')
        relative = str(path.relative_to(folder))
        if path.is_dir():
            f.directory(path)
            st = path.lstat()
            directories[relative] = tuple(getattr(st, key) for key in
                ('st_dev', 'st_ino', 'st_uid', 'st_mode'))
        else:
            files[relative] = ordinary.update_file_state(path)
    f.require(set(files) == KEYLESS_FAILED_FILES and set(directories) == {'.'} | expected_dirs
        and all(row is not None and row['mode'] == (0o600 if name == 'failure.json' else 0o400)
            and f.digest(row['data']) == request['qualification_files'][name] for name, row in files.items()),
        'ordinary_keyless_exact_before_native_failure_required')
    failure = json.loads(files['failure.json']['data'], object_pairs_hook=f.unique)
    claim = failure.get('original_attempt', {})
    f.require(set(failure) == {'state', 'original_attempt', 'retry_authorized', 'a0_probe_cleanup'}
        and failure['state'] == 'REFUSED_OR_UNCERTAIN' and failure['retry_authorized'] is False
        and failure['a0_probe_cleanup'] == 'OWN_INITIAL_PROBE_CUSTODY'
        and set(claim) == {'boot_id', 'started_mono', 'deadline_mono', 'budget_seconds'}
        and type(claim['boot_id']) is str and bool(claim['boot_id'])
        and type(claim['budget_seconds']) is int and claim['budget_seconds'] == 300
        and all(type(claim[k]) in (int, float) and math.isfinite(claim[k])
                for k in ('started_mono', 'deadline_mono'))
        and claim['started_mono'] >= 0 and claim['deadline_mono'] - claim['started_mono'] == 300
        and request['failure'] == {'path': str(profile_home / 'workers/qualification/failure.json'),
            'sha256': request['qualification_files']['failure.json']},
        'ordinary_keyless_original300_failure_required')
    closed = f.read_json(f.pin(request['closed_failure']))
    f.require(closed.get('state') == 'CLOSED_FAILED_FIRST_ORIGINAL300_BEFORE_NATIVE_SCOPE_NO_RETRY'
        and closed.get('failure') == request['failure'] and closed.get('server_original_attempt') == claim
        and closed.get('no_retry') is True and closed.get('original_attempt_marker_retained') is True
        and closed.get('native_DSH_scope_created') is False
        and closed.get('native_model_or_web_probe_started') is False
        and closed.get('A0_bootstrap_or_keys_or_native_route_started') is False
        and closed.get('workers') == 'OFF' and closed.get('worker_runtime_acceptance') is False,
        'ordinary_keyless_closed_original300_required')
    for kind in ('dsh', 'a0'):
        root = profile_home / 'workers' / kind
        for name in ('jobs', 'staging', 'cache'):
            path = f.directory(root / name)
            f.require(not list(path.iterdir()), 'ordinary_keyless_worker_activity_present')
        for name in ('runtime-receipt.json', 'bootstrap', 'probe-plan.json'):
            f.require(not os.path.lexists(root / name), 'ordinary_keyless_native_setup_already_started')
    return {'files': files, 'directories': directories, 'original_attempt': claim}


def _keyless_source_inputs(request, home, budget):
    """Verify the complete installed native identity before importing native code."""
    source = f.directory(home / 'hermes-agent')
    original = f.read_json(f.pin(request['installed_input']))
    value = f.read_json(f.pin(request['recovery_input']))
    allowed = {'scripts/friday_install.py', 'scripts/friday_worker_preparation.py'}
    old = original.get('project_files', {}); new = value.get('project_files', {})
    f.require(request['installed_input'] != request['recovery_input']
        and {k: v for k, v in original.items() if k != 'project_files'} ==
            {k: v for k, v in value.items() if k != 'project_files'}
        and original.get('home') == str(home) and value['product']['runtime'] == {'enabled': False}
        and set(old) == set(new) and allowed <= set(old)
        and all(new[k] == sha for k, sha in old.items() if k not in allowed)
        and all(new[k] != old[k] for k in allowed),
        'ordinary_keyless_only_reviewed_source_delta_required')
    _, donors = budget.call(f.spec_checked, value, cli_only=True)
    marker = f.read_json(f.pin(request['root_marker']))
    receipt = f.read_json(f.pin(request['source_receipt']))
    stamp = f.read_json(f.pin(request['stamp']))
    f.require(marker.get('schema') == f.SCHEMA and marker.get('home') == str(home)
        and marker.get('source') == str(source) and marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
        and marker.get('runtime_ready') is False
        and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('input_sha256') == request['installed_input']['sha256']
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and receipt.get('schema') == 'friday.hermes-source.v1'
        and len(receipt.get('files', {})) == 17682 and len(receipt.get('layers', [])) == 77
        and len(marker.get('plugin_files', {})) == 45 and len(request['history']) == 428
        and stamp.get('schemaVersion') == 2 and stamp.get('distribution') == 'friday-rework'
        and stamp.get('payload') == 'bootstrap'
        and stamp.get('fridaySource') == {'baseTree': receipt.get('base_tree'), 'layers': receipt.get('layers')},
        'ordinary_keyless_native77_project3_identity_required')
    budget.call(f.composition_checked, original, source, receipt, donors['hermes'])
    budget.call(f.composition_checked, value, source, receipt, donors['hermes'])
    plugins = {k: v for k, v in old.items() if k.startswith('plugins/friday_rework/')}
    f.require(marker['plugin_files'] == plugins, 'ordinary_keyless_plugin_marker_changed')
    ordinary.checked_plugin_inventory(home, plugins)
    for ref in request['history']:
        path = budget.call(f.pin, ref)
        f.require(path.is_relative_to(home / 'preparation'), 'ordinary_keyless_foreign_history')
    for name, ref in request['reports'].items():
        path = budget.call(f.pin, ref)
        f.require(path.is_relative_to(home / 'preparation') and path.name == NAMES[name],
            'ordinary_keyless_foreign_report')
    for name, sha in marker['profile_files'].items():
        f.require(f.digest(f.owned_file(home / name, private=True)) == sha,
            'ordinary_keyless_root_profile_changed')
    f.native_packages(source)
    return value, marker, donors


def _keyless_admission(request, home, profile_home, config, attachment):
    """Retain the existing admitted gen1 home and its disabled runtime."""
    from hermes_cli import friday_user_scope as user, friday_product_access as access
    from hermes_cli.friday_ordinary_gateway import check
    from hermes_cli.plugins_state import _plugin_data_namespace
    from hermes_cli.config import require_readable_config_before_write
    check(home, role=False)
    binding = request['binding']; settings = configuration_settings(config)
    f.require(settings['runtime'] == {'enabled': False}
        and [b for b in settings['user_isolation']['bindings']
            if b['runtime_profile'] == request['profile']] == [binding]
        and f.pin(request['access_state']) == home / 'plugin-data' /
            _plugin_data_namespace('friday_rework', '') / 'state.json',
        'ordinary_keyless_root_binding_changed')
    principal = tuple(binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))
    key = access.principal_id(*principal)
    state = access.validate_access(f.read_json(f.pin(request['access_state']))[access.KEY])
    row = state['users'].get(key)
    f.require(row is not None and row['enabled'] is True and row['role'] == 'user'
        and row['generation'] == request['generation']
        and tuple(row[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')) == principal,
        'ordinary_keyless_original_access_changed')
    own = require_readable_config_before_write(profile_home / 'config.yaml')
    own_settings = configuration_settings(own)
    f.require(own_settings['runtime'] == {'enabled': False} and not own_settings.get('worker_requirements'),
        'ordinary_keyless_user_workers_must_remain_off')
    proof = f.read_json(f.pin(request['onboarding']))
    f.require(proof.get('config_sha256') == request['configuration']['sha256']
        and proof.get('binding_sha256') == user._fingerprint(binding)
        and proof.get('authorization_home') == str(home), 'ordinary_keyless_original_proof_changed')
    user.check_onboarding_home(home, profile_home, binding)
    info = profile_home.stat()
    with user.authority(profile_home):
        user.UserScope(home, profile_home, request['profile'], principal, dict(binding),
            (info.st_dev, info.st_ino), request['generation']).check()
    template = settings['onboarding']['templates']['friday-local']
    f.require(set(attachment) == {'template', 'template_sha256', 'installation_config_sha256',
        'config_sha256', 'proof', 'marker', 'binding_sha256', 'generation', 'runtimes',
        'a0_network', 'required_names'} and attachment['template'] == 'friday-local'
        and attachment['template_sha256'] == user._fingerprint(template)
        and attachment['installation_config_sha256'] == f.digest(f.owned_file(home / 'config.yaml', private=True))
        and attachment['config_sha256'] == proof['config_sha256']
        and attachment['proof'] == request['onboarding'] and attachment['marker'] == request['user_marker']
        and attachment['binding_sha256'] == user._fingerprint(binding)
        and attachment['generation'] == request['generation']
        and set(attachment['runtimes']) == {'dsh', 'a0'}, 'ordinary_keyless_original_attachment_changed')
    return own


def recover_keyless(request, request_path, budget):
    """One explicit, consumed repair; never qualify, start or enable a worker."""
    _keyless_request(request)
    started = time.monotonic()
    f.require(0 < budget.deadline - started <= request['seconds'],
        'ordinary_keyless_original_maintenance_deadline_required')
    # Stop proof and restoration retain ten seconds of the SAME original
    # maintenance clock. Useful work cannot consume that cleanup allowance.
    original_budget = budget
    from scripts.install_containment import Budget
    budget = Budget(request['seconds'], started=original_budget.deadline - request['seconds'],
        deadline=original_budget.deadline - 10)
    home = f.directory(f.canonical(request['home']))
    f.require(os.environ.get('HERMES_HOME') == str(home), 'ordinary_keyless_exact_environment_required')
    profile_home = f.directory(home / 'profiles' / request['profile'])
    parent = f.directory(home / 'preparation')
    request_path = f.canonical(str(request_path))
    request_state = ordinary.update_file_state(request_path)
    f.owned_file(request_path, private=True)
    f.require(f.read_json(request_path) == request, 'ordinary_keyless_request_changed')
    paths = {'root_marker': home / f.MARKER, 'source_receipt': home / 'hermes-agent.source.json',
        'stamp': home / 'hermes-agent/install-stamp.json', 'root_configuration': home / 'config.yaml',
        'root_profile': home / 'FRIDAY-PROFILE.json', 'onboarding': profile_home / '.friday-onboarding.json',
        'user_marker': profile_home / '.friday-user-scope.json', 'configuration': profile_home / 'config.yaml',
        'attachment': profile_home / 'workers/attachment.json'}
    refs = {k: v for k, v in request.items() if type(v) is dict and set(v) == {'path', 'sha256'}}
    refs.update({'preparation-' + k: v for k, v in request['preparations'].items()})
    refs.update({'report-' + k: v for k, v in request['reports'].items()})
    refs.update({'history-' + str(i): v for i, v in enumerate(request['history'])})
    pinned = {}
    for name, ref in refs.items():
        path = budget.call(f.pin, ref)
        if name in paths: f.require(path == paths[name], 'ordinary_keyless_exact_paths_required')
        if name in paths and name not in ('source_receipt', 'stamp'):
            f.owned_file(path, private=True)
        if name.startswith('preparation-'):
            f.require(path == profile_home / 'workers' / name[12:] / 'runtime-input.json',
                'ordinary_keyless_exact_preparation_path_required')
        pinned[name] = ordinary.update_file_state(path)
    f.require(len({ref['path'] for ref in request['history']}) == len(request['history']),
        'ordinary_keyless_duplicate_history_refused')
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(fd); linked = home.lstat()
        f.require((info.st_dev, info.st_ino) == (linked.st_dev, linked.st_ino),
            'ordinary_keyless_home_identity_changed')
        tx = parent / ('ordinary-keyless-recovery-' + request['recovery_id'])
        f.require(not os.path.lexists(tx), 'ordinary_keyless_recovery_consumed_no_retry')
        # The failed experiment is a second dedup key, even with a new recovery ID.
        for previous in parent.glob('ordinary-keyless-recovery-*'):
            f.directory(previous)
            intent = f.read_json(previous / 'intent.json')
            f.require(intent.get('failure') != request['failure'], 'ordinary_keyless_failure_already_consumed')
        value, marker, donors = _keyless_source_inputs(request, home, budget)
        from hermes_cli.config import require_readable_config_before_write
        config = require_readable_config_before_write(home / 'config.yaml')
        attachment = f.read_json(paths['attachment'])
        own = _keyless_admission(request, home, profile_home, config, attachment)
        failed = _keyless_failed_tree(request, profile_home)
        budget.call(reusable, value, home, request['reports'], donors, budget)
        from plugins.friday_rework.worker_provision import preparation, prepare_inputs
        from plugins.friday_rework.user_worker_join import validate_installation_inputs
        from hermes_cli import friday_user_scope as user
        declarations = configuration_settings(config)['onboarding']['templates']['friday-local']['worker_inputs']
        validate_installation_inputs(declarations)
        target = home / 'harness/friday-web-keyless.mjs'
        helper_name = 'plugins/friday_rework/adapters/dsh_keyless_web.mjs'
        helper = f.owned_file(f.ROOT / helper_name)
        helper_pin = {'path': str(target), 'sha256': value['project_files'][helper_name]}
        f.require(f.digest(helper) == helper_pin['sha256'] and not os.path.lexists(target)
            and declarations['workers']['dsh']['dsh']['web']['profile'] == 'exa-keyless'
            and declarations['workers']['dsh']['dsh']['payload_root'] == str(home / 'harness'),
            'ordinary_keyless_exact_missing_helper_required')
        metadata = {}
        for kind, ref in request['preparations'].items():
            row, runtime = preparation(profile_home, request['profile'], kind, ref)
            f.require(runtime == attachment['runtimes'][kind]
                and row.get('attachment') == request['attachment'] and row['generation'] == request['generation']
                and row['principal_binding_sha256'] == user._fingerprint(request['binding']),
                'ordinary_keyless_original_preparation_changed')
            metadata[kind] = row
        old_native = declarations['workers']['dsh']['dsh']['native_files']
        f.require(old_native == attachment['runtimes']['dsh']['dsh']['native_files']
            and all(row['path'] != str(target) for row in old_native),
            'ordinary_keyless_original_native_inventory_changed')
        changed = copy.deepcopy(config)
        configuration_settings(changed)['onboarding']['templates']['friday-local'][
            'worker_inputs']['workers']['dsh']['dsh']['native_files'].append(helper_pin)
        new_attachment = copy.deepcopy(attachment)
        new_attachment['runtimes']['dsh']['dsh']['native_files'].append(helper_pin)
        new_attachment['template_sha256'] = user._fingerprint(
            configuration_settings(changed)['onboarding']['templates']['friday-local'])
        import hermes_yaml
        changed_raw = hermes_yaml.safe_dump(changed, allow_unicode=True, sort_keys=False).encode()
        new_attachment['installation_config_sha256'] = f.digest(changed_raw)
        attachment_raw = ordinary.encoded(new_attachment)
        attachment_pin = {'path': str(paths['attachment']), 'sha256': f.digest(attachment_raw)}
        new_metadata = copy.deepcopy(metadata)
        for kind, row in new_metadata.items():
            row['attachment'] = attachment_pin
            if kind == 'dsh': row['runtime']['dsh']['native_files'].append(helper_pin)
        updated = copy.deepcopy(marker)
        updated['input_sha256'] = request['recovery_input']['sha256']
        updated['ordinary_gateway']['operator_entry'] = {'input': request['recovery_input'],
            'script': {'path': str(f.ROOT / 'scripts/friday_native.py'),
                'sha256': value['project_files']['scripts/friday_native.py']}}
        from hermes_cli.friday_ordinary_gateway import normalized_configuration
        from hermes_cli.config_effective import _effective
        updated['ordinary_gateway']['configuration_sha256'] = normalized_configuration(_effective(changed))
        updated['profile_files']['config.yaml'] = f.digest(changed_raw)
        payloads = {'config.yaml': changed_raw,
            str(paths['attachment'].relative_to(home)): attachment_raw,
            **{str(Path(request['preparations'][kind]['path']).relative_to(home)): ordinary.encoded(row)
                for kind, row in new_metadata.items()}, f.MARKER: ordinary.encoded(updated),
            str(target.relative_to(home)): helper}
        saved = {name: ordinary.update_file_state(home / name) for name in payloads}
        f.require(saved[str(target.relative_to(home))] is None,
            'ordinary_keyless_helper_must_be_absent')
        retained = {path: ordinary.update_file_state(path) for base in (home, profile_home)
            for path in (base / '.env', base / 'auth.json')}
        def unchanged(*, published=False):
            budget.check()
            f.require(ordinary.same_update_file(request_path, request_state), 'ordinary_keyless_request_changed')
            affected = set(payloads) if published else set()
            for name, state in pinned.items():
                path = Path(refs[name]['path'])
                if (path.is_relative_to(home) and str(path.relative_to(home)) in affected) or (
                        published and name == 'failure'): continue
                f.require(ordinary.same_update_file(path, state), 'ordinary_keyless_pinned_identity_changed')
            budget.call(f.spec_checked, value, cli_only=True)
            ordinary.checked_plugin_inventory(home, marker['plugin_files'])
            f.require(all(ordinary.same_update_file(path, state) for path, state in retained.items()),
                'ordinary_keyless_credentials_changed')
        from scripts.dsh_prepare import StopUnconfirmed
        with ordinary.stopped_consumers(home, request['native_unit'], original_budget) as prove, \
                ordinary.retained_build_lock(home / 'hermes-agent') as build_prove, \
                ordinary.retained_first_contact_config_lock(home / 'config.yaml'), \
                ordinary.retained_first_contact_config_lock(profile_home / 'config.yaml'):
            unchanged(); prove(); build_prove()
            f.require(_keyless_failed_tree(request, profile_home) == failed,
                'ordinary_keyless_failed_tree_identity_changed')
            f.require(all(ordinary.same_update_file(home / name, before) for name, before in saved.items()),
                'ordinary_keyless_beforeimage_changed')
            tx.mkdir(mode=0o700)
            intent = {'schema': KEYLESS_RECOVERY_SCHEMA, 'state': 'CONSUMED_NO_RETRY',
                'recovery_id': request['recovery_id'], 'request_sha256': f.digest(request_state['data']),
                'failure': request['failure'], 'original_attempt': failed['original_attempt'],
                'maintenance_clock': {'started_mono': started, 'deadline_mono': original_budget.deadline,
                    'useful_deadline_mono': budget.deadline, 'cleanup_seconds': 10, 'seconds': request['seconds']},
                'transition': request['transition'], 'runtime_authority': 'NOT_GRANTED',
                'consumers_started': False, 'workers_enabled': False, 'resume_allowed': False,
                'archive_mapping': {str(profile_home / 'workers/qualification'): str(tx / 'failed-qualification')},
                'before': {name: None if row is None else {'sha256': f.digest(row['data']), 'mode': row['mode'],
                    'identity': list(row['identity'])} for name, row in saved.items()}}
            ordinary.write(tx / 'intent.json', ordinary.encoded(intent))
            owned = {}; archived = False
            try:
                before_dir = tx / 'before'; before_dir.mkdir(mode=0o700)
                for name, row in saved.items():
                    if row is None: continue
                    ordinary.private_parents(before_dir, name)
                    ordinary.write(before_dir / name, row['data'], row['mode'])
                # Keep immutable byte preimages even if a later rollback returns
                # the original failed tree to its canonical consumed location.
                failure_before = tx / 'failed-before'; failure_before.mkdir(mode=0o700)
                for name, row in failed['files'].items():
                    ordinary.private_parents(failure_before, name)
                    ordinary.write(failure_before / name, row['data'], row['mode'])
                ordinary.write(tx / 'before-mapping.json', ordinary.encoded({str(home / name):
                    str(before_dir / name) for name, row in saved.items() if row is not None}))
                ordinary.sync_directory(tx); ordinary.sync_directory(parent)
                unchanged(); prove(); build_prove()
                folder = profile_home / 'workers/qualification'; archive = tx / 'failed-qualification'
                f.require(_keyless_failed_tree(request, profile_home) == failed,
                    'ordinary_keyless_failed_tree_identity_changed')
                f.require(not os.path.lexists(archive), 'ordinary_keyless_archive_target_occupied')
                os.rename(folder, archive); archived = True
                ordinary.sync_directory(folder.parent); ordinary.sync_directory(tx)
                f.require(_keyless_failed_tree(request, profile_home, folder=archive) == failed,
                    'ordinary_keyless_archive_identity_changed')
                # The absent-only helper gets the same exact inode accounting as metadata.
                order = [str(target.relative_to(home)), *[n for n in payloads if n != str(target.relative_to(home))]]
                for name in order:
                    budget.check(); prove(); build_prove()
                    ordinary.publish_update_file(home / name, payloads[name],
                        0o400 if saved[name] is None else saved[name]['mode'], saved[name], owned, name)
                unchanged(published=True)
                f.require(all(ordinary.same_update_file(home / name, owned[name]) for name in payloads),
                    'ordinary_keyless_published_identity_changed')
                _keyless_admission(request, home, profile_home, changed, new_attachment)
                validate_installation_inputs(configuration_settings(changed)['onboarding']['templates'][
                    'friday-local']['worker_inputs'])
                for kind in ('dsh', 'a0'):
                    ref = reference(Path(request['preparations'][kind]['path']))
                    row, runtime = preparation(profile_home, request['profile'], kind, ref)
                    f.require(row == new_metadata[kind] and runtime == new_attachment['runtimes'][kind],
                        'ordinary_keyless_repaired_preparation_changed')
                    budget.call(prepare_inputs, profile_home, request['profile'], kind, runtime, own,
                        a0_network=new_attachment['a0_network'] if kind == 'a0' else None,
                        tools=request['binding']['tools'])
                f.require(_keyless_failed_tree(request, profile_home, folder=archive) == failed
                    and not os.path.lexists(folder), 'ordinary_keyless_archive_identity_changed')
                prove(); build_prove(); unchanged(published=True)
                budget.call(f.composition_checked, value, home / 'hermes-agent',
                    f.read_json(Path(request['source_receipt']['path'])), donors['hermes'])
                result = {'state': 'REPAIRED_CONSUMERS_STOPPED_WORKERS_OFF_NEW_RUNTIME_NOT_AUTHORIZED',
                    'ready': False, 'consumers_started': False, 'workers_enabled': False,
                    'runtime_acceptance': 'NOT_GRANTED', 'new_runtime_authority': 'NOT_GRANTED',
                    'original_attempt': failed['original_attempt'], 'old_attempt_retry_authorized': False,
                    'archive_mapping': intent['archive_mapping'], 'recovery_id': request['recovery_id'],
                    'request_sha256': intent['request_sha256'], 'resume_allowed': False}
                ordinary.write(tx / 'committed.json', ordinary.encoded(result)); ordinary.sync_directory(tx)
                return result
            except BaseException as primary:
                try:
                    prove(); build_prove()
                    ordinary.restore_update_files(home, saved, owned)
                    if archived:
                        f.require(not os.path.lexists(folder) and
                            _keyless_failed_tree(request, profile_home, folder=archive) == failed,
                            'ordinary_keyless_archive_restore_ownership_changed')
                        os.rename(archive, folder)
                        ordinary.sync_directory(folder.parent); ordinary.sync_directory(tx)
                    ordinary.write(tx / 'failure.json', ordinary.encoded({'state': 'ROLLED_BACK_CONSUMED_NO_RETRY',
                        'original_attempt': failed['original_attempt'], 'retry_authorized': False,
                        'runtime_authority': 'NOT_GRANTED', 'diagnostic': f.retained_diagnostic(primary, 'ordinary-keyless-recovery')}))
                    ordinary.sync_directory(tx)
                except BaseException as secondary:
                    f.remember_secondary(primary, secondary)
                    raise StopUnconfirmed('ordinary keyless recovery ownership/rollback requires reconciliation') from primary
                raise
    except f.Refused as exc:
        if exc.reason == 'ordinary_update_native_lock_release_unconfirmed':
            from scripts.dsh_prepare import StopUnconfirmed
            raise StopUnconfirmed('ordinary keyless recovery native custody release requires reconciliation') from exc
        raise
    finally:
        os.close(fd)


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
