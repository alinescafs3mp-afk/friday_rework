"""Inert Linux Python supervisor for ONE trusted, owned RESULT helper.

No subprocess/daemon/model. Caller must already be a dedicated resource-limited
helper, never TUI/backend. No general hostile-code containment is claimed.
All effectful loading, validation, filesystem operations and cleanup run in the
single owned child. Parent performs only bounded IPC, pidfd signal and WNOHANG
wait; never waits for worker filesystem or worker finally to cooperate.
"""
import json
import math
import os
from pathlib import Path
import resource
import select
import signal
import socket
import stat
import threading
import time
import uuid

LIMIT = 65536
AS = 268435456
PENDING = {}  # Retain exact pidfd custody if termination is unconfirmed.


class Refusal(ValueError):
    pass


def birth(pid):
    return Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()[19]


def caps():
    return {'AS': list(resource.getrlimit(resource.RLIMIT_AS)),
            'CPU': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'FSIZE': list(resource.getrlimit(resource.RLIMIT_FSIZE)),
            'CORE': list(resource.getrlimit(resource.RLIMIT_CORE)),
            'affinity': sorted(os.sched_getaffinity(0))}


def valid_caps(c):
    for key, maximum in [('AS', AS), ('CPU', 60), ('FSIZE', 67108864)]:
        pair = c.get(key)
        if (not isinstance(pair, list) or len(pair) != 2 or
                any(type(x) is not int for x in pair) or
                not 0 < pair[0] <= pair[1] <= maximum):
            raise Refusal('finite dedicated helper caps required')
    if c.get('CORE') != [0, 0] or not 0 < len(c.get('affinity', [])) <= 2:
        raise Refusal('core/affinity boundary')


def frame(value):
    b = json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()
    if len(b) > LIMIT:
        raise Refusal('custody frame bound')
    return b


def send(sock, value, end):
    b = frame(value)
    while time.monotonic() < end:
        try:
            if sock.send(b) != len(b):
                raise Refusal('short custody packet')
            return
        except BlockingIOError:
            select.select([], [sock], [], max(0, min(.01, end-time.monotonic())))
    raise TimeoutError('custody send expired')


def receive(sock):
    b, _, flags, _ = sock.recvmsg(LIMIT + 1)
    if not b:
        raise EOFError('custody closed')
    if flags & socket.MSG_TRUNC or len(b) > LIMIT:
        raise Refusal('custody frame bound')
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise Refusal('duplicate custody field')
            d[k] = v
        return d
    def bad(_):
        raise Refusal('nonfinite custody field')
    o = json.loads(b, object_pairs_hook=pairs, parse_constant=bad)
    if not isinstance(o, dict):
        raise Refusal('custody envelope')
    return o


def persist_birth(directory, value):
    """Worker-only I/O: fully inside retained parent deadline, before GO."""
    p = Path(directory)
    if not p.is_absolute() or str(p) != os.path.normpath(str(p)) or '..' in p.parts:
        raise Refusal('custody path')
    for a in [*p.parents, p]:
        if stat.S_ISLNK(a.lstat().st_mode):
            raise Refusal('custody symlink')
    st = p.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise Refusal('private custody directory')
    # Existing records refuse: no same-directory retry or overwrite.
    fd = os.open(p/'WORKER-BIRTH.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(frame(value)); f.flush(); os.fsync(f.fileno())
    d = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(d)
    finally:
        os.close(d)


class Custody:
    def __init__(self, sock, operation_end):
        self.sock = sock
        self.operation_end = operation_end
        self.active = True
        self.cleanup = 2.0

    def tighten(self, end):
        if type(end) not in (int, float) or not math.isfinite(end) or end <= time.monotonic():
            raise Refusal('original useful clock expired')
        end = min(end, self.operation_end)
        send(self.sock, {'kind': 'TIGHTEN', 'end': end}, self.operation_end)
        while time.monotonic() < end:
            if select.select([self.sock], [], [], max(0, min(.01, end-time.monotonic())))[0]:
                if receive(self.sock) != {'kind': 'ACK', 'end': end}:
                    raise Refusal('deadline acknowledgement')
                self.operation_end = end
                return
        raise TimeoutError('original clock not acknowledged')

    def commit(self, receipt):
        # Called ONLY after canonical file+parent-directory fsync succeeded.
        send(self.sock, {'kind': 'DURABLE', 'receipt': receipt}, self.operation_end)


def durable_shape(o):
    if not isinstance(o, dict) or o.get('state') != 'ENQUEUED':
        raise Refusal('unconfirmed admission marker')
    for k in ('event_id', 'sha256', 'recipient_thread', 'recipient_generation',
              'sender_generation', 'assignment_id', 'assignment_generation', 'submission_id'):
        if not isinstance(o.get(k), str) or not o[k]:
            raise Refusal('admission marker identity')
    if str(uuid.UUID(o['submission_id'])) != o['submission_id']:
        raise Refusal('admission marker submission')
    if uuid.UUID(o['submission_id']).int == 0 or o.get('assignment_action') != 'complete':
        raise Refusal('admission marker shape')
    frame(o)
    return o


def signal_owned(pid, ticks, pidfd):
    """Never send to a numeric PID after an identity mismatch.

    pidfd binds the original child even if the numeric PID is reused. Refuse
    missing pidfd support instead of substituting kill(PID) or a process group.
    """
    if pidfd is None:
        raise Refusal('owned pidfd required')
    try:
        if birth(pid) != ticks:
            return False
    except FileNotFoundError:
        return False
    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
    return True


def supervise(operation, custody_dir, *, wall=20.0, cleanup=2.0, hard_end=None):
    """ONE fork, whole entry including import/load and unwinding <= original wall.

    hard_end is the trusted caller's retained original useful monotonic deadline;
    it may only shorten the 20s cap. The child also tightens against exact grant
    clock before any reservation/lifecycle/native effect. A kernel-stuck child
    gives STOP_UNCONFIRMED at the finite return boundary; never false closure.
    """
    started = time.monotonic()
    if (type(wall) not in (int, float) or type(cleanup) not in (int, float)
            or not math.isfinite(wall) or not math.isfinite(cleanup)
            or not 0 < cleanup < wall <= 20):
        raise Refusal('whole wall includes bounded cleanup')
    final_end = started + wall
    if hard_end is not None:
        if type(hard_end) not in (int, float) or not math.isfinite(hard_end):
            raise Refusal('original caller deadline')
        final_end = min(final_end, hard_end)
    operation_end = final_end-cleanup
    if operation_end <= started:
        raise Refusal('original caller clock expired')
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise Refusal('dedicated single-thread helper required')
    # Automatic reaping or an inherited reaper breaks direct-wait custody.
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise Refusal('SIGCHLD must be SIG_DFL before fork')
    caller_caps = caps(); valid_caps(caller_caps)
    timer = signal.getitimer(signal.ITIMER_REAL)
    if timer[1] or (timer[0] and timer[0] <= final_end-started):
        raise Refusal('earlier/periodic owner timer retained')
    if PENDING:
        raise Refusal('STOP_UNCONFIRMED existing custody; no new admission')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise Refusal('Linux pidfd custody unavailable')
    caller = {'pid': os.getpid(), 'birth': birth(os.getpid()), 'caps': caller_caps}
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    a.setblocking(False); b.setblocking(False)
    pid = os.fork()
    if pid == 0:
        try:
            a.close()
            # Fork inherited the already constrained 256MiB/CPU2 boundary.
            resource.setrlimit(resource.RLIMIT_CPU, (min(40, resource.getrlimit(resource.RLIMIT_CPU)[0]), min(40, resource.getrlimit(resource.RLIMIT_CPU)[1])))
            me = {'pid': os.getpid(), 'birth': birth(os.getpid()), 'caps': caps()}
            valid_caps(me['caps'])
            persist_birth(custody_dir, {'caller': caller, 'worker': me,
                          'combined_hard_AS': caller_caps['AS'][1]+me['caps']['AS'][1],
                          'before_GO': True, 'operation_end': operation_end, 'final_end': final_end})
            send(b, {'kind': 'BIRTH', 'worker': me}, operation_end)
            while time.monotonic() < operation_end:
                if select.select([b], [], [], max(0, min(.01, operation_end-time.monotonic())))[0]:
                    if receive(b) != {'kind': 'GO'}:
                        raise Refusal('GO required')
                    break
            else:
                raise TimeoutError('GO expired')
            # Trusted accepted Python source must not create extra descendants.
            def no_spawn(*_a, **_k):
                raise Refusal('only registered worker permitted')
            os.fork = no_spawn
            if hasattr(os, 'forkpty'): os.forkpty = no_spawn
            if hasattr(os, 'posix_spawn'): os.posix_spawn = no_spawn
            if hasattr(os, 'posix_spawnp'): os.posix_spawnp = no_spawn
            custody = Custody(b, operation_end)
            custody.cleanup = cleanup
            result = operation(custody)
            send(b, {'kind': 'RESULT', 'result': result}, operation_end)
            os._exit(0)  # No Python atexit/implicit unwinding outside custody.
        except BaseException as exc:
            try: send(b, {'kind': 'ERROR', 'class': type(exc).__name__}, operation_end)
            except BaseException: pass
            os._exit(2)
    # Custody exists BEFORE any parent close, wait, birth or pidfd teardown.
    # Retain socket objects as well as fd identity: an exceptional close may
    # have released its descriptor already and must never be retried blindly.
    held = {'pid': pid, 'birth': None, 'pidfd': None, 'pidfd_identity': None,
            'custody_dir': str(custody_dir), 'no_replay': True,
            'durable': None, 'result': None, 'worker': None,
            'wait_errors': [], 'teardown_errors': [], 'reaped': False,
            'wait_status': None, 'sockets': [a, b]}
    PENDING[pid] = held
    ticks = None; pidfd = None; setup_failure = None
    try:
        ticks = birth(pid); held['birth'] = ticks
        pidfd = os.pidfd_open(pid); held['pidfd'] = pidfd
        st = os.fstat(pidfd)
        held['pidfd_identity'] = (st.st_dev, st.st_ino)
    except BaseException as exc:
        setup_failure = type(exc).__name__
        teardown_error(held, 'setup', exc)
    try:
        b.close()
    except BaseException as exc:
        teardown_error(held, 'peer_socket_close', exc)
    worker = None; result = None; durable = None; failure = setup_failure
    status = None; stopped = False; packet_count = 0; wait_errors = held['wait_errors']
    try:
        while pidfd is not None and time.monotonic() < operation_end:
            readable = select.select([a], [], [], max(0, min(.01, operation_end-time.monotonic())))[0]
            if readable:
                try:
                    message = receive(a)
                except EOFError:
                    break
                packet_count += 1
                if packet_count > 8:
                    raise Refusal('custody notification bound')
                kind = message.get('kind')
                if kind == 'BIRTH' and worker is None:
                    worker = message['worker']; held['worker'] = worker; valid_caps(worker['caps'])
                    if worker['pid'] != pid or worker['birth'] != ticks:
                        raise Refusal('worker birth mismatch')
                    if caller_caps['AS'][1]+worker['caps']['AS'][1] > AS*2:
                        raise Refusal('combined birth caps')
                    send(a, {'kind': 'GO'}, operation_end)
                elif kind == 'TIGHTEN' and worker is not None:
                    end = message['end']
                    if type(end) not in (int, float) or not math.isfinite(end) or end > operation_end:
                        raise Refusal('clock reset/extension')
                    operation_end = end
                    # Keep the SAME initial final boundary, only shorten it.
                    final_end = min(final_end, end+cleanup)
                    send(a, {'kind': 'ACK', 'end': end}, operation_end)
                elif kind == 'DURABLE' and worker is not None and durable is None:
                    durable = durable_shape(message['receipt']); held['durable'] = durable
                elif kind == 'RESULT' and worker is not None:
                    result = message['result']; held['result'] = result
                    if not isinstance(result, dict): raise Refusal('worker result object')
                    if result.get('state') == 'ENQUEUED' and durable is None:
                        raise Refusal('no durable marker; cannot promote UNKNOWN')
                elif kind == 'ERROR':
                    failure = message.get('class', 'WorkerError')
                else:
                    raise Refusal('custody phase/protocol')
            try:
                got, st = os.waitpid(pid, os.WNOHANG)
            except BaseException as exc:
                wait_errors.append({'phase': 'loop', 'class': type(exc).__name__, 'errno': getattr(exc, 'errno', None)})
                raise
            if got == pid:
                status = st; stopped = True; break
            if got:
                raise Refusal('wrong direct-wait child')
    except BaseException as exc:
        failure = type(exc).__name__
    finally:
        if not stopped:
            try: signal_owned(pid, ticks, pidfd)
            except ProcessLookupError: pass
            except BaseException as exc: failure = type(exc).__name__
            while time.monotonic() < final_end:
                try:
                    got, st = os.waitpid(pid, os.WNOHANG)
                except BaseException as exc:
                    failure = type(exc).__name__
                    wait_errors.append({'phase': 'cleanup', 'class': type(exc).__name__, 'errno': getattr(exc, 'errno', None)})
                    break  # Unknown custody: drain packets, retain pidfd, never infer reaping.
                if got == pid:
                    status = st; stopped = True; break
                if got:
                    failure = 'wrong direct-wait child'
                    break
                try:
                    select.select([pidfd] if pidfd is not None else [], [], [], max(0, min(.01, final_end-time.monotonic())))
                except BaseException as exc:
                    failure = type(exc).__name__
                    teardown_error(held, 'cleanup_select', exc)
                    break
        # Drain already queued packets without waiting, so committed durable
        # admission survives timeout between checkpoint and child teardown.
        for _ in range(8-packet_count):
            try:
                message = receive(a)
                if message.get('kind') == 'DURABLE' and worker is not None and durable is None:
                    durable = durable_shape(message['receipt']); held['durable'] = durable
                elif message.get('kind') == 'RESULT' and worker is not None:
                    result = message['result']; held['result'] = result
            except (BlockingIOError, EOFError): break
            except BaseException as exc: failure = type(exc).__name__; break
        held.update(durable=durable, result=result, worker=worker, reaped=stopped, wait_status=status)
        try:
            a.close()
        except BaseException as exc:
            failure = type(exc).__name__
            teardown_error(held, 'parent_socket_close', exc)
    fresh_absent = False
    if stopped:
        try: fresh_absent = ticks is not None and birth(pid) != ticks
        except FileNotFoundError: fresh_absent = ticks is not None
        except BaseException as exc:
            failure = type(exc).__name__
            teardown_error(held, 'fresh_birth', exc)
    confirmed_stop = stopped and fresh_absent
    # A close failure must return retained custody, even after a successful
    # direct wait. Reconciliation checks descriptor identity before retrying.
    if confirmed_stop and not held['teardown_errors']:
        confirmed_stop = release_resources(held)
    else:
        confirmed_stop = False
    if confirmed_stop:
        del PENDING[pid]
    held.update(durable=durable, result=result, worker=worker, reaped=stopped,
                wait_status=status, fresh_exact_birth_absent=fresh_absent)
    # Do not infer zero RPCs from a deadline. No mutation is retried here.
    out = result if isinstance(result, dict) else {'state': 'UNKNOWN', 'queue_calls': 'UNKNOWN'}
    if out.get('state') == 'ENQUEUED' and durable is None:
        out = {'state': 'UNKNOWN', 'queue_calls': 'UNKNOWN'}
    if durable is not None:
        out = {**out, **durable}
    return {**out, 'whole_wall': {'caller': caller, 'worker': worker,
                'pid': pid, 'birth': ticks, 'packet_count': packet_count,
                'started_monotonic': started, 'operation_end': operation_end, 'final_end': final_end,
                'elapsed': time.monotonic()-started, 'reaped': stopped,
                'fresh_exact_birth_absent': fresh_absent,
                'status': 'STOP_CONFIRMED' if confirmed_stop else 'STOP_UNCONFIRMED',
                'direct_wait_returncode': os.waitstatus_to_exitcode(status) if status is not None else None,
                'failure': failure, 'wait_errors': wait_errors, 'teardown_errors': held['teardown_errors'], 'no_replay': True}, 'no_retry': True,
            'enqueue_is_not_read': True}


def teardown_error(held, phase, exc):
    held['teardown_errors'].append({'phase': phase, 'class': type(exc).__name__,
                                     'errno': getattr(exc, 'errno', None)})


def release_resources(held):
    """Release only still-owned handles, never an ambiguous reused number."""
    ok = True
    for sock in held['sockets']:
        if sock.fileno() >= 0:
            try:
                sock.close()
            except BaseException as exc:
                teardown_error(held, 'socket_reconcile_close', exc); ok = False
    fd = held['pidfd']
    if fd is not None:
        try:
            st = os.fstat(fd)
        except OSError as exc:
            if exc.errno == 9:  # Fresh EBADF proves this descriptor is absent.
                held['pidfd'] = None
            else:
                teardown_error(held, 'pidfd_fstat', exc); ok = False
        except BaseException as exc:
            teardown_error(held, 'pidfd_fstat', exc); ok = False
        else:
            if held['pidfd_identity'] is None:
                # Setup never established an fd identity. Keep the handle and
                # caller alive; no inference of release or close of a reused fd.
                ok = False
            elif (st.st_dev, st.st_ino) != held['pidfd_identity']:
                # The old handle was released; the replacement is not ours.
                held['pidfd'] = None
            else:
                try:
                    os.close(fd)
                    held['pidfd'] = None
                except BaseException as exc:
                    teardown_error(held, 'pidfd_close', exc); ok = False
    return ok and all(sock.fileno() < 0 for sock in held['sockets']) and held['pidfd'] is None


def reconcile_pending(pid):
    """Same living caller: actual direct wait AND fresh birth AND handle close.

    ECHILD, absence and close exceptions never substitute for direct wait.
    No signal, new child, admission or replay occurs in reconciliation.
    """
    held = PENDING[pid]
    if not held['reaped']:
        try:
            got, status = os.waitpid(pid, os.WNOHANG)
        except BaseException as exc:
            held['wait_errors'].append({'phase': 'reconcile', 'class': type(exc).__name__, 'errno': getattr(exc, 'errno', None)})
            return {'status': 'STOP_UNCONFIRMED', 'failure': type(exc).__name__, 'no_replay': True}
        if got != pid:
            return {'status': 'STOP_UNCONFIRMED', 'no_replay': True}
        held['reaped'] = True
        held['wait_status'] = status
    try:
        absent = held['birth'] is not None and birth(pid) != held['birth']
    except FileNotFoundError:
        absent = held['birth'] is not None
    except BaseException as exc:
        teardown_error(held, 'reconcile_birth', exc)
        return {'status': 'STOP_UNCONFIRMED', 'failure': type(exc).__name__, 'no_replay': True}
    if not absent or not release_resources(held):
        return {'status': 'STOP_UNCONFIRMED', 'teardown_errors': held['teardown_errors'], 'no_replay': True}
    del PENDING[pid]
    return {'status': 'STOP_CONFIRMED', 'pid': pid, 'birth': held['birth'],
            'reaped': True, 'fresh_exact_birth_absent': True,
            'direct_wait_returncode': os.waitstatus_to_exitcode(held['wait_status']),
            'durable': held['durable'], 'result': held['result'],
            'teardown_errors': held['teardown_errors'], 'no_replay': True}
