"""INERT until Root admits this exact stock finite host/caller invocation.

Adapts C25 fixture_host-v5: one Popen direct child, wait(timeout), exact pidfd
stop, direct wait and subreaper cleanup. Inputs/pins prove consistency only.
No installed owner, daemon, authority protocol, automatic retry or C26 nesting.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import select
import signal
import stat
import subprocess
import sys
import time

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
    return {'pid': pid, 'birth': v[19], 'ppid': int(v[1]),
            'pgid': int(v[2]), 'sid': int(v[3])}


def absent(row):
    try:
        return identity(row['pid'])['birth'] != row['birth']
    except FileNotFoundError:
        return True


def read_pin(ref, maximum=1048576):
    require(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}, 'pin shape')
    p = Path(ref['path'])
    require(p.is_absolute() and '..' not in p.parts and str(p) == os.path.normpath(str(p)), 'pin path')
    require(type(ref['bytes']) is int and 0 <= ref['bytes'] <= maximum, 'pin size')
    for parent in reversed(p.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode), 'pin ancestor')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
            require(size <= maximum, 'read bound')
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


def original(clock):
    fields = ('started_at_unix', 'started_at_monotonic', 'original_seconds',
              'cleanup_seconds', 'useful_deadline_unix', 'final_deadline_unix')
    require(all(type(clock.get(k)) in (int, float) and math.isfinite(clock[k]) for k in fields), 'clock numeric')
    elapsed = time.monotonic() - clock['started_at_monotonic']
    require(3 <= clock['cleanup_seconds'] < clock['original_seconds'] and elapsed >= 0
            and abs(time.time() - clock['started_at_unix'] - elapsed) <= 2
            and clock['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and clock['useful_deadline_unix'] == clock['started_at_unix'] + clock['original_seconds'] - clock['cleanup_seconds']
            and clock['final_deadline_unix'] == clock['started_at_unix'] + clock['original_seconds'], 'original clock consistency')
    return (clock['started_at_monotonic'] + clock['original_seconds'] - clock['cleanup_seconds'],
            clock['started_at_monotonic'] + clock['original_seconds'])


def main():
    require(len(sys.argv) == 4, 'exact input: path bytes SHA256')
    ref = {'path': sys.argv[1], 'bytes': int(sys.argv[2]), 'sha256': sys.argv[3]}
    spec = json.loads(read_pin(ref, LIMIT))
    keys = {'host', 'caller', 'helper', 'entry', 'descriptor', 'clock', 'evidence',
            'fixture_root', 'record', 'wall_cap', 'caller_wall_seconds',
            'host_cleanup_seconds', 'outer_timeout_seconds'}
    require(set(spec) == keys and spec['host']['path'] == SELF, 'exact one-shot input fields')
    for key in ('host', 'caller', 'helper', 'entry', 'descriptor'):
        read_pin(spec[key])
    require(spec['caller']['path'] == str(Path(SELF).with_name('stock_install_caller.py')), 'fixed caller')
    clock = json.loads(read_pin(spec['clock'], LIMIT))
    useful, final = original(clock)
    for key in ('wall_cap', 'caller_wall_seconds', 'host_cleanup_seconds', 'outer_timeout_seconds'):
        require(type(spec[key]) in (int, float) and math.isfinite(spec[key]) and spec[key] > 0, 'finite launch caps')
    require(spec['wall_cap'] <= 30 and spec['caller_wall_seconds'] <= spec['wall_cap']
            and spec['host_cleanup_seconds'] <= 5
            and spec['caller_wall_seconds'] + spec['host_cleanup_seconds'] + 2 <= spec['outer_timeout_seconds'] <= 60,
            'shortening-only physical caps')
    require(time.monotonic() + spec['outer_timeout_seconds'] < useful
            and time.time() + spec['outer_timeout_seconds'] < clock['useful_deadline_unix'], 'outer guard fits original useful clock')
    for kind, cap in ((resource.RLIMIT_AS, AS), (resource.RLIMIT_CPU, 60), (resource.RLIMIT_FSIZE, MAX)):
        require(resource.getrlimit(kind) == (cap, cap), 'hard host resources before caller')
    require(resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
            and 0 < len(os.sched_getaffinity(0)) <= 2
            and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL
            and len(list(Path('/proc/self/task').iterdir())) == 1, 'host custody boundary')
    children = Path('/proc/self/task/' + str(os.getpid()) + '/children')
    require(not children.read_text().strip(), 'finite host starts without children')
    host = identity(os.getpid())
    outer = identity(os.getppid())
    expected_outer = [b'/usr/bin/timeout', b'-s', b'KILL',
                      (str(spec['outer_timeout_seconds']) + 's').encode(),
                      PYTHON.encode(), b'-I', b'-B', SELF.encode(),
                      ref['path'].encode(), str(ref['bytes']).encode(), ref['sha256'].encode()]
    require(Path('/proc/' + str(outer['pid']) + '/cmdline').read_bytes().split(b'\0')[:-1] == expected_outer,
            'actual stock outer invocation differs')
    require(host['pgid'] == outer['pgid'], 'whole cohort outer guard')
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, 'finite host subreaper')
    require(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0 and os.getppid() == outer['pid'], 'host parent death')
    record = Path(spec['record'])
    e = Path(spec['evidence'])
    require(record.parent == e.parent and record != e and record.is_absolute()
            and '..' not in record.parts and str(record) == os.path.normpath(str(record)), 'exact private records')
    for parent in reversed(record.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode), 'record ancestor')
    require(record.parent.stat().st_uid == os.getuid() and not record.parent.stat().st_mode & 0o077, 'private record parent')
    require(not e.exists(), 'no attempt replay')
    record.mkdir(mode=0o700)
    deadline_mono = min(useful, time.monotonic() + spec['caller_wall_seconds'])
    deadline_unix = min(clock['useful_deadline_unix'], time.time() + spec['caller_wall_seconds'])
    launch = {'input': ref, 'host': host, 'outer_guard': outer,
              'deadline_monotonic': deadline_mono, 'deadline_unix': deadline_unix}
    put(record / 'LAUNCH.json', launch)
    put(record / 'HOST-BIRTH.json', {'host': host, 'outer_guard': outer,
        'limits': Path('/proc/self/limits').read_text(), 'affinity': sorted(os.sched_getaffinity(0)),
        'Source_caller_worker_hard_AS_sum': 2 * AS, 'whole_timeout_host_caller_worker_hard_AS_sum': 4 * AS,
        'original_clock': clock, 'unknown_initial_metadata_RSS': 'UNKNOWN',
        'authority': 'Root actual independently admitted exact external invocation; this file is consistency only'})
    proc = None
    pfd = None
    code = None
    fault = None
    timed_out = False
    adopted = []
    known = []
    stdout = open(record / 'stdout.log', 'xb')
    stderr = open(record / 'stderr.log', 'xb')
    try:
        proc = subprocess.Popen([PYTHON, '-I', '-B', spec['caller']['path'],
                                 str(record / 'LAUNCH.json')], stdout=stdout, stderr=stderr,
                                close_fds=True, start_new_session=False)
        caller = identity(proc.pid)
        known.append(caller)
        require(caller['ppid'] == os.getpid() and caller['pgid'] == host['pgid'], 'actual owned caller')
        pfd = os.pidfd_open(proc.pid)
        put(record / 'CALLER-BIRTH.json', caller)
        wait_seconds = lambda: max(0, min(deadline_mono - time.monotonic(), deadline_unix - time.time()))
        try:
            code = proc.wait(timeout=wait_seconds())
        except subprocess.TimeoutExpired:
            timed_out = True
            signal.pidfd_send_signal(pfd, signal.SIGKILL)
            code = proc.wait(timeout=max(0, min(spec['host_cleanup_seconds'], final - time.monotonic(),
                                              clock['final_deadline_unix'] - time.time())))
    except BaseException as exc:
        fault = {'class': type(exc).__name__, 'detail': str(exc)[:300]}
        if proc is not None and code is None and pfd is not None:
            try:
                signal.pidfd_send_signal(pfd, signal.SIGKILL)
                code = proc.wait(timeout=max(0, min(spec['host_cleanup_seconds'], final - time.monotonic(),
                                                  clock['final_deadline_unix'] - time.time())))
            except BaseException as stop:
                fault['stop'] = type(stop).__name__
    finally:
        stdout.close()
        stderr.close()
        if pfd is not None:
            os.close(pfd)
    cleanup_until = min(time.monotonic() + spec['host_cleanup_seconds'], final)
    while code is not None:
        try:
            values = children.read_text().split()
            if not values:
                break
            require(time.monotonic() < cleanup_until and time.time() < clock['final_deadline_unix'], 'STOP_UNCONFIRMED adopted child')
            for value in values:
                row = identity(int(value))
                require(row['ppid'] == os.getpid() and row['pgid'] == host['pgid'], 'owned adopted identity')
                if row not in known:
                    known.append(row)
                fd = os.pidfd_open(row['pid'])
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    os.close(fd)
                pid, status = os.waitpid(row['pid'], os.WNOHANG)
                if pid:
                    adopted.append({'pid': pid, 'birth': row['birth'], 'direct_wait': True,
                                    'returncode': os.waitstatus_to_exitcode(status)})
            select.select([], [], [], 0.01)
        except BaseException as exc:
            fault = {'class': type(exc).__name__, 'detail': str(exc)[:300]}
            break
    worker_file = e / 'WORKER-BIRTH.json'
    if worker_file.exists():
        try:
            s = worker_file.lstat()
            require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid()
                    and not s.st_mode & 0o077 and s.st_size <= LIMIT, 'worker birth evidence inode')
            worker = json.loads(worker_file.read_bytes())
            require(type(worker['pid']) is int and type(worker['birth']) is str, 'worker birth evidence shape')
            if not any(row['pid'] == worker['pid'] and row['birth'] == worker['birth'] for row in known):
                known.append({'pid': worker['pid'], 'birth': worker['birth'], 'kind': 'Source_worker'})
        except BaseException as exc:
            fault = {'class': type(exc).__name__, 'detail': str(exc)[:300]}
    closure = [dict(row, fresh_birth_absent=absent(row)) for row in known]
    whole_closed = code is not None and not children.read_text().strip() and all(r['fresh_birth_absent'] for r in closure)
    result = {'caller_direct_wait': code is not None, 'caller_returncode': code,
              'caller_timed_out': timed_out, 'known_fresh_closure': closure,
              'adopted_direct_wait': adopted, 'whole_owned_directchild_cohort_closed': whole_closed,
              'fault': fault, 'attempt_outcome': 'UNKNOWN_NO_REPLAY' if fault or code != 0 else 'CALLER_RETURN_OBSERVED_NOT_INSTALL_ACCEPTANCE',
              'scope_release': 'Root decides only after this host actual direct return and fresh closure',
              'installed_admission': 'NOT_CLAIMED', 'original_clock': clock}
    put(record / 'OUTSIDE-CLOSURE.json', result)
    print(json.dumps(result, sort_keys=True))
    if not whole_closed:
        # Do not voluntarily drop a still-live finite host's physical scope.
        # The independently admitted stock outer timeout remains the enforcer.
        # No new attempt/lease or historical signaling is performed here.
        while True:
            signal.pause()
    return 0 if whole_closed and code == 0 and fault is None else 2


if __name__ == '__main__':
    sys.exit(main())
