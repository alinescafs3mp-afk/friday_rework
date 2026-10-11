"""INERT author controls; NOT_RUN until distinct Root host/caller admission.

No loader, CLI, fake authority owner, supervisor, thread, network, or auto-run.
The already admitted exact host injects the SAME-READ pinned helper and genuine
existing owner into one AS256 single-threaded caller. Helper forks one AS256
worker, serialized. Host validates caller exit/whole cohort closure outside.
An inside observation is never independent acceptance or caller-final closure.
"""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import types

CASES = (
    'positive', 'duplicate_evidence', 'missing_owner', 'incomplete_owner',
    'SIGCHLD_IGN', 'SIGCHLD_custom', 'before_GO_denial',
    'entry_flock_stop', 'descriptor_flock_stop', 'result_fsync_flock_stop',
    'wait_EIO_after_kill', 'wait_EIO_after_durable_result',
    'wait_zero_until_final', 'pending_notification_EIO',
    'caller_final_close_flock', 'caller_owner_unwound_flock',
)


def reference(path):
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def write(path, value, mode=0o400):
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


class Proxy:
    """Module-local faults; never patch global os used by the actual Root host."""
    def __init__(self, original, **changes):self.original=original;self.changes=changes
    def __getattr__(self, name):return self.changes.get(name,getattr(self.original,name))


class ObserveOwner:
    """Delegation only. No grant minting or default enforcer implementation."""
    def __init__(self, actual, *, deny_go=False, fail_pending=False, unwind=None):
        self.actual=actual;self.handle=None;self.held=False;self.pending_seen=False
        self.deny_go=deny_go;self.fail_pending=fail_pending;self.unwind=unwind
    def require_authority(self, request):return self.actual.require_authority(request)
    def hold(self, lease, c):
        self.actual.hold(lease,c);self.handle=c;self.held=True
    def before_go(self, lease, c):
        if self.deny_go:raise RuntimeError('owned test before-GO denial')
        return self.actual.before_go(lease,c)
    def pending(self, lease, c):
        self.pending_seen=True
        if self.fail_pending:raise OSError(errno.EIO,'owned test notification failure')
        return self.actual.pending(lease,c)
    def helper_unwound(self, lease, c):
        if self.unwind:self.unwind()
        return self.actual.helper_unwound(lease,c)


def execute(case, H, genuine_owner, helper_pin, authority_clock, clock_ref, case_root,
            *, outside_stall_path=None):
    """One physical synthetic case in the distinct already guarded host caller.

    Root must independently admit exact caller + controls + helper closure BEFORE
    importing/executing these bytes. ALL returned states are author observations.
    Outside stall cases EXPECT caller termination and require OUTSIDE assertions;
    they cannot return PASS from inside. Pending wait cases intentionally retain
    real custody and block next admission until Root confirms original cleanup.
    """
    if case not in CASES:raise ValueError('unknown control')
    root=Path(case_root)
    if not root.is_absolute() or '..' in root.parts:raise ValueError('absolute owned fixture')
    # Only a fresh own fixture supplied by the actual existing host, no live R.
    if not root.is_relative_to(Path(__file__).resolve().parent.parent):
        raise ValueError('fixture outside exact new C28 private output')
    root.mkdir(mode=0o700)
    parent=os.getpid();lock=root/'owned-stall.lock';holder=None
    marker=root/'ENTRY-DURABLE.json';e=root/'attempt'
    entry=root/'entry.py';desc=root/'descriptor.json'
    text=('import json\nfrom pathlib import Path\n'
          'def perform(p,sha):\n'
          ' d=json.loads(Path(p).read_bytes())\n'
          ' Path(d["marker"]).write_text("PRIVATE_SYNTHETIC_DURABLE_MARKER")\n'
          ' return {"state":"PRIVATE_SYNTHETIC_ENTRY_RETURNED"}\n')
    write(entry,text.encode())
    write(desc,{'source':reference(entry),'clock':clock_ref,'marker':str(marker)})
    entry_ref=reference(entry);desc_ref=reference(desc)
    original_os=H.os;original_signal=H.signal;original_pin=H.read_pin
    owner=ObserveOwner(genuine_owner,deny_go=case=='before_GO_denial',
                       fail_pending=case=='pending_notification_EIO')
    killed=False
    def block_on(path):
        write(root/'PHYSICAL-STALL-REACHED.json',{'case':case,'pid':os.getpid(),
              'birth':H.birth(os.getpid()),'path':str(path)})
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        try:fcntl.flock(fd,fcntl.LOCK_EX)
        finally:os.close(fd)
    if case in ('entry_flock_stop','descriptor_flock_stop','result_fsync_flock_stop',
                'wait_EIO_after_kill','wait_zero_until_final','pending_notification_EIO'):
        write(lock,b'',0o600);holder=os.open(lock,os.O_RDWR);fcntl.flock(holder,fcntl.LOCK_EX)
    def pin(ref,*args,**kw):
        target=desc_ref['path'] if case=='descriptor_flock_stop' else entry_ref['path']
        if os.getpid()!=parent and holder is not None and ref['path']==target and case!='result_fsync_flock_stop':
            block_on(lock)
        return original_pin(ref,*args,**kw)
    def kill(*args,**kw):
        nonlocal killed
        result=signal.pidfd_send_signal(*args,**kw);killed=True;return result
    def wait(pid, flags):
        own=(os.getpid()==parent and owner.handle is not None and pid==owner.handle.pid)
        if own and case in ('wait_EIO_after_kill','pending_notification_EIO') and killed:
            raise OSError(errno.EIO,'owned direct-wait EIO')
        if own and case=='wait_EIO_after_durable_result' and (e/'WORKER-RESULT.json').exists():
            raise OSError(errno.EIO,'owned durable-result direct-wait EIO')
        if own and case=='wait_zero_until_final' and killed:return 0,0
        return os.waitpid(pid,flags)
    def sync(fd):
        if (os.getpid()!=parent and case=='result_fsync_flock_stop'
                and os.readlink('/proc/self/fd/'+str(fd))==str(e/'WORKER-RESULT.json')):
            block_on(lock)
        return os.fsync(fd)
    def outside_block():
        if outside_stall_path is None:raise ValueError('Root-held physical stall fixture required')
        path=Path(outside_stall_path)
        if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(Path(__file__).resolve().parent.parent):
            raise ValueError('outside stall must be exact new C28 private fixture')
        block_on(path)
        raise AssertionError('outside guardian failed: stalled caller resumed')
    def close(fd):
        if (case=='caller_final_close_flock' and os.getpid()==parent
                and owner.handle is not None and fd==owner.handle.fds.get('evidence')
                and (e/'DIRECT-WAIT-CLOSURE.json').exists()):outside_block()
        return os.close(fd)
    if case=='caller_owner_unwound_flock':owner.unwind=outside_block
    H.os=Proxy(os,waitpid=wait,fsync=sync,close=close)
    H.signal=Proxy(signal,pidfd_send_signal=kill)
    H.read_pin=pin
    previous_chld=signal.getsignal(signal.SIGCHLD)
    try:
        if case=='SIGCHLD_IGN':signal.signal(signal.SIGCHLD,signal.SIG_IGN)
        if case=='SIGCHLD_custom':signal.signal(signal.SIGCHLD,lambda *_:None)
        supplied_owner=owner
        if case=='missing_owner':supplied_owner=None
        if case=='incomplete_owner':supplied_owner=types.SimpleNamespace(require_authority=owner.require_authority)
        try:
            result=H.run(entry_ref,desc_ref,clock_ref,authority_clock,e,owner=supplied_owner,
                         helper_pin=helper_pin,fixture_root=root,wall_cap=.12 if holder is not None else 2)
        except H.Refusal as exc:
            if case not in ('missing_owner','incomplete_owner','SIGCHLD_IGN','SIGCHLD_custom'):raise
            assert not e.exists() and owner.handle is None
            return {'inside_observation':'REFUSED_BEFORE_ATTEMPT','case':case,'detail':str(exc),
                    'caller_outer_closure':'MUST_BE_OBSERVED_BY_ROOT'}
        except H.StopUnconfirmed as exc:
            if case not in ('wait_EIO_after_kill','wait_EIO_after_durable_result',
                            'wait_zero_until_final','pending_notification_EIO'):raise
            c=exc.custody
            assert owner.held and c is owner.handle and c.fds.get('pidfd') is not None
            assert c.state=='STOP_UNCONFIRMED' and not c.waited and owner.pending_seen
            if holder is not None:assert (root/'PHYSICAL-STALL-REACHED.json').exists()
            os.fstat(c.fds['pidfd'])  # Real retained open identity, not just a PID receipt.
            if case=='wait_EIO_after_durable_result':
                assert marker.exists() and c.worker_result['state']=='ENTRY_RETURNED'
                assert c.snapshot()['attempt_outcome']=='UNKNOWN_NO_REPLAY'
            return {'inside_observation':'PENDING_CUSTODY_RETAINED','case':case,
                    'custody':c.snapshot(),'same_registered_object':True,
                    'next_admission':'BLOCKED_UNTIL_EXISTING_ROOT_CONFIRMED_CLOSURE',
                    'caller_outer_closure':'MUST_BE_OBSERVED_BY_ROOT'}
        if case.startswith('caller_'):raise AssertionError('outside final-stall control returned')
        assert result['direct_wait'] and result['fresh_birth_absent']
        assert result['retained_fds']=={} and result['mask_restored'] and not result['capacity_release']
        if case in ('positive','duplicate_evidence'):
            assert result['returncode']==0 and marker.exists()
            assert result['attempt_outcome']=='ENTRY_RETURN_OBSERVED_NOT_OUTER_ACCEPTANCE'
            if case=='duplicate_evidence':
                before={p.name:p.read_bytes() for p in e.iterdir()}
                again=H.run(entry_ref,desc_ref,clock_ref,authority_clock,e,owner=owner,
                            helper_pin=helper_pin,fixture_root=root,wall_cap=2)
                assert again['known_pid'] is None and again['failure']['class']=='FileExistsError'
                assert before=={p.name:p.read_bytes() for p in e.iterdir()}
        elif case=='before_GO_denial':
            assert result['returncode']==-9 and not marker.exists()
            assert not (e/'WORKER-GO.json').exists()
        else:
            assert (root/'PHYSICAL-STALL-REACHED.json').exists()
            assert result['returncode']==-9 and result['timed_out']
            assert result['attempt_outcome']=='UNKNOWN_NO_REPLAY'
        return {'inside_observation':'EXPECTED_HELPER_OBSERVATION','case':case,'custody':result,
                'caller_outer_closure':'MUST_BE_OBSERVED_BY_ROOT','independent_acceptance':False}
    finally:
        # No release of a retained pending child/pidfd, and no Root admission reset.
        H.os=original_os;H.signal=original_signal;H.read_pin=original_pin
        signal.signal(signal.SIGCHLD,previous_chld)
        if holder is not None:fcntl.flock(holder,fcntl.LOCK_UN);os.close(holder)
