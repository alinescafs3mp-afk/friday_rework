"""Finite source fixture runner: fresh CLOCK, exact pre-effect worker hash and PID/start barrier."""
import hashlib,json,os,resource,signal,subprocess,sys,threading,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
def write(name,data):
 with open(OUT/name,'x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
def identity(pid):return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
def alive(pid,ticks):
 try:return identity(pid)==ticks
 except FileNotFoundError:return False
def state():
 fds={}
 for n in os.listdir('/proc/self/fd'):
  try:fds[n]=os.readlink('/proc/self/fd/'+n)
  except FileNotFoundError:pass
 return {'fds':fds,'threads':[t.name for t in threading.enumerate()],'children':Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()}
profile=sys.argv[1];source_args=sys.argv[2:]
clock=json.loads((OUT/'CLOCK.json').read_text())
deadline=clock['monotonic']+clock['original_seconds'];cleanup=clock['cleanup_seconds']
remaining=deadline-time.monotonic()
if remaining<=cleanup+5:raise RuntimeError('original_cleanup_boundary_reached')
cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,65))
before=state();spid=os.getpid();sticks=identity(spid)
def bound():
 os.sched_setaffinity(0,{cpu});resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(40,45));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));os.setsid()
home=OUT/('inert-home-'+profile);home.mkdir(mode=0o700)
env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(home),'HERMES_HOME':str(home),'XDG_CONFIG_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
worker=OUT/'native_worker.py';digest=hashlib.file_digest(worker.open('rb'),'sha256').hexdigest()
started=time.monotonic();killed=False;error=None;cleanup_error=None;p=None;ticks=None;code=None
with open(OUT/(profile+'.stdout'),'xb') as stdout,open(OUT/(profile+'.stderr'),'xb') as stderr:
 try:
  p=subprocess.Popen([sys.executable,'-I','-B',str(worker),'--profile',profile]+source_args,cwd=OUT,env=env,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,preexec_fn=bound,close_fds=True)
  ticks=identity(p.pid);timeout=min(90,max(1,remaining-cleanup))
  write(profile+'-START.json',{'supervisor_pid':spid,'supervisor_start_ticks':sticks,'pid':p.pid,'start_ticks':ticks,'worker_sha256':digest,'interpreter':sys.executable,'worker_AS_bytes':768*1024**2,'supervisor_AS_bytes':128*1024**2,'affinity':[cpu],'readiness':'stdin execute barrier; only sys import/readline before release; interpreter bootstrap earlier unmeasured','effective_deadline_monotonic':deadline,'timeout_seconds':timeout})
  p.stdin.write(b'execute\n');p.stdin.flush();p.stdin.close();code=p.wait(timeout=timeout)
 except BaseException as e:error=repr(e)
 finally:
  if p is not None:
   if p.stdin and not p.stdin.closed:p.stdin.close()
   if p.poll() is None:
    try:
     if ticks is None:raise RuntimeError('STOP_UNCONFIRMED: worker PID/start not captured')
     if alive(p.pid,ticks):os.killpg(p.pid,signal.SIGKILL);killed=True
     code=p.wait(timeout=10)
    except BaseException as e:cleanup_error=repr(e)
after=state()
rec={'pid':p.pid if p else None,'start_ticks':ticks,'supervisor_pid':spid,'supervisor_start_ticks':sticks,'exit_code':code,'error':error,'cleanup_error':cleanup_error,'killed':killed,'wait_reaped':p is not None and p.returncode is not None,'proc_identity_absent':ticks is not None and not alive(p.pid,ticks),'elapsed_seconds':time.monotonic()-started,'before':before,'after':after,'FD_thread_child_closed':before==after,'child_rusage_peak_rss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'whole_tree_peak_rss':'UNKNOWN'}
write(profile+'-EXECUTION.json',rec);print(json.dumps(rec))
if error or cleanup_error or code or killed or before!=after:sys.exit(1)
