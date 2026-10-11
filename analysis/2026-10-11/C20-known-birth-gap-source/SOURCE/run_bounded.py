"""Fork one576MiB inert worker before lowering ownHARD to128MiB.
Child never raises inherited hard limits; no prlimit escalation is used.
Serial stages and one192MiB reader => actual aggregateHARD896MiB.
"""
import os,sys,json,time,pathlib,resource,signal,select,subprocess,hashlib,traceback
W=pathlib.Path(__file__).parent;os.umask(0o077);CPUS=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,CPUS)
CLOCK=json.loads((W/'CLOCK.json').read_text());assert time.monotonic()<CLOCK['useful_monotonic']
def birth(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
def save(n,j):
 b=(json.dumps(j,indent=2)+'\n').encode();assert len(b)<=65536
 p=W/n
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(0o400)
CLOCK.update(launcher={'pid':os.getpid(),'birth':birth(os.getpid()),'hard_AS_bytes':128*1024**2},shared_cpus=CPUS)
save('EXECUTION-CLOCK.json',CLOCK)
stub="import os,sys,json,resource,signal;signal.alarm(max(1,int(float(sys.argv[4]))));os.write(int(sys.argv[1]),json.dumps({'pid':os.getpid(),'birth':open('/proc/self/stat').read().rsplit(')',1)[1].split()[19],'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),'affinity':sorted(os.sched_getaffinity(0)),'before_GO':True}).encode());os.close(int(sys.argv[1]));assert os.read(int(sys.argv[2]),1)==b'G';os.close(int(sys.argv[2]));os.execv(sys.executable,[sys.executable,'-B',sys.argv[3]])"
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(576*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.sched_setaffinity(0,CPUS)
rr,rw=os.pipe();gr,gw=os.pipe();p=subprocess.Popen([sys.executable,'-B','-c',stub,str(rw),str(gr),str(W/'pipeline_worker.py'),str(CLOCK['useful_monotonic']-time.monotonic())],stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(rw,gr),preexec_fn=limits,start_new_session=True)
os.close(rw);os.close(gr);bd=birth(p.pid);out=b'';err=b''
resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(120,120));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
try:
 assert select.select([rr],[],[],5)[0];ready=json.loads(os.read(rr,65536));os.close(rr);rr=-1
 assert ready['birth']==bd and ready['AS']==[576*1024**2]*2 and ready['affinity']==CPUS and ready['FSIZE']==[64*1024**2]*2
 assert resource.prlimit(p.pid,resource.RLIMIT_AS)==(576*1024**2,)*2
 save('LAUNCHER-WORKER-PREGO.json',{'launcher':CLOCK['launcher'],'worker':{'pid':p.pid,'birth':bd},'ready':ready,'actual_worker_limits':pathlib.Path(f'/proc/{p.pid}/limits').read_text(),'actual_launcher_limits':pathlib.Path('/proc/self/limits').read_text(),'shared_CPUs':CPUS,'actual_two_process_HARD_AS_bytes':704*1024**2,'maximum_with_one_reader_HARD_AS_bytes':896*1024**2,'before_GO':True,'worker_source_sha256':hashlib.sha256((W/'pipeline_worker.py').read_bytes()).hexdigest()})
 assert birth(p.pid)==bd and time.monotonic()<CLOCK['useful_monotonic'];os.write(gw,b'G');os.close(gw);gw=-1
 out,err=p.communicate(timeout=max(1,CLOCK['useful_monotonic']-time.monotonic()+3))
except BaseException as e:
 save('LAUNCHER-FAILURE.json',{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc(),'original_clock_unchanged':True})
 raise
finally:
 if rr>=0:os.close(rr)
 if gw>=0:os.close(gw)
 if p.returncode is None:
  if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGTERM)
  try:out,err=p.communicate(timeout=3)
  except subprocess.TimeoutExpired:
   if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGKILL)
   out,err=p.communicate(timeout=3)
 save('PIPELINE-DIRECT-CLOSED.json',{'launcher':CLOCK['launcher'],'pid':p.pid,'birth':bd,'returncode':p.returncode,'directwait':True,'fresh_birth':birth(p.pid),'exact_birth_absent':birth(p.pid)!=bd,'stdout_bytes':len(out),'stdout_sha256':hashlib.sha256(out).hexdigest(),'stderr_bytes':len(err),'stderr_sha256':hashlib.sha256(err).hexdigest(),'stdout_preview':out[-6000:].decode(errors='replace'),'stderr_preview':err[-5000:].decode(errors='replace'),'all_named_source_HARD_bound':896*1024**2,'elapsed_from_original_TASK':time.time()-CLOCK['actual_task_started_unix']})
print(out.decode(errors='replace'));print(err.decode(errors='replace'),file=sys.stderr)
raise SystemExit(p.returncode)
