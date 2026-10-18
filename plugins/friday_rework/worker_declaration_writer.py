"""One native stopped worker declaration transaction; never starts a worker.

The source proposal is data. Only the existing root native operator, with
current source/build/PM and all-consumer stop custody, can publish it. Historical
attempts and journals are retained; a failed request cannot obtain a new clock.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

from .worker_declarations import (
    DeclarationError, _read_reference, _reference, _same, fingerprint,
    load_declaration_source, plan_declaration_delta, require, _at, _replace,
    TEMPLATE_INPUTS,
    validate_declaration_source,
)

APPLY_SCHEMA = 'friday.worker-declarations.apply.v1'
APPLY_FIELDS = frozenset({'schema', 'seconds', 'home', 'profile',
    'previous_input', 'current_input', 'native_unit', 'before', 'retained',
    'declaration_source', 'launcher_source', 'clock', 'native_pm'})
CLEANUP_RESERVE = 20


def _request_snapshot(reference):
    path = _reference(reference)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid()
            and first.st_nlink == 1 and stat.S_IMODE(first.st_mode) == 0o600
            and first.st_size <= 32 * 1024**2, 'worker_declaration_request_identity_changed')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(32 * 1024**2 + 1)
        keys = ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode',
            'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(data) <= 32 * 1024**2
            and hashlib.sha256(data).hexdigest() == reference['sha256']
            and all(getattr(first, key) == getattr(os.fstat(fd), key)
                == getattr(path.lstat(), key) for key in keys),
            'worker_declaration_request_identity_changed')
        return {'data': data, 'mode': 0o600, 'identity': tuple(getattr(first, key)
            for key in ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode'))}
    finally:
        os.close(fd)


def _new_journal(path, data):
    """Keep the created descriptor's identity; a reread cannot invent ownership."""
    from scripts import friday_ordinary_install as ordinary
    path = Path(path)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        parent_info = os.fstat(parent)
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            require(count > 0, 'worker_declaration_journal_write_failed')
            view = view[count:]
        os.fsync(fd)
        info = os.fstat(fd)
        created = {'data': data, 'mode': 0o600, 'identity': tuple(getattr(info, key)
            for key in ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode'))}
        require(ordinary.same_update_file(path, created, parent),
            'worker_declaration_created_journal_changed')
        named = path.parent.lstat()
        require((named.st_dev, named.st_ino, named.st_mode, named.st_uid)
            == (parent_info.st_dev, parent_info.st_ino, parent_info.st_mode, parent_info.st_uid),
            'worker_declaration_journal_parent_changed')
        os.fsync(parent)
        return created
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def validated_clock(reference, seconds):
    """Use the pinned original boot/monotonic interval, without a fresh start."""
    require(type(seconds) is int and 30 <= seconds <= 180,
        'worker_declaration_original_finite_budget_required')
    clock = _read_reference(reference)
    require(type(clock) is dict and set(clock) == {'schema', 'boot_id',
        'started_mono', 'deadline_mono', 'seconds'}
        and clock['schema'] == 'friday.worker-declarations.clock.v1'
        and type(clock['seconds']) is int and clock['seconds'] == seconds,
        'worker_declaration_original_clock_required')
    start, end = clock['started_mono'], clock['deadline_mono']
    require(type(start) in (int, float) and type(end) in (int, float)
        and math.isfinite(start) and math.isfinite(end) and start >= 0
        and abs(end - start - seconds) < 0.001,
        'worker_declaration_original_clock_interval_changed')
    require(clock['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'worker_declaration_original_boot_changed')
    now = time.monotonic()
    require(start <= now and now + CLEANUP_RESERVE < end,
        'worker_declaration_original_clock_expired')
    return clock


def validate_installation_delta(previous, current, plan):
    """No source/PM/credentials/budget change rides this configuration writer.

    Source promotion, including this code and the launcher, must have completed
    under its own supported native transaction. Both input generations contain
    the identical already-installed source inventory. The installation input
    also carries the matching policy/endpoints consumed by worker_install's
    real validator; these three leaves derive from the same typed declaration.
    """
    require(type(previous) is dict and type(current) is dict
        and type(previous.get('product')) is dict
        and type(current.get('product')) is dict,
        'worker_declaration_native_inputs_required')
    left, right = copy.deepcopy(previous), copy.deepcopy(current)
    require('a0_deployment' in left['product'] and 'a0_deployment' in right['product'],
        'worker_declaration_input_deployment_required')
    before = left['product'].pop('a0_deployment')
    after = right['product'].pop('a0_deployment')
    inputs = _at(plan['root_config'], TEMPLATE_INPUTS)
    for path, source in (
        (('worker_install', 'a0', 'policy'), ('workers', 'a0', 'a0', 'policy')),
        (('worker_install', 'a0', 'network', 'policy'), ('a0_network', 'policy')),
        (('worker_install', 'a0', 'network', 'endpoints'), ('a0_network', 'endpoints')),
    ):
        original = _at(left, path)
        require(_same(_at(right, path), _at(inputs, source)),
            'worker_declaration_installation_network_join_changed')
        _replace(right, path, original)
    require(_same(left, right) and not _same(before, after),
        'worker_declaration_unrelated_installation_delta')
    require(_same(after, plan['root_config']['a0_deployment']),
        'worker_declaration_current_input_deployment_changed')
    # The ordinary contract and protected compressor remain byte-semantic
    # complements. Never mutate runtime declarations or worker_install budgets.
    require(_same(previous['product'].get('runtime'), {'enabled': False})
        and _same(current['product'].get('runtime'), {'enabled': False}),
        'worker_declaration_runtime_must_remain_disabled')


def prepare_afterimages(authority, plan, stage):
    """Build five private afterimages with real native serializers/resealers.

    This helper grants no authority and publishes no live file. The owning
    apply entry retains StoppedOperator custody before and after invoking it.
    """
    from scripts import friday_ordinary_install as ordinary
    from plugins.friday_rework.onboarding import (
        prepare_admin_config_edit, finish_admin_config_edit, validate_template)
    from hermes_cli import friday_user_scope as user
    from hermes_cli.config import atomic_config_write
    from hermes_cli.config_effective import load_user_config_effective
    from hermes_cli.friday_ordinary_gateway import normalized_configuration
    from hermes_cli.friday_credential_admission import local_route, profile_policy
    from hermes_yaml import safe_load

    f = ordinary.api()
    home, profile_home = authority.home, authority.profile_home
    prefix = str(profile_home.relative_to(home)) + '/'
    root_cfg, own_cfg = plan['root_config'], plan['profile_config']
    validate_installation_delta(authority.previous, authority.current, plan)
    templates = root_cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    for template in templates.values():
        validate_template(template)
    prepared = prepare_admin_config_edit(profile_home, own_cfg)
    require(prepared is not None and prepared['marker'] is not None,
        'worker_declaration_existing_profile_reseal_required')
    original_proof = json.loads(authority.before[prefix + user.ONBOARDING]['data'])
    require(_same(prepared['proof'], original_proof),
        'worker_declaration_native_profile_proof_changed')
    require(prepared['receipt_sha256'] == hashlib.sha256(
        authority.before[prefix + user.ONBOARDING]['data']).hexdigest()
        and prepared['marker_sha256'] == hashlib.sha256(
            authority.before[prefix + user.MARKER]['data']).hexdigest(),
        'worker_declaration_native_profile_reseal_cas_changed')
    stage = Path(stage)
    f.directory(stage)
    require(not list(stage.iterdir()), 'worker_declaration_empty_stage_required')
    for name, cfg in (('config.yaml', root_cfg), (prefix + 'config.yaml', own_cfg)):
        ordinary.private_parents(stage, name)
        atomic_config_write(stage / name, cfg)
        require(_same(safe_load(f.owned_file(stage / name, private=True)), cfg),
            'worker_declaration_native_serialization_changed')
    own_stage = stage / prefix
    for name in (user.ONBOARDING, user.MARKER):
        ordinary.write(own_stage / name, authority.before[prefix + name]['data'])
    # The real signer operates only on staging copies. Live receipts always go
    # through the same owned-inode publisher as the two configurations.
    finish_admin_config_edit(own_stage, prepared)
    updated = copy.deepcopy(authority.marker)
    updated['input_sha256'] = authority.request['current_input']['sha256']
    updated['profile_files']['config.yaml'] = f.digest(
        f.owned_file(stage / 'config.yaml', private=True))
    phase = updated['ordinary_gateway']
    phase['configuration_sha256'] = normalized_configuration(
        load_user_config_effective(stage / 'config.yaml', fail_closed=True))
    phase['operator_entry']['input'] = copy.deepcopy(authority.request['current_input'])
    # Preserve source receipt/stamp/operator script/credentials/FRIDAY-PROFILE,
    # all original attempts and every unrelated native marker field.
    ordinary.write(stage / f.MARKER, ordinary.encoded(updated))
    local_route(root_cfg)
    local_route(own_cfg)
    # This validator needs the unchanged profile contract in its synthetic
    # staging home. It is retained, never part of the live publication set.
    ordinary.write(stage / 'FRIDAY-PROFILE.json',
        f.owned_file(home / 'FRIDAY-PROFILE.json', private=True))
    profile_policy(stage, root_cfg)
    result = {name: ordinary.update_file_state(stage / name)
        for name in authority.before}
    require(len(result) == 5 and all(state is not None and state['mode'] == 0o600
        for state in result.values()), 'worker_declaration_exact_five_afterimages_required')
    for directory in sorted((p for p in stage.rglob('*') if p.is_dir()),
            key=lambda p: len(p.parts), reverse=True):
        f.directory(directory)
        ordinary.sync_directory(directory)
    ordinary.sync_directory(stage)
    return result


def _native_final_check(authority):
    """Read real native consumers, never grant readiness from this journal."""
    from scripts import friday_ordinary_install as ordinary
    from hermes_cli import friday_user_scope as user
    from hermes_cli.friday_ordinary_gateway import check
    from hermes_cli.friday_product_access import current_access, principal_id
    f = ordinary.api()
    with user.authority(authority.home):
        check(authority.home, role=False)
        key = principal_id(*(authority.binding[k] for k in
            ('platform', 'transport_profile', 'account_id', 'user_id')))
        row = current_access()['users'].get(key)
    require(_same(row, authority.row), 'worker_declaration_current_generation_changed')
    identity = authority.profile_home.stat()
    principal = tuple(authority.binding[k] for k in
        ('platform', 'transport_profile', 'account_id', 'user_id'))
    with user.authority(authority.profile_home):
        user.UserScope(authority.home, authority.profile_home,
            authority.profile_home.name, principal, dict(authority.binding),
            (identity.st_dev, identity.st_ino), row['generation']).check()
    f.inspect(authority.current, authority.request['current_input']['sha256'])


def _planned_delta(authority):
    """Reject foreign/stale data before consumption; repeat inside native locks."""
    from hermes_cli.config import fast_safe_load
    from hermes_cli.friday_product_access import principal_id
    request = authority.request
    bundle, inputs, identity = load_declaration_source(request['declaration_source'])
    prefix = str(authority.profile_home.relative_to(authority.home)) + '/'
    root_cfg = fast_safe_load(authority.before['config.yaml']['data'].decode('utf-8-sig'))
    own_cfg = fast_safe_load(authority.before[prefix + 'config.yaml']['data'].decode('utf-8-sig'))
    validate_declaration_source(request['declaration_source'], root_cfg, own_cfg,
        root_home=authority.home, profile_home=authority.profile_home)
    plan = plan_declaration_delta(root_cfg, own_cfg, inputs, identity, bundle)
    require(plan['principal'] == principal_id(*(authority.binding[key] for key in
        ('platform', 'transport_profile', 'account_id', 'user_id')))
        and plan['generation'] == authority.row['generation'],
        'worker_declaration_native_identity_join_changed')
    require(inputs['workers']['a0']['a0']['launcher']['sha256']
        == request['launcher_source']['sha256'],
        'worker_declaration_current_launcher_join_changed')
    validate_installation_delta(authority.previous, authority.current, plan)
    return plan


def apply_declarations(request, *, request_path=None, request_sha256=None):
    """Publish one finite, native stopped transaction; no automatic reprepare."""
    require(type(request) is dict and set(request) == APPLY_FIELDS
        and request.get('schema') == APPLY_SCHEMA,
        'worker_declaration_exact_apply_request_required')
    reference = {'path': str(request_path) if request_path is not None else None,
        'sha256': request_sha256}
    _reference(reference)
    request_state = _request_snapshot(reference)
    authenticated = _read_reference(reference)
    require(_same(authenticated, request), 'worker_declaration_request_cas_changed')
    clock = validated_clock(request['clock'], request['seconds'])
    from scripts.install_containment import Budget
    budget = Budget(request['seconds'], started=clock['started_mono'],
        deadline=clock['deadline_mono'])
    from .stopped_operator import StoppedOperator
    from scripts import friday_ordinary_install as ordinary
    from scripts.dsh_prepare import StopUnconfirmed
    f = ordinary.api()
    authority = StoppedOperator(request, budget, request_reference=reference)
    # Retain original request inode as well as raw bytes: a same-body replacement
    # is an edit, not fresh authority. Source refs and clock are likewise retained
    # by StoppedOperator for the entire native operation.
    def request_unchanged():
        require(ordinary.same_update_file(Path(request_path), request_state),
            'worker_declaration_request_identity_changed')
    request_unchanged()
    authority.preflight()
    preflight_plan = _planned_delta(authority)
    authority.before_unchanged()
    request_unchanged()
    authority.consume()  # Durable one-shot directory BEFORE native claims.
    owned = {}
    committed = False
    after = None
    commit_state = None
    try:
        with authority:
            authority.before_unchanged()
            request_unchanged()
            prefix = str(authority.profile_home.relative_to(authority.home)) + '/'
            plan = _planned_delta(authority)
            require(_same(plan, preflight_plan), 'worker_declaration_preflight_plan_changed')
            authority.before_unchanged()
            request_unchanged()
            stage = authority.tx / 'stage'
            stage.mkdir(mode=0o700)
            before_dir = authority.tx / 'before'
            before_dir.mkdir(mode=0o700)
            for name, state in authority.before.items():
                ordinary.private_parents(before_dir, name)
                ordinary.write(before_dir / name, state['data'], state['mode'])
            for directory in sorted((p for p in before_dir.rglob('*') if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
                ordinary.sync_directory(directory)
            ordinary.sync_directory(before_dir)
            after = prepare_afterimages(authority, plan, stage)
            ordinary.sync_directory(authority.tx)
            authority.before_unchanged()
            request_unchanged()
            # Existing directory-descriptor implementation prevents redirected
            # publication/rollback through a replaced parent path.
            with ordinary.SourceUpdateDirectories(authority.home, authority.before, []) as directories:
                try:
                    order = ['config.yaml', prefix + 'config.yaml',
                        prefix + '.friday-onboarding.json', prefix + '.friday-user-scope.json', f.MARKER]
                    require(set(order) == set(authority.before),
                        'worker_declaration_publication_set_changed')
                    for name in order:
                        authority.prove()
                        directories.prove()
                        request_unchanged()
                        budget.check(reserve=CLEANUP_RESERVE)
                        require(all(ordinary.same_update_file(authority.home / key,
                            owned.get(key, value), directories.parent_fd(key))
                            for key, value in authority.before.items()),
                            'worker_declaration_publication_cas_changed')
                        require(ordinary.same_update_file(stage / name, after[name]),
                            'worker_declaration_stage_identity_changed')
                        ordinary.publish_update_file(authority.home / name, after[name]['data'],
                            authority.before[name]['mode'], authority.before[name], owned, name,
                            parent_fd=directories.parent_fd(name))
                    authority.prove()
                    directories.prove()
                    request_unchanged()
                    budget.call(_native_final_check, authority)
                    authority.source_unchanged()
                    authority.prove()
                    require(all(ordinary.same_update_file(authority.home / key, owned[key],
                        directories.parent_fd(key)) for key in authority.before),
                        'worker_declaration_commit_identity_changed')
                    result = {'state': 'WORKER_DECLARATIONS_REBOUND_CONSUMERS_STOPPED',
                        'ready': False, 'workers_enabled': False, 'consumers_started': False,
                        'database_changed': False, 'native_migration': 'IMPLEMENTED',
                        'runtime_acceptance': 'NOT_GRANTED', 'automatic_prepare': False,
                        'request_sha256': request_sha256, 'clock': request['clock'],
                        'previous_input': request['previous_input'], 'current_input': request['current_input'],
                        'semantic_changes': plan['semantic_changes'],
                        'after': {key: f.digest(value['data']) for key, value in after.items()},
                        'original_attempt_consumed': True}
                    commit_state = _new_journal(authority.tx / 'committed.json', ordinary.encoded(result))
                    require(commit_state is not None and commit_state['data'] == ordinary.encoded(result),
                        'worker_declaration_commit_receipt_changed')
                    committed = True
                except BaseException as original:
                    # Never roll back once a commit may exist. An uncertain
                    # commit or released authority requires reconciliation.
                    if committed or os.path.lexists(authority.tx / 'committed.json'):
                        raise StopUnconfirmed('worker declaration commit requires reconciliation') from original
                    try:
                        authority.prove(cleanup=True)
                        directories.prove()
                        request_unchanged()
                        ordinary.restore_update_files(authority.home, authority.before, owned,
                            directories=directories)
                        authority.prove(cleanup=True)
                        _native_rollback_check(authority)
                        _new_journal(authority.tx / 'rolled-back.json', ordinary.encoded({
                            'state': 'ROLLED_BACK_CONSUMED_NO_RETRY', 'ready': False,
                            'workers_enabled': False, 'clock': request['clock']}))
                    except BaseException as restoration:
                        f.remember_secondary(original, restoration)
                        raise StopUnconfirmed('worker declaration rollback requires reconciliation') from original
                    raise
        # Ownership release is part of the result. No reacquire or mutation
        # follows it. Drift here stays ambiguous rather than undoing a commit.
        authority.prove_released()
        request_unchanged()
        require(committed and all(ordinary.same_update_file(authority.home / key, owned[key])
            for key in authority.before)
            and ordinary.same_update_file(authority.tx / 'committed.json', commit_state),
            'worker_declaration_released_result_identity_changed')
        return result
    except BaseException as error:
        if committed:
            raise StopUnconfirmed('worker declaration committed outcome requires reconciliation') from error
        raise


def _native_rollback_check(authority):
    from scripts import friday_ordinary_install as ordinary
    from hermes_cli import friday_user_scope as user
    with user.authority(authority.home):
        ordinary.api().inspect(authority.previous,
            authority.request['previous_input']['sha256'])
