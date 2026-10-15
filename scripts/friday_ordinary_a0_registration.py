"""Finite installed ordinary A0 registration through the supported installer.

A separate native GNU180/user-service owner must invoke the registration phase.
Registration never starts/enables a daemon, changes an install marker or
configuration, resets an install clock, or grants worker/job authority.
"""
from __future__ import annotations

import copy
import fcntl
import json
import math
import os
from pathlib import Path
import re
import resource
import stat
import time

from scripts import friday_install as f
from scripts.install_containment import Budget

SCHEMA = 'friday.ordinary-a0-registration.v1'
CLOCK = 'friday.ordinary-a0-registration-clock.v1'
INTENT = 'friday.ordinary-a0-registration-intent.v1'
RECEIPT = 'friday.ordinary-a0-registration-receipt.v1'
SOURCE = 'scripts/friday_ordinary_a0_registration.py'
CAPS = {'memory.max': '2147483648', 'memory.swap.max': '0',
        'pids.max': '128', 'cpu.max': '200000 100000'}
PINS = ('current_input', 'registration_input', 'marker', 'source_receipt', 'configuration', 'profile')


def registration_clock():
    # Reuse only the native GNU birth observation, never an old CLI assignment.
    return dict(f.installed_cli_clock(), schema=CLOCK)


def clock_checked(clock):
    fields = {'schema', 'seconds', 'cleanup_seconds', 'started_mono', 'deadline_mono',
              'useful_deadline_mono', 'boot_id', 'gnu_pid', 'gnu_starttime_ticks'}
    f.require(type(clock) is dict and set(clock) == fields and clock['schema'] == CLOCK
              and type(clock['seconds']) is int and clock['seconds'] == 180
              and type(clock['cleanup_seconds']) is int and clock['cleanup_seconds'] == 30
              and all(type(clock[k]) in (int, float) and math.isfinite(clock[k]) for k in
                      ('started_mono', 'deadline_mono', 'useful_deadline_mono'))
              and clock['deadline_mono'] == clock['started_mono'] + 180
              and clock['useful_deadline_mono'] == clock['started_mono'] + 150
              and type(clock['gnu_pid']) is int and clock['gnu_pid'] > 1
              and type(clock['gnu_starttime_ticks']) is int and clock['gnu_starttime_ticks'] > 0,
              'ordinary_a0_original_registration_clock_required')
    return Budget(180, started=clock['started_mono'], deadline=clock['deadline_mono'])


def native_owner(request, clock):
    """Actual current finite native custody, independent of old installed scopes."""
    clock_checked(clock)
    f.require(os.getppid() == clock['gnu_pid'] and
              Path('/proc/sys/kernel/random/boot_id').read_text().strip() == clock['boot_id'] and
              clock['started_mono'] <= time.monotonic() < clock['useful_deadline_mono'] - 1,
              'ordinary_a0_native_owner_or_time_changed')
    proc = Path('/proc') / str(clock['gnu_pid'])
    raw = (proc / 'stat').read_text()
    binary = Path('/usr/bin/gnutimeout'); info = binary.stat()
    f.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
              and int(raw.rsplit(')', 1)[1].split()[19]) == clock['gnu_starttime_ticks']
              and (proc / 'exe').resolve() == binary
              and (proc / 'cmdline').read_bytes().split(b'\0')[1:4] ==
              [b'--signal=TERM', b'--kill-after=2s', b'180s'], 'ordinary_a0_native_gnu_birth_changed')
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    f.require(len(rows) == 1 and rows[0].startswith('0::/'), 'ordinary_a0_unified_cgroup_required')
    group = rows[0][3:]; unit = 'friday-rework-ordinary-a0-registration-' + request['request_id'] + '.service'
    f.require(group.rsplit('/', 1)[-1] == unit and request['unit'] == unit
              and '..' not in Path(group).parts
              and (proc / 'cgroup').read_text() == Path('/proc/self/cgroup').read_text(),
              'ordinary_a0_owned_native_scope_required')
    root = Path('/sys/fs/cgroup') / group.lstrip('/')
    f.require(all((root / k).read_text().strip() == v for k, v in CAPS.items())
              and os.sched_getaffinity(0) == os.sched_getaffinity(clock['gnu_pid']) == {0, 1}
              and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
              and resource.getrlimit(resource.RLIMIT_FSIZE) == (268435456, 268435456),
              'ordinary_a0_native_caps_required')
    busroot = f.directory(Path('/run/user') / str(os.getuid())); bus = busroot / 'bus'; info = bus.lstat()
    f.require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
              'ordinary_a0_owned_user_bus_required')
    from scripts.dsh_prepare import run
    from scripts import a0_runtime as runtime
    names = ('Id', 'InvocationID', 'ActiveState', 'SubState', 'MainPID', 'ControlPID', 'ControlGroup',
             'RuntimeMaxUSec', 'TimeoutStopUSec', 'KillMode', 'ExecMainStartTimestampMonotonic')
    text = run(['/usr/bin/systemctl', '--user', 'show', unit, '--property=' + ','.join(names)],
               f.ROOT, timeout=5, env=runtime.ENV, deadline=clock['useful_deadline_mono'])[0]
    pairs = [row.split('=', 1) for row in text.splitlines()]; seen = dict(pairs)
    f.require(len(pairs) == len(seen) == len(names) and set(seen) == set(names)
              and re.fullmatch('[0-9a-f]{32}', seen.get('InvocationID', ''))
              and seen == {'Id': unit, 'InvocationID': seen['InvocationID'], 'ActiveState': 'active',
                           'SubState': 'running', 'MainPID': str(clock['gnu_pid']), 'ControlPID': '0',
                           'ControlGroup': group, 'RuntimeMaxUSec': '2min 28s', 'TimeoutStopUSec': '30s',
                           'KillMode': 'control-group', 'ExecMainStartTimestampMonotonic':
                           seen['ExecMainStartTimestampMonotonic']}
              and re.fullmatch('[1-9][0-9]{0,19}', seen['ExecMainStartTimestampMonotonic'])
              and abs(int(seen['ExecMainStartTimestampMonotonic']) / 1000000 - clock['started_mono']) < .2,
              'ordinary_a0_actual_native_scope_required')
    return {'unit': unit, 'invocation_id': seen['InvocationID'], 'cgroup': group, 'caps': dict(CAPS)}


def installed(request, budget):
    fields = {'schema', 'request_id', 'seconds', 'home', 'unit', *PINS, 'history'}
    f.require(type(request) is dict and set(request) == fields and request['schema'] == SCHEMA
              and type(request['request_id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', request['request_id'])
              and type(request['seconds']) is int and request['seconds'] == 180
              and request['unit'] == 'friday-rework-ordinary-a0-registration-' + request['request_id'] + '.service',
              'ordinary_a0_explicit_registration_request_required')
    home = f.directory(f.canonical(request['home']))
    paths = {name: budget.call(f.pin, request[name]) for name in PINS}
    for name, path in {'marker': home / f.MARKER, 'source_receipt': home / 'hermes-agent.source.json',
                       'configuration': home / 'config.yaml', 'profile': home / 'FRIDAY-PROFILE.json'}.items():
        f.require(paths[name] == path, 'ordinary_a0_current_installed_paths_required')
    current = f.read_json(paths['current_input']); value = f.read_json(paths['registration_input'])
    old = copy.deepcopy(current); new = copy.deepcopy(value)
    prior = old.pop('project_files'); fresh = new.pop('project_files')
    # The ordinary receiver may predate the accepted remaining-worker installer.
    # Keep that complete installer package when adding this registration entry;
    # operational settings and every non-installer source pin remain unchanged.
    worker_helper = 'scripts/friday_worker_preparation.py'
    allowed = {'scripts/a0_prepare.py', SOURCE, 'scripts/friday_install.py',
               'scripts/friday_ordinary_install.py', 'scripts/worker_install.py', worker_helper}
    f.require(old == new and current['home'] == str(home)
              and value['product']['runtime'] == {'enabled': False}
              and set(fresh) == set(prior) | {SOURCE} | ({worker_helper} if worker_helper in fresh else set())
              and all(fresh[n] == sha for n, sha in prior.items() if n not in allowed)
              and SOURCE in fresh, 'ordinary_a0_only_registration_source_change_required')
    _, donors = budget.call(f.spec_checked, value, cli_only=True)
    marker = f.read_json(paths['marker']); receipt = f.read_json(paths['source_receipt'])
    f.require(marker.get('schema') == f.SCHEMA and marker.get('home') == str(home)
              and marker.get('source') == str(home / 'hermes-agent')
              and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
              and marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
              and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
              and marker.get('runtime_ready') is False
              and marker.get('input_sha256') == request['current_input']['sha256']
              and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
              and type(marker.get('original_attempt')) is dict,
              'ordinary_a0_current_installed_receiver_required')
    budget.call(f.composition_checked, current, home / 'hermes-agent', receipt, donors['hermes'])
    from scripts.friday_ordinary_install import checked_plugin_inventory
    checked_plugin_inventory(home, marker['plugin_files'])
    f.native_packages(home / 'hermes-agent')
    from hermes_cli.friday_ordinary_gateway import check
    check(home, role=False)
    from hermes_cli.config import require_readable_config_before_write
    config = require_readable_config_before_write(paths['configuration'])
    f.require(config['plugins']['entries']['friday_rework']['settings']['runtime'] == {'enabled': False},
              'ordinary_a0_root_runtime_must_remain_disabled')
    f.require(type(request['history']) is list and request['history'], 'ordinary_a0_install_history_required')
    for ref in request['history']:
        path = budget.call(f.pin, ref)
        f.require(path.is_relative_to(home / 'preparation') or
                  (path.parent == home and path.name.startswith('FRIDAY-INSTALL.')),
                  'ordinary_a0_foreign_history')
    # Registration needs explicit A0 source/deployment declarations only; it
    # neither consumes worker build reports nor fabricates qualification.
    from scripts.worker_install import declared_a0
    effective = dict(value, product=dict(value['product'], runtime=budget.call(declared_a0, value, home)))
    from scripts.a0_prepare import service_plan, service_sources
    for name, data in budget.call(service_sources, value['project_files']).items():
        f.require(f.owned_file(home / 'worker-runtime-source' / name) == data,
                  'ordinary_a0_staged_source_changed')
    plan = budget.call(service_plan, effective, home)
    f.require(plan['required'], 'ordinary_a0_registration_plan_required')
    return home, value, effective, marker, plan


def register(request, request_path, *, clock):
    """One new installed registration under actual native custody, never replay."""
    budget = clock_checked(clock)
    home, value, effective, marker, plan = installed(request, budget)
    raw = f.owned_file(request_path, private=True)
    f.require(json.loads(raw, object_pairs_hook=f.unique) == request, 'ordinary_a0_request_changed')
    request_sha = f.digest(raw)
    parent = f.directory(home / 'preparation')
    tx = parent / ('ordinary-a0-registration-' + request['request_id'])
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Any retained attempt needs explicit reconciliation, including a
        # different request ID. Renaming an uncertain attempt grants no retry.
        f.require(not any(p.name.startswith('ordinary-a0-registration-') for p in parent.iterdir())
                  and not any(os.path.lexists(parent / ('a0-service.' + name + '.json')) for name in
                              ('intent', 'link-intent', 'reload-intent', 'receipt', 'failure')),
                  'ordinary_a0_attempt_consumed_requires_reconciliation')
        def verify():
            budget.check(reserve=30)
            f.require(f.digest(f.owned_file(request_path, private=True)) == request_sha, 'ordinary_a0_request_changed')
            for name in PINS: f.pin(request[name])
            for ref in request['history']: f.pin(ref)
            # This rechecks all nested source/deployment/policy pins without
            # writing the receiver configuration or the installed claim.
            _, _, current_effective, current_marker, current_plan = installed(request, budget)
            f.require(current_effective == effective and current_marker == marker and current_plan == plan,
                      'ordinary_a0_installed_identity_changed')
            return native_owner(request, clock)
        physical = verify()
        tx.mkdir(mode=0o700)
        original = {'schema': CLOCK, 'clock': clock, 'request_sha256': request_sha,
                    'request_id': request['request_id'], 'marker': request['marker'],
                    'current_input': request['current_input'], 'resume_allowed': False}
        f.publish(tx / 'intent.json', {'schema': INTENT, 'state': 'CONSUMED_NO_RETRY',
                  'original_attempt': original, 'physical': physical, 'plan': plan}, budget=budget)
        try:
            from scripts.a0_prepare import _register_service
            result = _register_service(effective, home, budget, plan=plan, original_attempt=original,
                        evidence=tx, verify=verify, intent_schema=INTENT, receipt_schema=RECEIPT)
            verify()
            f.publish(tx / 'result.json', result, budget=budget)
            return result
        except BaseException as exc:
            try:
                f.publish(tx / 'failure.json', {'state': 'REGISTRATION_REQUIRES_RECONCILIATION_NO_RETRY',
                          'original_attempt': original, 'resume_allowed': False,
                          'diagnostic': f.retained_diagnostic(exc, 'ordinary-a0-registration')})
            except BaseException as secondary:
                f.remember_secondary(exc, secondary)
            raise
    finally:
        os.close(fd)
