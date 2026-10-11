"""Owned serial processes; kernel inherited HARD proof at fork and before GO.
SOURCE roles: launcher384->128, worker384, reader384->192 MiB.
Maximum named fork transient896 MiB; steady704 MiB. No hard limit raise.
Host caller/TUI, unknown descendants and cgroup admission are outside this proof.
"""
import os,sys,pathlib,resource,subprocess,signal,select,json,time,hashlib
if sys.flags.optimize:raise SystemExit('REFUSED: SOURCE requires Python assertions enabled')
MIB=1024**2

def validate_clock(clock, *, require_live=True):
 # Preserve caller original start and minimum deadlines. No new budget is made.
 assert isinstance(clock,dict),'clock must be a caller object'
 for k in ('actual_task_started_unix','actual_task_started_monotonic','original_seconds','cleanup_seconds','useful_monotonic','final_monotonic'):
  assert type(clock[k]) in (int,float) and __import__('math').isfinite(clock[k]),'invalid clock number'
 start=clock['actual_task_started_monotonic'];useful=clock['useful_monotonic'];final=clock['final_monotonic']
 assert clock['original_seconds']>clock['cleanup_seconds']>=120,'caller cleanup reserve too small'
 assert start<useful<final<=start+clock['original_seconds']+.000001,'caller original deadline exceeded'
 assert final-useful>=clock['cleanup_seconds']-.000001,'caller cleanup deadline exceeded'
 if require_live:
  assert start<=time.monotonic(),'caller original start is in the future'
  assert time.monotonic()<useful,'caller original useful deadline expired'
 return clock

def birth(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None

def save(root,name,value):
 b=(json.dumps(value,indent=2)+'\n').encode();assert len(b)<=65536
 p=pathlib.Path(root)/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(0o400)

def hard(pid):return resource.prlimit(pid,resource.RLIMIT_AS)[1]

def proof(clock,child=None,parent_start=False):
 root=clock['launcher'];assert birth(root['pid'])==root['birth']
 ids=[root['pid']]
 if os.getpid()!=root['pid']:
  assert os.getppid()==root['pid'];ids.append(os.getpid())
 if child is not None:ids.append(child)
 caps=[hard(p) for p in ids];assert all(c>=0 for c in caps)
 assert sum(caps)<=896*MIB,(caps,'SOURCE topology above896MiB')
 assert all(sorted(os.sched_getaffinity(p))==clock['shared_cpus'] for p in ids)
 return {'named_process_HARD_AS_bytes':dict(zip(map(str,ids),caps)),
 'aggregate_HARD_AS_bytes':sum(caps),'bound_bytes':896*MIB,'shared_affinity':clock['shared_cpus'],
 'actual_kernel_read':True,'unobserved_descendants':'UNKNOWN_NOT_ADMITTED'}

STUB=r"""
import os,sys,json,resource,signal
rf,gf=int(sys.argv[1]),int(sys.argv[2]);cmd=json.loads(sys.argv[3]);target=int(sys.argv[4]);cpu=int(sys.argv[5]);wall=float(sys.argv[6])
signal.alarm(max(1,int(wall)))
b=open('/proc/self/stat').read().rsplit(')',1)[1].split()[19]
def note(phase):
 os.write(rf,(json.dumps({'pid':os.getpid(),'birth':b,'phase':phase,'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),'affinity':sorted(os.sched_getaffinity(0)),'command_executed':False})+'\n').encode())
note('BIRTH_INHERITED_HARD_BEFORE_LOWER')
if os.read(gf,1)!=b'L':sys.exit(91)
resource.setrlimit(resource.RLIMIT_AS,(target,target));resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
note('READY_BEFORE_GO');os.close(rf)
if os.read(gf,1)!=b'G':sys.exit(92)
os.close(gf);os.execvpe(cmd[0],cmd,os.environ)
"""

def note(fd,timeout):
 assert select.select([fd],[],[],max(.01,timeout))[0],'inert readiness timeout'
 # Each phase writes a single small line and waits for the corresponding token.
 return json.loads(os.read(fd,8192))

def run_owned(clock,cmd,root,name,target=192*MIB,cpu=30,env=None,data=None,launcher=False):
 assert time.monotonic()<clock['useful_monotonic'];wall=min(60,clock['useful_monotonic']-time.monotonic()) if not launcher else clock['useful_monotonic']-time.monotonic()
 assert hard(os.getpid())==384*MIB,'parent must be hard384 BEFORE fork'
 parent_before={'pid':os.getpid(),'birth':birth(os.getpid()),'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'actual_limits':pathlib.Path('/proc/self/limits').read_text(),'affinity':sorted(os.sched_getaffinity(0))}
 pre=proof(clock);assert pre['aggregate_HARD_AS_bytes']+384*MIB<=896*MIB
 rr,rw=os.pipe();gr,gw=os.pipe();p=subprocess.Popen([sys.executable,'-B','-c',STUB,str(rw),str(gr),json.dumps(cmd),str(target),str(cpu),str(wall)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,pass_fds=(rw,gr),start_new_session=True)
 os.close(rw);os.close(gr);bd=birth(p.pid);out=b'';err=b'';released=False
 row={'pid':p.pid,'birth':bd,'operation':cmd[0],'fork_parent_before':parent_before,'kernel_fork_inheritance_bound_bytes':pre['aggregate_HARD_AS_bytes']+384*MIB,'no_preexec_limit_transition':True}
 try:
  b=note(rr,min(5,wall));assert b['birth']==bd and b['AS']==[384*MIB]*2
  bp=proof(clock,p.pid);save(root,name+'-BIRTH.json',{**row,'child_inherited':b,'actual_birth_phase_HARD':bp,'before_child_lower':True,'inference':'Kernel fork inherits preobserved hard384; child did not change AS before birth barrier. Original host process creation outside admitted SOURCE boundary.'})
  if launcher:
   resource.setrlimit(resource.RLIMIT_AS,(128*MIB,)*2);resource.setrlimit(resource.RLIMIT_CPU,(120,120))
  os.write(gw,b'L');ready=note(rr,min(5,wall));os.close(rr);rr=-1
  assert ready['AS']==[target]*2 and ready['CPU']==[cpu]*2 and ready['FSIZE']==[64*MIB]*2 and ready['affinity']==clock['shared_cpus']
  gp=proof(clock,p.pid);save(root,name+'-PREGO.json',{**row,'ready':ready,'actual_aggregate_HARD':gp,'before_GO':True,'actual_limits':pathlib.Path(f'/proc/{p.pid}/limits').read_text()})
  assert birth(p.pid)==bd and time.monotonic()<clock['useful_monotonic'];os.write(gw,b'G');os.close(gw);gw=-1;released=True
  out,err=p.communicate(input=data,timeout=min(wall+2,clock['final_monotonic']-time.monotonic()))
 finally:
  if rr>=0:os.close(rr)
  if gw>=0:os.close(gw)
  if p.returncode is None:
   if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGTERM)
   try:out,err=p.communicate(timeout=3)
   except subprocess.TimeoutExpired:
    if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGKILL)
    out,err=p.communicate(timeout=3)
  row.update(returncode=p.returncode,directwait=True,fresh_birth=birth(p.pid),exact_birth_absent=birth(p.pid)!=bd,released_GO=released,stdout_bytes=len(out),stdout_sha256=hashlib.sha256(out).hexdigest(),stderr_bytes=len(err),stderr_sha256=hashlib.sha256(err).hexdigest())
  save(root,name+'-CLOSED.json',row);assert row['exact_birth_absent']
 return out,err,row

def aggregate_proof(clock,worker_pid,reader_pid=None):
 assert worker_pid==os.getpid()
 return proof(clock,reader_pid)
