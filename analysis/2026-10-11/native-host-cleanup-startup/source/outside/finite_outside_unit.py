"""Finite user-systemd launch/IPC/cleanup SOURCE; public admission is UNBOUND.

NativeSupervisor is injected from the exact reviewed product snapshot, and is
used only for observe/stop. This module neither imports that product nor starts
anything at import. Host startup/import custody and whole independent acceptance
must precede replacing the unconditional source gate in a reviewed composition.
"""
from __future__ import annotations
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import time
from dataclasses import dataclass, replace

SOURCE_ONLY = True
MAX_WIRE = 65536
MAX_FDS = 64
MAX_FILES = 128
MAX_PIDS = 128
MEMORY = 1024 ** 3
UNIT_RE = r'friday-rework-worker-[0-9a-f]{32}\.service'


class Unbound(RuntimeError):
    pass


class CleanupUnconfirmed(RuntimeError):
    def __init__(self, primary, errors, observed):
        super().__init__('STOP_UNCONFIRMED:' + repr([(s, type(e).__name__, str(e)) for s, e in errors]))
        self.primary_error = primary
        self.cleanup_errors = tuple(errors)
        self.observations = observed


def need(value, reason):
    if value is not True:
        raise Unbound(reason)


def require_native_admission():
    raise Unbound('SOURCE_ONLY_UNBOUND_WHOLE_ACCEPTANCE_AND_NATIVE_STARTUP_HOST_QUALIFICATION')


def signature(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_fd(fd, maximum):
    need(type(fd) is int and fd >= 0 and type(maximum) is int and 0 < maximum <= 128 * MEMORY,
         'EXACT_FD_READ_BOUND')
    raw = bytearray()
    while len(raw) <= maximum:
        part = os.pread(fd, min(65536, maximum + 1 - len(raw)), len(raw))
        if not part:
            break
        raw.extend(part)
    need(len(raw) <= maximum, 'HELD_BYTES_OVER_BOUND')
    return bytes(raw)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def exact_json(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_WIRE, 'FINITE_WIRE_BYTES')
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, 'DUPLICATE_WIRE_KEY')
            out[key] = value
        return out
    value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(Unbound('NONFINITE_WIRE_NUMBER')))
    need(type(value) is dict and canonical_json(value) == raw, 'CANONICAL_EXACT_WIRE')
    return value


def process_birth(pid):
    need(type(pid) is int and pid > 1, 'EXACT_PID')
    try:
        fd = os.open('/proc/' + str(pid) + '/stat', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            raw = os.read(fd, 65537)
        finally:
            os.close(fd)
        need(len(raw) <= 65536, 'BOUNDED_PROC_STAT')
        left, tail = raw.decode('ascii').rsplit(')', 1)
        fields = tail.split()
        need(int(left.split(' ', 1)[0]) == pid, 'PROC_PID_DRIFT')
        return (pid, int(fields[1]), int(fields[19]))
    except FileNotFoundError:
        return None


def process_group(pid):
    rows = bounded_path('/proc/' + str(pid) + '/cgroup', 4096).decode('ascii').splitlines()
    need(len(rows) == 1 and rows[0].startswith('0::/'), 'EXACT_UNIFIED_CGROUP')
    return rows[0][3:]


def bounded_path(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        result = bytearray()
        while len(result) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(result)))
            if not block:
                break
            result.extend(block)
        need(len(result) <= maximum, 'BOUNDED_KERNEL_PATH_OBSERVATION')
        return bytes(result)
    finally:
        os.close(fd)


def is_within(group, boundary):
    need(type(group) is str and type(boundary) is str and group.startswith('/')
         and boundary.startswith('/') and '..' not in group.split('/')
         and '..' not in boundary.split('/'), 'CANONICAL_CGROUP_NAMES')
    return group == boundary or group.startswith(boundary + '/')


def exact_cpus(cpus):
    need(type(cpus) in (tuple, list) and 0 < len(cpus) <= 2
         and all(type(x) is int and x >= 0 for x in cpus)
         and list(cpus) == sorted(set(cpus)), 'AT_MOST_TWO_SORTED_UNIQUE_CPUS')
    return tuple(cpus)


def parse_cpuset(raw):
    need(type(raw) is str and 0 < len(raw) <= 4096, 'BOUNDED_CPUSET')
    result = []
    for item in raw.strip().split(','):
        pair = item.split('-')
        need(1 <= len(pair) <= 2 and all(re.fullmatch(r'0|[1-9][0-9]*', p) for p in pair),
             'EXACT_CPUSET_FORMAT')
        first, last = int(pair[0]), int(pair[-1])
        need(first <= last and last - first < 2, 'CPUSET_OVER_TWO')
        result.extend(range(first, last + 1))
    return exact_cpus(result)


@dataclass(frozen=True)
class Grant:
    """Immutable ORIGINAL reservation, never a receipt granting admission."""
    token: str
    unit: str
    admission_hash: str
    accepted_unix: float
    accepted_monotonic: float
    useful_unix: float
    final_unix: float
    useful_monotonic: float
    final_monotonic: float
    parent_useful_unix: float
    parent_final_unix: float
    reservation: tuple
    cpus: tuple

    def validate(self):
        need(re.fullmatch(r'[0-9a-f]{64}', self.token) is not None, 'EXACT_ORIGINAL_TOKEN')
        need(re.fullmatch(UNIT_RE, self.unit) is not None, 'EXACT_UNIQUE_UNIT')
        need(re.fullmatch(r'[0-9a-f]{64}', self.admission_hash) is not None, 'EXACT_ADMISSION_HASH')
        values = (self.accepted_unix, self.accepted_monotonic, self.useful_unix, self.final_unix,
                  self.useful_monotonic, self.final_monotonic, self.parent_useful_unix, self.parent_final_unix)
        need(all(type(v) in (float, int) and math.isfinite(v) for v in values), 'FINITE_ORIGINAL_CLOCK')
        need(self.accepted_unix < self.useful_unix < self.final_unix
             and self.final_unix - self.accepted_unix <= 600
             and 0 < self.final_monotonic - self.accepted_monotonic <= 600
             and self.final_unix - self.useful_unix >= 60
             and self.final_monotonic - self.useful_monotonic >= 60
             and self.useful_unix <= self.parent_useful_unix
             and self.final_unix <= self.parent_final_unix
             and abs((self.final_unix - self.accepted_unix) -
                     (self.final_monotonic - self.accepted_monotonic)) < 0.000001
             and abs((self.useful_unix - self.accepted_unix) -
                     (self.useful_monotonic - self.accepted_monotonic)) < 0.000001,
             'ORIGINAL_600_CLEANUP_60_NO_RENEWAL')
        need(type(self.reservation) is tuple and len(self.reservation) == 2
             and all(type(v) is int and v >= 0 for v in self.reservation), 'EXACT_RESERVED_ROOT_DEV_INO')
        exact_cpus(self.cpus)
        return self

    def remaining(self, cleanup=False, reserve=0):
        need(type(reserve) in (float, int) and math.isfinite(reserve) and reserve >= 0,
             'EXACT_OPERATION_RESERVE')
        end_u = self.final_unix if cleanup else self.useful_unix
        end_m = self.final_monotonic if cleanup else self.useful_monotonic
        value = min(end_u - time.time(), end_m - time.monotonic())
        need(value > reserve, 'ORIGINAL_BOUND_EXHAUSTED')
        return value

    def wire(self):
        self.validate()
        return {'token': self.token, 'unit': self.unit, 'admission_hash': self.admission_hash,
                'accepted_unix': self.accepted_unix, 'accepted_monotonic': self.accepted_monotonic,
                'useful_unix': self.useful_unix,
                'final_unix': self.final_unix,
                'useful_monotonic': self.useful_monotonic, 'final_monotonic': self.final_monotonic,
                'parent_useful_unix': self.parent_useful_unix, 'parent_final_unix': self.parent_final_unix,
                'reservation': list(self.reservation), 'cpus': list(self.cpus)}


class CgroupCustody:
    """Kernel directory/ancestor descriptors; no creation or cgroup mutation."""
    def __init__(self, group, unit, grant):
        need(group.startswith('/') and group.endswith('/' + unit)
             and all(p and p not in ('.', '..') for p in group.split('/')[1:]), 'OWNED_UNIT_CGROUP')
        self.group = group
        self.grant = grant
        self.chain = []
        try:
            root = os.open('/sys/fs/cgroup', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.chain.append((root, None, None, self.dir_identity(os.fstat(root))))
            for part in group.split('/')[1:]:
                parent = self.chain[-1][0]
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                             dir_fd=parent)
                self.chain.append((fd, parent, part, self.dir_identity(os.fstat(fd))))
        except BaseException:
            self.close()
            raise

    @staticmethod
    def dir_identity(st):
        return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, stat.S_IFMT(st.st_mode))

    def verify(self):
        self.grant.remaining(cleanup=True)
        need(bool(self.chain), 'RETAINED_CGROUP_REQUIRED')
        for fd, parent, name, expected in self.chain:
            need(self.dir_identity(os.fstat(fd)) == expected, 'CGROUP_FD_DRIFT')
            if parent is not None:
                need(self.dir_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                     'CGROUP_NAMESPACE_DRIFT')

    def read(self, name, maximum=65536):
        need(name in ('cpu.max', 'memory.max', 'cpuset.cpus.effective', 'cgroup.events', 'cgroup.procs'),
             'FINITE_CGROUP_FILES')
        self.verify()
        fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=self.chain[-1][0])
        try:
            raw = os.read(fd, maximum + 1)
            need(len(raw) <= maximum, 'BOUNDED_CGROUP_READ')
            result = raw.decode('ascii')
        finally:
            os.close(fd)
        self.verify()
        return result

    def caps(self):
        cpu = self.read('cpu.max', 128).split()
        need(len(cpu) == 2 and all(re.fullmatch(r'[1-9][0-9]*', x) for x in cpu),
             'OBSERVED_FINITE_CPU_MAX_REQUIRED')
        quota, period = map(int, cpu)
        need(quota <= 2 * period, 'OBSERVED_CPU_QUOTA_OVER_TWO')
        memory = self.read('memory.max', 128).strip()
        need(re.fullmatch(r'[1-9][0-9]*', memory) is not None and int(memory) <= MEMORY,
             'OBSERVED_AGGREGATE_CGROUP_MEMORY_MAX_REQUIRED')
        cpus = parse_cpuset(self.read('cpuset.cpus.effective', 4096))
        need(set(cpus) <= set(self.grant.cpus), 'OBSERVED_CPUSET_DRIFT')
        need(self.populated() is True, 'HELD_CONTROLLER_POPULATION_REQUIRED')
        return {'quota': quota, 'period': period, 'cpus': list(cpus), 'memory_max': int(memory),
                'coverage': 'ALL_DESCENDANTS_IN_THIS_KERNEL_CGROUP',
                'address_space': 'LIMIT_AS_IS_SEPARATE_PER_PROCESS_NOT_AGGREGATE_AS',
                'requested_properties_credit': False}

    def populated(self):
        rows = [row.split() for row in self.read('cgroup.events').splitlines()]
        need(all(len(row) == 2 for row in rows), 'EXACT_CGROUP_EVENTS')
        fields = dict(rows)
        need(len(fields) == len(rows) and fields.get('populated') in ('0', '1'), 'EXACT_POPULATED_FIELD')
        return fields['populated'] == '1'

    def empty(self):
        before = self.populated()
        direct = self.read('cgroup.procs').strip()
        after = self.populated()
        return before is False and after is False and not direct

    def close(self):
        errors = []
        for fd, _, _, _ in reversed(self.chain):
            try:
                os.close(fd)
            except OSError as exc:
                errors.append(exc)
        self.chain = []
        if errors:
            raise CleanupUnconfirmed(None, [('cgroup_fd_close', e) for e in errors], {})

    def named_absent(self):
        """Only original leaf disappearance, with all original ancestors held."""
        self.grant.remaining(cleanup=True)
        need(bool(self.chain), 'RETAINED_CGROUP_REQUIRED')
        for fd, parent, name, expected in self.chain[:-1]:
            need(self.dir_identity(os.fstat(fd)) == expected, 'CGROUP_ANCESTOR_FD_DRIFT')
            if parent is not None:
                need(self.dir_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                     'CGROUP_ANCESTOR_NAMESPACE_DRIFT')
        _, parent, name, _ = self.chain[-1]
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False


def send_packet(sock, message, fds=()):
    raw = canonical_json(message)
    need(len(raw) <= MAX_WIRE and len(fds) <= MAX_FDS, 'FINITE_PACKET_AND_RIGHTS')
    control = [] if not fds else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', fds))]
    need(sock.sendmsg([raw], control) == len(raw), 'EXACT_ONE_SEQPACKET_SEND')


def recv_packet(sock, expect_rights=False):
    rights = []
    try:
        raw, ancillary, flags, _ = sock.recvmsg(MAX_WIRE, socket.CMSG_SPACE(MAX_FDS * array.array('i').itemsize),
                                               socket.MSG_CMSG_CLOEXEC)
        for level, kind, data in ancillary:
            need(level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, 'ONLY_SCM_RIGHTS')
            values = array.array('i')
            need(len(data) % values.itemsize == 0, 'EXACT_RIGHTS_WIDTH')
            values.frombytes(data)
            rights.extend(values)
        need(not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) and 0 < len(raw) <= MAX_WIRE,
             'TRUNCATED_OR_EMPTY_PACKET')
        need(len(rights) <= MAX_FDS and (bool(rights) is expect_rights), 'EXACT_EXPECTED_RIGHTS')
        return exact_json(raw), tuple(rights)
    except BaseException:
        for fd in rights:
            os.close(fd)
        raise


def peer_credential(sock):
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    pid, uid, gid = struct.unpack('3i', raw)
    need(pid > 1 and uid == os.getuid() and gid == os.getgid(), 'EXACT_SAME_OWNER_KERNEL_PEERCRED')
    return (pid, uid, gid)


CONTROLLER_BOOTSTRAP = r'''import os,sys,hashlib
outside=int(sys.argv[1]); birth=int(sys.argv[2]); sourcefd=int(sys.argv[3])
left,tail=open('/proc/%d/stat'%outside,'rb').read(65537).rsplit(b')',1)
assert int(tail.split()[19])==birth
fd=os.open('/proc/%d/fd/%d'%(outside,sourcefd),os.O_RDONLY)
raw=os.pread(fd,1048577,0)
assert len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==sys.argv[4]
namespace={'__name__':'__finite_held_controller__'}
exec(compile(raw,'<held-finite-outside-controller>','exec',dont_inherit=True),namespace)
os.close(fd)
namespace['controller_main'](sys.argv[5],sys.argv[6],outside,birth)
'''


def command_vector(interpreter_fd, source_fd, source_sha, outside_birth, socket_path, grant,
                   aggregate_slice):
    """Build the actual supported argv. No generic systemd FD forwarding."""
    grant.validate()
    need(type(interpreter_fd) is int and interpreter_fd >= 0 and type(source_fd) is int and source_fd >= 0,
         'RETAINED_FDS_REQUIRED')
    need(re.fullmatch(r'[0-9a-f]{64}', source_sha) is not None, 'EXACT_CONTROLLER_SOURCE_HASH')
    need(type(outside_birth) is tuple and outside_birth[0] == os.getpid(), 'EXACT_OUTSIDE_BIRTH')
    need(type(socket_path) is str and len(socket_path.encode()) <= 107 and socket_path.startswith('/'),
         'BOUNDED_ABSOLUTE_UNIX_SOCKET')
    need(type(aggregate_slice) is str and
         re.fullmatch(r'friday-rework-[0-9a-f]{32}\.slice', aggregate_slice) is not None,
         'EXISTING_OWNED_FINITE_AGGREGATE_SLICE_REQUIRED')
    runtime = math.floor(grant.remaining())
    need(runtime > 0, 'NO_RENEWED_RUNTIME')
    properties = ('Description=Friday rework ' + grant.admission_hash,
                  'KillMode=control-group', 'SendSIGKILL=yes', 'Restart=no', 'Delegate=no',
                  'Slice=' + aggregate_slice,
                  'CPUQuota=200%', 'AllowedCPUs=' + ','.join(map(str, grant.cpus)),
                  'MemoryMax=' + str(MEMORY), 'MemorySwapMax=0', 'LimitAS=' + str(MEMORY),
                  'TasksMax=128', 'NoNewPrivileges=yes', 'RuntimeMaxSec=' + str(runtime) + 's',
                  'TimeoutStartSec=' + str(min(runtime, 10)) + 's', 'TimeoutStopSec=10s')
    return ['/usr/bin/systemd-run', '--user', '--unit=' + grant.unit, '--service-type=exec',
            '--quiet', *['--property=' + p for p in properties], '--',
            '/proc/' + str(os.getpid()) + '/fd/' + str(interpreter_fd),
            '-I', '-S', '-B', '-c', CONTROLLER_BOOTSTRAP,
            str(os.getpid()), str(outside_birth[2]), str(source_fd), source_sha, socket_path, grant.token]


def independent_attempts(actions, primary=None):
    """Every stop/wait/witness action runs even after earlier actions fail."""
    errors, observations = [], {}
    for stage, action in actions:
        try:
            observations[stage] = action()
        except BaseException as exc:
            errors.append((stage, exc))
    return errors, observations


class FiniteOutsideOwner:
    """One finite service envelope, retained external lifetime and exact cleanup."""
    def __init__(self, supervisor, association, grant, directory_fd, socket_name,
                 interpreter, controller_source, worker_bootstrap, aggregate_cgroup, extra_buffers=()):
        grant.validate()
        need(association['supervisor'] == {'scope': 'user', 'unit': grant.unit}
             and association['admission_hash'] == grant.admission_hash and association.get('native') is None,
             'EXACT_ORIGINAL_UNLAUNCHED_ASSOCIATION')
        need(type(socket_name) is str and re.fullmatch(r'[a-z0-9-]{1,48}\.sock', socket_name), 'EXACT_OWN_SOCKET_NAME')
        need(len(extra_buffers) <= MAX_FDS - 3, 'FINITE_HELD_CLOSURE')
        self.supervisor = supervisor
        need(type(aggregate_cgroup) is CgroupCustody
             and aggregate_cgroup.grant is grant, 'ACTUAL_HELD_COMMON_AGGREGATE_CGROUP_REQUIRED')
        self.aggregate = aggregate_cgroup  # borrowed custody; never change/close caller's cap
        self.association = dict(association)
        self.grant = grant
        self.dirfd = os.dup(directory_fd)
        self.directory_identity = signature(os.fstat(self.dirfd))
        need(stat.S_ISDIR(self.directory_identity[4]) and self.directory_identity[2] == os.getuid()
             and stat.S_IMODE(self.directory_identity[4]) == 0o700, 'PRIVATE_HELD_SOCKET_DIRECTORY')
        self.socket_name = socket_name
        self.buffers = (interpreter, controller_source, worker_bootstrap, *extra_buffers)
        self.birth = process_birth(os.getpid())
        self.tool = None
        self.tool_birth = None
        self.tool_pidfd = None
        self.listener = None
        self.connection = None
        self.socket_identity = None
        self.endpoint_inodes = set()
        self.invocation = None
        self.group = None
        self.cgroup = None
        self.controller_birth = None
        self.controller_pidfd = None
        self.worker_birth = None
        self.worker_pidfd = None
        self.released = False
        self.launch_attempted = False
        self.unit_start_requested = False
        self.closed = False
        self.bundle = None

    def check_outside(self, group):
        need(process_birth(os.getpid()) == self.birth, 'OUTSIDE_OWNER_BIRTH_DRIFT')
        need(not is_within(process_group(os.getpid()), group), 'OWNER_INSIDE_TARGET_CGROUP_OR_DESCENDANT')

    def check_aggregate(self, target_group=None):
        caps = self.aggregate.caps()
        owner_group = process_group(os.getpid())
        need(is_within(owner_group, self.aggregate.group)
             and (target_group is None or is_within(target_group, self.aggregate.group)),
             'OWNER_TOOL_AND_TARGET_REQUIRE_ONE_OBSERVED_BOUNDED_ANCESTOR')
        need(set(os.sched_getaffinity(0)) <= set(caps['cpus']), 'OUTSIDE_OWNER_AFFINITY_OVER_BUDGET')
        return caps

    def observe_owned(self):
        self.grant.remaining(cleanup=True, reserve=3.1)
        row = self.supervisor.observe(self.association)
        need(row.unit == self.grant.unit, 'EXACT_NATIVE_UNIT')
        if not row.missing:
            need(self.invocation is None or row.invocation_id == self.invocation, 'RECYCLED_UNIT_INVOCATION_REJECTED')
            need(self.group is None or not row.control_group or row.control_group == self.group, 'NATIVE_CGROUP_DRIFT')
            if row.control_group:
                self.check_outside(row.control_group)
        return row

    def verify_buffers(self):
        rows = []
        for held in self.buffers:
            held.verify()
            st = os.fstat(held.fd)
            raw = held.raw
            need(stat.S_ISREG(st.st_mode) and not st.st_mode & (0o022 | stat.S_ISUID | stat.S_ISGID)
                 and raw == read_fd(held.fd, len(raw) + 1) and hashlib.sha256(raw).hexdigest() == held.sha256,
                 'REAL_HELD_SOURCE_CUSTODY')
            rows.append({'signature': list(signature(st)), 'sha256': held.sha256, 'length': len(raw)})
        need(self.buffers[0].raw.startswith(b'\x7fELF'), 'RETAINED_ELF_REQUIRED')
        need(0 < len(self.buffers[1].raw) <= 1048576 and 0 < len(self.buffers[2].raw) <= 65536,
             'FINITE_CONTROLLER_AND_LITERAL_WORKER_BOOTSTRAP')
        return rows

    def _socket_path(self):
        path = os.readlink('/proc/self/fd/' + str(self.dirfd))
        need(path.startswith('/') and not path.endswith(' (deleted)') and
             signature(os.stat(path, follow_symlinks=False)) == self.directory_identity,
             'HELD_SOCKET_DIRECTORY_NAMESPACE_DRIFT')
        return path + '/' + self.socket_name

    def launch_held(self):
        require_native_admission()
        need(not self.launch_attempted, 'ONE_LAUNCH_NO_RETRY')
        self.launch_attempted = True
        primary = None
        try:
            rows = self.verify_buffers()
            self.check_aggregate()
            self.grant.remaining(reserve=35)
            before = self.observe_owned()
            need(before.missing and before.quiescent, 'UNIQUE_UNIT_NOT_PREEXISTING')
            path = self._socket_path()
            try:
                os.stat(self.socket_name, dir_fd=self.dirfd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Unbound('SOCKET_PREEXISTS_NO_UNLINK')
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            self.listener.bind(path)
            self.socket_identity = signature(os.stat(self.socket_name, dir_fd=self.dirfd, follow_symlinks=False))
            self.endpoint_inodes.add(os.fstat(self.listener.fileno()).st_ino)
            self.listener.listen(1)
            self.listener.settimeout(min(10, self.grant.remaining()))
            argv = command_vector(self.buffers[0].fd, self.buffers[1].fd, self.buffers[1].sha256,
                                  self.birth, path, self.grant, self.aggregate.group.rsplit('/', 1)[-1])
            runtime = '/run/user/' + str(os.getuid())
            self.unit_start_requested = True
            self.tool = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, close_fds=True,
                                         env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
                                              'XDG_RUNTIME_DIR': runtime,
                                              'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + runtime + '/bus'})
            self.tool_pidfd = os.pidfd_open(self.tool.pid, 0)
            self.tool_birth = process_birth(self.tool.pid)
            need(self.tool_birth is not None and self.tool_birth[1] == os.getpid(), 'DIRECT_SYSTEMD_TOOL_BIRTH')
            self.tool.wait(timeout=min(10, self.grant.remaining()))
            need(self.tool.returncode == 0, 'SYSTEMD_RUN_FAILED_NO_RETRY')
            row = self.observe_owned()
            need(not row.missing and row.main_pid > 1 and row.populated is True
                 and re.fullmatch(r'[0-9a-f]{32}', row.invocation_id) is not None,
                 'ACTUAL_NATIVE_MAINPID_INVOCATION_CGROUP_REQUIRED')
            self.invocation, self.group = row.invocation_id, row.control_group
            self.association['native'] = {'invocation_id': self.invocation,
                                          'worker_reference': 'held-controller:' + str(row.main_pid)}
            self.check_outside(self.group)
            self.check_aggregate(self.group)
            self.cgroup = CgroupCustody(self.group, self.grant.unit, self.grant)
            self.cgroup.caps()
            self.controller_birth = process_birth(row.main_pid)
            need(self.controller_birth is not None and process_group(row.main_pid) == self.group,
                 'ACTUAL_CONTROLLER_BIRTH_AND_CGROUP')
            self.controller_pidfd = os.pidfd_open(row.main_pid, 0)
            self.connection, _ = self.listener.accept()
            self.connection.settimeout(min(10, self.grant.remaining()))
            self.endpoint_inodes.add(os.fstat(self.connection.fileno()).st_ino)
            need(peer_credential(self.connection)[0] == row.main_pid
                 and process_birth(row.main_pid) == self.controller_birth,
                 'KERNEL_PEER_IS_ACTUAL_NATIVE_MAINPID_AND_BIRTH')
            expected_exe = os.fstat(self.buffers[0].fd)
            actual_exe = os.stat('/proc/' + str(row.main_pid) + '/exe')
            need((actual_exe.st_dev, actual_exe.st_ino) == (expected_exe.st_dev, expected_exe.st_ino),
                 'ACTUAL_CONTROLLER_RETAINED_ELF_IDENTITY')
            hello, _ = recv_packet(self.connection)
            need(hello == {'phase': 'HELLO', 'token': self.grant.token}, 'EXACT_AUTHENTICATED_HELLO')
            self.verify_buffers()
            self.cgroup.caps()
            self.check_aggregate(self.group)
            self.grant.remaining()
            self.bundle = {'phase': 'CUSTODY', 'grant': self.grant.wire(), 'invocation': self.invocation,
                           'group': self.group, 'controller_birth': list(self.controller_birth),
                           'buffers': rows}
            send_packet(self.connection, self.bundle, tuple(h.fd for h in self.buffers))
            ready, _ = recv_packet(self.connection)
            expected_fields = {'phase', 'token', 'bundle_sha256', 'worker_birth', 'limit_as'}
            need(set(ready) == expected_fields and ready['phase'] == 'READY'
                 and ready['token'] == self.grant.token
                 and ready['bundle_sha256'] == hashlib.sha256(canonical_json(self.bundle)).hexdigest(),
                 'EXACT_HELD_READY_SOURCE_AND_ORIGINAL_RESERVATION')
            reported = ready['worker_birth']
            need(type(reported) is list and len(reported) == 3
                 and all(type(v) is int and v > 0 for v in reported), 'EXACT_WORKER_BIRTH_FIELDS')
            birth = process_birth(reported[0])
            need(birth == tuple(reported) and birth[1] == self.controller_birth[0]
                 and process_group(birth[0]) == self.group, 'ACTUAL_DIRECT_HELD_WORKER_PARENT_AND_BIRTH')
            self.worker_birth = birth
            self.worker_pidfd = os.pidfd_open(birth[0], 0)
            need(not select.select([self.worker_pidfd], [], [], 0)[0], 'READY_WORKER_ALREADY_EXITED')
            limits = bounded_path('/proc/' + str(birth[0]) + '/limits', 65536).decode('ascii')
            match = re.search(r'^Max address space\s+([0-9]+)\s+([0-9]+)\s+bytes$', limits, re.M)
            need(match is not None and 0 < int(match[1]) <= int(match[2]) <= MEMORY
                 and ready['limit_as'] == int(match[2]), 'SEPARATE_ACTUAL_PER_PROCESS_LIMIT_AS')
            self.cgroup.caps()
            need(set(os.sched_getaffinity(birth[0])) <= set(self.grant.cpus), 'ACTUAL_WORKER_AFFINITY')
            return ready
        except BaseException as exc:
            primary = exc
            self.cleanup(primary=exc)
            raise

    def release_once(self, ready):
        require_native_admission()
        try:
            return self._release_checked(ready)
        except BaseException as exc:
            self.cleanup(primary=exc)
            raise

    def _release_checked(self, ready):
        require_native_admission()
        need(not self.released and self.connection is not None and self.worker_birth is not None,
             'ONE_RELEASE_ONLY_AFTER_HELD_READY')
        need(ready['worker_birth'] == list(self.worker_birth) and ready['token'] == self.grant.token
             and ready['bundle_sha256'] == hashlib.sha256(canonical_json(self.bundle)).hexdigest(),
             'EXACT_ORIGINAL_RELEASE_IDENTITY')
        need(process_birth(self.worker_birth[0]) == self.worker_birth
             and process_birth(self.controller_birth[0]) == self.controller_birth, 'PRE_GO_BIRTH_DRIFT')
        row = self.observe_owned()
        need(row.main_pid == self.controller_birth[0] and row.control_group == self.group, 'PRE_GO_NATIVE_DRIFT')
        self.cgroup.caps()
        self.check_aggregate(self.group)
        self.verify_buffers()
        inventory = self.inventory_current_tree()
        need(inventory.get(self.controller_birth[0]) == self.controller_birth
             and inventory.get(self.worker_birth[0]) == self.worker_birth, 'EXACT_TREE_BEFORE_GO')
        self.grant.remaining()
        self.released = True  # never retry after an uncertain send
        send_packet(self.connection, {'phase': 'RELEASE', 'token': self.grant.token,
                                     'bundle_sha256': ready['bundle_sha256'],
                                     'worker_birth': list(self.worker_birth), 'grant': self.grant.wire()})

    def wait_exit_and_close(self):
        require_native_admission()
        primary = None
        result = None
        try:
            need(self.released, 'EXIT_ONLY_AFTER_ONE_RELEASE')
            self.connection.settimeout(self.grant.remaining())
            packet, _ = recv_packet(self.connection)
            need(set(packet) == {'phase', 'token', 'worker_birth', 'returncode'}
                 and packet['phase'] == 'EXIT' and packet['token'] == self.grant.token
                 and packet['worker_birth'] == list(self.worker_birth)
                 and type(packet['returncode']) is int, 'EXACT_AUTHENTICATED_CONTROLLER_WAIT_RESULT')
            result = packet
        except BaseException as exc:
            primary = exc
        # Stop/witness even after EXIT: grandchildren and descriptors can outlive
        # the waited direct worker. Controller's receipt is never global closure.
        observed = self.cleanup(primary=primary)
        if primary is not None:
            raise primary
        return {'worker_wait_receipt': result, 'outside_closure': observed}

    def _stop_unit(self):
        require_native_admission()
        if not self.unit_start_requested:
            return None
        self.grant.remaining(cleanup=True, reserve=21.1)
        # The unit name was fresh before the single launch. For partial launch,
        # capture its actual invocation before stop; never adopt a second one.
        row = self.observe_owned()
        if row.missing:
            return row
        if self.invocation is None:
            self.invocation, self.group = row.invocation_id, row.control_group
            self.association['native'] = {'invocation_id': self.invocation,
                                          'worker_reference': 'partial-held-controller:' + str(row.main_pid)}
        self.check_outside(self.group)
        return self.supervisor.stop(self.association)

    def _kill_tool(self):
        if self.tool is None or self.tool.poll() is not None:
            return None
        self.grant.remaining(cleanup=True)
        need(self.tool_pidfd is not None, 'DIRECT_TOOL_RETAINED_PIDFD_NO_NUMERIC_KILL')
        # Popen's still-unreaped direct-child relation prevents PID reuse even
        # if initial birth sampling itself failed. Never acquire another PID.
        if self.tool_birth is not None:
            need(process_birth(self.tool.pid) == self.tool_birth, 'DIRECT_TOOL_BIRTH_DRIFT')
        signal.pidfd_send_signal(self.tool_pidfd, signal.SIGKILL, None, 0)

    def _wait_tool(self):
        if self.tool is None:
            return None
        self.grant.remaining(cleanup=True)
        return self.tool.wait(timeout=min(3, self.grant.remaining(cleanup=True)))

    def _close_sockets(self):
        errors, observed = independent_attempts([(name, sock.close) for name, sock in
                                                [('connection_close', self.connection), ('listener_close', self.listener)]
                                                if sock is not None])
        if errors:
            raise CleanupUnconfirmed(None, errors, observed)

    def _unlink_owned_socket(self):
        if self.socket_identity is None:
            return None
        try:
            current = signature(os.stat(self.socket_name, dir_fd=self.dirfd, follow_symlinks=False))
        except FileNotFoundError:
            return None
        need(current == self.socket_identity, 'REPLACED_SOCKET_NO_FOREIGN_UNLINK')
        os.unlink(self.socket_name, dir_fd=self.dirfd)

    def _path_absent(self):
        try:
            os.stat(self.socket_name, dir_fd=self.dirfd, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False

    def _endpoints_absent(self):
        raw = bounded_path('/proc/net/unix', 4 * 1024 ** 2)
        active = {int(row.split()[6]) for row in raw.decode('ascii').splitlines()[1:] if len(row.split()) >= 7}
        return not (self.endpoint_inodes & active)

    def inventory_current_tree(self):
        """Finite real cgroup subtree births/FDs, no process-name discovery."""
        need(self.cgroup is not None, 'HELD_UNIT_CGROUP_BEFORE_INVENTORY')
        self.cgroup.verify()
        output = {}
        count = [0]
        def visit(fd, group):
            count[0] += 1
            need(count[0] <= MAX_FILES, 'FINITE_CGROUP_SUBTREE')
            pfd = os.open('cgroup.procs', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            try:
                raw = os.read(pfd, 65537)
            finally:
                os.close(pfd)
            need(len(raw) <= 65536, 'FINITE_CGROUP_PID_LIST')
            for item in raw.decode('ascii').split():
                need(re.fullmatch(r'[1-9][0-9]*', item) is not None, 'EXACT_CGROUP_PID')
                pid = int(item)
                need(pid not in output and len(output) < MAX_PIDS, 'FINITE_UNIQUE_CGROUP_PIDS')
                birth = process_birth(pid)
                need(birth is not None and process_group(pid) == group
                     and set(os.sched_getaffinity(pid)) <= set(self.grant.cpus), 'ACTUAL_TREE_KERNEL_IDENTITY')
                names = os.listdir('/proc/' + str(pid) + '/fd')
                need(len(names) <= 512, 'FINITE_OWN_PROCESS_DESCRIPTOR_INVENTORY')
                for name in names:
                    link = os.readlink('/proc/' + str(pid) + '/fd/' + name)
                    match = re.fullmatch(r'socket:\[([0-9]+)\]', link)
                    if match:
                        self.endpoint_inodes.add(int(match[1]))
                need(process_birth(pid) == birth, 'TREE_BIRTH_DRIFT_DURING_INVENTORY')
                output[pid] = birth
            names = os.listdir(fd)
            need(len(names) <= 512, 'FINITE_CGROUP_DIRECTORY_ENTRIES')
            for name in sorted(names):
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(st.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        visit(child, group + '/' + name)
                    finally:
                        os.close(child)
        visit(self.cgroup.chain[-1][0], self.group)
        self.cgroup.verify()
        return output

    def _births_absent(self):
        out = {}
        for name, original in [('tool', self.tool_birth), ('controller', self.controller_birth), ('worker', self.worker_birth)]:
            if original is not None:
                # Different birth at the same numeric PID proves original birth
                # absent, and grants no authority over the replacement process.
                now = process_birth(original[0])
                out[name] = now is None or now != original
        return out

    def _fresh_cgroup_empty(self):
        if self.cgroup is None:
            row = self.observe_owned()
            if not row.control_group:
                return row.quiescent
            # Partial launch still gets actual held cgroup evidence; absence of
            # a fully constructed READY handle cannot omit all-descendant proof.
            held = CgroupCustody(row.control_group, self.grant.unit, self.grant)
            try:
                return held.empty()
            finally:
                held.close()
        try:
            return self.cgroup.empty()
        except FileNotFoundError:
            # systemd can remove an empty transient cgroup. No replaced leaf or
            # changed ancestor is credited; independently read the exact unit.
            return self.cgroup.named_absent() and self.observe_owned().quiescent

    def cleanup(self, primary=None):
        started = time.monotonic()
        actions = [('pre_stop_own_endpoint_inventory', lambda: self.inventory_current_tree()
                    if self.cgroup is not None and not self.cgroup.named_absent() else {}),
                   ('outside_unit_stop', self._stop_unit), ('direct_tool_signal', self._kill_tool),
                   ('direct_tool_wait', self._wait_tool), ('own_sockets_close', self._close_sockets),
                   ('own_socket_unlink', self._unlink_owned_socket)]
        errors, observed = independent_attempts(actions, primary)
        # Fresh observations have a separate pass and no stop/signal dependency.
        witnesses = [('fresh_native_unit', self.observe_owned),
                     ('fresh_cgroup_empty', self._fresh_cgroup_empty),
                     ('fresh_birth_absence', self._births_absent), ('fresh_path_absence', self._path_absent),
                     ('fresh_endpoint_absence', self._endpoints_absent)]
        witness_errors, fresh = independent_attempts(witnesses, primary)
        errors.extend(witness_errors)
        observed.update(fresh)
        elapsed = time.monotonic() - started
        observed['cleanup_elapsed_seconds'] = elapsed
        observed['helper_reaped'] = self.tool is None or self.tool.returncode is not None
        observed['worker_reaped_by_outside'] = False  # outside is not its wait parent
        observed['closed'] = (not errors and elapsed <= 60 and observed['helper_reaped']
                              and fresh['fresh_native_unit'].quiescent is True
                              and fresh['fresh_cgroup_empty'] is True
                              and all(fresh['fresh_birth_absence'].values())
                              and fresh['fresh_path_absence'] is True and fresh['fresh_endpoint_absence'] is True)
        if not observed['closed'] and not errors:
            errors.append(('fresh_closure', Unbound('CLOSURE_NOT_OBSERVED')))
        fd_actions = [('controller_pidfd_close', lambda: os.close(self.controller_pidfd))] if self.controller_pidfd is not None else []
        if self.worker_pidfd is not None:
            fd_actions.append(('worker_pidfd_close', lambda: os.close(self.worker_pidfd)))
        if self.tool_pidfd is not None:
            fd_actions.append(('direct_tool_pidfd_close', lambda: os.close(self.tool_pidfd)))
        if self.cgroup is not None:
            fd_actions.append(('cgroup_fds_close', self.cgroup.close))
        fd_actions.append(('owned_socket_directory_fd_close', lambda: os.close(self.dirfd)))
        fd_errors, _ = independent_attempts(fd_actions)
        errors.extend(fd_errors)
        self.controller_pidfd = self.worker_pidfd = self.tool_pidfd = None
        self.closed = observed['closed'] and not errors
        if errors:
            raise CleanupUnconfirmed(primary, errors, observed) from primary
        return observed


def controller_main(socket_path, token, outside_pid, outside_start):
    """Runs INSIDE MainPID; worker is its direct child, outside stays alive.

    Invoked only by the exact -c stub. Current guard means neither this source
    nor an arbitrary caller can grant runtime qualification or native admission.
    """
    require_native_admission()
    need(process_birth(outside_pid)[2] == outside_start, 'OUTSIDE_OWNER_BIRTH_REQUIRED')
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
    fds = ()
    child = None
    pidfd = None
    worker_socket = None
    parent_socket = None
    primary = None
    try:
        connection.settimeout(10)
        connection.connect(socket_path)
        need(peer_credential(connection)[0] == outside_pid, 'AUTHENTICATED_OUTSIDE_PEER')
        send_packet(connection, {'phase': 'HELLO', 'token': token})
        packet, fds = recv_packet(connection, expect_rights=True)
        need(set(packet) == {'phase', 'grant', 'invocation', 'group', 'controller_birth', 'buffers'}
             and packet['phase'] == 'CUSTODY' and packet['grant']['token'] == token,
             'EXACT_CUSTODY_PACKET')
        wire = packet['grant']
        grant = Grant(**{**wire, 'reservation': tuple(wire['reservation']), 'cpus': tuple(wire['cpus'])}).validate()
        need(process_birth(os.getpid()) == tuple(packet['controller_birth'])
             and process_group(os.getpid()) == packet['group'], 'ACTUAL_IN_UNIT_CONTROLLER')
        need(len(fds) == len(packet['buffers']) and len(fds) >= 3, 'EXACT_HELD_DESCRIPTOR_ORDER')
        for fd, row in zip(fds, packet['buffers']):
            need(set(row) == {'signature', 'sha256', 'length'}
                 and signature(os.fstat(fd)) == tuple(row['signature']), 'SCM_HELD_FD_SIGNATURE')
            raw = read_fd(fd, row['length'] + 1)
            need(len(raw) == row['length'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'SCM_HELD_BYTES')
        bootstrap = read_fd(fds[2], 65536).decode('utf8')
        need(0 < len(bootstrap.encode()) <= 65536, 'EXACT_LITERAL_WORKER_BOOTSTRAP')
        parent_socket, worker_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        parent_socket.settimeout(min(10, grant.remaining()))
        child = subprocess.Popen(['/proc/self/fd/' + str(fds[0]), '-I', '-S', '-B', '-c', bootstrap,
                                  str(worker_socket.fileno()), token, str(grant.useful_monotonic),
                                  str(os.getpid()), str(process_birth(os.getpid())[2])],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 env={'LC_ALL': 'C', 'LANG': 'C'}, close_fds=True,
                                 pass_fds=tuple(sorted({*fds, worker_socket.fileno()})))
        worker_socket.close()
        worker_socket = None
        birth = process_birth(child.pid)
        need(birth is not None and birth[1] == os.getpid() and child.poll() is None,
             'DIRECT_HELD_WORKER_KERNEL_BIRTH_BEFORE_READY')
        pidfd = os.pidfd_open(child.pid, 0)
        digest = hashlib.sha256(canonical_json(packet)).hexdigest()
        send_packet(parent_socket, {'phase': 'WORKER_CUSTODY', 'bundle': packet,
                                    'bundle_sha256': digest, 'fds': list(fds)})
        ready, _ = recv_packet(parent_socket)
        need(set(ready) == {'phase', 'token', 'worker_birth', 'limit_as'}
             and ready['phase'] == 'READY' and ready['token'] == token
             and ready['worker_birth'] == list(birth) and process_birth(child.pid) == birth,
             'EXACT_DIRECT_WORKER_READY')
        send_packet(connection, {**ready, 'bundle_sha256': digest})
        release, _ = recv_packet(connection)
        need(release == {'phase': 'RELEASE', 'token': token, 'bundle_sha256': digest,
                         'worker_birth': list(birth), 'grant': wire}, 'ONE_EXACT_ORIGINAL_RELEASE')
        grant.remaining()
        need(process_birth(child.pid) == birth and not select.select([pidfd], [], [], 0)[0],
             'EXACT_PRE_RELEASE_KERNEL_BIRTH')
        send_packet(parent_socket, release)
        code = child.wait(timeout=grant.remaining())
        send_packet(connection, {'phase': 'EXIT', 'token': token, 'worker_birth': list(birth), 'returncode': code})
    except BaseException as exc:
        primary = exc
        raise
    finally:
        actions = []
        if child is not None:
            def child_stop():
                if child.poll() is None:
                    need(pidfd is not None, 'NO_NUMERIC_PID_FALLBACK')
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL, None, 0)
            actions.extend([('direct_worker_stop', child_stop),
                            ('direct_worker_wait', lambda: child.wait(timeout=min(3, grant.remaining(cleanup=True))))])
        if pidfd is not None:
            actions.append(('worker_pidfd_close', lambda: os.close(pidfd)))
        for name, sock in [('worker_socket_close', worker_socket), ('parent_socket_close', parent_socket),
                           ('connection_close', connection)]:
            if sock is not None:
                actions.append((name, sock.close))
        for index, fd in enumerate(fds):
            actions.append(('received_fd_close_' + str(index), lambda fd=fd: os.close(fd)))
        errors, observed = independent_attempts(actions, primary)
        if errors:
            raise CleanupUnconfirmed(primary, errors, observed) from primary


class WorkerHeldChannel:
    """Exact worker-side READY/GO seam, after independently held startup custody.

    The bootstrap receives FD/token/original monotonic bound/controller birth as
    the five literal argv fields above. It must validate its complete held graph
    before constructing this channel; this source gate never grants that proof.
    """
    def __init__(self, fd, token, useful_monotonic, controller_pid, controller_start,
                 bundle_sha256, original_grant):
        require_native_admission()
        need(type(fd) is int and fd >= 0 and re.fullmatch(r'[0-9a-f]{64}', token) is not None,
             'EXACT_WORKER_CHANNEL_FD_TOKEN')
        self.socket = socket.socket(fileno=os.dup(fd))
        self.grant = original_grant.validate()
        need(original_grant.token == token and original_grant.useful_monotonic == useful_monotonic
             and re.fullmatch(r'[0-9a-f]{64}', bundle_sha256) is not None, 'EXACT_ORIGINAL_WORKER_GRANT')
        self.digest = bundle_sha256
        self.birth = process_birth(os.getpid())
        parent = process_birth(controller_pid)
        need(parent is not None and parent[2] == controller_start
             and self.birth[1] == controller_pid and peer_credential(self.socket)[0] == controller_pid,
             'WORKER_CHANNEL_KERNEL_DIRECT_CONTROLLER_PARENT')
        self.released = False

    @classmethod
    def from_bootstrap_arguments(cls, fd, token, useful_monotonic, controller_pid, controller_start):
        require_native_admission()
        probe = socket.socket(fileno=os.dup(fd))
        try:
            need(peer_credential(probe)[0] == controller_pid
                 and process_birth(os.getpid())[1] == controller_pid
                 and process_birth(controller_pid)[2] == controller_start, 'ACTUAL_DIRECT_PARENT_CHANNEL')
            remaining = useful_monotonic - time.monotonic()
            need(0 < remaining <= 600, 'ORIGINAL_WORKER_CHANNEL_BOUND')
            probe.settimeout(min(10, remaining))
            packet, _ = recv_packet(probe)
            need(set(packet) == {'phase', 'bundle', 'bundle_sha256', 'fds'}
                 and packet['phase'] == 'WORKER_CUSTODY'
                 and packet['bundle_sha256'] == hashlib.sha256(canonical_json(packet['bundle'])).hexdigest(),
                 'EXACT_WORKER_BUNDLE')
            bundle = packet['bundle']
            wire = bundle['grant']
            grant = Grant(**{**wire, 'reservation': tuple(wire['reservation']), 'cpus': tuple(wire['cpus'])}).validate()
            need(grant.token == token and grant.useful_monotonic == useful_monotonic,
                 'ORIGINAL_WORKER_TOKEN_DEADLINE')
            inherited = packet['fds']
            need(type(inherited) is list and 3 <= len(inherited) <= MAX_FDS
                 and len(inherited) == len(bundle['buffers'])
                 and len(set(inherited)) == len(inherited)
                 and all(type(n) is int and n >= 0 for n in inherited), 'EXACT_INHERITED_FD_MAP')
            for fd_number, row in zip(inherited, bundle['buffers']):
                need(signature(os.fstat(fd_number)) == tuple(row['signature'])
                     and hashlib.sha256(read_fd(fd_number, row['length'] + 1)).hexdigest() == row['sha256'],
                     'WORKER_HELD_FD_SOURCE_IDENTITY')
            need(process_group(os.getpid()) == bundle['group'], 'ACTUAL_WORKER_OWNED_CGROUP')
            return cls(fd, token, useful_monotonic, controller_pid, controller_start,
                       packet['bundle_sha256'], grant)
        finally:
            probe.close()

    def ready_and_wait_release(self):
        require_native_admission()
        need(not self.released, 'ONE_WORKER_RELEASE')
        self.grant.remaining()
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        need(0 < soft <= hard <= MEMORY, 'ACTUAL_WORKER_PER_PROCESS_AS_LIMIT')
        send_packet(self.socket, {'phase': 'READY', 'token': self.grant.token,
                                 'worker_birth': list(self.birth), 'limit_as': hard})
        self.socket.settimeout(self.grant.remaining())
        release, _ = recv_packet(self.socket)
        expected = {'phase': 'RELEASE', 'token': self.grant.token, 'bundle_sha256': self.digest,
                    'worker_birth': list(self.birth), 'grant': self.grant.wire()}
        need(release == expected and process_birth(os.getpid()) == self.birth,
             'EXACT_WORKER_SINGLE_RELEASE_ORIGINAL_RESERVATION_CLOCK_SOURCE')
        self.grant.remaining()
        self.released = True
        return release

    def close(self):
        self.socket.close()


if __name__ == '__main__':
    require_native_admission()
