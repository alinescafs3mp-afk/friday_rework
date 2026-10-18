"""Archive one exact stale own worker setup, granting no execution authority.

The caller retains the onboarding and profile configuration transactions and
revalidates current operator/grant/config/proof/marker authority through verify.
No preparation, qualification, credential write, deletion, or retry happens here.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

SCHEMA = 'friday.worker-stale-archive.v1'
INTENT = 'ARCHIVE_STALE_WORKER_SETUP_NO_RETRY'
ARCHIVE = 'worker-setup-archive'
RESERVE = 20
MAX_FILE = 64 * 1024**2
MAX_TREE = 128 * 1024**2
MAX_NODES = 4096
FIELDS = {'schema', 'intent', 'home', 'profile', 'binding_sha256', 'generation',
    'tree', 'original_attempt', 'original_failure', 'closed_custody',
    'original_clock', 'native_cessation', 'native_unit', 'current', 'original_archive'}


class ArchiveRefused(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class StopUnconfirmed(RuntimeError):
    def __init__(self, reason='worker_archive_stop_unconfirmed'):
        self.reason = reason
        super().__init__(reason)


def _require(value, reason):
    if not value:
        raise ArchiveRefused(reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _unique(rows):
    result = {}
    for key, value in rows:
        _require(key not in result, 'worker_archive_duplicate_json_key')
        result[key] = value
    return result


def _json(data):
    return json.loads(data, object_pairs_hook=_unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ArchiveRefused('worker_archive_nonfinite_json')))


def decode_request(data):
    """Strict protected JSON decoding; duplicate/nonfinite fields are refused."""
    _require(type(data) is bytes and len(data) <= 16 * 1024**2,
        'worker_archive_bounded_request_bytes_required')
    return _json(data)


def _identity(info, *, file=False):
    names = ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode') if file else (
        'st_dev', 'st_ino', 'st_uid', 'st_mode')
    return [getattr(info, name) for name in names]


def _private_dir(info):
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700, 'worker_archive_private_directory_required')


def _read_at(parent_fd, name, *, private=True):
    # The existing generic descriptor-relative reader checks regular/nlink/uid,
    # byte bounds, and named/opened identity including concurrent byte changes.
    from scripts.friday_ordinary_install import update_file_state_at
    row = update_file_state_at(Path(name), parent_fd)
    _require(row is not None and (row['mode'] in (0o400, 0o600) if private
        else row['mode'] in (0o400, 0o600, 0o644)), 'worker_archive_owned_file_required')
    return row


class _Directory:
    """Retain every path edge; a renamed parent cannot redirect later effects."""
    def __init__(self, path, *, private=True):
        self.path = Path(path)
        self.fds = []
        self.edges = []
        try:
            _require(self.path.is_absolute() and self.path == Path(os.path.normpath(self.path)),
                'worker_archive_exact_absolute_path_required')
            root = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(root)
            for component in self.path.parts[1:]:
                parent = self.fds[-1]
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent)
                self.fds.append(fd)
                info = os.fstat(fd)
                sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                _require(info.st_uid in (0, os.getuid())
                    and (not stat.S_IMODE(info.st_mode) & 0o022 or sticky_root),
                    'worker_archive_unsafe_parent_directory')
                self.edges.append((parent, component, fd, _identity(info)))
            if private:
                _private_dir(os.fstat(self.fd))
            else:
                _require(os.fstat(self.fd).st_uid == os.getuid(),
                    'worker_archive_owned_parent_required')
            self.prove()
        except BaseException:
            self.close()
            raise

    @property
    def fd(self):
        return self.fds[-1]

    def prove(self):
        for parent, name, fd, identity in self.edges:
            _require(_identity(os.fstat(fd)) == identity == _identity(
                os.stat(name, dir_fd=parent, follow_symlinks=False)), 'worker_archive_parent_identity_changed')

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _snapshot_fd(fd, *, budget=None):
    files, directories = {}, {}
    total = 0
    device = os.fstat(fd).st_dev

    def walk(current, prefix):
        nonlocal total
        if budget is not None:
            budget.check(reserve=RESERVE)
        first = os.fstat(current)
        _private_dir(first)
        _require(first.st_dev == device, 'worker_archive_mounted_tree_refused')
        directories[prefix] = _identity(first)
        names = sorted(os.listdir(current))
        _require(len(files) + len(directories) + len(names) <= MAX_NODES,
            'worker_archive_tree_limit')
        for name in names:
            _require(name not in ('.', '..') and '/' not in name, 'worker_archive_invalid_member')
            relative = name if prefix == '.' else prefix + '/' + name
            before = os.stat(name, dir_fd=current, follow_symlinks=False)
            _require(before.st_dev == device, 'worker_archive_mounted_tree_refused')
            if stat.S_ISDIR(before.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                try:
                    _require(_identity(before) == _identity(os.fstat(child)), 'worker_archive_directory_changed')
                    walk(child, relative)
                    _require(_identity(before) == _identity(os.stat(name, dir_fd=current,
                        follow_symlinks=False)), 'worker_archive_directory_changed')
                finally:
                    os.close(child)
            else:
                _require(stat.S_ISREG(before.st_mode), 'worker_archive_link_or_special_file_refused')
                row = _read_at(current, name)
                total += len(row['data'])
                _require(total <= MAX_TREE, 'worker_archive_tree_limit')
                files[relative] = {'sha256': _digest(row['data']), 'bytes': len(row['data']),
                    'mode': row['mode'], 'identity': list(row['identity'])}
        last = os.fstat(current)
        keys = ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_mtime_ns', 'st_ctime_ns')
        _require(names == sorted(os.listdir(current)) and all(getattr(first, key) == getattr(last, key)
            for key in keys), 'worker_archive_tree_changed_during_read')
    walk(fd, '.')
    return {'files': files, 'directories': directories}


def snapshot_tree(path, *, budget=None):
    """Bounded full byte/mode/inode manifest; links and nonprivate nodes refuse."""
    with _Directory(path) as directory:
        result = _snapshot_fd(directory.fd, budget=budget)
        directory.prove()
        return result


def _ref(value):
    return (type(value) is dict and set(value) == {'path', 'sha256'}
        and type(value['path']) is str and Path(value['path']).is_absolute()
        and str(Path(value['path'])) == value['path']
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None)


def validate_request(home, binding, generation, request):
    """Validate exact request shape; authority remains with the protected caller."""
    from hermes_cli import friday_user_scope as scope
    _require(type(request) is dict and set(request) == FIELDS and request['schema'] == SCHEMA
        and request['intent'] == INTENT and request['home'] == str(home)
        and request['profile'] == binding['runtime_profile']
        and request['binding_sha256'] == scope._fingerprint(binding)
        and type(generation) is int and generation > 0
        and type(request['generation']) is int and request['generation'] == generation,
        'worker_archive_explicit_exact_request_required')
    _require(type(request['current']) is dict and set(request['current']) == {
        'root_configuration', 'configuration', 'onboarding', 'user_marker'}
        and all(_ref(ref) for ref in request['current'].values())
        and type(request['original_archive']) is dict
        and set(request['original_archive']) == {'intent', 'committed'}
        and all(_ref(ref) for ref in request['original_archive'].values())
        and all(_ref(request[key]) for key in ('original_failure', 'closed_custody',
            'original_clock', 'native_cessation', 'native_unit')), 'worker_archive_exact_pins_required')
    tree = request['tree']
    _require(type(tree) is dict and set(tree) == {'files', 'directories'}
        and type(tree['files']) is dict and type(tree['directories']) is dict
        and '.' in tree['directories'] and 0 < len(tree['files']) + len(tree['directories']) <= MAX_NODES,
        'worker_archive_complete_tree_manifest_required')
    for kind in ('files', 'directories'):
        for name, row in tree[kind].items():
            path = PurePosixPath(name)
            _require(type(name) is str and not path.is_absolute() and '..' not in path.parts
                and str(path) == name, 'worker_archive_invalid_manifest_member')
            if kind == 'files':
                _require(type(row) is dict and set(row) == {'sha256', 'bytes', 'mode', 'identity'}
                    and re.fullmatch('[0-9a-f]{64}', str(row['sha256'])) is not None
                    and type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_FILE
                    and type(row['mode']) is int and row['mode'] in (0o400, 0o600)
                    and type(row['identity']) is list and len(row['identity']) == 5,
                    'worker_archive_invalid_file_manifest')
            else:
                _require(type(row) is list and len(row) == 4, 'worker_archive_invalid_directory_manifest')
    claim = request['original_attempt']
    _require(type(claim) is dict and set(claim) == {'boot_id', 'started_mono', 'deadline_mono', 'budget_seconds'}
        and type(claim['boot_id']) is str and bool(claim['boot_id'])
        and type(claim['budget_seconds']) is int and claim['budget_seconds'] == 300
        and all(type(claim[key]) in (int, float) and math.isfinite(claim[key])
            for key in ('started_mono', 'deadline_mono')) and claim['started_mono'] >= 0
        and claim['deadline_mono'] - claim['started_mono'] == 300, 'worker_archive_original_attempt_required')
    for name, row in tree['files'].items():
        _require(all(type(number) is int and number >= 0 for number in row['identity'])
            and row['identity'][2] == os.getuid() and row['identity'][3] == 1
            and stat.S_ISREG(row['identity'][4]) and stat.S_IMODE(row['identity'][4]) == row['mode'],
            'worker_archive_invalid_file_identity')
    for name, row in tree['directories'].items():
        _require(all(type(number) is int and number >= 0 for number in row)
            and row[2] == os.getuid() and stat.S_ISDIR(row[3]) and stat.S_IMODE(row[3]) == 0o700,
            'worker_archive_invalid_directory_identity')
    return request


def _pinned(ref, *, private=True):
    _require(_ref(ref), 'worker_archive_invalid_pin')
    path = Path(ref['path'])
    with _Directory(path.parent, private=private) as parent:
        row = _read_at(parent.fd, path.name, private=private)
        parent.prove()
    _require(_digest(row['data']) == ref['sha256'], 'worker_archive_pin_changed')
    return row


def read_request(ref):
    """Bounded exact protected request bytes, mode, and retained inode state."""
    row = _pinned(ref)
    _require(len(row['data']) <= 16 * 1024**2, 'worker_archive_bounded_request_bytes_required')
    return row


def _provenance(home, request, *, budget=None):
    """Consume retained evidence, never old recovery code or historical authority."""
    claim = request['original_attempt']
    rows = {key: _pinned(request[key]) for key in ('original_failure', 'closed_custody',
        'original_clock', 'native_cessation')}
    failure, closed, clock, cessation = (_json(rows[key]['data']) for key in (
        'original_failure', 'closed_custody', 'original_clock', 'native_cessation'))
    _require(set(failure) == {'state', 'original_attempt', 'retry_authorized', 'a0_probe_cleanup', 'error_kind'}
        and failure['state'] == 'REFUSED_OR_UNCERTAIN' and failure['original_attempt'] == claim
        and failure['retry_authorized'] is False and failure['a0_probe_cleanup'] == 'OWN_INITIAL_PROBE_CUSTODY'
        and failure['error_kind'] == 'internal_error', 'worker_archive_failed_attempt_required')
    refs = closed.get('refs', {})
    _require(closed.get('schema') == 'friday.exact-current-normal-diagnostic-closure.v1'
        and closed.get('state') == 'CONSUMED_CLOSED_FAILED_503_INTERNAL_ERROR_WORKERS_OFF_NO_RETRY'
        and closed.get('original_server_attempt') == claim and closed.get('original_physical_seconds') == 420
        and closed.get('original_physical_deadline_preserved') is True
        and closed.get('retry_authorized') is False and closed.get('actual_HTTP_qualification_POSTs') == 1
        and closed.get('A0') == 'NOT_STARTED_NO_BOOTSTRAP_OR_PLAN' and closed.get('worker_runtime') is False
        and closed.get('all_actual_owned_finite_clients_reaped') is True
        and refs.get('ROOT-DIAGNOSTIC-CLOCK.json') == request['original_clock']
        and refs.get('ROOT-DIAGNOSTIC-RESULT.json') == request['native_cessation'],
        'worker_archive_closed_custody_required')
    _require(type(clock.get('operation')) is str and bool(clock['operation'])
        and clock['operation'] == cessation.get('operation') and clock.get('boot_id') == claim['boot_id']
        and clock.get('physical_seconds') == 420 and clock.get('server_entry_seconds') == 300
        and clock.get('POST_count') == 1 and clock.get('retry_authorized') is False
        and all(type(clock.get(key)) in (int, float) and math.isfinite(clock[key])
            for key in ('started_monotonic', 'deadline_monotonic'))
        and clock['deadline_monotonic'] - clock['started_monotonic'] == 420
        and clock['started_monotonic'] <= claim['started_mono'] < claim['deadline_mono'] <= clock['deadline_monotonic']
        and cessation.get('failure') == failure and cessation.get('response', {}).get('status') == 503
        and cessation.get('retry_authorized') is False and cessation.get('bootstrap_state') is None
        and cessation.get('bootstrap_cleanup_confirmed') is True
        and cessation.get('all_observed_native_units_terminal') is True
        and cessation.get('model_calls_by_this_operation') == 0
        and cessation.get('per_job_authority') == 'NOT_GRANTED', 'worker_archive_original_clock_or_cessation_required')
    units = cessation.get('native_after')
    own_unit = 'friday-qualify-dsh-' + _digest(str(home / 'workers/qualification/dsh-safety').encode())[:24] + '-1.scope'
    _require(type(units) is dict and 1 <= len(units) <= 32
        and own_unit in units and 'friday-rework-docker.service' in units
        and all(type(row) is dict and row.get('ActiveState') == 'inactive' and row.get('SubState') == 'dead'
            and row.get('ControlGroup') == '' and row.get('InvocationID') == ''
            and row.get('MainPID', '0') == '0' and row.get('ControlPID', '0') == '0' for row in units.values()),
        'worker_archive_historical_worker_cessation_required')
    old = request['original_archive']
    intent, committed = (_json(_pinned(old[key])['data']) for key in ('intent', 'committed'))
    parent = Path(old['intent']['path']).parent
    root = Path(request['current']['root_configuration']['path']).parent
    _require(Path(old['intent']['path']).name == 'intent.json'
        and parent.parent == root / 'preparation'
        and Path(old['committed']['path']) == parent / 'committed.json'
        and Path(request['original_failure']['path']) == parent / 'failed-qualification/failure.json',
        'worker_archive_original_archive_paths_required')
    original = home / 'workers/qualification'
    mapping = {str(original): str(parent / 'failed-qualification')}
    _require(intent.get('schema') == 'friday.ordinary-closed-worker-reconciliation.v2'
        and intent.get('state') == 'CONSUMED_NO_RETRY' and intent.get('original_attempt') == claim
        and intent.get('old_attempt_retry_authorized') is False and intent.get('runtime_authority') == 'NOT_GRANTED'
        and intent.get('archive_mapping') == mapping
        and intent.get('failure') == {'path': str(original / 'failure.json'),
            'sha256': request['original_failure']['sha256']}
        and committed.get('state') == 'ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY'
        and committed.get('original_attempt') == claim and committed.get('archive_mapping') == mapping
        and committed.get('runtime_authority') == 'NOT_GRANTED'
        and all(committed.get(key) is False for key in ('old_attempt_retry_authorized', 'ready',
            'resume_allowed', 'workers_enabled', 'consumers_started', 'runtime_acceptance')),
        'worker_archive_original_archive_required')
    _require(intent.get('tree') == snapshot_tree(parent / 'failed-qualification', budget=budget),
        'worker_archive_original_archive_changed')
    return {'operation': clock['operation'], 'native_units': sorted(units),
        'pins': {**{key: request[key] for key in rows}, **{'archive-' + key: ref for key, ref in old.items()}}}


def _prepared_tree(home, binding, generation, fd, tree):
    """Only the known unobserved input footprint; no unknown activity adopted."""
    from hermes_cli import friday_user_scope as scope
    from .worker_provision import own_runtime
    attachment = _json(_read_at(fd, 'attachment.json')['data'])
    _require(set(attachment) == {'template', 'template_sha256', 'installation_config_sha256',
        'config_sha256', 'proof', 'marker', 'binding_sha256', 'generation', 'runtimes',
        'a0_network', 'required_names'} and attachment['binding_sha256'] == scope._fingerprint(binding)
        and type(attachment['generation']) is int and attachment['generation'] == generation
        and type(attachment['runtimes']) is dict and set(attachment['runtimes']) == {'dsh', 'a0'},
        'worker_archive_foreign_attachment')
    attachment_ref = {'path': str(home / 'workers/attachment.json'),
        'sha256': tree['files']['attachment.json']['sha256']}
    names = {'attachment.json'}
    directories = {'.'}
    for kind in ('dsh', 'a0'):
        root = home / 'workers' / kind
        runtime, _ = own_runtime(home, binding['runtime_profile'], kind, attachment['runtimes'][kind])
        child = os.open(kind, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            prepared = _json(_read_at(child, 'runtime-input.json')['data'])
        finally:
            os.close(child)
        _require(set(prepared) == {'runtime', 'inputs', 'principal_binding_sha256', 'generation',
            'state', 'unobserved', 'attachment'} and prepared['state'] == 'PREPARED_RUNTIME_UNOBSERVED'
            and prepared['principal_binding_sha256'] == scope._fingerprint(binding)
            and type(prepared['generation']) is int and prepared['generation'] == generation
            and prepared['runtime'] == runtime and prepared['attachment'] == attachment_ref
            and type(prepared['inputs']) is list and len(prepared['inputs']) <= MAX_NODES,
            'worker_archive_foreign_preparation')
        names.add(kind + '/runtime-input.json')
        directories.update({kind, *(kind + '/' + name for name in ('jobs', 'staging', 'cache', 'inputs'))})
        declared = set()
        for ref in prepared['inputs']:
            _require(_ref(ref), 'worker_archive_invalid_prepared_input')
            path = Path(ref['path'])
            _require(path.is_relative_to(root / 'inputs') and path != root / 'inputs'
                and '..' not in path.parts, 'worker_archive_foreign_prepared_input')
            relative = str(path.relative_to(home / 'workers'))
            _require(relative not in declared and tree['files'].get(relative, {}).get('sha256') == ref['sha256'],
                'worker_archive_prepared_input_changed')
            declared.add(relative)
            names.add(relative)
            for parent in PurePosixPath(relative).parents:
                if str(parent) != '.':
                    directories.add(str(parent))
    _require(set(tree['files']) == names and set(tree['directories']) == directories,
        'worker_archive_unknown_or_active_artifact')


@contextmanager
def _native_guard(home, request, budget):
    """Actual stopped gateway/workers and retained gateway ownership only.

    A dashboard owns the API invoking this operation; serve roles stay untouched.
    No request value can supply a guard function or turn historical data into one.
    """
    from hermes_cli import friday_user_scope as scope
    from gateway import host_rendezvous as hr
    from gateway.status import get_running_pid_identity_strict
    from hermes_cli import gateway as gw
    from scripts.dsh_prepare import run
    root = Path(request['current']['root_configuration']['path']).parent
    claimed = False
    claim_entered = False
    primary = None
    with scope.authority(root):
        _require(gw.get_systemd_unit_path(system=False) == Path(request['native_unit']['path'])
            and not os.path.lexists(gw.get_systemd_unit_path(system=True)), 'worker_archive_exact_native_unit_required')
        unit_row = _pinned(request['native_unit'], private=False)
        runtime = Path('/run/user') / str(os.getuid())
        with _Directory(runtime):
            info = (runtime / 'bus').lstat()
            _require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
                'worker_archive_owned_user_bus_required')
        state = hr.host_state_dir()
        with _Directory(state) as retained:
            lock = hr.lock_path(hr.ROLE_GATEWAY)
            _require(lock.parent == state and not hr.owns_host_lock(hr.ROLE_GATEWAY),
                'worker_archive_native_gateway_scope_changed')
            before = _read_at(retained.fd, lock.name)
            _require(before['data'] == b'', 'worker_archive_existing_empty_gateway_lock_required')
            role_path = hr.record_path(hr.ROLE_GATEWAY)
            _require(role_path.parent == state, 'worker_archive_native_record_scope_changed')

            def prove(*, cleanup=False):
                retained.prove()
                _require(_read_at(retained.fd, lock.name) == before,
                    'worker_archive_native_lock_identity_changed')
                _require(_pinned(request['native_unit'], private=False) == unit_row,
                    'worker_archive_native_unit_changed')
                units = {
                    gw.get_service_name() + '.service': {'LoadState': 'loaded', 'ActiveState': 'inactive',
                        'SubState': 'dead', 'MainPID': '0', 'ControlPID': '0'},
                    'friday-rework-docker.service': {'LoadState': 'loaded', 'ActiveState': 'inactive',
                        'SubState': 'dead', 'MainPID': '0', 'ControlPID': '0', 'ControlGroup': '', 'InvocationID': ''},
                }
                own = 'friday-qualify-dsh-' + _digest(str(home / 'workers/qualification/dsh-safety').encode())[:24] + '-1.scope'
                historical = _json(_pinned(request['native_cessation'])['data'])['native_after']
                _require(type(historical) is dict and 1 <= len(historical) <= 32,
                    'worker_archive_bounded_historical_units_required')
                own_pattern = re.escape(own.rsplit('-', 1)[0]) + '-[1-9][0-9]*\\.scope'
                for name in historical:
                    # Other historical profile observations stay archived and
                    # cannot supply names for current native probes or custody.
                    if re.fullmatch(own_pattern, name):
                        units[name] = {'LoadState': 'not-found', 'ActiveState': 'inactive',
                            'SubState': 'dead', 'ControlGroup': '', 'InvocationID': ''}
                _require(own in units, 'worker_archive_own_worker_unit_required')
                for name, expected in units.items():
                    output = run(['/usr/bin/env', 'XDG_RUNTIME_DIR=' + str(runtime),
                        'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime / 'bus'), 'SYSTEMCTL_FORCE_BUS=1',
                        '/usr/bin/systemctl', '--user', 'show', name, '--property=' + ','.join(expected)],
                        root, timeout=min(5, budget.check(reserve=0 if cleanup else RESERVE)),
                        deadline=budget.deadline if cleanup else budget.deadline - RESERVE)[0]
                    pairs = [line.split('=', 1) for line in output.splitlines() if line]
                    _require(len(pairs) == len(expected) and all(len(row) == 2 for row in pairs)
                        and dict(pairs) == expected, 'worker_archive_current_native_stop_required')
                _require(get_running_pid_identity_strict(root / 'gateway.pid') is None
                    and get_running_pid_identity_strict(home / 'gateway.pid') is None
                    and not os.path.lexists(role_path) and hr.read_record(hr.ROLE_GATEWAY, include_stale=True) is None,
                    'worker_archive_native_gateway_activity_present')
                absent = [home / 'workers' / name for name in ('qualification', 'a0/bootstrap',
                    'a0/probe-plan.json', 'a0/runtime-receipt.json', 'dsh/runtime-receipt.json')]
                absent += [root.parent / 'rootless-docker/config/local-route.json',
                    runtime / 'friday-rework-docker/rootlesskit/child_pid', runtime / 'friday-rework-docker/route-guard.json']
                _require(not any(os.path.lexists(path) for path in absent), 'worker_archive_native_worker_activity_present')
                if claimed:
                    _require(hr.owns_host_lock(hr.ROLE_GATEWAY), 'worker_archive_gateway_custody_lost')
            try:
                prove()
                try:
                    claim_entered = True
                    outcome, _ = hr.claim_host_lock(hr.ROLE_GATEWAY)
                    claimed = hr.owns_host_lock(hr.ROLE_GATEWAY)
                except BaseException as exc:
                    # Native ownership may have been entered before it raised.
                    try:
                        claimed = hr.owns_host_lock(hr.ROLE_GATEWAY)
                    except BaseException:
                        raise StopUnconfirmed('worker_archive_gateway_claim_ownership_unknown') from exc
                    if claimed:
                        raise StopUnconfirmed('worker_archive_gateway_claim_interrupted') from exc
                    # A native exception may retain an unregistered open lock
                    # handle; a false bookkeeping lookup cannot prove release.
                    raise StopUnconfirmed('worker_archive_gateway_claim_outcome_unknown') from exc
                if outcome is hr.HostLockOutcome.ACQUIRED and not claimed:
                    raise StopUnconfirmed('worker_archive_gateway_claim_custody_lost')
                if outcome is not hr.HostLockOutcome.ACQUIRED and claimed:
                    raise StopUnconfirmed('worker_archive_gateway_claim_result_uncertain')
                _require(outcome is hr.HostLockOutcome.ACQUIRED,
                    'worker_archive_gateway_custody_unavailable')
                prove()
                yield prove
                prove(cleanup=True)
            except BaseException as exc:
                primary = exc
                raise
            finally:
                if claim_entered:
                    try:
                        hr.release_host_lock(hr.ROLE_GATEWAY)
                        _require(not hr.owns_host_lock(hr.ROLE_GATEWAY), 'worker_archive_gateway_release_unconfirmed')
                        retained.prove()
                        _require(_read_at(retained.fd, lock.name) == before,
                            'worker_archive_native_lock_identity_changed')
                    except BaseException as exc:
                        stopped = StopUnconfirmed('worker_archive_native_custody_release_unconfirmed')
                        stopped.friday_custody_primary = primary or exc
                        stopped.friday_custody_secondary = (exc,) if primary is not None else ()
                        raise stopped from (primary or exc)


def _mkdir_at(parent, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        os.fsync(parent)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        _private_dir(os.fstat(fd))
        _require(_identity(os.fstat(fd)) == _identity(os.stat(name, dir_fd=parent,
            follow_symlinks=False)), 'worker_archive_directory_identity_changed')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write_at(parent, name, value):
    """Publish once and return the exact row owned by this created descriptor."""
    data = encoded(value)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    try:
        created = _identity(os.fstat(fd), file=True)
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
        row = _read_at(parent, name)
        _require(row['data'] == data and row['mode'] == 0o600
            and list(row['identity']) == created == _identity(os.fstat(fd), file=True),
            'worker_archive_receipt_write_unconfirmed')
        os.fsync(parent)
        _require(_read_at(parent, name) == row, 'worker_archive_receipt_write_unconfirmed')
        return row
    finally:
        os.close(fd)


def _exists(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _consumed(home_fd, tree_key, attempt_key):
    """Read-only replay check, including interrupted intent/claim publication."""
    if not _exists(home_fd, ARCHIVE):
        return False
    handles = []
    try:
        parent = os.open(ARCHIVE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
        handles.append(parent)
        _private_dir(os.fstat(parent))
        result = False
        for directory, name in (('consumed-trees', tree_key + '.json'),
                ('consumed-attempts', attempt_key),
                ('consumed-attempts', attempt_key + '.json'), ('transactions', tree_key)):
            if not _exists(parent, directory):
                continue
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            handles.append(fd)
            _private_dir(os.fstat(fd))
            # A damaged/partial marker is still consumed, never a reason to retry.
            result = result or _exists(fd, name)
        return result
    finally:
        for fd in reversed(handles):
            os.close(fd)


def _claim_attempt(attempts_fd, attempt_key, value, *, existing=False):
    """The atomic directory name is the permanent claim, even without JSON.

    Its parent is synchronized before returning or entering any native/worker
    mutation. A partial claim.json never makes the attempt available again.
    """
    try:
        os.mkdir(attempt_key, 0o700, dir_fd=attempts_fd)
    except FileExistsError:
        _require(existing, 'worker_archive_consumed_no_retry')
    os.fsync(attempts_fd)
    fd = os.open(attempt_key, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=attempts_fd)
    try:
        _private_dir(os.fstat(fd))
        _require(_identity(os.fstat(fd)) == _identity(os.stat(attempt_key,
            dir_fd=attempts_fd, follow_symlinks=False)), 'worker_archive_attempt_claim_changed')
        if not _exists(fd, 'claim.json'):
            _write_at(fd, 'claim.json', value)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _prove_edges(edges):
    for parent, name, fd, identity in edges:
        _require(_identity(os.fstat(fd)) == identity == _identity(os.stat(
            name, dir_fd=parent, follow_symlinks=False)), 'worker_archive_retained_parent_changed')


def _retain_stop(home_fd, tree_key, attempt_key, request):
    """Durable no-retry evidence even if native custody failed before intent."""
    handles = []
    try:
        parent = _mkdir_at(home_fd, ARCHIVE)
        handles.append(parent)
        attempts = _mkdir_at(parent, 'consumed-attempts')
        handles.append(attempts)
        value = {'schema': SCHEMA, 'state': 'STOP_UNCONFIRMED', 'tree_key': tree_key,
            'attempt_key': attempt_key, 'retry_authorized': False,
            'runtime_authority': 'NOT_GRANTED', 'original_attempt': request['original_attempt'],
            'request_sha256': _digest(encoded(request))}
        claim = _claim_attempt(attempts, attempt_key, value, existing=True)
        handles.append(claim)
        transactions = _mkdir_at(parent, 'transactions')
        handles.append(transactions)
        tx = _mkdir_at(transactions, tree_key)
        handles.append(tx)
        for directory, key in (('consumed-trees', tree_key),):
            fd = _mkdir_at(parent, directory)
            handles.append(fd)
            if not _exists(fd, key + '.json'):
                _write_at(fd, key + '.json', value)
        if not _exists(tx, 'stop-unconfirmed.json'):
            _write_at(tx, 'stop-unconfirmed.json', value)
    finally:
        for fd in reversed(handles):
            os.close(fd)


def archive(home, binding, generation, request, *, verify, budget):
    """One consumed transaction. Failure/interruption never creates retry authority."""
    from scripts.friday_ordinary_install import rename_directory_noreplace
    from scripts.dsh_prepare import StopUnconfirmed as NativeStopUnconfirmed
    home = Path(home)
    validate_request(home, binding, generation, request)
    _require(callable(verify) and hasattr(budget, 'check') and hasattr(budget, 'deadline'),
        'worker_archive_retained_authority_and_budget_required')
    budget.check(reserve=RESERVE)
    verify()
    request_bytes = encoded(request)
    tree = request['tree']
    tree_key = _digest(encoded({'home': str(home), 'identity': tree['directories']['.']}))
    attempt_key = _digest(encoded({'home': str(home), 'profile': binding['runtime_profile'],
        'generation': generation, 'original_attempt': request['original_attempt']}))
    handles = []
    tx = None
    mutated = False
    renamed = False
    committed = False
    failure_written = False
    attempt_claim_entered = False
    outcome = None
    committed_state = None
    released_state = None
    with _Directory(home) as retained:
        fcntl.flock(retained.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if _consumed(retained.fd, tree_key, attempt_key):
                retained.prove()
                verify()
                return {'state': 'WORKER_ARCHIVE_ALREADY_CONSUMED_NO_RETRY', 'ready': False,
                    'runtime_authority': 'NOT_GRANTED', 'retry_authorized': False,
                    'old_attempt_retry_authorized': False, 'tree_key': tree_key}
            parent = _mkdir_at(retained.fd, ARCHIVE)
            handles.append(parent)
            archive_identity = _identity(os.fstat(parent))
            _require(not set(os.listdir(parent)) - {'.lock', 'consumed-trees', 'consumed-attempts', 'transactions'},
                'worker_archive_unknown_receipt_artifact')
            lock = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            handles.append(lock)
            lock_info = os.fstat(lock)
            _require(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid == os.getuid()
                and lock_info.st_nlink == 1 and stat.S_IMODE(lock_info.st_mode) == 0o600
                and lock_info.st_size == 0, 'worker_archive_private_lock_required')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            indexes = {}
            edges = [(retained.fd, ARCHIVE, parent, archive_identity)]
            for name in ('consumed-trees', 'consumed-attempts', 'transactions'):
                indexes[name] = _mkdir_at(parent, name)
                handles.append(indexes[name])
                edges.append((parent, name, indexes[name], _identity(os.fstat(indexes[name]))))
            _require(not _exists(indexes['consumed-trees'], tree_key + '.json')
                and not _exists(indexes['consumed-attempts'], attempt_key + '.json')
                and not _exists(indexes['consumed-attempts'], attempt_key)
                and not _exists(indexes['transactions'], tree_key), 'worker_archive_consumed_no_retry')

            retained.prove()
            _prove_edges(edges)
            verify()
            _require(encoded(request) == request_bytes, 'worker_archive_request_mutated')
            attempt_claim_entered = True
            claim_value = {'schema': SCHEMA, 'state': 'CONSUMED_NO_RETRY', 'tree_key': tree_key,
                'attempt_key': attempt_key, 'request_sha256': _digest(request_bytes),
                'original_attempt': request['original_attempt'], 'runtime_authority': 'NOT_GRANTED',
                'retry_authorized': False}
            attempt_claim = _claim_attempt(indexes['consumed-attempts'], attempt_key, claim_value)
            handles.append(attempt_claim)
            edges.append((indexes['consumed-attempts'], attempt_key, attempt_claim,
                _identity(os.fstat(attempt_claim))))
            retained.prove()
            _prove_edges(edges)
            verify()
            _require(encoded(request) == request_bytes, 'worker_archive_request_mutated')
            with _native_guard(home, request, budget) as native_prove:
                workers = os.open('workers', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=retained.fd)
                handles.append(workers)
                _require(_snapshot_fd(workers, budget=budget) == tree, 'worker_archive_exact_tree_changed')
                _prepared_tree(home, binding, generation, workers, tree)
                provenance = _provenance(home, request, budget=budget)

                def prove(*, archived=False, cleanup=False, native=True):
                    budget.check(reserve=0 if cleanup else RESERVE)
                    verify()
                    _require(encoded(request) == request_bytes, 'worker_archive_request_mutated')
                    retained.prove()
                    _prove_edges(edges)
                    _require(_identity(os.fstat(lock), file=True) == list(_read_at(parent, '.lock')['identity']),
                        'worker_archive_lock_identity_changed')
                    _require(_identity(os.fstat(parent)) == archive_identity == _identity(os.stat(ARCHIVE,
                        dir_fd=retained.fd, follow_symlinks=False)), 'worker_archive_receipt_parent_changed')
                    _require(_provenance(home, request, budget=None if cleanup else budget) == provenance,
                        'worker_archive_original_provenance_changed')
                    if native:
                        if cleanup:
                            native_prove(cleanup=True)
                        else:
                            native_prove()
                    source_fd, source_name = (tx, 'workers') if archived else (retained.fd, 'workers')
                    _require(_identity(os.fstat(workers)) == _identity(os.stat(source_name,
                        dir_fd=source_fd, follow_symlinks=False)) == tree['directories']['.'],
                        'worker_archive_tree_custody_changed')
                    _require(_snapshot_fd(workers, budget=None if cleanup else budget) == tree,
                        'worker_archive_exact_tree_changed')
                    if archived:
                        _require(not _exists(retained.fd, 'workers'), 'worker_archive_new_workers_collision')
                    if committed_state is not None:
                        _require(_read_at(tx, 'committed.json') == committed_state
                            and not any(_exists(tx, name) for name in ('disposition.json',
                                'failure.json', 'stop-unconfirmed.json')),
                            'worker_archive_commit_disposition_changed')
                    if released_state is not None:
                        _require(_read_at(tx, 'released.json') == released_state,
                            'worker_archive_release_receipt_changed')

                prove()
                os.mkdir(tree_key, 0o700, dir_fd=indexes['transactions'])
                os.fsync(indexes['transactions'])
                tx = os.open(tree_key, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=indexes['transactions'])
                handles.append(tx)
                edges.append((indexes['transactions'], tree_key, tx, _identity(os.fstat(tx))))
                metadata = {'schema': SCHEMA, 'state': 'CONSUMED_NO_RETRY', 'tree_key': tree_key,
                    'attempt_key': attempt_key, 'request_sha256': _digest(request_bytes),
                    'original_attempt': request['original_attempt'], 'tree': tree,
                    'provenance': provenance, 'old_attempt_retry_authorized': False,
                    'runtime_authority': 'NOT_GRANTED', 'deadline_mono': budget.deadline}
                _write_at(tx, 'intent.json', metadata)
                _write_at(indexes['consumed-trees'], tree_key + '.json', metadata)
                os.fsync(parent)
                try:
                    prove()
                    _require(not _exists(tx, 'workers'), 'worker_archive_destination_occupied')
                    mutated = True
                    rename_directory_noreplace(retained.fd, 'workers', tx, 'workers')
                    renamed = True
                    os.fsync(retained.fd)
                    os.fsync(tx)
                    prove(archived=True)
                    outcome = {'state': 'ARCHIVED_STALE_WORKER_SETUP_NO_RUNTIME_AUTHORITY',
                        'ready': False, 'workers_enabled': False, 'runtime_acceptance': False,
                        'runtime_authority': 'NOT_GRANTED',
                        'old_attempt_retry_authorized': False, 'retry_authorized': False,
                        'tree_key': tree_key, 'original_attempt': request['original_attempt'],
                        'archive': str(home / ARCHIVE / 'transactions' / tree_key / 'workers')}
                    committed_state = _write_at(tx, 'committed.json', outcome)
                    _require(type(committed_state) is dict and committed_state['data'] == encoded(outcome)
                        and committed_state['mode'] == 0o600
                        and _read_at(tx, 'committed.json') == committed_state,
                        'worker_archive_commit_write_ownership_changed')
                    committed = True
                    prove(archived=True)
                except BaseException as primary:
                    try:
                        # A rename exception is not assumed to mean no mutation.
                        at_source = _exists(retained.fd, 'workers')
                        at_archive = _exists(tx, 'workers')
                        if mutated and at_archive and not at_source:
                            prove(archived=True, cleanup=True)
                            rename_directory_noreplace(tx, 'workers', retained.fd, 'workers')
                            renamed = False
                            os.fsync(retained.fd)
                            os.fsync(tx)
                            prove(cleanup=True)
                        elif mutated:
                            _require(at_source and not at_archive and not renamed,
                                'worker_archive_rename_outcome_uncertain')
                            prove(cleanup=True)
                        disposition = {'state': 'ROLLED_BACK_CONSUMED_NO_RETRY',
                            'retry_authorized': False, 'runtime_authority': 'NOT_GRANTED',
                            'commit_receipt_may_exist': _exists(tx, 'committed.json'),
                            'original_attempt': request['original_attempt']}
                        _write_at(tx, 'disposition.json', disposition)
                        _write_at(tx, 'failure.json', disposition)
                        failure_written = True
                    except BaseException as secondary:
                        try:
                            if not _exists(tx, 'stop-unconfirmed.json'):
                                _write_at(tx, 'stop-unconfirmed.json', {'state': 'STOP_UNCONFIRMED',
                                    'retry_authorized': False, 'runtime_authority': 'NOT_GRANTED',
                                    'original_attempt': request['original_attempt'], 'tree_key': tree_key})
                        except BaseException:
                            pass
                        raise StopUnconfirmed('worker_archive_rollback_or_persistence_unconfirmed') from secondary
                    raise primary
            # Native __exit__ has now proved lock release. No success before it.
            # No native ownership assertion/reacquisition or rollback is valid
            # here. Drift after release retains the archive and STOP evidence.
            _require(committed and outcome is not None, 'worker_archive_commit_unconfirmed')
            prove(archived=True, cleanup=True, native=False)
            release_value = {'state': 'COMMITTED_CUSTODY_RELEASE_CONFIRMED',
                'tree_key': tree_key, 'retry_authorized': False, 'runtime_authority': 'NOT_GRANTED'}
            released_state = _write_at(tx, 'released.json', release_value)
            _require(type(released_state) is dict and released_state['data'] == encoded(release_value)
                and released_state['mode'] == 0o600 and _read_at(tx, 'released.json') == released_state,
                'worker_archive_release_write_ownership_changed')
            prove(archived=True, cleanup=True, native=False)
            return outcome
        except BaseException as exc:
            if tx is None and (attempt_claim_entered or isinstance(exc, (StopUnconfirmed, NativeStopUnconfirmed))):
                try:
                    retained.prove()
                    _retain_stop(retained.fd, tree_key, attempt_key, request)
                except BaseException as secondary:
                    stopped = StopUnconfirmed('worker_archive_native_custody_and_evidence_unconfirmed')
                    stopped.friday_custody_primary = exc
                    stopped.friday_custody_secondary = (secondary,)
                    raise stopped from exc
                if isinstance(exc, ArchiveRefused):
                    # An admitted attempt is consumed conservatively even when
                    # an active/changed/foreign input refuses before any move.
                    raise
                raise StopUnconfirmed('worker_archive_claim_or_native_custody_unconfirmed') from exc
            if tx is not None and not failure_written:
                try:
                    if not _exists(tx, 'stop-unconfirmed.json'):
                        _write_at(tx, 'stop-unconfirmed.json', {'state': 'STOP_UNCONFIRMED',
                            'tree_key': tree_key, 'retry_authorized': False,
                            'runtime_authority': 'NOT_GRANTED', 'committed_receipt_present': committed})
                except BaseException:
                    pass
                raise StopUnconfirmed('worker_archive_custody_or_receipt_unconfirmed') from exc
            raise
        finally:
            for fd in reversed(handles):
                os.close(fd)
