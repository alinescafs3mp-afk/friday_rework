#!/usr/bin/python3
"""INACTIVE source primitives; host startup/import custody is not supplied here."""
import os, stat, sys, json, hashlib, time, math, signal
from pathlib import Path

HOST_CUSTODY = None

class BoundaryRefusal(RuntimeError):
    pass

def require(condition, reason):
    if condition is not True:
        raise BoundaryRefusal(reason)

def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(type(k) is str and exact(a[k], b[k]) for k in a)
    if type(a) in (tuple, list): return len(a) == len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a == b

def strict_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise BoundaryRefusal('DUPLICATE_RELEASE_MEMBER')
            out[k]=v
        return out
    # JSON's shortest-roundtrip binary64 representation retains the exact original
    # monotonic deadline. Integers stay integers; nonfinite/overflow tokens refuse.
    def finite_float(token):
        value=float(token)
        require(math.isfinite(value),'NONFINITE_RELEASE_NUMERIC_TOKEN')
        return value
    def bad(v): raise BoundaryRefusal('NONFINITE_RELEASE_NUMERIC_TOKEN')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float, parse_constant=bad)

def dir_identity(st):
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)]

def file_identity(st):
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_nlink,
            stat.S_IMODE(st.st_mode), st.st_size, st.st_mtime_ns, st.st_ctime_ns]

class SecureDirectory:
    """Retain every ancestor FD; verify its FD and its name relative to its parent."""
    def __init__(self, path, expected=None):
        raw=os.fspath(path); self.rows=[]; self.closed=False
        require(raw.startswith('/') and raw==str(Path(raw)) and '..' not in raw.split('/'), 'NONCANONICAL_PARENT')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
            self.rows.append((fd,None,None,dir_identity(os.fstat(fd))))
            for name in Path(raw).parts[1:]:
                parent=self.rows[-1][0]
                fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                self.rows.append((fd,parent,name,dir_identity(os.fstat(fd))))
            self.path=Path(raw); self.fd=self.rows[-1][0]; self.identity=self.rows[-1][3]
            if expected is not None: require(exact(self.identity,expected),'RESERVED_ROOT_IDENTITY_DRIFT')
            self.verify()
        except BaseException:
            self.close(); raise
    def verify(self):
        require(not self.closed,'CLOSED_PARENT_CUSTODY')
        for fd,parent,name,identity in self.rows:
            st=os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid in (0,os.getuid()) and not st.st_mode&0o022,'UNSAFE_PARENT')
            require(exact(dir_identity(st),identity),'PARENT_FD_IDENTITY_DRIFT')
            if parent is not None:
                named=os.stat(name,dir_fd=parent,follow_symlinks=False)
                require(stat.S_ISDIR(named.st_mode) and exact(dir_identity(named),identity),'PARENT_NAMED_IDENTITY_DRIFT')
        return self.identity
    def close(self):
        if not self.closed:
            for fd,_,_,_ in reversed(self.rows): os.close(fd)
            self.closed=True
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

class VerifiedBytes:
    """A single bounded no-follow FD read; execution retains and rechecks that custody."""
    def __init__(self,path,expected_sha=None,max_bytes=1048576,mode=None,parent_identity=None):
        self.path=Path(path); self.fd=None; self.parent=None; self.closed=False
        require(type(max_bytes) is int and 0<max_bytes<=128*1024**2,'INVALID_BOUND')
        self.max_bytes=max_bytes
        try:
            self.parent=SecureDirectory(self.path.parent,parent_identity)
            self.fd=os.open(self.path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=self.parent.fd)
            st=os.fstat(self.fd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and not st.st_mode&(0o022|stat.S_ISUID|stat.S_ISGID),'UNSAFE_SOURCE_FILE')
            if mode is not None: require(stat.S_IMODE(st.st_mode)==mode,'SOURCE_MODE_REQUIRED')
            require(st.st_size<=max_bytes,'BOUNDED_SOURCE_SIZE')
            self.identity=file_identity(st); self.raw=self._read_fd()
            self.sha256=hashlib.sha256(self.raw).hexdigest()
            if expected_sha is not None: require(exact(self.sha256,expected_sha),'VERIFIED_SOURCE_SHA_DRIFT')
            self.verify()
        except BaseException:
            self.close(); raise
    def _read_fd(self):
        pieces=[]; size=0
        while True:
            part=os.pread(self.fd,min(65536,self.max_bytes+1-size),size)
            if not part: break
            pieces.append(part); size+=len(part)
            require(size<=self.max_bytes,'BOUNDED_SOURCE_READ')
        return b''.join(pieces)
    def verify(self):
        require(not self.closed,'CLOSED_SOURCE_CUSTODY'); self.parent.verify()
        fd_st=os.fstat(self.fd); named=os.stat(self.path.name,dir_fd=self.parent.fd,follow_symlinks=False)
        require(stat.S_ISREG(named.st_mode) and exact(file_identity(fd_st),self.identity)
                and exact(file_identity(named),self.identity),'SOURCE_FD_NAMED_METADATA_DRIFT')
        require(self._read_fd()==self.raw,'VERIFIED_FD_BYTES_DRIFT')
        self.parent.verify(); require(exact(file_identity(os.fstat(self.fd)),self.identity),'SOURCE_AFTER_READ_DRIFT')
        require(exact(file_identity(os.stat(self.path.name,dir_fd=self.parent.fd,follow_symlinks=False)),self.identity),'SOURCE_AFTER_NAMED_DRIFT')
        return self.identity
    def close(self):
        if not self.closed:
            if self.fd is not None: os.close(self.fd)
            if self.parent is not None: self.parent.close()
            self.closed=True
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

def execute_verified(source,namespace):
    """No run_path/loader/pathname reread; compile and execute the verified buffer."""
    source.verify()
    code=compile(source.raw,str(source.path),'exec',dont_inherit=True,optimize=0)
    source.verify()
    exec(code,namespace)
    source.verify()
    return namespace

def require_host_custody():
    """A receipt/JSON cannot authorize startup. The existing host must bind custody."""
    require(HOST_CUSTODY is not None,'INACTIVE_HOST_INTERPRETER_IMPORT_ENV_RESOURCE_CUSTODY_UNBOUND')
    require(sys.flags.optimize==0 and sys.flags.isolated==1 and sys.flags.no_site==1,'PINNED_ISOLATED_UNOPTIMIZED_STARTUP_REQUIRED')
    HOST_CUSTODY.verify_startup_before_effects()
    HOST_CUSTODY.verify_import_graph_and_environment()
    HOST_CUSTODY.verify_aggregate_hard_resources(2,1024**3)
    return HOST_CUSTODY

def validate_release(reservation,release,identity,token,program_sha,helper_sha,root_identity,original_deadline):
    require(type(reservation) is dict and type(release) is dict,'RELEASE_OBJECT_REQUIRED')
    require(exact(reservation,release),'RELEASE_RESERVATION_BINDING_REQUIRED')
    required={'schema':'friday.native-peer-rpc.exact-prebarrier-child.v2','pid':identity['pid'],'start_token':identity['start_token'],'ppid':identity['ppid'],
              'affinity':identity['affinity'],'token':token,'program_sha256':program_sha,
              'helper_sha256':helper_sha,'root_identity':root_identity,'ready':True,
              'aggregate_AS_limit_bytes':1024**3,'aggregate_affinity':identity['affinity']}
    for key,value in required.items(): require(exact(release.get(key),value),'EXACT_PREBARRIER_BINDING_REQUIRED:'+key)
    require(type(original_deadline) in (int,float) and math.isfinite(original_deadline),
            'FINITE_TYPED_ORIGINAL_WALL_REQUIRED')
    require(exact(release.get('wall_deadline_monotonic'),original_deadline),
            'EXACT_ORIGINAL_WALL_BINDING_REQUIRED')
    require(type(release.get('wall_deadline_monotonic')) in (int,float)
            and math.isfinite(release['wall_deadline_monotonic'])
            and release['wall_deadline_monotonic']>time.monotonic(),'FINITE_ORIGINAL_WALL_REQUIRED')
    return release

def finite_cleanup_within_original120(value):
    """A boolean or unknown measurement is not a measured cleanup duration."""
    return type(value) in (int,float) and 0 <= value <= 120 and math.isfinite(value)

def exact_closure_complete(closure):
    return (type(closure) is dict and closure.get('closed') is True
            and finite_cleanup_within_original120(closure.get('cleanup_elapsed_seconds'))
            and all(closure.get(k) is True for k in
                    ('worker_reaped','process_absence','path_absence','endpoint_absence')))

def read_process_launch_identity(pid):
    """Independent kernel observation; READY/child output supplies no identity."""
    raw=Path('/proc/'+str(pid)+'/stat').read_text()
    a=raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'ppid':int(a[1]),'start_token':a[19],
            'affinity':sorted(os.sched_getaffinity(pid))}

class LaunchCustody:
    """Retain kernel pidfd and independently verify the launcher's birth tuple.

    Existing admitted launch_verified_source_held must return a direct held child
    with launch_identity acquired before it returns, independent of READY. This
    return-handle obligation is UNBOUND until the existing host is qualified.
    No new host method or installed controller is provided by this source.
    """
    def __init__(self,child):
        self.fd=None;self.closed=False
        try:
            claimed=getattr(child,'launch_identity',None)
            require(type(claimed) is dict and set(claimed)=={'pid','ppid','start_token','affinity'},
                    'STOP_UNCONFIRMED_LAUNCH_CUSTODY_UNBOUND')
            pid=claimed['pid'];birth=claimed['start_token'];affinity=claimed['affinity']
            approved=sorted(os.sched_getaffinity(0))
            require(type(pid) is int and pid>1 and exact(pid,child.pid)
                    and type(claimed['ppid']) is int and claimed['ppid']==os.getpid()
                    and type(birth) is str and birth.isdecimal()
                    and type(affinity) is list and 0<len(affinity)<=2
                    and all(type(x) is int and x>=0 for x in affinity)
                    and sorted(set(affinity))==affinity and 0<len(approved)<=2
                    and set(affinity)<=set(approved),'STOP_UNCONFIRMED_LAUNCH_IDENTITY_INVALID')
            require(exact(read_process_launch_identity(pid),claimed),'STOP_UNCONFIRMED_LAUNCH_PID_BIRTH_DRIFT')
            self.fd=os.pidfd_open(pid,0)
            require(exact(read_process_launch_identity(pid),claimed),'STOP_UNCONFIRMED_LAUNCH_PID_BIRTH_DRIFT')
            self.identity={k:(list(v) if type(v) is list else v) for k,v in claimed.items()}
        except BaseException:
            self.close();raise
    def bind_ready(self,ready):
        require(type(ready) is dict and all(exact(ready.get(k),v) for k,v in self.identity.items()),
                'READY_LAUNCH_KERNEL_CUSTODY_BINDING_REQUIRED')
        require(exact(read_process_launch_identity(self.identity['pid']),self.identity),
                'STOP_UNCONFIRMED_LAUNCH_PID_BIRTH_DRIFT')
    def close(self):
        if not self.closed:
            if self.fd is not None:os.close(self.fd)
            self.closed=True

def signal_exact(pid,start_token,sig,readproc,send=None):
    """Recheck process birth immediately before every TERM/KILL; never broad kill."""
    current=readproc(pid)
    if current is None: return False
    require(type(pid) is int and pid>1 and exact(current['start'],start_token),'STOP_UNCONFIRMED_PID_BIRTH_DRIFT')
    if send is not None:
        # Inert fixture observer only; the admitted host uses kernel PID custody.
        send(pid,sig)
        return True
    fd=os.pidfd_open(pid,0)
    try:
        current=readproc(pid)
        require(current is not None and exact(current['start'],start_token),'STOP_UNCONFIRMED_PID_BIRTH_DRIFT')
        signal.pidfd_send_signal(fd,sig,None,0)
        return True
    finally:
        os.close(fd)

def compatibility_pass(observation):
    """Persisted PASS alone is never success; all fields are actual supervisor observations."""
    truth=('actual_exit0','worker_reaped','ready_validated','inventory_before_go','pid_birth_validated',
           'host_custody_admitted','affinity_validated','resources_within_budget','useful_deadline_met',
           'final_deadline_met','cleanup_within_original120','process_closure_closed','fresh_receipt_validated','fresh_result_validated',
           'exact_final_process_absence','exact_final_path_absence','exact_final_endpoint_absence')
    return (all(observation.get(k) is True for k in truth)
            and type(observation.get('worker_returncode')) is int and observation['worker_returncode']==0
            and observation.get('validator_verdict')=='PASS' and observation.get('resource_stop') is None
            and observation.get('cleanup_escalation_needed') is False)

class CleanupUnconfirmed(BoundaryRefusal):
    def __init__(self, primary, errors, closure):
        self.primary_error = primary
        self.cleanup_errors = tuple(errors)
        self.closure = closure
        super().__init__('STOP_UNCONFIRMED:' + repr([(stage, type(exc).__name__, str(exc)) for stage, exc in errors]))

def cleanup_returned_child(host, child, custody, primary=None, hard_deadline=None):
    """Stop and fresh outside observation are independent, with the original clock.

    No secondary pidfd or READY failure discards the host's retained ownership.
    An unknown owner is never converted into a PID signal or successful closure.
    """
    errors = []; closure = None; identity = None
    try:
        if custody is None:
            identity = host.retained_owned_launch_identity(child)
            host.stop_owned_returned_child_before_original_final_deadline(child)
        else:
            identity = custody.identity
            host.stop_reap_exact_before_original_final_deadline(child, identity)
    except BaseException as exc:
        errors.append(('stop_owned_returned', exc))
    finally:
        try:
            # This method observes; it must never repeat the failed stop.
            closure = host.fresh_owned_returned_absence(child, identity, hard_deadline=hard_deadline)
            if not exact_closure_complete(closure):
                errors.append(('fresh_witness', BoundaryRefusal('STOP_UNCONFIRMED_FRESH_CLOSURE')))
        except BaseException as exc:
            errors.append(('fresh_witness', exc))
    if errors:
        raise CleanupUnconfirmed(primary, errors, closure) from primary
    return closure
