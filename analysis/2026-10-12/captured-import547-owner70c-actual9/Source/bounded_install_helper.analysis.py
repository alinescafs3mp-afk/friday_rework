"""INERT C28 Source candidate. No CLI, installation, or invocation at import.

Execution requires a DISTINCT, already admitted Root custody/deadline owner.
This module does not implement, authenticate, or create that owner. Its supplied
interface is a trusted caller capability, not a hash/JSON/boolean runtime grant.
The owner must cover caller bootstrap, child BEFORE fork/GO, blocking syscalls,
and caller teardown/return under the original clock. Missing owner => no fork.
No hostile-Python sandbox or universal uninterruptible-kernel stop guarantee.
"""
from __future__ import annotations
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import select
import signal
import stat
import sys
import time

AS = 268435456
MAX = 67108864
LIMIT = 65536


class Refusal(ValueError): pass
class Deadline(TimeoutError): pass


class StopUnconfirmed(RuntimeError):
    """The registered live custody stays with Root; this is NOT release/closure."""
    def __init__(self, custody):
        self.custody = custody
        super().__init__('STOP_UNCONFIRMED; retained original custody; NO_REPLAY')


def birth(pid):
    return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]


def absent(pid, ticks):
    try: return birth(pid) != ticks
    except FileNotFoundError: return True


def limits():
    for kind, cap in ((resource.RLIMIT_AS,AS),(resource.RLIMIT_CPU,60),(resource.RLIMIT_FSIZE,MAX)):
        soft, hard = resource.getrlimit(kind)
        if not 0 < soft <= hard <= cap: raise Refusal('hard resource boundary before fork')
    if resource.getrlimit(resource.RLIMIT_CORE) != (0,0): raise Refusal('core boundary')
    if not 0 < len(os.sched_getaffinity(0)) <= 2: raise Refusal('CPU affinity boundary')
    return {'pid':os.getpid(),'birth':birth(os.getpid()),
            'AS':list(resource.getrlimit(resource.RLIMIT_AS)),
            'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),
            'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),
            'CORE':list(resource.getrlimit(resource.RLIMIT_CORE)),
            'affinity':sorted(os.sched_getaffinity(0))}


def read_pin(ref, maximum=1048576, *, custody=None):
    if not isinstance(ref,dict) or set(ref) != {'path','bytes','sha256'}: raise Refusal('pin shape')
    if type(ref['bytes']) is not int or not 0 <= ref['bytes'] <= maximum: raise Refusal('pin size')
    p=Path(ref['path'])
    if not p.is_absolute() or '..' in p.parts: raise Refusal('pin path')
    for parent in reversed(p.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode): raise Refusal('pin symlink ancestor')
    fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    label=None
    try:
        if custody is not None:
            label='pin_read_'+str(len(custody.fds));custody.track(label,fd)
        a=os.fstat(fd)
        def identity(s): return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode)
        if (not stat.S_ISREG(a.st_mode) or a.st_nlink != 1 or a.st_uid != os.getuid()
                or a.st_mode & 0o077 or a.st_size > maximum): raise Refusal('pin inode')
        chunks=[];n=0
        while True:
            b=os.read(fd,min(8192,maximum+1-n))
            if not b: break
            chunks.append(b);n+=len(b)
            if n > maximum: raise Refusal('pin bound')
        raw=b''.join(chunks)
        if identity(a)!=identity(os.fstat(fd)) or identity(a)!=identity(p.lstat()): raise Refusal('pin changed')
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']: raise Refusal('pin mismatch')
        return raw
    finally:
        if custody is None:os.close(fd)
        else:
            custody.close_fd(label)
            if custody.fds.get(label) is not None:raise Refusal('pin close uncertain; existing custody retained')


def check_clock(clock):
    fields=('started_at_unix','started_at_monotonic','original_seconds','cleanup_seconds',
            'useful_deadline_unix','final_deadline_unix')
    if any(type(clock.get(k)) not in (int,float) or not math.isfinite(clock[k]) for k in fields):
        raise Refusal('clock numeric shape')
    start=clock['started_at_unix'];span=clock['original_seconds'];clean=clock['cleanup_seconds']
    elapsed=time.monotonic()-clock['started_at_monotonic']
    if (not 3 <= clean < span or elapsed < 0 or time.time()<start
            or abs(time.time()-start-elapsed)>2
            or clock['useful_deadline_unix']!=start+span-clean
            or clock['final_deadline_unix']!=start+span
            or clock['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip()):
        raise Refusal('historical clock inconsistent')
    remaining=min(clock['useful_deadline_unix']-time.time(),span-clean-elapsed)
    if remaining<=0: raise Deadline('original useful deadline exhausted')
    return remaining


class Custody:
    """Mutable identity/resources registered with the existing owner BEFORE fork.

    The owner holds this object across helper exceptions. It must keep the outer
    process scope too; pid/birth/FD metadata alone is NOT a living custodian.
    Neither a pending exception nor a worker FINAL authorizes capacity release.
    """
    def __init__(self, owner, lease, caller, clock, stop_mono, stop_unix, final_mono, final_unix):
        self.owner=owner;self.lease=lease;self.caller=caller;self.clock=clock
        self.stop_mono=stop_mono;self.stop_unix=stop_unix
        self.final_mono=final_mono;self.final_unix=final_unix
        self.pid=None;self.ticks=None;self.status=None;self.waited=False
        self.fds={};self.fd_ids={};self.fd_errors={}
        self.errors=[];self.worker=None;self.worker_result=None
        self.failure=None;self.timed_out=False;self.put=None
        self.state='REGISTERED_BEFORE_FORK';self.child_absent=None
        self.mask=None;self.mask_restored=True

    def fault(self, phase, exc):
        # Bounded diagnostics; the actual resource handles remain in this object.
        if len(self.errors)<32:
            self.errors.append({'phase':phase,'class':type(exc).__name__,'detail':str(exc)[:300]})

    def track(self, name, fd):
        # Assign BEFORE fstat: capture failure must still retain the open handle.
        occupied=self.fds.get(name) is not None
        if occupied: name=name+'_additional_'+str(len(self.fds))
        self.fds[name]=fd
        s=os.fstat(fd);self.fd_ids[name]=(s.st_dev,s.st_ino,stat.S_IFMT(s.st_mode))
        if occupied: raise Refusal('occupied descriptor label; both handles retained')
        return fd

    def close_fd(self, name):
        """Never blindly retry an ambiguous close or close a reused descriptor."""
        fd=self.fds.get(name)
        if fd is None: return
        if name in self.fd_errors: return  # Existing owner must reconcile first.
        try:
            s=os.fstat(fd);identity=(s.st_dev,s.st_ino,stat.S_IFMT(s.st_mode))
            if identity != self.fd_ids.get(name): raise Refusal('retained FD identity changed: '+name)
            os.close(fd);self.fds[name]=None
        except BaseException as exc:
            self.fault('close_'+name,exc);self.fd_errors[name]=type(exc).__name__
            # A failed close may already have released the FD. Do not re-close it.
            try: os.fstat(fd)
            except OSError as probe:
                if probe.errno==errno.EBADF:
                    self.fds[name]=None;self.fd_errors.pop(name,None)
            except BaseException as probe: self.fault('close_probe_'+name,probe)

    def before_final(self):
        return time.monotonic()<self.final_mono and time.time()<self.final_unix

    def wait_once(self):
        if self.pid is None or self.waited: return True
        try:
            got,status=os.waitpid(self.pid,os.WNOHANG)
            if got==self.pid: self.status=status;self.waited=True;return True
            if got!=0: raise Refusal('wait returned another child')
        except BaseException as exc:
            self.fault('direct_wait',exc);return False
        return None

    def request_stop(self):
        """Only exact owned direct child. No process groups, TUI, or blind kill."""
        if self.pid is None or self.waited: return
        try:
            fd=self.fds.get('pidfd')
            if fd is not None:
                s=os.fstat(fd)
                if (s.st_dev,s.st_ino,stat.S_IFMT(s.st_mode))!=self.fd_ids['pidfd']:
                    raise Refusal('pidfd identity changed')
                signal.pidfd_send_signal(fd,signal.SIGKILL)
            else:
                # Retained, unreaped direct child; PID cannot be reused yet.
                # No non-child PID fallback and no fallback after ECHILD.
                if self.ticks is None: self.ticks=birth(self.pid)
                if birth(self.pid)!=self.ticks: raise Refusal('direct child identity changed')
                os.kill(self.pid,signal.SIGKILL)
        except ProcessLookupError: pass  # Still requires direct wait + absence.
        except BaseException as exc: self.fault('request_stop',exc)

    def settle_child(self):
        if self.pid is None: self.child_absent=None;return True
        if not self.waited:
            self.request_stop()
            while self.before_final():
                result=self.wait_once()
                if result is True: break
                if result is False: break  # Transfer pending; no raw wait error.
                try: select.select([],[],[],min(0.01,max(0,self.final_mono-time.monotonic())))
                except BaseException as exc: self.fault('wait_pause',exc);break
        if not self.waited: return False
        try:
            if self.ticks is None: raise Refusal('birth missing at direct closure')
            self.child_absent=absent(self.pid,self.ticks)
        except BaseException as exc: self.fault('fresh_absence',exc);return False
        return self.child_absent is True

    def snapshot(self):
        outcome='UNKNOWN_NO_REPLAY'
        if self.pid is None:outcome='NO_WORKER_EXECUTION'
        elif (self.waited and self.child_absent is True and self.status==0
              and self.failure is None and not self.errors
              and isinstance(self.worker_result,dict)
              and self.worker_result.get('state')=='ENTRY_RETURNED'):
            outcome='ENTRY_RETURN_OBSERVED_NOT_OUTER_ACCEPTANCE'
        return {'caller':self.caller,'worker':self.worker,'known_pid':self.pid,
                'known_birth':self.ticks,'direct_wait':self.waited,
                'returncode':os.waitstatus_to_exitcode(self.status) if self.waited else None,
                'fresh_birth_absent':self.child_absent,'state':self.state,
                'failure':self.failure,'timed_out':self.timed_out,
                'worker_result':self.worker_result,'errors':list(self.errors),
                'retained_fds':{n:fd for n,fd in self.fds.items() if fd is not None},
                'ambiguous_closes':dict(self.fd_errors),'mask_restored':self.mask_restored,
                'original_elapsed_observed':time.monotonic()-self.clock['started_at_monotonic'],
                'original_final_monotonic':self.clock['started_at_monotonic']+self.clock['original_seconds'],
                'attempt_final_monotonic':self.final_mono,'attempt_final_unix':self.final_unix,
                'attempt_outcome':outcome,
                'no_replay':True,'capacity_release':False,
                'caller_process_closure':'NOT_OBSERVED_INSIDE_HELPER; existing outside owner retains scope',
                'unknown_descendants':'UNKNOWN; Root must own whole execution boundary'}

    def finish(self):
        """No raw cleanup exception discards custody. No self-issued release."""
        self.state='STOPPING'
        settled=self.settle_child()
        # Capture a durable result even when direct wait is uncertain. A worker
        # result is retained evidence, never promoted into direct-wait closure.
        if self.worker_result is None and self.fds.get('evidence') is not None:
            try:
                fd=os.open('WORKER-RESULT.json',os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,
                           dir_fd=self.fds['evidence'])
                self.track('result_read',fd)
                s=os.fstat(fd)
                if not stat.S_ISREG(s.st_mode) or s.st_size>LIMIT or s.st_nlink!=1:
                    raise Refusal('worker result inode/bound')
                raw=os.read(fd,LIMIT+1)
                if len(raw)>LIMIT: raise Refusal('worker result bound')
                self.worker_result=json.loads(raw)
            except FileNotFoundError: pass
            except BaseException as exc: self.fault('retained_worker_result',exc)
        for name in list(self.fds):
            if name in ('pidfd','evidence'): continue
            self.close_fd(name)
        if self.mask is not None and not self.mask_restored:
            try:signal.pthread_sigmask(signal.SIG_SETMASK,self.mask);self.mask_restored=True
            except BaseException as exc:self.fault('restore_signal_mask',exc)
        # pidfd stays live across any unconfirmed wait/absence. Registry ownership
        # was established before fork; owner notification is not a late transfer.
        if settled: self.close_fd('pidfd')
        eligible=settled and self.mask_restored and not self.fd_errors and self.before_final()
        self.state='HELPER_TEARDOWN' if eligible else 'STOP_UNCONFIRMED'
        if self.put is not None:
            try:self.put('DIRECT-WAIT-CLOSURE.json' if eligible else 'STOP-UNCONFIRMED.json',self.snapshot())
            except BaseException as exc:self.fault('closure_evidence',exc);eligible=False
        # Every fallible final close/owner callback remains covered by the distinct
        # admitted outside deadline. No alarm is cancelled at this boundary.
        if eligible:self.close_fd('evidence')
        eligible=(eligible and not self.fd_errors and self.mask_restored
                  and all(fd is None for fd in self.fds.values()) and self.before_final())
        if eligible:
            self.state='HELPER_RETURN_PREPARED_OUTER_SCOPE_HELD'
            try:self.owner.helper_unwound(self.lease,self)
            except BaseException as exc:self.fault('owner_unwound',exc);eligible=False
            eligible=eligible and self.before_final()
        if not eligible:
            self.state='STOP_UNCONFIRMED'
            try:self.owner.pending(self.lease,self)
            except BaseException as exc:self.fault('owner_pending',exc)
            # The already registered object still has the pidfd/live resources,
            # independent of notification success. Root must not release/replay.
            raise StopUnconfirmed(self)
        return self.snapshot()


def run(entry, descriptor, clock_ref, authority_clock, evidence, *, owner=None,
        helper_pin=None, fixture_root=None, wall_cap=30):
    """One attempt, only with existing distinct Root custody/deadline admission.

    OWNER CONTRACT (no concrete implementation supplied here):
    require_authority(request) -> existing lease. Verifies genuine issuer, exact
    helper/caller/entry closure, clock and physical guardian; admission is live
    BEFORE this helper's bootstrap/first effect, not minted by this callback.
    hold(lease,custody) atomically keeps the actual mutable handles BEFORE fork;
    before_go(lease,custody) verifies child birth/AS256+256 and whole cohort guard;
    pending(lease,custody) retains capacity, original deadline and reconciliation;
    helper_unwound(lease,custody) records helper outcome WITHOUT releasing outer
    caller scope. Only actual outside process closure can release that scope.
    All methods are covered by that existing outside deadline. No new service,
    supervisor, thread, model, local fabricated JSON grant, or retry is provided.
    """
    if owner is None: raise Refusal('missing independently admitted existing Root custody/deadline owner')
    for name in ('require_authority','hold','before_go','pending','helper_unwound'):
        if not callable(getattr(owner,name,None)): raise Refusal('incomplete existing custody owner: '+name)
    caller=limits()
    if signal.getsignal(signal.SIGCHLD)!=signal.SIG_DFL:
        raise Refusal('SIGCHLD must be default for direct-child custody')
    if len(list(Path('/proc/self/task').iterdir()))!=1:
        raise Refusal('single-threaded admitted caller required before fork')
    if type(wall_cap) not in (int,float) or not math.isfinite(wall_cap) or not 0<wall_cap<=30:
        raise Refusal('bounded per-entry cap')
    remaining=check_clock(authority_clock)
    stop_mono=min(authority_clock['started_at_monotonic']+authority_clock['original_seconds']
                  -authority_clock['cleanup_seconds'],time.monotonic()+min(remaining,wall_cap))
    stop_unix=min(authority_clock['useful_deadline_unix'],time.time()+wall_cap)
    final_mono=min(authority_clock['started_at_monotonic']+authority_clock['original_seconds'],stop_mono+5)
    final_unix=min(authority_clock['final_deadline_unix'],stop_unix+5)
    request={'caller':caller,'helper':helper_pin,'entry':entry,'descriptor':descriptor,
             'clock_pin':clock_ref,'authority_clock':authority_clock,
             'evidence':str(evidence),'fixture_root':None if fixture_root is None else str(fixture_root),
             'stop_monotonic':stop_mono,'stop_unix':stop_unix,
             'final_monotonic':final_mono,'final_unix':final_unix,
             'sum_hard_AS_bytes':2*AS,'outside_deadline_through_actual_caller_exit':True}
    # Trusted capability supplies authority; same-byte comparisons below supply
    # consistency only. They cannot prove issuer, admission, or kernel stop.
    lease=owner.require_authority(request)
    if lease is None or isinstance(lease,(bool,int,float,str,bytes,dict,list,tuple,set)):
        raise Refusal('existing owner lease required; a primitive/JSON grant is insufficient')
    c=Custody(owner,lease,caller,authority_clock,stop_mono,stop_unix,final_mono,final_unix)
    try:owner.hold(lease,c)  # Before open attempt FDs or children.
    except BaseException as exc:
        c.fault('owner_hold',exc);c.state='STOP_UNCONFIRMED'
        try:owner.pending(lease,c)
        except BaseException as notify:c.fault('owner_pending',notify)
        raise StopUnconfirmed(c) from exc
    try:
        captured_clock=read_pin(clock_ref,LIMIT,custody=c)
        if json.loads(captured_clock)!=authority_clock: raise Refusal('historical clock authority mismatch')
        if helper_pin is None or helper_pin['path']!=__file__:raise Refusal('exact admitted helper pin required')
        read_pin(helper_pin,custody=c)
        check_clock(authority_clock)
        e=Path(evidence)
        if not e.is_absolute() or '..' in e.parts or str(e)!=os.path.normpath(str(e)):
            raise Refusal('absolute canonical evidence path required')
        for parent in reversed(e.parents):
            if not stat.S_ISDIR(parent.lstat().st_mode):raise Refusal('evidence ancestor')
        if e.parent.stat().st_uid!=os.getuid() or e.parent.stat().st_mode & 0o077:
            raise Refusal('private evidence parent')
        e.mkdir(mode=0o700)  # Attempt evidence existence => refusal, never replay.
        parentfd=c.track('parent_dir',os.open(e.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
        os.fsync(parentfd);c.close_fd('parent_dir')
        if c.fd_errors:raise Refusal('parent directory close uncertain before fork')
        dfd=c.track('evidence',os.open(e,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
        directory_identity=(os.fstat(dfd).st_dev,os.fstat(dfd).st_ino)
        def append(name,value):
            st=e.lstat()
            if (st.st_dev,st.st_ino)!=directory_identity:raise Refusal('helper evidence inode changed')
            raw=(json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode()
            if len(raw)>LIMIT:raise Refusal('helper evidence bound')
            # In child the external scope owns teardown too; caller never imports
            # entry code. Register this FD before any fallible write/fsync.
            fd=c.track('evidence_leaf',os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                                             0o400,dir_fd=dfd))
            try:
                offset=0
                while offset<len(raw):
                    count=os.write(fd,raw[offset:])
                    if count<=0:raise OSError('helper evidence zero write')
                    offset+=count
                os.fsync(fd)
            finally:c.close_fd('evidence_leaf')
            if c.fds.get('evidence_leaf') is not None:raise Refusal('evidence leaf close uncertain')
            os.fsync(dfd)
        c.put=append
        append('RESERVED.json',{'state':'UNKNOWN_NO_REPLAY','entry':entry,'descriptor':descriptor,
               'clock':clock_ref,'caller':caller,'stop_monotonic':stop_mono,'stop_unix':stop_unix,
               'cleanup_monotonic':final_mono,'cleanup_unix':final_unix,
               'existing_outside_owner_required':True,'capacity_release':False})
        rd,wr=os.pipe()
        # Retain BOTH handles before the first fallible fstat.
        c.fds.update({'read_pipe':rd,'write_pipe':wr})
        for name,fd in (('read_pipe',rd),('write_pipe',wr)):
            s=os.fstat(fd);c.fd_ids[name]=(s.st_dev,s.st_ino,stat.S_IFMT(s.st_mode))
        parent_pid=os.getpid()
        c.mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM,signal.SIGINT,signal.SIGTERM})
        c.mask_restored=False
        c.pid=os.fork()  # Caller+child hard512 BEFORE fork; no third process.
        if c.pid==0:
            try:
                c.close_fd('write_pipe')
                libc=ctypes.CDLL(None,use_errno=True)
                if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent_pid:os._exit(123)
                signal.pthread_sigmask(signal.SIG_SETMASK,c.mask);c.mask_restored=True
                resource.setrlimit(resource.RLIMIT_CPU,(40,40))
                worker=limits();append('WORKER-BIRTH.json',worker)
                ready=c.track('ready',os.open('BIRTH-READY',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400,dir_fd=dfd))
                c.close_fd('ready')
                if os.read(rd,1)!=b'G':os._exit(124)
                c.close_fd('read_pipe')
                def no_effect(event,args):
                    if event in {'os.fork','os.forkpty','os.posix_spawn','os.exec','os.system',
                                 'subprocess.Popen','socket.__new__','os.kill','os.killpg'}:
                        raise Refusal('entry process/network/signal effect forbidden')
                sys.addaudithook(no_effect)
                try:
                    append('WORKER-GO.json',worker);check_clock(authority_clock)
                    captured_descriptor=json.loads(read_pin(descriptor,LIMIT,custody=c))
                    if captured_descriptor.get('clock')!=clock_ref or captured_descriptor.get('source')!=entry:
                        raise Refusal('entry/descriptor/original clock binding')
                    raw=read_pin(entry,custody=c);ns={'__name__':'<bounded_installer>','__file__':entry['path']}
                    exec(compile(raw,entry['path'],'exec'),ns)
                    if fixture_root is not None:
                        fixture=Path(fixture_root)
                        if fixture==Path('/private/runtime') or not fixture.is_relative_to(e.parent):
                            raise Refusal('fixture root must be within owned evidence parent')
                        ns['R']=fixture
                    value=ns['perform'](descriptor['path'],descriptor['sha256'])
                    append('WORKER-RESULT.json',{'state':'ENTRY_RETURNED','value':value});os._exit(0)
                except BaseException as exc:
                    try:append('WORKER-RESULT.json',{'state':'UNKNOWN_NO_REPLAY',
                               'exception_class':type(exc).__name__,'detail':str(exc)[:400]})
                    except BaseException:pass
                    os._exit(2)
            except BaseException as exc:
                try:append('WORKER-RESULT.json',{'state':'UNKNOWN_NO_REPLAY','exception_class':type(exc).__name__,'detail':str(exc)[:400]})
                except BaseException:pass
                os._exit(2)
            finally:os._exit(125)  # Child never falls into parent cleanup/owner callbacks.
        c.ticks=birth(c.pid);c.track('pidfd',os.pidfd_open(c.pid))
        signal.pthread_sigmask(signal.SIG_SETMASK,c.mask);c.mask_restored=True
        c.close_fd('read_pipe')
        while not (e/'BIRTH-READY').exists():
            if time.monotonic()>=stop_mono or time.time()>=stop_unix:raise Deadline('before GO deadline')
            got=c.wait_once()
            if got is False:raise Refusal('direct wait uncertain before GO')
            if got is True:raise Refusal('worker ended before GO')
            select.select([],[],[],0.01)
        c.worker=json.loads((e/'WORKER-BIRTH.json').read_bytes())
        if (c.worker['pid']!=c.pid or c.worker['birth']!=c.ticks or c.worker['AS']!=[AS,AS]
                or c.worker['affinity']!=caller['affinity'] or c.worker['CORE']!=[0,0]):
            raise Refusal('worker birth/resources')
        owner.before_go(lease,c)
        append('BEFORE-GO.json',{'caller':caller,'worker':c.worker,'sum_hard_AS_bytes':2*AS,
               'hard_bound_before_fork':True,'outside_owner_retained':True})
        if time.monotonic()>=stop_mono or time.time()>=stop_unix:raise Deadline('GO useful deadline')
        os.write(wr,b'G');c.close_fd('write_pipe');c.state='WORKER_RUNNING'
        while True:
            got=c.wait_once()
            if got is True:break
            if got is False:raise Refusal('direct wait uncertain after GO')
            if time.monotonic()>=stop_mono or time.time()>=stop_unix:raise Deadline('entry deadline')
            select.select([],[],[],0.01)
    except BaseException as exc:
        c.failure={'class':type(exc).__name__,'detail':str(exc)[:400]};c.timed_out=isinstance(exc,Deadline)
    # No finally raw-wait path. All fallible cleanup retains c with its existing
    # owner. No signal handler/timer is installed or cancelled by this helper.
    try:return c.finish()
    except StopUnconfirmed:raise
    except BaseException as exc:
        c.fault('unexpected_cleanup',exc);c.state='STOP_UNCONFIRMED'
        try:owner.pending(lease,c)
        except BaseException as notify:c.fault('owner_pending',notify)
        raise StopUnconfirmed(c) from exc
