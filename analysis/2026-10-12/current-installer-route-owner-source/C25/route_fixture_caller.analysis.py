"""Finite stock caller adapting Root's existing v4/v5 fixture; no issuer object.
Exact Root admission BEFORE execution required. One caller256 + one worker256.
"""
import os,sys,time,json,hashlib,signal,resource,ctypes,types,select
from pathlib import Path
OUT=Path(__file__).absolute().parent
AS=268435456
def identity(pid):
    s=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'birth':s[19],'ppid':int(s[1]),'pgid':int(s[2]),'sid':int(s[3])}
def put(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def capture(ref):
    p=Path(ref['path']);before=p.lstat();fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);assert (before.st_dev,before.st_ino,before.st_ctime_ns)==(st.st_dev,st.st_ino,st.st_ctime_ns)
        assert st.st_size<=1048576 and st.st_uid==os.getuid() and st.st_nlink==1 and not st.st_mode&0o077
        raw=os.read(fd,1048577);after=os.fstat(fd);named=p.lstat()
        assert (st.st_dev,st.st_ino,st.st_ctime_ns,st.st_mtime_ns,st.st_size)==(after.st_dev,after.st_ino,after.st_ctime_ns,after.st_mtime_ns,after.st_size)==(named.st_dev,named.st_ino,named.st_ctime_ns,named.st_mtime_ns,named.st_size)
    finally:os.close(fd)
    assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
    return raw
def load(ref,raw):
    module=types.ModuleType('<private_route_source>');module.__file__=ref['path']
    exec(compile(raw,ref['path'],'exec'),module.__dict__);return module
def main():
    cfg=json.loads(Path(sys.argv[1]).read_bytes());rec=Path(cfg['record']);clock=json.loads(capture(cfg['clock']))
    assert capture(cfg['host_program']) and capture(cfg['caller'])
    assert identity(os.getppid())==cfg['host'] and identity(cfg['outer']['pid'])==cfg['outer']
    assert time.monotonic()<cfg['deadline_monotonic']<=clock['started_at_monotonic']+1020-3
    assert resource.getrlimit(resource.RLIMIT_AS)==(AS,AS)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(60,60)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(67108864,67108864)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0) and sorted(os.sched_getaffinity(0))==[0,1]
    libc=ctypes.CDLL(None,use_errno=True);parent=os.getppid()
    assert libc.prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==parent
    caller=identity(os.getpid());put(rec/'CALLER-BEFORE-FORK.json',{'caller':caller,'limits':Path('/proc/self/limits').read_text()})
    source=capture(cfg['source']);controls=capture(cfg['controls'])
    # No Source execute in caller. Child inherits actual hard AS before fork/GO.
    rd,wr=os.pipe();pid=os.fork()
    if pid==0:
        os.close(wr);parent=os.getppid()
        assert libc.prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==parent
        worker=identity(os.getpid());put(rec/'WORKER-BIRTH.json',{'worker':worker,'AS':list(resource.getrlimit(resource.RLIMIT_AS))})
        assert os.read(rd,1)==b'G';os.close(rd)
        try:
            cohort={'sol':{'tui':{'pid':caller['pid'],'birth':caller['birth']},'backend':{'pid':worker['pid'],'birth':worker['birth']}},
                    'astra':{'tui':{'pid':cfg['outer']['pid'],'birth':cfg['outer']['birth']},'backend':{'pid':cfg['host']['pid'],'birth':cfg['host']['birth']}}}
            M=load(cfg['source'],source);C=load(cfg['controls'],controls)
            result=C.execute(cfg['case'],M,cfg['root'],cohort);put(rec/'INSIDE-OBSERVATION.json',result)
        except BaseException as exc:
            put(rec/'WORKER-FAILURE.json',{'class':type(exc).__name__,'message':str(exc)[:1200]});os._exit(2)
        os._exit(0)
    os.close(rd);worker=identity(pid);pfd=os.pidfd_open(pid)
    while not (rec/'WORKER-BIRTH.json').exists():
        assert time.monotonic()<cfg['deadline_monotonic']-1
        select.select([],[],[],0.001)
    child=json.loads((rec/'WORKER-BIRTH.json').read_bytes());assert child['worker']==worker and child['AS']==[AS,AS]
    put(rec/'BEFORE-GO.json',{'caller':caller,'worker':worker,'sum_hard_AS_bytes':2*AS,
         'source_same_read_pin':cfg['source'],'controls_same_read_pin':cfg['controls'],
         'actual_hard_bound_before_fork_GO':True,'outside_host_scope_held':True})
    os.write(wr,b'G');os.close(wr)
    while True:
        got,status=os.waitpid(pid,os.WNOHANG)
        if got:break
        if time.monotonic()>=cfg['deadline_monotonic']-0.5:
            signal.pidfd_send_signal(pfd,signal.SIGKILL);got,status=os.waitpid(pid,0);break
        select.select([],[],[],0.002)
    os.close(pfd);assert got==pid
    try:gone=identity(pid)['birth']!=worker['birth']
    except FileNotFoundError:gone=True
    assert gone and not Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
    code=os.waitstatus_to_exitcode(status)
    put(rec/'CALLER-DIRECT-RETURN.json',{'caller':caller,'worker':worker,'direct_wait_returncode':code,
          'worker_fresh_absent':gone,'actual_caller_exit':'outside host observes after direct return'})
    raise SystemExit(code if code>=0 else 128-code)
if __name__=='__main__':main()
