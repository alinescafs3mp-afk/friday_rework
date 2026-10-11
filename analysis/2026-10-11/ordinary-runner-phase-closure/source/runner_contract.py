"""Pure source runner contracts. JSON consistency never grants host custody.

The existing host supplies a live adapter out of band. This module neither
creates a lock/broker nor treats an audit hook as a kernel boundary.
"""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import threading
import time

MAX_FILE = 8 * 1024**2

class Refusal(ValueError):
    pass

def need(value, cause):
    if not value:
        raise Refusal(cause)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'duplicate_json_key:' + key)
        out[key] = value
    return out

def parse(data):
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(Refusal('nonfinite_json')))

def lexical(path):
    """Reject traversal before normalizing; relative paths use the actual cwd."""
    need(isinstance(path, (str, bytes, os.PathLike)), 'descriptor_path_forbidden')
    raw = os.fsdecode(path)
    need(raw and '\x00' not in raw and '..' not in raw.split('/'), 'path_traversal')
    return Path(os.path.abspath(raw))

def canonical_path(path, root=None):
    path = lexical(path)
    if root is not None:
        root = lexical(root)
        need(path.is_relative_to(root), 'outside_owned_root')
    for part in reversed((path, *path.parents)):
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        need(not stat.S_ISLNK(mode), 'symlink_component:' + str(part))
    need(path.resolve(strict=False) == path, 'noncanonical_path')
    return path

def parent_fd(path):
    """Walk every parent under O_NOFOLLOW. Caller owns/always closes result."""
    path = lexical(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in path.parts[1:-1]:
            new = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_bytes(path, maximum=MAX_FILE):
    path = canonical_path(path)
    directory = parent_fd(path)
    fd = None
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        fd = os.open(path.name, flags, dir_fd=directory)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'nonregular_or_oversized_input')
        chunks, size = [], 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - size))
            if not part:
                break
            size += len(part)
            need(size <= maximum, 'oversized_input')
            chunks.append(part)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(identity(before) == identity(after), 'changed_during_read')
        final = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        need(identity(after) == identity(final), 'changed_path_after_read')
        canonical_path(path)  # replaced ancestors are refused as well
        need(identity(after) == identity(path.stat()), 'changed_ancestor_after_read')
        return b''.join(chunks)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)

def pin(path):
    data = read_bytes(path)
    return {'path': str(canonical_path(path)), 'sha256': digest(data), 'bytes': len(data)}

def verify(value, label='input'):
    need(isinstance(value, dict) and set(value) == {'path', 'sha256', 'bytes'}, 'invalid_ref:' + label)
    need(isinstance(value['path'], str) and Path(value['path']).is_absolute(), 'invalid_ref_path:' + label)
    sha = value['sha256']
    need(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'invalid_ref_sha:' + label)
    need(type(value['bytes']) is int and 0 <= value['bytes'] <= MAX_FILE, 'invalid_ref_size:' + label)
    data = read_bytes(value['path'])
    need(len(data) == value['bytes'] and digest(data) == sha, 'changed_ref:' + label)
    return data  # exactly these immutable bytes, never reopen to deserialize/exec

def document(value, label='document'):
    return parse(verify(value, label))

def rooted_write(root, relative, data, exclusive=True):
    need(exclusive is True, 'nonexclusive_rooted_write_forbidden')
    root = canonical_path(root)
    need(isinstance(relative, str) and not Path(relative).is_absolute(), 'absolute_output_name')
    target = canonical_path(root / relative, root)
    need(target != root and '..' not in relative.split('/'), 'path_traversal')
    need(isinstance(data, bytes) and len(data) <= MAX_FILE, 'output_bound')
    directory = parent_fd(target)
    fd = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        flags |= os.O_EXCL
        fd = os.open(target.name, flags, 0o600, dir_fd=directory)
        need(stat.S_ISREG(os.fstat(fd).st_mode), 'nonregular_output')
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            need(count > 0, 'short_output_write')
            offset += count
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
    return {'path': str(target), 'sha256': digest(data), 'bytes': len(data)}

def save(root, relative, value, exclusive=True):
    return rooted_write(root, relative, canonical(value) + b'\n', exclusive)

def pid_start(pid):
    need(type(pid) is int and pid > 0, 'invalid_pid')
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        return int(text[text.rfind(')') + 2:].split()[19])
    except FileNotFoundError:
        return None

def budget_limits(budget, now=None):
    need(isinstance(budget, dict) and set(budget) == {'start_epoch', 'seconds', 'cleanup_seconds', 'hard_epoch', 'clock_ref'}, 'original_budget_schema')
    for key in ('start_epoch', 'seconds', 'cleanup_seconds', 'hard_epoch'):
        need(type(budget[key]) in (int, float) and math.isfinite(budget[key]), 'budget_type')
    clock = document(budget['clock_ref'], 'original_execution_clock')
    need(clock['original_seconds'] == budget['seconds'] and clock['cleanup_seconds'] == budget['cleanup_seconds'], 'original_clock_budget_mismatch')
    start = datetime.datetime.fromisoformat(clock['accepted_msk']).timestamp()
    need(abs(start - budget['start_epoch']) < .001, 'original_clock_start_reset')
    need(budget['seconds'] > 0 and budget['cleanup_seconds'] >= 60 and
         budget['cleanup_seconds'] < budget['seconds'] and
         budget['start_epoch'] < budget['hard_epoch'] <= budget['start_epoch'] + budget['seconds'], 'original_budget_changed')
    if 'hard_epoch' in clock:
        need(clock['hard_epoch'] == budget['hard_epoch'], 'original_hard_deadline_changed')
    now = time.time() if now is None else now
    need(budget['start_epoch'] <= now < budget['hard_epoch'] - budget['cleanup_seconds'], 'original_useful_deadline_expired')
    return budget['hard_epoch'], budget['hard_epoch'] - budget['cleanup_seconds']

def resources(limits):
    need(isinstance(limits, dict) and set(limits) == {'CPUs', 'worker_address_space_bytes', 'aggregate_address_space_bytes', 'output_bytes'}, 'resource_schema')
    need(all(type(v) is int for v in limits.values()), 'resource_type')
    need(limits['CPUs'] == 2 and 1024**3 <= limits['worker_address_space_bytes'] <= 2 * 1024**3, 'source_checker_original_1GiB_resource_unavailable')
    need(limits['aggregate_address_space_bytes'] >= limits['worker_address_space_bytes'] + 96 * 1024**2, 'aggregate_resource_undeclared')
    need(1024**2 <= limits['output_bytes'] <= MAX_FILE, 'output_bound_schema')
    return limits

def read_scope(scope):
    need(isinstance(scope, dict) and set(scope) == {'files', 'roots'}, 'read_scope_schema')
    need(isinstance(scope['files'], list) and isinstance(scope['roots'], list), 'read_scope_schema')
    need(scope['files'] and len(scope['files']) <= 20000 and len(scope['roots']) <= 64, 'read_scope_empty_or_unbounded')
    paths = []
    for item in scope['files']:
        verify(item, 'approved_read_input')
        paths.append(item['path'])
    need(len(paths) == len(set(paths)), 'duplicate_read_input')
    for root in scope['roots']:
        value = canonical_path(root)
        need(str(value) == root and value.is_dir() and len(value.parts) > 2, 'unbounded_or_missing_read_root')
    need(len(scope['roots']) == len(set(scope['roots'])), 'duplicate_read_root')
    return scope

def revalidate_inputs(admission):
    """Recheck original trust/pins at each barrier; do not repin changed bytes."""
    for name, value in admission['pins'].items():
        verify(value, name)
    for name, value in admission['auxiliary'].items():
        verify(value, 'auxiliary:' + name)
    read_scope(admission['read_scope'])
    budget_limits(admission['budget'])
    resources(admission['resources'])
    return verify(admission['checker'], 'admitted_checker')


def cpu_affinity(values, maximum, scope=None):
    """Canonical CPU IDs; bool is not an int and a list is not authority."""
    need(type(maximum) is int and maximum > 0, 'affinity_maximum_type')
    need(type(values) is list and 0 < len(values) <= maximum, 'affinity_shape')
    need(all(type(cpu) is int and cpu >= 0 for cpu in values), 'affinity_cpu_type')
    need(len(values) == len(set(values)), 'affinity_duplicate_cpu')
    need(values == sorted(values), 'affinity_noncanonical_order')
    if scope is not None:
        cpu_affinity(scope, 4096)
        need(set(values).issubset(scope), 'affinity_outside_host_scope')
    return values[:]


def require_loader(loader):
    # Only the integration owner's authenticated EXISTING loader, supplied out
    # of band, can implement this obligation. No CLI/env/JSON/import fallback.
    # A callable shape or source fixture does not authenticate an installed host.
    need(loader is not None and not isinstance(loader, dict) and
         callable(getattr(loader, 'capture_loaded_implementation', None)),
         'authenticated_existing_loader_unavailable')
    return loader


def loaded_implementation(loader, implementation, phase, actor, namespace, binding=None, worker=None):
    """Compare retained loader buffers, never infer loading by reading __file__.

    Proposed EXISTING-host obligation, currently UNBOUND. The trusted loader
    must have retained the immutable buffers BEFORE exec and associated the
    exact executing namespace/code and native interpreter/PID birth. For a
    parent it also retains the exact pending worker image; for a worker it
    retains the parent's launch provenance. No self-authored receipt is proof.
    The tuple below is an immutable observation returned by that live verifier,
    not an authentication mechanism. Pure synthetic adapters test predicates.
    """
    require_loader(loader)
    need(actor in ('parent', 'worker'), 'loaded_actor')
    process = {'pid': os.getpid(), 'start_ticks': pid_start(os.getpid())}
    need(process['start_ticks'] is not None, 'loaded_process_birth_missing')
    context = {'phase': phase, 'actor': actor, 'process': process, 'worker': worker,
               'implementation': implementation, 'binding': binding}
    # Do not permit a verifier to mutate the expected dictionaries in place.
    context_bytes = canonical(context)
    observation = loader.capture_loaded_implementation(context=parse(context_bytes), namespace=namespace)
    need(type(observation) is tuple and len(observation) == 3, 'immutable_loader_observation_required')
    joined_context, sources, running_interpreter = observation
    need(type(joined_context) is bytes and joined_context == context_bytes, 'loaded_context_mismatch')
    need(type(sources) is tuple and len(sources) == 4, 'loaded_source_membership')
    names = set()
    identities = {}
    for item in sources:
        need(type(item) is tuple and len(item) == 4, 'immutable_loaded_buffer_required')
        name, path, buffer, state = item
        need(type(name) is str and name in implementation and name != 'interpreter' and name not in names,
             'loaded_source_membership')
        need(type(path) is str and type(buffer) is bytes and len(buffer) <= MAX_FILE, 'immutable_loaded_buffer_required')
        loaded_names = {'source_runner.py', 'gate_inputs.py', 'runner_contract.py'} if actor == 'parent' else {'runner_worker.py', 'runner_contract.py'}
        need(state == ('loaded' if name in loaded_names else 'retained_launch_image'), 'loaded_image_state')
        ref = {'path': path, 'bytes': len(buffer), 'sha256': digest(buffer)}
        need(ref == implementation[name], 'loaded_implementation_changed:' + name)
        names.add(name); identities[name] = ref
    need(names == set(implementation) - {'interpreter'}, 'loaded_source_membership')
    need(type(running_interpreter) is bytes, 'immutable_interpreter_provenance_required')
    need(running_interpreter == canonical(implementation['interpreter']), 'loaded_interpreter_changed')
    # This identity is serialized in the immutable admission, and compared at
    # every boundary against the live loader's retained observation again.
    identities['interpreter'] = implementation['interpreter']
    return canonical(identities)


def resource_observation(observation, limits, worker, job_ref, approved, *, configured=True):
    """Validate an observation obtained from the retained host callback only."""
    need(type(observation) is dict and set(observation) ==
         {'worker', 'job', 'approved_affinity', 'available_affinity', 'observed_limits'},
         'trusted_resource_observation_required')
    need(canonical(observation['worker']) == canonical(worker) and canonical(observation['job']) == canonical(job_ref), 'resource_worker_job_mismatch')
    available = cpu_affinity(observation['available_affinity'], 4096)
    wanted = cpu_affinity(approved, limits['CPUs'], available)
    actual = cpu_affinity(observation['approved_affinity'], limits['CPUs'], available)
    need(actual == wanted, 'host_approved_affinity_changed')
    observed = observation['observed_limits']
    if worker is not None:
        need(type(worker) is dict and set(worker) == {'pid', 'start_ticks'} and
             all(type(v) is int and v > 0 for v in worker.values()), 'resource_worker_identity_type')
    if worker is None or configured is False:
        need(observed is None, 'unlaunched_resource_observation')
    else:
        need(type(observed) is dict and set(observed) ==
             {'affinity', 'address_space_bytes', 'CPU_seconds', 'file_size_bytes'},
             'worker_resource_observation_mismatch')
        need(cpu_affinity(observed['affinity'], limits['CPUs'], available) == wanted, 'worker_affinity_changed')
        for key, expected in [('address_space_bytes', limits['worker_address_space_bytes']),
                              ('CPU_seconds', 60), ('file_size_bytes', limits['output_bytes'])]:
            pair = observed[key]
            need(type(pair) is list and len(pair) == 2 and all(type(v) is int and v >= 0 for v in pair) and
                 pair == [expected, expected], 'worker_resource_observation_mismatch')
    return parse(canonical(observation))  # detach the live adapter's mutable result

def custody_context(admission, phase, worker=None, job_ref=None):
    return {'binding_sha256': admission['binding_sha256'], 'grant_sha256': admission['pins']['grant']['sha256'],
            'implementation_sha256': digest(canonical(admission['implementation'])),
            'read_scope_sha256': digest(canonical(admission['read_scope'])),
            'output_root': admission['output_root'], 'original_budget': admission['budget'],
            'resources': admission['resources'], 'approved_affinity': admission['approved_affinity'],
            'loaded_identity': admission['loaded_identity'], 'phase': phase, 'worker': worker, 'job': job_ref}

def require_custody(adapter, admission, phase, worker=None, job_ref=None):
    """Only a trusted existing-host live verifier passed by its owner can grant.

    CLI has no adapter, no import-from-JSON/plugin option, no synthetic fallback.
    The integration owner must implement this against the EXISTING real lock,
    kernel read/write/exec/resource/child fence, retained until reaping. The
    return value is an observation from that live adapter, not a JSON receipt.
    """
    need(adapter is not None and not isinstance(adapter, dict) and callable(getattr(adapter, 'verify_retained', None)), 'existing_host_custody_adapter_unavailable')
    context = custody_context(admission, phase, worker, job_ref)
    context_bytes = canonical(context)
    observation = adapter.verify_retained(parse(context_bytes))
    need(isinstance(observation, dict) and canonical(observation.get('context')) == context_bytes, 'custody_context_mismatch')
    for key in ('actual_exclusive_lock', 'kernel_read_scope', 'kernel_write_scope', 'kernel_exec_pins',
                'kernel_child_fence', 'kernel_resource_limits', 'original_budget_enforced', 'retained_until_reap'):
        need(observation.get(key) is True, 'custody_not_proven:' + key)
    slot = admission['exclusive_slot']
    need(canonical(observation.get('owner')) == canonical({'pid': slot['owner_pid'], 'start_ticks': slot['owner_start_ticks']}), 'custody_owner_mismatch')
    need(pid_start(slot['owner_pid']) == slot['owner_start_ticks'], 'slot_owner_identity_missing')
    observation['resource_observation'] = resource_observation(observation.get('resource_observation'),
        admission['resources'], worker, job_ref, admission['approved_affinity'],
        configured=phase != 'worker_before_configure')
    return observation

class AuditPolicy:
    """Canonical source diagnostic, supplemental to REQUIRED real host custody.

    Python auditing does not intercept every native syscall. It cannot certify
    protection from malicious Python/ctypes, ancestry races or inherited FDs.
    """
    FORBIDDEN = ('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork',
                 'pty.', 'ctypes.dlopen', 'ctypes.dlsym', 'mmap.__new__', 'fcntl.', 'os.kill',
                 'os.chroot', 'signal.pthread_kill')
    MUTATIONS = {'os.mkdir': (2, 0), 'os.rmdir': (1, 0), 'os.remove': (1, 0),
                 'os.chmod': (2, 0), 'os.chown': (3, 0), 'os.utime': (3, 0),
                 'os.truncate': (None, 0)}
    def __init__(self, output, scope):
        self.output = canonical_path(output)
        self.files = {r['path'] for r in scope['files']}
        self.roots = tuple(canonical_path(r) for r in scope['roots'])
    def read(self, path):
        need(not isinstance(path, int) and Path(os.fsdecode(path)).is_absolute(), 'relative_or_descriptor_read_forbidden')
        value = canonical_path(path)
        need(value.is_relative_to(self.output) or str(value) in self.files or
             any(value.is_relative_to(root) for root in self.roots), 'outside_approved_read_scope')
        return value
    def write(self, path, dir_fd=None):
        need(dir_fd in (None, -1), 'foreign_dir_fd_mutation')
        need(not isinstance(path, int) and Path(os.fsdecode(path)).is_absolute(), 'relative_or_descriptor_mutation_forbidden')
        return canonical_path(path, self.output)
    def check(self, event, args):
        need(not any(event.startswith(p) for p in self.FORBIDDEN), 'native_runtime_effect_forbidden:' + event)
        if event == 'open':
            need(not isinstance(args[0], int), 'foreign_descriptor_open')
            mode, flags = args[1] or '', args[2] or 0
            if any(c in mode for c in 'wax+') or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                self.write(args[0])
            else:
                self.read(args[0])
        elif event in ('os.listdir', 'os.scandir'):
            self.read(args[0] if args and args[0] is not None else os.getcwd())
        elif event in ('os.rename', 'os.link'):
            need(len(args) >= 4 and args[2] in (None, -1) and args[3] in (None, -1), 'foreign_dir_fd_mutation')
            self.write(args[0]); self.write(args[1])
        elif event == 'os.symlink':
            raise Refusal('symlink_mutation_forbidden')
        elif event in self.MUTATIONS:
            fd_index, path_index = self.MUTATIONS[event]
            dir_fd = args[fd_index] if fd_index is not None and len(args) > fd_index else None
            self.write(args[path_index], dir_fd)
        elif event in ('os.setxattr', 'os.removexattr', 'os.chflags'):
            self.write(args[0])
        elif event == 'os.chdir':
            raise Refusal('cwd_mutation_forbidden')

def job_payload(admission, checker, auxiliary, root_edits):
    return {'schema': 'friday.known-source-checker-job.v2', 'admission': admission,
            'checker': checker, 'auxiliary': auxiliary, 'root_edits': root_edits,
            'independent_acceptance': False, 'runtime_grant': False}

def verify_job(job_ref, output, expected_admission_sha):
    job = document(job_ref, 'job')
    need(job.get('schema') == 'friday.known-source-checker-job.v2', 'job_schema')
    admission = job['admission']
    need(digest(canonical(admission)) == expected_admission_sha, 'changed_admission')
    need(str(canonical_path(output)) == admission['output_root'], 'job_output_mismatch')
    need(job.get('runtime_grant') is False and job.get('independent_acceptance') is False, 'job_false_authority')
    revalidate_inputs(admission)
    checker = verify(job['checker'], 'job_checker')
    need(canonical_path(job['checker']['path'], output).parent == canonical_path(output), 'job_checker_escaping')
    need(set(job['auxiliary']) == set(admission['auxiliary']), 'job_auxiliary_membership')
    for name, copied in job['auxiliary'].items():
        original = admission['auxiliary'][name]
        need(copied['path'] == str(canonical_path(output) / name) and copied['sha256'] == original['sha256'] and copied['bytes'] == original['bytes'], 'job_auxiliary_repin')
        verify(copied, 'job_auxiliary:' + name)
    return job, checker

def completion(record, closure, job_ref, worker, budget, limits, now, absent, supervisor_children,
               *, trusted_resources=None, approved_affinity=None):
    need(type(record.get('exit_code')) is int and record.get('exit_code') == 0 and record.get('failure') is None and record.get('worker_reaped') is True, 'worker_exit_not_success')
    need(isinstance(closure, dict) and closure.get('schema') == 'friday.source-worker-closure.v2', 'missing_or_invalid_worker_closure')
    need(canonical(closure.get('worker')) == canonical(worker) and canonical(closure.get('job')) == canonical(job_ref), 'stale_worker_closure')
    need(closure.get('completed') is True and closure.get('children') == [] and closure.get('threads') == ['MainThread'] and type(closure.get('FD_delta')) is int and closure.get('FD_delta') == 0, 'worker_obligations_unclosed')
    observed = closure.get('observed_limits', {})
    trusted = resource_observation(trusted_resources, limits, worker, job_ref, approved_affinity)
    need(type(observed) is dict and observed == trusted['observed_limits'], 'worker_resource_observation_mismatch')
    # Validate the closure itself; Python bool/int equality must not smuggle a
    # malformed closure that compares equal to a correctly typed observation.
    resource_observation(dict(trusted, observed_limits=observed), limits, worker, job_ref, approved_affinity)
    need(closure.get('approved_affinity') == trusted['approved_affinity'], 'closure_approved_affinity_changed')
    cpu_affinity(closure.get('approved_affinity'), limits['CPUs'], trusted['available_affinity'])
    need(canonical(closure.get('resources')) == canonical(limits) and canonical(closure.get('original_budget')) == canonical(budget), 'closure_limits_changed')
    need(closure.get('runtime_grant') is False and closure.get('independent_acceptance') is False, 'closure_false_authority')
    need(absent is True and supervisor_children == [], 'worker_or_supervisor_birth_remaining')
    need(type(closure.get('ended_epoch')) in (int, float) and math.isfinite(closure['ended_epoch']) and
         budget['start_epoch'] <= closure['ended_epoch'] <= now <= budget['hard_epoch'], 'closure_outside_original_budget')
    need(type(closure.get('output_bytes')) is int and 0 <= closure['output_bytes'] <= limits['output_bytes'], 'closure_output_bound')
    return True


def output_inventory(output, maximum):
    root = canonical_path(output)
    total, files = 0, {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        canonical_path(directory, root)
        need(len(dirs) + len(names) <= 20000, 'output_membership_bound')
        for name in dirs:
            canonical_path(Path(directory) / name, root)
        for name in names:
            path = canonical_path(Path(directory) / name, root)
            st = path.lstat()
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'nonregular_or_aliased_output')
            total += st.st_size
            need(total <= maximum and len(files) < 20000, 'aggregate_output_bound')
            files[path.relative_to(root).as_posix()] = pin(path)
    return {'total_bytes': total, 'files': files}
