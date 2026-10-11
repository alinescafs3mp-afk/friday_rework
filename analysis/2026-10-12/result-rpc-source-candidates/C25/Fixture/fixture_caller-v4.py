"""Finite private review adapter; never an installed or production authority.

Root must approve these exact bytes before use. Stock host subprocess.wait timeout is the outside
physical guard; this adapter owns the real mutable custody until reconciliation.
"""
import os, sys, time, json, hashlib, resource, signal, stat, types, errno, fcntl, ctypes
from pathlib import Path

OUT = Path(__file__).resolve().parent
AS = 268435456
def birth(pid):
    return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
def pin(path):
    raw=Path(path).read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def put(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def limits(pid='self'):
    return Path('/proc/'+str(pid)+'/limits').read_text()
def procstat(pid):
    raw=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'ppid':int(raw[1]),'pgid':int(raw[2]),'sid':int(raw[3]),'birth':raw[19]}
def fds():
    rows={}
    for p in Path('/proc/self/fd').iterdir():
        try: rows[p.name]=os.readlink(p)
        except FileNotFoundError:pass
    return rows
def load(ref):
    raw=Path(ref['path']).read_bytes()
    assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
    module=types.ModuleType('<private_source_review>');module.__file__=ref['path']
    exec(compile(raw,ref['path'],'exec'),module.__dict__)
    return module

class Lease: pass
class ActualFixtureOwner:
    """An admitted finite fixture capability, not installed authority.

    The actual stock outside direct-wait host and existing timeout120 retain the
    caller scope; this live registry retains custody before fork and through EIO.
    """
    def __init__(self,cfg,clock,helper_ref):
        self.cfg=cfg;self.clock=clock;self.helper_ref=helper_ref
        self.lease=Lease();self.registry=[];self.events=[]
        self.guard=procstat(os.getppid());self.caller=procstat(os.getpid())
        assert self.guard['pid']==cfg['host']['pid']
        assert self.guard['birth']==cfg['host']['birth']
        assert self.guard['pgid']==self.caller['pgid']==cfg['outer_guard']['pgid']
        assert birth(cfg['host']['pid'])==cfg['host']['birth']
        cmd=Path('/proc/'+str(self.guard['pid'])+'/cmdline').read_bytes()
        assert cfg['host_program']['path'].encode() in cmd
        assert pin(cfg['host_program']['path'])==cfg['host_program']
        assert birth(cfg['outer_guard']['pid'])==cfg['outer_guard']['birth']
        assert cfg['guard_deadline_monotonic'] <= clock['started_at_monotonic']+1020
    def require_authority(self,request):
        assert request['helper']==self.helper_ref and request['authority_clock']==self.clock
        assert request['caller']['pid']==os.getpid() and request['caller']['birth']==birth(os.getpid())
        assert request['sum_hard_AS_bytes']==2*AS
        assert self.cfg['guard_deadline_monotonic'] <= request['final_monotonic']
        assert time.monotonic()<self.cfg['guard_deadline_monotonic']
        assert birth(self.guard['pid'])==self.guard['birth']
        for key in ('entry','descriptor'):
            ref=request[key];assert Path(ref['path']).is_relative_to(Path(self.cfg['case_root']))
            assert pin(ref['path'])==ref
        assert Path(request['evidence']).is_relative_to(Path(self.cfg['case_root']))
        assert request['clock_pin']==pin(OUT/'CLOCK.json')
        # A previous completed helper does not release caller scope. Pending
        # custody prohibits even another helper attempt in this same caller.
        assert not any(c.state=='STOP_UNCONFIRMED' for c in self.registry)
        self.events.append({'event':'require_authority','actual_guard':self.guard,'caller':self.caller})
        return self.lease
    def hold(self,lease,c):
        assert lease is self.lease and c.pid is None and not c.fds
        self.registry.append(c)
        self.events.append({'event':'hold','object_identity':id(c),'before_fork':True})
    def before_go(self,lease,c):
        assert lease is self.lease and any(c is held for held in self.registry)
        st=procstat(c.pid);assert st['ppid']==os.getpid() and st['birth']==c.ticks
        assert st['pgid']==self.guard['pgid']
        assert c.worker['AS']==[AS,AS] and c.caller['AS']==[AS,AS]
        actual=limits(c.pid);assert '268435456' in actual
        os.fstat(c.fds['pidfd']);os.fstat(c.fds['evidence'])
        assert time.monotonic()<self.cfg['guard_deadline_monotonic']
        self.events.append({'event':'before_GO','worker':st,'actual_limits':actual})
    def pending(self,lease,c):
        assert lease is self.lease and any(c is held for held in self.registry)
        self.events.append({'event':'pending','snapshot':c.snapshot(),'capacity_release':False})
    def helper_unwound(self,lease,c):
        assert lease is self.lease and any(c is held for held in self.registry)
        self.events.append({'event':'helper_unwound','caller_scope_still_held':True})
    def reconcile(self):
        # Same object/child only. No re-execution, no replacement lease/clock.
        rows=[]
        for c in self.registry:
            before=c.snapshot()
            if c.pid is not None and not c.waited:
                fd=c.fds.get('pidfd')
                if fd is not None:
                    signal.pidfd_send_signal(fd,signal.SIGKILL)
                got,status=os.waitpid(c.pid,0)
                assert got==c.pid;c.status=status;c.waited=True
                c.child_absent=c.ticks!=birth(c.pid) if Path('/proc/'+str(c.pid)).exists() else True
            for name in list(c.fds):c.close_fd(name)
            assert all(v is None for v in c.fds.values()) and not c.fd_errors
            assert c.mask_restored and (c.pid is None or (c.waited and c.child_absent))
            rows.append({'before':before,'after':c.snapshot(),'same_object':True,'independent_real_directwait':True})
        return rows

def main():
    cfg=json.loads(Path(sys.argv[1]).read_bytes());clock=json.loads((OUT/'CLOCK.json').read_bytes())
    parent_pid=os.getppid();libc=ctypes.CDLL(None,use_errno=True)
    assert libc.prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==parent_pid
    root=Path(cfg['case_root']);basefds=fds()
    assert resource.getrlimit(resource.RLIMIT_AS)==(AS,AS)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(60,60)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(67108864,67108864)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    assert list(sorted(os.sched_getaffinity(0)))==[0,1]
    owner=ActualFixtureOwner(cfg,clock,cfg['helper'])
    put(Path(cfg['case_record'])/'CALLER-BEFORE-IMPORT.json',{'caller':procstat(os.getpid()),'guard':owner.guard,
        'limits':limits(),'affinity':sorted(os.sched_getaffinity(0)),'fds':basefds,
        'external_deadline':cfg['guard_deadline_monotonic'],'root_authority':'exact Root admission outside this object; fixture only'})
    if cfg['case']=='independent_bootstrap_stall':
        put(Path(cfg['case_record'])/'PREIMPORT-STALL-REACHED.json',{'pid':os.getpid(),'birth':birth(os.getpid())})
        fd=os.open(cfg['outside_stall_path'],os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
        raise AssertionError('outside bootstrap guard failed')
    H=load(cfg['helper'])
    if cfg['case'].startswith('independent_'):
        result=independent(cfg,H,owner,clock)
    else:
        C=load(cfg['controls'])
        result=C.execute(cfg['case'],H,owner,cfg['helper'],clock,pin(OUT/'CLOCK.json'),root,
            outside_stall_path=cfg['outside_stall_path'])
    put(Path(cfg['case_record'])/'INSIDE-OBSERVATION.json',result)
    closure=owner.reconcile()
    finalfds=fds();assert finalfds==basefds,(basefds,finalfds)
    put(Path(cfg['case_record'])/'CALLER-RETURN-PREPARED.json',{'closure':closure,'events':owner.events,
        'fd_baseline':basefds,'fd_final':finalfds,'actual_caller_exit':'requires outside directwait; not claimed inside'})

def independent(cfg,H,owner,clock):
    case=cfg['case'];root=Path(cfg['case_root']);root.mkdir(mode=0o700)
    entry=root/'entry.py';desc=root/'descriptor.json';e=root/'attempt';marker=root/'durable.txt'
    raw=('from pathlib import Path\nimport json\ndef perform(p,s):\n d=json.loads(Path(p).read_bytes())\n Path(d["marker"]).write_text("INDEPENDENT_REAL_DURABLE")\n return {"independent":True}\n').encode()
    fd=os.open(entry,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400);os.write(fd,raw);os.close(fd)
    put(desc,{'source':pin(entry),'clock':pin(OUT/'CLOCK.json'),'marker':str(marker)})
    actual_os=H.os;actual_finish=H.Custody.finish;actual_close=H.Custody.close_fd
    if case=='independent_owner_denial':
        def denied(request):raise PermissionError('independent actual owner refuses')
        owner.require_authority=denied
    if case=='independent_hold_EIO':
        oldhold=owner.hold
        def hold(lease,c):oldhold(lease,c);raise OSError(errno.EIO,'independent pre-fork registration response failure')
        owner.hold=hold
    if case=='independent_durable_wait_EIO':
        class FaultOS:
            def __getattr__(self,n):return getattr(os,n)
            def waitpid(self,pid,flags):
                if (e/'WORKER-RESULT.json').exists():raise OSError(errno.EIO,'independent result is not wait')
                return os.waitpid(pid,flags)
        H.os=FaultOS()
    if case=='independent_final_evidence_close_stall':
        def close(c,name):
            if name=='evidence' and c.state=='HELPER_TEARDOWN':
                put(root/'INDEPENDENT-STALL-REACHED.json',{'pid':os.getpid(),'birth':birth(os.getpid()),'phase':'final_evidence_close'})
                fd=os.open(cfg['outside_stall_path'],os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
                raise AssertionError('outside guard failed')
            return actual_close(c,name)
        H.Custody.close_fd=close
    if case=='independent_before_GO_live_cohort_stall':
        actual_before_go=owner.before_go
        def before_go(lease,c):
            actual_before_go(lease,c)
            put(root/'INDEPENDENT-STALL-REACHED.json',{'pid':os.getpid(),'birth':birth(os.getpid()),
                'phase':'before_GO_live_caller_and_worker','worker':c.worker,'live_custody':c.snapshot()})
            fd=os.open(cfg['outside_stall_path'],os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
            raise AssertionError('outside whole-cohort guard failed')
        owner.before_go=before_go
    if case=='independent_callback_stall':
        def unwind(lease,c):
            put(root/'INDEPENDENT-STALL-REACHED.json',{'pid':os.getpid(),'birth':birth(os.getpid()),'phase':'owner_callback'})
            fd=os.open(cfg['outside_stall_path'],os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
            raise AssertionError('outside guard failed')
        owner.helper_unwound=unwind
    try:
        try:
            result=H.run(pin(entry),pin(desc),pin(OUT/'CLOCK.json'),clock,e,
                owner=None if case=='independent_missing_owner' else owner,helper_pin=cfg['helper'],fixture_root=root,wall_cap=2)
        except H.Refusal as exc:
            assert case=='independent_missing_owner' and not e.exists() and not owner.registry
            return {'independent_observation':'refused_missing_owner','detail':str(exc)}
        except PermissionError as exc:
            assert case=='independent_owner_denial' and not e.exists() and not owner.registry
            return {'independent_observation':'real_owner_denial_before_fork','detail':str(exc)}
        except H.StopUnconfirmed as exc:
            assert case in ('independent_durable_wait_EIO','independent_hold_EIO')
            c=exc.custody;assert any(c is r for r in owner.registry)
            assert c.state=='STOP_UNCONFIRMED' and not c.waited
            if case=='independent_durable_wait_EIO':
                assert marker.exists() and c.worker_result['state']=='ENTRY_RETURNED'
                os.fstat(c.fds['pidfd']);os.fstat(c.fds['evidence'])
                assert c.snapshot()['attempt_outcome']=='UNKNOWN_NO_REPLAY'
            else:assert c.pid is None and not e.exists()
            return {'independent_observation':'same_live_custody_retained','custody':c.snapshot()}
        assert case=='independent_positive',case
        assert result['returncode']==0 and result['direct_wait'] and result['fresh_birth_absent'] and marker.exists()
        assert result['retained_fds']=={} and not result['capacity_release']
        return {'independent_observation':'real_positive','custody':result}
    finally:
        H.os=actual_os;H.Custody.finish=actual_finish;H.Custody.close_fd=actual_close

if __name__=='__main__':main()
