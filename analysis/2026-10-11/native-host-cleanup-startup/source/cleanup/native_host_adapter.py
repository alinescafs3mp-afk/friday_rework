#!/usr/bin/python3
"""Inactive finite native-host components. No public entry point grants admission.

Pure parsers describe requirements; observations are not loaded-source provenance.
The current drivers cannot activate this module: startup/import/launch admission
is deliberately unavailable. Root must qualify the final composed artifact.
"""
import os
import sys
import stat
import time
import math
import signal
import select
import hashlib
import subprocess

SOURCE_ONLY = True
NATIVE_ADMISSION = None
MAX_CPU = 2
MAX_MEMORY = 1024 ** 3


class Unbound(RuntimeError):
    pass


class StopUnconfirmed(RuntimeError):
    pass


def require_native_admission():
    # This artifact has no authentication/binding mechanism. Changing a module
    # variable or passing a fixture receipt must not turn it into live authority.
    raise Unbound('INACTIVE_SOURCE_NO_AUTHENTICATED_NATIVE_ADMISSION_COMPONENT')


def require(condition, reason):
    if condition is not True:
        raise Unbound(reason)


def finite_number(value, reason):
    require(type(value) in (int, float) and math.isfinite(value), reason)
    return value


def canonical_cpus(value):
    require(type(value) is list and 0 < len(value) <= MAX_CPU,
            'EXACT_AT_MOST_TWO_CPUS_REQUIRED')
    require(all(type(x) is int and x >= 0 for x in value)
            and value == sorted(set(value)), 'SORTED_UNIQUE_CPU_INTEGERS_REQUIRED')
    return tuple(value)


def exact_identity(value, expected_ppid=None, approved_cpus=None):
    require(type(value) is dict and set(value) ==
            {'pid', 'ppid', 'start_token', 'affinity'}, 'EXACT_LAUNCH_IDENTITY_FIELDS')
    require(type(value['pid']) is int and value['pid'] > 1
            and type(value['ppid']) is int and value['ppid'] > 0,
            'EXACT_PID_PPID_REQUIRED')
    token = value['start_token']
    require(type(token) is str and token.isascii() and token.isdecimal()
            and token == str(int(token)) and int(token) > 0, 'EXACT_PROC_BIRTH_TOKEN_REQUIRED')
    if expected_ppid is not None:
        require(type(expected_ppid) is int and value['ppid'] == expected_ppid,
                'DIRECT_CHILD_CONTROLLER_PARENT_REQUIRED')
    affinity = canonical_cpus(value['affinity'])
    if approved_cpus is not None:
        require(set(affinity) <= set(canonical_cpus(approved_cpus)),
                'LAUNCH_AFFINITY_OUTSIDE_APPROVED_CONTROLLER_CPUS')
    return (value['pid'], value['ppid'], token, affinity)


def identity_dict(identity):
    return {'pid': identity[0], 'ppid': identity[1],
            'start_token': identity[2], 'affinity': list(identity[3])}


def proc_identity(stat_bytes, affinity, pid):
    require(type(stat_bytes) is bytes and len(stat_bytes) <= 65536,
            'BOUNDED_PROC_STAT_BYTES_REQUIRED')
    # comm can contain spaces and parentheses; split at the final closing paren.
    try:
        text = stat_bytes.decode('ascii')
        left, tail = text.rsplit(')', 1)
        observed_pid = int(left.split(' ', 1)[0])
        fields = tail.split()
        result = {'pid': observed_pid, 'ppid': int(fields[1]),
                  'start_token': fields[19], 'affinity': affinity}
    except (UnicodeError, ValueError, IndexError) as exc:
        raise Unbound('INVALID_PROC_STAT_OBSERVATION') from exc
    require(type(pid) is int and observed_pid == pid, 'PROC_PID_MISMATCH')
    exact_identity(result)
    return result


class OriginalClock:
    """One initial unix/monotonic pair; every bound is capped, never renewed."""
    def __init__(self, clock, parent, *, original_seconds, cleanup_seconds,
                 sampled_unix, sampled_monotonic):
        require(type(clock) is dict and type(parent) is dict, 'CLOCK_OBJECTS_REQUIRED')
        require(type(original_seconds) is int and original_seconds > cleanup_seconds > 0
                and type(cleanup_seconds) is int, 'EXACT_ORIGINAL_RESERVE_REQUIRED')
        finite_number(sampled_unix, 'FINITE_CLOCK_SAMPLE')
        finite_number(sampled_monotonic, 'FINITE_CLOCK_SAMPLE')
        for row in (clock, parent):
            for name in ('accepted_unix', 'useful_deadline_unix', 'final_deadline_unix'):
                finite_number(row.get(name), 'FINITE_ORIGINAL_CLOCK:' + name)
            require(row['accepted_unix'] < row['useful_deadline_unix']
                    < row['final_deadline_unix'], 'ORDERED_ORIGINAL_CLOCK_REQUIRED')
        require(clock.get('original_seconds') == original_seconds
                and type(clock.get('original_seconds')) is int
                and clock.get('cleanup_seconds') == cleanup_seconds
                and type(clock.get('cleanup_seconds')) is int, 'NO_CLOCK_BUDGET_RESET')
        require(clock['final_deadline_unix'] <= clock['accepted_unix'] + original_seconds
                and clock['useful_deadline_unix'] <= clock['final_deadline_unix'] - cleanup_seconds,
                'ORIGINAL_USEFUL_FINAL_RESERVE_REQUIRED')
        self.final_unix = min(clock['final_deadline_unix'], parent['final_deadline_unix'])
        self.useful_unix = min(clock['useful_deadline_unix'], parent['useful_deadline_unix'],
                               self.final_unix - cleanup_seconds)
        offset = sampled_monotonic - sampled_unix
        self.final_monotonic = self.final_unix + offset
        self.useful_monotonic = self.useful_unix + offset
        self.cleanup_seconds = cleanup_seconds
        self.accepted_unix = clock['accepted_unix']
        self.original_seconds = original_seconds
        require(sampled_unix < self.useful_unix, 'ORIGINAL_USEFUL_DEADLINE_EXHAUSTED')

    def remaining(self, *, cleanup=False, minimum=0):
        finite_number(minimum, 'FINITE_OPERATION_RESERVE_REQUIRED')
        require(minimum >= 0, 'NONNEGATIVE_OPERATION_RESERVE_REQUIRED')
        end = self.final_monotonic if cleanup else self.useful_monotonic
        left = end - time.monotonic()
        require(left > minimum, 'ORIGINAL_BOUND_EXHAUSTED')
        # Wall-clock advancement also shortens the bound; backwards movement
        # cannot extend the originally recorded monotonic deadline.
        unix_end = self.final_unix if cleanup else self.useful_unix
        left = min(left, unix_end - time.time())
        require(left > minimum, 'ORIGINAL_BOUND_EXHAUSTED')
        return left

    def wire_useful_ns(self):
        # Integer flooring never extends the original monotonic deadline.
        return math.floor(self.useful_monotonic * 1_000_000_000)


def parse_fields(raw, required):
    require(type(raw) is str and len(raw) <= 65536, 'BOUNDED_CGROUP_OBSERVATION')
    fields = {}
    for line in raw.splitlines():
        parts = line.split()
        require(len(parts) == 2 and parts[0] not in fields, 'EXACT_CGROUP_FIELDS')
        fields[parts[0]] = parts[1]
    require(all(k in fields for k in required), 'MISSING_CGROUP_FIELDS')
    return fields


def parse_cpu_set(raw):
    require(type(raw) is str and len(raw) <= 4096 and bool(raw.strip()), 'FINITE_CPUSET_REQUIRED')
    values = []
    for item in raw.strip().split(','):
        parts = item.split('-')
        require(len(parts) in (1, 2) and all(x.isascii() and x.isdecimal() for x in parts),
                'EXACT_CPUSET_FORMAT')
        start, end = int(parts[0]), int(parts[-1])
        require(0 <= start <= end and end - start < MAX_CPU, 'CPUSET_OVER_BUDGET')
        values.extend(range(start, end + 1))
    require(values == sorted(set(values)), 'CPUSET_DUPLICATE_OR_UNORDERED')
    return canonical_cpus(values)


def observed_resource_caps(cpu_max, memory_max, cpuset, events, *, allowed_cpus):
    """Only cgroup file contents qualify; requested systemd properties do not."""
    allowed = canonical_cpus(allowed_cpus)
    require(type(cpu_max) is str and len(cpu_max) <= 128, 'BOUNDED_CPU_MAX')
    parts = cpu_max.split()
    require(len(parts) == 2 and all(x.isascii() and x.isdecimal() for x in parts),
            'ACTUAL_FINITE_CPU_QUOTA_REQUIRED')
    quota, period = map(int, parts)
    require(quota > 0 and period > 0 and quota <= MAX_CPU * period,
            'ACTUAL_CPU_QUOTA_OVER_BUDGET')
    require(type(memory_max) is str and len(memory_max) <= 128
            and memory_max.strip().isascii() and memory_max.strip().isdecimal(),
            'ACTUAL_FINITE_MEMORY_MAX_REQUIRED')
    memory = int(memory_max.strip())
    require(0 < memory <= MAX_MEMORY, 'ACTUAL_MEMORY_MAX_OVER_BUDGET')
    effective = parse_cpu_set(cpuset)
    require(set(effective) <= set(allowed), 'ACTUAL_EFFECTIVE_CPUSET_DRIFT')
    fields = parse_fields(events, ('populated',))
    require(fields['populated'] in ('0', '1'), 'EXACT_POPULATED_OBSERVATION_REQUIRED')
    return {'cpu_quota': quota, 'cpu_period': period, 'memory_max': memory,
            'effective_cpus': list(effective), 'populated': fields['populated'] == '1',
            'aggregate_memory_kind': 'CGROUP_MEMORY_NOT_AGGREGATE_ADDRESS_SPACE',
            'requested_properties_credit': False}


def bounded_read_fd(fd, maximum):
    require(type(fd) is int and fd >= 0 and type(maximum) is int
            and 0 < maximum <= 128 * 1024 ** 2, 'EXACT_FD_READ_BOUND')
    pieces = []; count = 0
    while True:
        part = os.pread(fd, min(65536, maximum + 1 - count), count)
        if not part:
            break
        pieces.append(part); count += len(part)
        require(count <= maximum, 'FD_BYTES_OVER_BOUND')
    return b''.join(pieces)


def file_signature(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


class HeldExecutableBuffer:
    """Borrow an already ancestor-verified FD; retain bytes and compiled object.

    Ancestor custody is supplied by the exact boundary VerifiedBytes object,
    never by this module reopening a pathname. This object does not authenticate
    the interpreter, extension loader or startup imports.
    """
    def __init__(self, verified, *, expected_sha, expected_mode, binary=False):
        verified.verify()
        require(type(expected_sha) is str and len(expected_sha) == 64,
                'EXACT_EXPECTED_BUFFER_SHA_REQUIRED')
        self.verified = verified
        self.fd = os.dup(verified.fd)
        self.closed = False
        try:
            st = os.fstat(self.fd)
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                    and not st.st_mode & (0o022 | stat.S_ISUID | stat.S_ISGID)
                    and stat.S_IMODE(st.st_mode) == expected_mode,
                    'PROTECTED_HELD_BUFFER_REQUIRED')
            self.signature = file_signature(st)
            self.raw = bounded_read_fd(self.fd, verified.max_bytes)
            require(self.raw == verified.raw
                    and hashlib.sha256(self.raw).hexdigest() == expected_sha,
                    'EXACT_VERIFIED_BUFFER_REQUIRED')
            self.sha256 = expected_sha
            self.binary = binary
            require(not binary or self.raw.startswith(b'\x7fELF'), 'FD_EXEC_ELF_REQUIRED')
            self.code = None if binary else compile(self.raw, str(verified.path), 'exec',
                                                   dont_inherit=True, optimize=0)
            self.namespace = None
            self.loaded_code = None
            self.verify()
        except BaseException:
            self.close(); raise

    def verify(self):
        require(not self.closed, 'CLOSED_HELD_BUFFER')
        self.verified.verify()
        require(file_signature(os.fstat(self.fd)) == self.signature
                and bounded_read_fd(self.fd, len(self.raw) + 1) == self.raw,
                'HELD_FD_OR_BYTES_DRIFT')
        return self.sha256

    def execute_exact(self, namespace):
        require(not self.binary and type(namespace) is dict, 'EXACT_SOURCE_NAMESPACE_REQUIRED')
        self.verify()
        self.namespace = namespace; self.loaded_code = self.code
        exec(self.code, namespace)
        self.verify()
        return namespace

    def verify_loaded_buffer(self, namespace, code):
        self.verify()
        require(namespace is self.namespace and code is self.loaded_code
                and code is self.code, 'LOADED_OBJECT_NOT_HELD_BUFFER')

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self.fd)


def exec_interpreter_fd_component(interpreter, bootstrap, arguments, environment):
    """Concrete Linux/Python FD-exec component; source-only gate prevents calls.

    No systemd FD forwarding is claimed. This component requires a qualified
    already-owned cgroup and native bootstrap/import custody BEFORE use.
    """
    require_native_admission()
    require(os.execve in os.supports_fd and interpreter.binary, 'HOST_FDEXEC_ELF_REQUIRED')
    require(type(bootstrap) is str and 0 < len(bootstrap.encode()) <= 65536,
            'BOUNDED_EXACT_BOOTSTRAP_REQUIRED')
    require(type(arguments) is list and all(type(x) is str for x in arguments),
            'EXPLICIT_EXEC_ARGUMENTS_REQUIRED')
    require(type(environment) is dict and set(environment) <= {'LC_ALL', 'LANG'}
            and all(type(v) is str for v in environment.values()),
            'NO_INHERITED_STARTUP_ENVIRONMENT')
    interpreter.verify()
    os.execve(interpreter.fd, ['python3', '-I', '-S', '-B', '-c', bootstrap, *arguments],
              dict(environment))


class KernelChild:
    """Finite launcher handle: immutable launch tuple captured before READY.

    Owns one retained pidfd and one direct child process; capture failure must
    be closed by the launcher before it can raise or return. Existing systemd
    service MainPID is not a direct child of the caller and cannot be substituted.
    """
    def __init__(self, process, read_identity, *, owner, clock):
        require_native_admission()
        self.owner = owner; self.clock = clock; self.process = process
        self.pidfd = None; self.closed = False
        clock.remaining()
        approved = sorted(os.sched_getaffinity(0))
        before = exact_identity(read_identity(process.pid), os.getpid(), approved)
        self.pidfd = os.pidfd_open(process.pid, 0)
        try:
            after = exact_identity(read_identity(process.pid), os.getpid(), approved)
            require(before == after and process.poll() is None, 'PRE_READY_BIRTH_DRIFT')
            require(not select.select([self.pidfd], [], [], 0)[0], 'PRE_READY_CHILD_ALREADY_EXITED')
            self._launch_identity = after
        except BaseException as exc:
            # Returning a pidfd without a verified birth is forbidden. The
            # launcher still owns its direct Popen child and must reap it.
            os.close(self.pidfd); self.pidfd = None
            raise StopUnconfirmed('PRE_READY_CAPTURE_FAILED_LAUNCHER_MUST_CLOSE') from exc

    @property
    def pid(self):
        return self.process.pid

    @property
    def launch_identity(self):
        return identity_dict(self._launch_identity)

    @property
    def kernel_identity(self):
        return self.launch_identity

    @property
    def returncode(self):
        return self.process.returncode

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        remaining = self.clock.remaining(cleanup=True)
        if timeout is not None:
            finite_number(timeout, 'FINITE_WAIT_TIMEOUT')
            require(timeout > 0, 'POSITIVE_WAIT_TIMEOUT')
            remaining = min(remaining, timeout)
        return self.process.wait(timeout=remaining)

    def signal_exact(self, sig, read_identity):
        self.clock.remaining(cleanup=True)
        require(not self.closed and self.pidfd is not None, 'RETAINED_PIDFD_REQUIRED')
        if self.process.poll() is not None:
            return False
        require(exact_identity(read_identity(self.process.pid), os.getpid()) == self._launch_identity,
                'STOP_UNCONFIRMED_BIRTH_DRIFT')
        signal.pidfd_send_signal(self.pidfd, sig, None, 0)
        return True

    def close_after_reap(self):
        require(self.process.poll() is not None, 'STOP_UNCONFIRMED_NOT_REAPED')
        if not self.closed:
            self.closed = True
            if self.pidfd is not None:
                closing = self.pidfd; self.pidfd = None; os.close(closing)


def valid_cleanup(closure, maximum=120):
    if type(closure) is not dict or type(maximum) is not int or maximum <= 0:
        return False
    duration = closure.get('cleanup_elapsed_seconds')
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= maximum:
        return False
    return (all(closure.get(k) is True for k in
                ('closed', 'worker_reaped', 'process_absence', 'path_absence', 'endpoint_absence'))
            and closure.get('escalation_needed') is False)


class ExistingNativeBoundary:
    """Map only real NativeSupervisor.observe/stop; no invented launch method.

    The existing methods have fixed 3s observe and 3+15+3s stop bounds. A call is
    refused when that full bound does not fit the ORIGINAL final clock. These
    methods alone do not bind loaded code, cgroup caps, direct child or endpoints.
    """
    def __init__(self, supervisor, association, clock):
        self.supervisor = supervisor; self.association = association; self.clock = clock
        self.invocation = None

    def observe(self):
        require_native_admission()
        self.clock.remaining(cleanup=True, minimum=3.1)
        row = self.supervisor.observe(self.association)
        self.clock.remaining(cleanup=True)
        require(type(row.invocation_id) is str and row.invocation_id,
                'OWNED_EXISTING_INVOCATION_REQUIRED')
        if self.invocation is None:
            self.invocation = row.invocation_id
        require(row.invocation_id == self.invocation, 'NATIVE_INVOCATION_CHANGED')
        return row

    def stop(self):
        require_native_admission()
        self.clock.remaining(cleanup=True, minimum=21.1)
        require(self.invocation is not None, 'OBSERVED_INVOCATION_BEFORE_STOP_REQUIRED')
        row = self.supervisor.stop(self.association)
        self.clock.remaining(cleanup=True)
        require((not row.invocation_id or row.invocation_id == self.invocation)
                and row.quiescent is True, 'STOP_UNCONFIRMED_NATIVE_CGROUP')
        return row


class HeldCgroup:
    """Retain no-follow cgroup directory FDs; qualify actual kernel cap files.

    This finite component does not create, move, delete or change any cgroup.
    A requested systemd property is never an input to resource qualification.
    """
    def __init__(self, group, *, unit, invocation, allowed_cpus, clock):
        require_native_admission()
        require(type(group) is str and group.startswith('/')
                and group.endswith('/' + unit) and '..' not in group.split('/')
                and all(part for part in group.split('/')[1:]), 'OWNED_CANONICAL_CGROUP_REQUIRED')
        require(type(invocation) is str and len(invocation) == 32
                and all(c in '0123456789abcdef' for c in invocation), 'EXACT_INVOCATION_REQUIRED')
        self.group = group; self.unit = unit; self.invocation = invocation
        self.allowed_cpus = list(canonical_cpus(allowed_cpus)); self.clock = clock
        self.rows = []; self.closed = False
        try:
            fd = os.open('/sys/fs/cgroup', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.rows.append((fd, None, None, self._signature(os.fstat(fd))))
            for part in group.split('/')[1:]:
                parent = self.rows[-1][0]
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                             dir_fd=parent)
                self.rows.append((fd, parent, part, self._signature(os.fstat(fd))))
            self.fd = self.rows[-1][0]
            self.verify()
        except BaseException:
            self.close(); raise

    @staticmethod
    def _signature(st):
        # cgroup pseudo-file sizes/times are mutable; directory dev/inode/type
        # retains the kernel object without pretending its contents are static.
        return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, stat.S_IFMT(st.st_mode))

    def verify(self):
        require(not self.closed, 'CLOSED_CGROUP_CUSTODY')
        self.clock.remaining(cleanup=True)
        for fd, parent, name, identity in self.rows:
            require(self._signature(os.fstat(fd)) == identity, 'CGROUP_FD_IDENTITY_DRIFT')
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISDIR(named.st_mode) and self._signature(named) == identity,
                        'CGROUP_NAMED_IDENTITY_DRIFT')

    def read(self, name, maximum=65536):
        require(name in {'cpu.max', 'memory.max', 'memory.current', 'cpuset.cpus.effective',
                         'cgroup.events', 'cgroup.procs'}, 'FINITE_CGROUP_READ_SET')
        self.verify()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=self.fd)
        try:
            raw = os.read(fd, maximum + 1)
            require(len(raw) <= maximum, 'BOUNDED_KERNEL_CGROUP_READ')
            result = raw.decode('ascii')
        finally:
            os.close(fd)
        self.verify()
        return result

    def observe_caps(self):
        before = self.read('cgroup.events')
        result = observed_resource_caps(self.read('cpu.max'), self.read('memory.max'),
                                        self.read('cpuset.cpus.effective'), before,
                                        allowed_cpus=self.allowed_cpus)
        after = parse_fields(self.read('cgroup.events'), ('populated',))
        require(after['populated'] == ('1' if result['populated'] else '0'),
                'CGROUP_POPULATION_CHANGED_DURING_OBSERVATION')
        self.verify()
        return result

    def confirm_empty(self):
        # cgroup.events populated=0 covers descendants, including detached
        # sessions. Root cgroup.procs alone is insufficient for tree absence.
        before = parse_fields(self.read('cgroup.events'), ('populated',))
        direct = self.read('cgroup.procs')
        after = parse_fields(self.read('cgroup.events'), ('populated',))
        return before['populated'] == after['populated'] == '0' and not direct.strip()

    def close(self):
        if not self.closed:
            self.closed = True
            for fd, _, _, _ in reversed(self.rows):
                os.close(fd)


class IndependentlyHeldUnitEnvelope:
    """Source counterpart for an actual outside controller; never self-stop.

    Construction needs native admission and real NativeSupervisor observations.
    This is a held ownership component, not a JSON receipt or binding grant.
    Startup/transport/source qualification of the outside controller is UNBOUND.
    """
    def __init__(self, native, cgroup, clock):
        require_native_admission()
        require(type(native) is ExistingNativeBoundary and type(cgroup) is HeldCgroup,
                'EXACT_INDEPENDENT_HELD_UNIT_COMPONENTS_REQUIRED')
        row = native.observe()
        require(row.main_pid != os.getpid() and row.control_group == cgroup.group
                and row.invocation_id == cgroup.invocation,
                'INDEPENDENT_OUTSIDE_UNIT_CONTROLLER_REQUIRED')
        require_owner_outside_group(os.getpid(), cgroup.group)
        self.native = native; self.cgroup = cgroup; self.clock = clock
        self.owner_pid = os.getpid(); self.owner_birth = read_kernel_identity_component(os.getpid())
        self.unit = cgroup.unit; self.invocation = cgroup.invocation
    def verify(self):
        require_native_admission()
        require(os.getpid() == self.owner_pid
                and read_kernel_identity_component(self.owner_pid) == self.owner_birth,
                'OUTSIDE_OWNER_BIRTH_CUSTODY_REQUIRED')
        require_owner_outside_group(self.owner_pid, self.cgroup.group)
        self.cgroup.verify(); self.clock.remaining(cleanup=True)
    def stop(self):
        self.verify(); self.clock.remaining(cleanup=True, minimum=24.2)
        return self.native.stop()
    def observe(self):
        self.verify()
        row = self.native.observe()
        require(not row.invocation_id or row.invocation_id == self.invocation,
                'OUTSIDE_UNIT_INVOCATION_DRIFT')
        return {'native_quiescent': row.quiescent is True, 'cgroup_empty': self.cgroup.confirm_empty(),
                'path_absence': None, 'endpoint_absence': None, 'closed': False}

def cleanup_failure(primary, errors, observations):
    exc = StopUnconfirmed('STOP_UNCONFIRMED:' + repr([(stage, type(e).__name__, str(e)) for stage, e in errors]))
    exc.primary_error = primary; exc.cleanup_errors = tuple(errors); exc.observations = observations
    return exc

def fresh_owned_observation_component(child, native, cgroup, read_identity, clock):
    """Independent read/wait witness. Never calls stop or sends a signal."""
    errors = []; out = {}; started = time.monotonic()
    actions = [('native', lambda: native.observe()),
               ('cgroup', lambda: cgroup.confirm_empty()),
               ('wait', lambda: child.wait(timeout=max(0.001, clock.remaining(cleanup=True) - 3.1))),
               ('process', lambda: read_identity(child.process.pid))]
    for name, action in actions:
        try:
            clock.remaining(cleanup=True)
            out[name] = action()
        except BaseException as exc:
            errors.append((name, exc))
    out['closed'] = False
    out['worker_reaped'] = 'wait' in out and child.returncode is not None
    out['process_absence'] = out.get('cgroup') is True and 'process' in out and out['process'] is None
    out['path_absence'] = None; out['endpoint_absence'] = None
    out['cleanup_elapsed_seconds'] = time.monotonic() - started
    out['escalation_needed'] = None
    if errors: raise cleanup_failure(None, errors, out)
    return out

def bounded_owned_cleanup_component(child, identity, native, cgroup, read_identity, clock):
    require_native_admission()
    require(type(child) is KernelChild and child.launch_identity == identity,
            'EXACT_RETAINED_PRE_READY_CUSTODY_REQUIRED')
    require(type(native) is ExistingNativeBoundary and type(cgroup) is HeldCgroup,
            'OWNED_NATIVE_CGROUP_COMPONENTS_REQUIRED')
    started = time.monotonic(); errors = []; observed = None
    try:
        # Reserve the real outside observe bound from the ORIGINAL cleanup wall.
        clock.remaining(cleanup=True, minimum=24.2)
        require(native.stop().quiescent is True, 'STOP_UNCONFIRMED_NATIVE_UNIT')
    except BaseException as exc:
        errors.append(('native_stop', exc))
    finally:
        try:
            observed = fresh_owned_observation_component(child, native, cgroup, read_identity, clock)
        except BaseException as exc:
            errors.append(('fresh_witness', exc))
    if errors: raise cleanup_failure(None, errors, observed)
    elapsed = time.monotonic() - started
    require(math.isfinite(elapsed) and 0 <= elapsed <= min(120, clock.cleanup_seconds),
            'STOP_UNCONFIRMED_ORIGINAL_CLEANUP_BOUND')
    observed['cleanup_elapsed_seconds'] = elapsed
    # Endpoints/path owner is still missing; this partial result is never closure.
    return observed


def read_kernel_cgroup_component(pid):
    """Observe the actual unified cgroup of a held live process; no READY input."""
    require(type(pid) is int and pid > 1, 'EXACT_PROCESS_PID_REQUIRED')
    fd = os.open('/proc/' + str(pid) + '/cgroup', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = os.read(fd, 65537)
    finally:
        os.close(fd)
    require(len(raw) <= 65536, 'BOUNDED_PROC_CGROUP_REQUIRED')
    try:
        rows = raw.decode('ascii').splitlines()
    except UnicodeError as exc:
        raise Unbound('ASCII_UNIFIED_CGROUP_REQUIRED') from exc
    require(len(rows) == 1 and rows[0].startswith('0::'), 'EXACT_UNIFIED_CGROUP_REQUIRED')
    group = rows[0][3:]
    require(group.startswith('/') and (group == '/' or
            all(part and part not in ('.', '..') for part in group.split('/')[1:])),
            'CANONICAL_UNIFIED_CGROUP_REQUIRED')
    return group


def require_owner_outside_group(pid, target):
    require(type(target) is str and target.startswith('/') and target != '/' and
            all(part and part not in ('.', '..') for part in target.split('/')[1:]),
            'CANONICAL_TARGET_CGROUP_REQUIRED')
    before = read_kernel_identity_component(pid)
    require(before is not None, 'LIVE_OUTSIDE_OWNER_REQUIRED')
    actual = read_kernel_cgroup_component(pid)
    after = read_kernel_identity_component(pid)
    require(before == after, 'OUTSIDE_OWNER_BIRTH_DRIFT_DURING_CGROUP_OBSERVATION')
    require(actual != target and not actual.startswith(target + '/'),
            'OUTSIDE_OWNER_IS_WITHIN_TARGET_CGROUP')
    return actual


def read_kernel_identity_component(pid):
    """Actual proc tuple observer; cannot be replaced by a READY receipt."""
    require(type(pid) is int and pid > 1, 'EXACT_PROCESS_PID_REQUIRED')
    try:
        fd = os.open('/proc/' + str(pid) + '/stat', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            raw = os.read(fd, 65537)
        finally:
            os.close(fd)
        return proc_identity(raw, sorted(os.sched_getaffinity(pid)), pid)
    except FileNotFoundError:
        return None


def launch_owned_direct_fd_child_component(interpreter, bootstrap, inherited_buffers,
                                          arguments, *, native, cgroup, owner, clock,
                                          stdout, stderr, outside_owner=None):
    """Finite direct-child source component inside an ALREADY owned service.

    systemd-run must have started the controller envelope, not this child.
    Popen/pass_fds is an existing supported interface. /proc/self/fd refers to
    the retained ELF FD inherited by the exec child; no arbitrary descriptors
    are assumed to pass through systemd. Native admission stays unavailable.

    The exact bootstrap must supply its own held READY/GO channels and full
    graph; this component alone never authorizes GO or product effects.
    """
    require_native_admission()
    require(type(interpreter) is HeldExecutableBuffer and interpreter.binary
            and type(bootstrap) is HeldExecutableBuffer and not bootstrap.binary,
            'EXACT_HELD_INTERPRETER_BOOTSTRAP_REQUIRED')
    require(type(inherited_buffers) is list and all(type(x) is HeldExecutableBuffer
            for x in inherited_buffers), 'EXACT_HELD_IMPORT_PROGRAM_BUFFERS_REQUIRED')
    require(type(arguments) is list and all(type(x) is str for x in arguments),
            'EXPLICIT_CHILD_ARGUMENTS_REQUIRED')
    require(type(native) is ExistingNativeBoundary and type(cgroup) is HeldCgroup,
            'EXISTING_OWNED_CONTROLLER_ENVELOPE_REQUIRED')
    observed = native.observe()
    require(observed.main_pid == os.getpid() and observed.control_group == cgroup.group
            and observed.invocation_id == cgroup.invocation,
            'CONTROLLER_MUST_ALREADY_EXECUTE_INSIDE_OWNED_SERVICE')
    caps = cgroup.observe_caps()
    require(caps['populated'] is True and set(os.sched_getaffinity(0)) <= set(caps['effective_cpus']),
            'OBSERVED_CONTROLLER_RESOURCE_CUSTODY_REQUIRED')
    buffers = [interpreter, bootstrap, *inherited_buffers]
    for held in buffers:
        held.verify()
    bootstrap_text = bootstrap.raw.decode('utf8')
    require(0 < len(bootstrap.raw) <= 65536, 'BOUNDED_LITERAL_BOOTSTRAP')
    process = None; pidfd = None; child = None
    try:
        clock.remaining()
        process = subprocess.Popen(['/proc/self/fd/' + str(interpreter.fd),
                                    '-I', '-S', '-B', '-c', bootstrap_text, *arguments],
                                   env={'LC_ALL': 'C', 'LANG': 'C'},
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   close_fds=True, pass_fds=tuple(sorted({x.fd for x in buffers})))
        # Direct child ownership and kernel pidfd exist before READY parsing.
        # A live child or unreaped zombie's PID cannot be reused while its
        # owning controller retains the wait relationship.
        pidfd = os.pidfd_open(process.pid, 0)
        before = exact_identity(read_kernel_identity_component(process.pid), os.getpid(), caps['effective_cpus'])
        after = exact_identity(read_kernel_identity_component(process.pid), os.getpid(), caps['effective_cpus'])
        require(before == after and process.poll() is None
                and not select.select([pidfd], [], [], 0)[0], 'PRE_READY_EXACT_BIRTH_CUSTODY_REQUIRED')
        child = object.__new__(KernelChild)
        child.owner = owner; child.clock = clock; child.process = process
        child.pidfd = pidfd; child.closed = False; child._launch_identity = before
        pidfd = None  # ownership moved once to the returned handle
        for held in buffers:
            held.verify()
        cgroup.observe_caps(); clock.remaining()
        return child
    except BaseException as cause:
        if process is not None:
            owned_fd = child.pidfd if child is not None else pidfd
            errors = []; observations = {}
            try:
                if process.poll() is None:
                    # Retained pidfd is authenticated by direct Popen ownership.
                    # No numeric-PID fallback if pidfd capture failed.
                    if owned_fd is not None:
                        clock.remaining(cleanup=True)
                        signal.pidfd_send_signal(owned_fd, signal.SIGKILL, None, 0)
                    else:
                        require(type(outside_owner) is IndependentlyHeldUnitEnvelope
                                and outside_owner.invocation == cgroup.invocation
                                and outside_owner.cgroup.group == cgroup.group,
                                'UNBOUND_INDEPENDENT_OUTSIDE_UNIT_OWNER')
                        # Outside envelope stop is handled independently below.
                        pass
            except BaseException as exc:
                errors.append(('owned_pidfd_stop', exc))
            finally:
                # The independent unit stop is not coupled to signal success.
                # It precedes a potentially blocking direct wait so the original
                # cleanup reserve remains available to stop all descendants.
                try:
                    require(type(outside_owner) is IndependentlyHeldUnitEnvelope,
                            'UNBOUND_INDEPENDENT_OUTSIDE_UNIT_OWNER')
                    require(outside_owner.invocation == cgroup.invocation
                            and outside_owner.cgroup.group == cgroup.group,
                            'EXACT_OUTSIDE_UNIT_ENVELOPE_BINDING_REQUIRED')
                    outside_owner.stop()
                except BaseException as exc:
                    errors.append(('outside_unit_stop', exc))
                # Even stop failure cannot skip direct wait and independent reads.
                for name, action in [('direct_wait', lambda: process.wait(timeout=max(0.001, clock.remaining(cleanup=True) - 3.1))),
                                     ('native_observe', lambda: native.observe()),
                                     ('cgroup_empty', lambda: cgroup.confirm_empty()),
                                     ('fresh_process', lambda: read_kernel_identity_component(process.pid))]:
                    try:
                        clock.remaining(cleanup=True); observations[name] = action()
                    except BaseException as exc:
                        errors.append((name, exc))
                if type(outside_owner) is IndependentlyHeldUnitEnvelope:
                    try: observations['outside_witness'] = outside_owner.observe()
                    except BaseException as exc: errors.append(('outside_witness', exc))
                elif observations.get('cgroup_empty') is not True:
                    errors.append(('outside_unit_owner', Unbound('UNBOUND_INDEPENDENT_OUTSIDE_UNIT_OWNER')))
                if owned_fd is not None:
                    os.close(owned_fd)
                    if child is not None: child.pidfd = None; child.closed = True
                    pidfd = None
            if errors: raise cleanup_failure(cause, errors, observations) from cause
        raise

    finally:
        if pidfd is not None:
            closing = pidfd; pidfd = None; os.close(closing)


class FiniteNativeHostAdapter:
    """Exact caller surface, deliberately unbound. Not an installed API.

    A dict, fixture method, mutable module constant, requested unit property or
    path SHA cannot grant startup authority. There is intentionally no bind API.
    Independent qualification must supply a reviewed real bootstrap integration.
    """
    def __init__(self, clock, *, run_token, reserved_root_identity,
                 gated_helper_sha256=None, staged_validator_sha256=None):
        require(type(clock) is OriginalClock, 'EXACT_ORIGINAL_CLOCK_COMPONENT')
        require(type(run_token) is str and len(run_token) >= 16, 'EXACT_RUN_TOKEN')
        self.clock = clock; self.run_token = run_token
        self.reserved_root_identity = reserved_root_identity
        self.gated_helper_sha256 = gated_helper_sha256
        self.staged_validator_sha256 = staged_validator_sha256
        self.original_useful_deadline_monotonic = clock.useful_monotonic
        self.parent_final_deadline_unix = clock.final_unix
        self.parent_useful_deadline_unix = clock.useful_unix
        self.inventory_before_go = False
        self.pid_birth_validated = False
        self.all_actual_affinities_within_budget = False
        self.hard_resource_boundary_validated = False
        self._owned = object()
        self._outside_unit_envelope = None  # no runtime qualification/bind authority supplied

    def verify_startup_before_effects(self):
        raise Unbound('UNBOUND_NATIVE_INTERPRETER_ELF_LOADER_STARTUP_HELD_PROVENANCE')

    def verify_import_graph_and_environment(self):
        raise Unbound('UNBOUND_COMPLETE_TRANSITIVE_NATIVE_IMPORT_GRAPH_ENVIRONMENT')

    def verify_aggregate_hard_resources(self, cpus, memory):
        require(type(cpus) is int and cpus == MAX_CPU and type(memory) is int
                and memory == MAX_MEMORY, 'CANONICAL_RESOURCE_REQUEST_REQUIRED')
        raise Unbound('UNBOUND_OBSERVED_CGROUP_CAPS_ALL_DESCENDANTS_AS_SEMANTICS')

    def launch_verified_source_held(self, gate, program, command, root, token, stdout, stderr):
        # Nothing has started when this method refuses. A future finite launch
        # counterpart must own partial creation until cleanup has been observed.
        self.clock.remaining()
        self.verify_startup_before_effects()
        raise Unbound('UNBOUND_FINITE_SYSTEMD_OR_DELEGATED_CGROUP_FDEXEC_LAUNCHER')

    def kernel_identity_before_ready(self, child):
        require(type(child) is KernelChild and child.owner is self._owned
                and not child.closed, 'HOST_OWNED_PRE_READY_HANDLE_REQUIRED')
        value = child.launch_identity
        expected = exact_identity(value, os.getpid(), sorted(os.sched_getaffinity(0)))
        observed = read_kernel_identity_component(child.process.pid)
        require(observed is not None and exact_identity(observed, os.getpid(),
                sorted(os.sched_getaffinity(0))) == expected, 'PRE_READY_RETAINED_KERNEL_BIRTH_DRIFT')
        return value

    def validate_actual_ready(self, child, token, gate_identity, program_identity, root_identity):
        self.kernel_identity_before_ready(child)
        raise Unbound('UNBOUND_AUTHENTICATED_HELD_READY_CHANNEL_AND_SOURCE_GRAPH')

    def verify_ready_and_resources_before_go(self, identity, reservation):
        exact_identity({k: identity[k] for k in ('pid', 'ppid', 'start_token', 'affinity')})
        self.verify_aggregate_hard_resources(MAX_CPU, MAX_MEMORY)
        raise Unbound('UNBOUND_PRE_GO_UNIT_INVOCATION_SOURCE_INVENTORY')

    def release_exact_held_child(self, child, identity):
        require(child.launch_identity == identity, 'EXACT_GO_KERNEL_IDENTITY_REQUIRED')
        raise Unbound('UNBOUND_AUTHENTICATED_SINGLE_RELEASE_CHANNEL')

    def wait_exact_with_original_wall(self, child, identity):
        require(type(child) is KernelChild and child.owner is self._owned
                and not child.closed and child.launch_identity == identity,
                'EXACT_WAIT_RETAINED_CUSTODY_REQUIRED')
        return child.wait(timeout=self.clock.remaining())

    def retained_owned_launch_identity(self, child):
        require(type(child) is KernelChild and child.owner is self._owned
                and child.clock is self.clock and not child.closed
                and type(child.pidfd) is int and child.pidfd >= 0,
                'UNBOUND_NO_AUTHENTICATED_RETURNED_HOST_HANDLE')
        return child.launch_identity

    def stop_owned_returned_child_before_original_final_deadline(self, child):
        errors = []; owned = False
        try:
            self.retained_owned_launch_identity(child)
            owned = True
            self.clock.remaining(cleanup=True)
            if child.process.poll() is None:
                signal.pidfd_send_signal(child.pidfd, signal.SIGKILL, None, 0)
        except BaseException as exc:
            errors.append(('owned_pidfd_stop', exc))
        finally:
            # The host's held independent envelope is its own allocated unit.
            # Failure of returned-child identity/signal may not skip its stop.
            try:
                envelope = self._outside_unit_envelope
                require(type(envelope) is IndependentlyHeldUnitEnvelope,
                        'UNBOUND_INDEPENDENT_OUTSIDE_UNIT_OWNER_FOR_DESCENDANTS')
                envelope.stop()
            except BaseException as exc:
                errors.append(('outside_unit_stop', exc))
            if owned:
                try:
                    child.wait(timeout=max(0.001, self.clock.remaining(cleanup=True) - 3.1))
                except BaseException as exc:
                    errors.append(('direct_wait', exc))
        if errors: raise cleanup_failure(None, errors, None)

    def stop_reap_exact_before_original_final_deadline(self, child, identity):
        require(self.retained_owned_launch_identity(child) == identity,
                'EXACT_STOP_RETAINED_CUSTODY_REQUIRED')
        return self.stop_owned_returned_child_before_original_final_deadline(child)

    def fresh_owned_returned_absence(self, child, identity=None, **kwargs):
        # A concrete fresh observation independent from the stop path. It cannot
        # supply genuine unit/path/endpoint authority absent external qualification.
        errors = []; observations = {}
        try:
            retained = self.retained_owned_launch_identity(child)
            if identity is not None: require(retained == identity, 'EXACT_FRESH_RETAINED_CUSTODY_REQUIRED')
        except BaseException as exc:
            errors.append(('ownership', exc))
        for name, action in [('direct_wait', lambda: child.wait(timeout=self.clock.remaining(cleanup=True))),
                             ('process', lambda: read_kernel_identity_component(child.process.pid))]:
            try:
                self.clock.remaining(cleanup=True); observations[name] = action()
            except BaseException as exc:
                errors.append((name, exc))
        envelope = self._outside_unit_envelope
        if type(envelope) is IndependentlyHeldUnitEnvelope:
            try: observations['outside_unit'] = envelope.observe()
            except BaseException as exc: errors.append(('outside_unit', exc))
        else: errors.append(('outside_unit', Unbound('UNBOUND_INDEPENDENT_OUTSIDE_UNIT_OWNER')))
        errors.append(('path_endpoint', Unbound('UNBOUND_INDEPENDENT_OUTSIDE_PATH_ENDPOINT_WITNESS')))
        raise cleanup_failure(None, errors, observations)

    def fresh_exact_stop_reap_and_absence(self, child, identity, **kwargs):
        return self.fresh_owned_returned_absence(child, identity, **kwargs)

    def validate_original_clock(self, clock, *, original_seconds, cleanup_seconds):
        require(type(original_seconds) is int and original_seconds == self.clock.original_seconds
                and type(cleanup_seconds) is int and cleanup_seconds == self.clock.cleanup_seconds,
                'EXACT_ORIGINAL_CLOCK_BUDGET_REQUIRED')
        require(type(clock) is dict and clock.get('accepted_unix') == self.clock.accepted_unix,
                'EXACT_ORIGINAL_CLOCK_BINDING_REQUIRED')
        self.clock.remaining()
        return {'accepted_unix': self.clock.accepted_unix,
                'useful_deadline_unix': self.clock.useful_unix,
                'final_deadline_unix': self.clock.final_unix}

    def current_exact_owned_tree(self, child, identity):
        self.kernel_identity_before_ready(child)
        raise Unbound('UNBOUND_CGROUP_INODE_INVOCATION_ALL_PROCESS_BIRTH_INVENTORY')

    def read_fresh_result_and_genuine_receipt(self, root, ready, clock):
        raise Unbound('UNBOUND_GENUINE_RECEIPT_ORIGINAL_RUN_TOKEN_FRESH_CUSTODY')

    def actual_worker_ready_before_go(self, proc, affinity):
        raise Unbound('UNBOUND_WORKER_PRE_READY_PARENT_CGROUP_CHANNEL')

    def record_ready_before_go(self, identity, own, source, parent, address_space):
        raise Unbound('UNBOUND_WORKER_PRE_READY_PARENT_CGROUP_CHANNEL')

    def wait_verified_go_with_original_deadline(self, ready, clock):
        raise Unbound('UNBOUND_WORKER_HELD_GO_CHANNEL')

    def verify_original_wall_before_go(self):
        self.clock.remaining()
        self.verify_startup_before_effects()


if __name__ == '__main__':
    raise Unbound('INACTIVE_SOURCE_ONLY_NO_NATIVE_ADMISSION')
