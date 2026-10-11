"""Bounded one-shot supervisor. Reproduction writes only to a fresh OUTPUT.

CLOCK is assignment acceptance, never reset by this runner. Each worker receives
one readiness pipe barrier so PID/start is captured before source execution.
"""
import os, sys, json, time, signal, resource, subprocess, hashlib, pathlib, threading

OUT = pathlib.Path(__file__).resolve().parent
PYTHON = sys.executable

def dump(path, value):
    with open(OUT/path, 'x') as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write('\n')

def children():
    return pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()

def fdstate():
    result={}
    for name in os.listdir('/proc/self/fd'):
        try: result[name]=os.readlink('/proc/self/fd/'+name)
        except FileNotFoundError: pass
    return result

def identity(path):
    p=pathlib.Path(path); s=p.lstat()
    if p.is_symlink() or not p.is_file(): raise RuntimeError('not_regular: '+str(p))
    read_mode='O_NOATIME'
    try: fd=os.open(p,os.O_RDONLY|os.O_NOATIME)
    except PermissionError:
        read_mode='O_RDONLY_root_owned_fallback'
        fd=os.open(p,os.O_RDONLY)
    with os.fdopen(fd,'rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p),sha256=h,bytes=s.st_size,mode=oct(s.st_mode & 0o7777),dev=s.st_dev,
                ino=s.st_ino,uid=s.st_uid,gid=s.st_gid,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,
                ctime_ns=s.st_ctime_ns,atime_ns=s.st_atime_ns,read_mode=read_mode)

def main():
    resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,768*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(60,65))
    cpu=min(os.sched_getaffinity(0)); os.sched_setaffinity(0,{cpu})
    name=sys.argv[1]; worker=OUT/(name+'.py')
    candidate=sys.argv[2];native=sys.argv[3]
    clock=json.loads((OUT/'CLOCK.json').read_text())
    remaining=(clock['original_deadline_monotonic_ns']-time.monotonic_ns())/1e9
    if remaining<5: raise RuntimeError('original_assignment_budget_exhausted')
    before=dict(fds=fdstate(),threads=[t.name for t in threading.enumerate()],children=children())
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL'}}
    env.update(HOME=str(OUT/'inert-home'),HERMES_HOME=str(OUT/'inert-home'),
               XDG_CONFIG_HOME=str(OUT/'inert-home'),PYTHONDONTWRITEBYTECODE='1',
               OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    def bound():
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU,(40,45))
        resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
        os.setsid()
    start=time.monotonic_ns(); killed=False
    with open(OUT/(name+'.stdout'),'xb') as stdout, open(OUT/(name+'.stderr'),'xb') as stderr:
        p=subprocess.Popen([PYTHON,'-I','-B',str(worker),'--candidate',candidate,'--native',native],cwd=OUT,env=env,stdin=subprocess.PIPE,
                           stdout=stdout,stderr=stderr,preexec_fn=bound,close_fds=True)
        stat=pathlib.Path(f'/proc/{p.pid}/stat').read_text(); ticks=int(stat.rsplit(')',1)[1].split()[19])
        record=dict(pid=p.pid,start_ticks=ticks,worker=identity(worker),cpu_affinity=[cpu],
                    address_space_bytes=768*1024**2,original_clock=clock['start_monotonic_ns'],
                    wall_timeout_seconds=min(90,max(1,remaining-60)),stdin_barrier=True)
        dump(name+'-START.json',record)
        p.stdin.write(b'execute\n');p.stdin.flush();p.stdin.close()
        try: code=p.wait(timeout=record['wall_timeout_seconds'])
        except subprocess.TimeoutExpired:
            current=pathlib.Path(f'/proc/{p.pid}/stat').read_text()
            if int(current.rsplit(')',1)[1].split()[19]) != ticks: raise RuntimeError('pid_reuse')
            os.killpg(p.pid,signal.SIGKILL); killed=True; code=p.wait(timeout=10)
    after=dict(fds=fdstate(),threads=[t.name for t in threading.enumerate()],children=children())
    closure=dict(exit_code=code,elapsed_seconds=(time.monotonic_ns()-start)/1e9,
                 exact_pid=p.pid,exact_start_ticks=ticks,wait_reaped=True,
                 proc_identity_absent=not pathlib.Path(f'/proc/{p.pid}').exists(),killed=killed,
                 before=before,after=after,zero_fd_thread_child_drift=before==after,
                 whole_process_peak_rss='UNKNOWN',child_rusage_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    dump(name+'-EXECUTION.json',closure)
    print(json.dumps(closure))
    if code or killed or before!=after: sys.exit(1)

if __name__=='__main__': main()
