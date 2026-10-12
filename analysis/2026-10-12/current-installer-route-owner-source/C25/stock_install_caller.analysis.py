"""INERT one-shot caller for Root's exact admitted stock finite host.

Adapts C25 fixture_caller-v4; never authenticates Root from JSON, hashes or an
owner object. Root controls the exact invocation externally BEFORE bootstrap.
The supplied capability confines that already admitted request, one use only.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import types

AS = 268435456
MAX = 67108864
LIMIT = 65536
SELF = str(Path(__file__).resolve())
PYTHON = '/analysis/NOT_CONNECTED/python'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def identity(pid):
    v = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'birth': v[19], 'ppid': int(v[1]), 'pgid': int(v[2]), 'sid': int(v[3])}


def read_pin(ref, maximum=1048576):
    require(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}, 'pin shape')
    p = Path(ref['path'])
    require(p.is_absolute() and '..' not in p.parts and str(p) == os.path.normpath(str(p)), 'pin path')
    require(type(ref['bytes']) is int and 0 <= ref['bytes'] <= maximum, 'pin size')
    for parent in reversed(p.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode), 'pin ancestor')
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and a.st_uid == os.getuid()
                and not a.st_mode & 0o077 and a.st_size <= maximum, 'private regular pin')
        chunks, size = [], 0
        while True:
            b = os.read(fd, min(8192, maximum + 1 - size))
            if not b:
                break
            chunks.append(b)
            size += len(b)
            require(size <= maximum, 'pin read bound')
        raw = b''.join(chunks)
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_mtime_ns, s.st_ctime_ns)
        require(key(a) == key(os.fstat(fd)) == key(p.lstat()), 'pin drift')
        require(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'pin mismatch')
        return raw
    finally:
        os.close(fd)


def put(path, value):
    raw = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    require(len(raw) <= LIMIT, 'evidence bound')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def caller_limits():
    for kind, cap in ((resource.RLIMIT_AS, AS), (resource.RLIMIT_CPU, 60), (resource.RLIMIT_FSIZE, MAX)):
        require(resource.getrlimit(kind) == (cap, cap), 'hard caller resources before Source')
    require(resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
            and 0 < len(os.sched_getaffinity(0)) <= 2, 'caller core/affinity')
    return {'pid': os.getpid(), 'birth': identity(os.getpid())['birth'],
            'AS': [AS, AS], 'CPU': [60, 60], 'FSIZE': [MAX, MAX], 'CORE': [0, 0],
            'affinity': sorted(os.sched_getaffinity(0))}


class _Lease:
    pass


class _RootOneShotOwner:
    """Confines Root's externally chosen exact request; supplies no new issuer.

    Only the approved main below creates/uses this capability. The actual stock
    parent retains caller closure. The SAME custody is held before any fork.
    """
    def __init__(self, spec, launch, clock):
        self.spec, self.launch, self.clock = spec, launch, clock
        self.lease = _Lease()
        self.used = False
        self.custody = None
        self.events = []
        self.caller = caller_limits()
        self._live()

    def _live(self):
        host = identity(os.getppid())
        require(host == self.launch['host'], 'actual outside direct caller owner changed')
        require(identity(self.launch['outer_guard']['pid']) == self.launch['outer_guard'], 'actual stock outer guard changed')
        require(identity(os.getpid())['pgid'] == host['pgid'] == self.launch['outer_guard']['pgid'], 'same owned physical cohort')
        require(time.monotonic() < self.launch['deadline_monotonic']
                and time.time() < self.launch['deadline_unix'], 'actual outside deadline exhausted')
        cmd = Path('/proc/' + str(host['pid']) + '/cmdline').read_bytes().split(b'\0')[:-1]
        ref = self.launch['input']
        require(cmd == [PYTHON.encode(), b'-I', b'-B', self.spec['host']['path'].encode(),
                        ref['path'].encode(), str(ref['bytes']).encode(), ref['sha256'].encode()], 'pinned actual finite host invocation')
        read_pin(self.spec['host'])

    def require_authority(self, request):
        require(not self.used, 'one-shot capability already consumed')
        self.used = True
        self._live()
        fields = {'caller', 'helper', 'entry', 'descriptor', 'clock_pin', 'authority_clock',
                  'evidence', 'fixture_root', 'stop_monotonic', 'stop_unix',
                  'final_monotonic', 'final_unix', 'sum_hard_AS_bytes',
                  'outside_deadline_through_actual_caller_exit'}
        require(type(request) is dict and set(request) == fields, 'exact helper request fields')
        expected = {'caller': self.caller, 'helper': self.spec['helper'], 'entry': self.spec['entry'],
                    'descriptor': self.spec['descriptor'], 'clock_pin': self.spec['clock'],
                    'authority_clock': self.clock, 'evidence': self.spec['evidence'],
                    'fixture_root': self.spec['fixture_root'], 'sum_hard_AS_bytes': 2 * AS,
                    'outside_deadline_through_actual_caller_exit': True}
        require(all(request[k] == v for k, v in expected.items()), 'exact admitted request scope mismatch')
        require(request['outside_deadline_through_actual_caller_exit'] is True, 'actual outside ownership required')
        useful_mono = self.clock['started_at_monotonic'] + self.clock['original_seconds'] - self.clock['cleanup_seconds']
        final_mono = self.clock['started_at_monotonic'] + self.clock['original_seconds']
        for key in ('stop_monotonic', 'stop_unix', 'final_monotonic', 'final_unix'):
            require(type(request[key]) in (int, float) and math.isfinite(request[key]), 'exact finite request deadline')
        require(time.monotonic() < request['stop_monotonic'] <= min(useful_mono, time.monotonic() + self.spec['wall_cap'])
                and time.time() < request['stop_unix'] <= min(self.clock['useful_deadline_unix'], time.time() + self.spec['wall_cap'])
                and request['final_monotonic'] == min(final_mono, request['stop_monotonic'] + 5)
                and request['final_unix'] == min(self.clock['final_deadline_unix'], request['stop_unix'] + 5)
                and self.launch['deadline_monotonic'] <= request['final_monotonic']
                and self.launch['deadline_unix'] <= request['final_unix'], 'original physical clock/request bounds')
        require(abs((request['stop_unix'] - self.clock['started_at_unix'])
                    - (request['stop_monotonic'] - self.clock['started_at_monotonic'])) <= 2, 'dual-clock request consistency')
        for key in ('helper', 'entry', 'descriptor', 'clock'):
            read_pin(self.spec[key], LIMIT if key in ('descriptor', 'clock') else 1048576)
        self.events.append({'event': 'require_authority', 'exact_scope_matched': True, 'issuer': 'EXTERNAL_ROOT_NOT_AUTHENTICATED_BY_JSON'})
        return self.lease

    def hold(self, lease, custody):
        require(self.custody is None, 'no second custody')
        self.custody = custody  # Retain SAME mutable object before fallible checks.
        require(lease is self.lease and self.used and custody.pid is None and not custody.fds
                and custody.caller == self.caller and custody.clock == self.clock, 'pre-fork exact custody registration')
        self.events.append({'event': 'hold', 'before_fork': True, 'same_mutable_object': True})

    def before_go(self, lease, custody):
        require(lease is self.lease and custody is self.custody, 'same pre-registered custody')
        self._live()
        worker = identity(custody.pid)
        require(worker['ppid'] == os.getpid() and worker['birth'] == custody.ticks
                and worker['pgid'] == self.launch['host']['pgid'], 'owned current worker birth')
        require(custody.worker['AS'] == [AS, AS] and custody.worker['CPU'] == [40, 40]
                and custody.worker['CORE'] == [0, 0] and custody.worker['affinity'] == self.caller['affinity'], 'worker resources before GO')
        os.fstat(custody.fds['pidfd'])
        os.fstat(custody.fds['evidence'])
        self.events.append({'event': 'before_GO', 'worker': worker, 'sum_hard_AS_bytes': 2 * AS})

    def pending(self, lease, custody):
        require(lease is self.lease and custody is self.custody, 'same pending custody')
        self.events.append({'event': 'pending', 'snapshot': custody.snapshot(), 'capacity_release': False})

    def helper_unwound(self, lease, custody):
        require(lease is self.lease and custody is self.custody, 'same unwound custody')
        self._live()
        self.events.append({'event': 'helper_unwound', 'caller_scope_retained': True})

    def reconcile(self):
        c = self.custody
        if c is None:
            return None
        self._live()
        before = c.snapshot()
        if c.pid is not None and not c.waited:
            fd = c.fds.get('pidfd')
            require(fd is not None and not c.fd_errors, 'STOP_UNCONFIRMED no unambiguous owned pidfd')
            s = os.fstat(fd)
            require((s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode)) == c.fd_ids['pidfd'], 'retained pidfd identity')
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            pid, status = os.waitpid(c.pid, 0)  # Actual direct wait; stock parent still bounds this syscall.
            require(pid == c.pid, 'exact current direct child wait')
            c.status, c.waited = status, True
            try:
                c.child_absent = identity(c.pid)['birth'] != c.ticks
            except FileNotFoundError:
                c.child_absent = True
        for name in list(c.fds):
            c.close_fd(name)  # Never retries an ambiguous close or replaces a handle.
        require(not c.fd_errors and all(fd is None for fd in c.fds.values()) and c.mask_restored
                and (c.pid is None or (c.waited and c.child_absent)), 'STOP_UNCONFIRMED retained resources')
        return {'before': before, 'after': c.snapshot(), 'same_object': True,
                'caller_closure': 'outside stock Popen direct wait still required'}


def main():
    require(len(sys.argv) == 2, 'exact host launch input')
    launch_path = Path(sys.argv[1])
    require(launch_path.is_absolute() and launch_path.name == 'LAUNCH.json', 'launch path')
    launch_stat = launch_path.lstat()
    require(stat.S_ISREG(launch_stat.st_mode) and launch_stat.st_nlink == 1
            and launch_stat.st_uid == os.getuid() and not launch_stat.st_mode & 0o077
            and launch_stat.st_size <= LIMIT, 'private launch input')
    launch = json.loads(launch_path.read_bytes())
    require(set(launch) == {'input', 'host', 'outer_guard', 'deadline_monotonic', 'deadline_unix'}, 'launch fields')
    spec = json.loads(read_pin(launch['input'], LIMIT))
    require(spec['caller']['path'] == SELF and spec['record'] == str(launch_path.parent), 'exact pinned caller scope')
    read_pin(spec['caller'])
    caller_limits()
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL
            and len(list(Path('/proc/self/task').iterdir())) == 1, 'one-thread default SIGCHLD caller')
    parent = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0 and os.getppid() == parent, 'caller parent-death before Source')
    clock = json.loads(read_pin(spec['clock'], LIMIT))
    owner = _RootOneShotOwner(spec, launch, clock)  # External scope already live before helper import.
    record = launch_path.parent
    put(record / 'CALLER-BEFORE-IMPORT.json', {'caller': identity(os.getpid()), 'actual_host': launch['host'],
        'limits': caller_limits(), 'deadline_monotonic': launch['deadline_monotonic'],
        'deadline_unix': launch['deadline_unix'], 'original_clock': clock,
        'admission': 'Root externally approves exact invocation; input and owner object never mint authority'})
    raw = read_pin(spec['helper'])
    helper = types.ModuleType('<Root-admitted-current-helper>')
    helper.__file__ = spec['helper']['path']
    exec(compile(raw, spec['helper']['path'], 'exec'), helper.__dict__)
    result = None
    failure = None
    try:
        result = helper.run(spec['entry'], spec['descriptor'], spec['clock'], clock, spec['evidence'],
                            owner=owner, helper_pin=spec['helper'], fixture_root=spec['fixture_root'],
                            wall_cap=spec['wall_cap'])
    except BaseException as exc:
        failure = {'class': type(exc).__name__, 'detail': str(exc)[:300], 'attempt_outcome': 'UNKNOWN_NO_REPLAY'}
    closure = owner.reconcile()
    put(record / 'CALLER-RETURN-PREPARED.json', {'result': result, 'failure': failure,
        'same_custody_closure': closure, 'events': owner.events, 'capacity_release': False,
        'caller_exit': 'NOT_OBSERVED_INSIDE; actual outside direct wait required', 'original_clock': clock})
    return 0 if failure is None and result is not None and result['attempt_outcome'] == 'ENTRY_RETURN_OBSERVED_NOT_OUTER_ACCEPTANCE' else 2


if __name__ == '__main__':
    sys.exit(main())
