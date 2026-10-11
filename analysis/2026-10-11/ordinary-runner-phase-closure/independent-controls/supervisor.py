import datetime, hashlib, json, os, pathlib, resource, select, subprocess, sys, time
O=pathlib.Path(__file__).parent
clock=json.loads((O/'CLOCK.json').read_text())
def birth(pid):
    try:
        t=pathlib.Path(f'/proc/{pid}/stat').read_text();return int(t[t.rfind(')')+2:].split()[19])
    except FileNotFoundError:return None
def save(n,d):
    p=O/n;p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');p.chmod(0o600)
def ref(p):
    b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
cpus=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,cpus)
resource.setrlimit(resource.RLIMIT_AS,(96*1024**2,1024**3));resource.setrlimit(resource.RLIMIT_CPU,(15,60));resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
environment={'supervisor':{'pid':os.getpid(),'start_ticks':birth(os.getpid())},'available_affinity':sorted(os.sched_getaffinity(0)),'max_aggregate_AS_bytes':864*1024**2,'clock':ref(O/'CLOCK.json'),'admitted_source_controls':False}
for p in ['/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/memory.max','/sys/fs/cgroup/memory.current','/proc/pressure/cpu','/proc/pressure/io','/proc/pressure/memory']:
    try:environment[p]=pathlib.Path(p).read_text().strip()
    except OSError as e:environment[p]={'unknown':str(e)}
save('RESOURCE-ENVIRONMENT.json',environment)
child=subprocess.Popen([sys.executable,'-I','-B',str(O/'controls.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
resource.setrlimit(resource.RLIMIT_AS,(96*1024**2,96*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
pid=child.pid;start=birth(pid);admitted=False;failure=None
try:
    timeout=min(10,max(.01,clock['useful_deadline_unix']-time.time()))
    if not select.select([child.stdout],[],[],timeout)[0]:raise RuntimeError('helper_ready_timeout')
    ready=json.loads(child.stdout.readline());assert ready['pid']==pid and ready['start_ticks']==start
    assert ready['affinity']==cpus and ready['AS_bytes']==[768*1024**2]*2 and ready['CPU_seconds']==[45]*2 and ready['file_size_bytes']==[8*1024**2]*2
    assert ready['children']==[] and ready['threads']==['MainThread']
    assert time.time()<clock['useful_deadline_unix']
    admission={'worker':{'pid':pid,'start_ticks':start},'actual_ready':ready,'controls':ref(O/'controls.py'),'supervisor':ref(O/'supervisor.py'),'clock':ref(O/'CLOCK.json'),'approved_affinity':cpus,'aggregate_AS_bytes':864*1024**2,'aggregate_output_bytes':16*1024**2,'source_only_inert_fixture':True,'runtime_grant':False,'admitted_unix':time.time()}
    supervisor_caps={'pid':os.getpid(),'start_ticks':birth(os.getpid()),'affinity':sorted(os.sched_getaffinity(0)),'AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),'file_size_bytes':list(resource.getrlimit(resource.RLIMIT_FSIZE))}
    assert supervisor_caps['AS_bytes']==[96*1024**2]*2 and supervisor_caps['CPU_seconds']==[15]*2 and supervisor_caps['affinity']==cpus
    assert supervisor_caps['AS_bytes'][1]+ready['AS_bytes'][1]==864*1024**2<=1024**3
    admission['actual_supervisor_caps_before_GO']=supervisor_caps
    admission['repeat_because']='First complete controls run did not serialize actual supervisor getrlimit caps before GO; mandatory aggregate resource witness, same source and original clock, no inherited execution credit'
    save('HELPER-ADMISSION.json',admission);admitted=True
    child.stdin.write('ADMITTED\n');child.stdin.flush()
    stdout,stderr=child.communicate(timeout=min(180,max(.01,clock['useful_deadline_unix']-time.time())))
    (O/'HELPER-STDOUT.txt').write_text(stdout);(O/'HELPER-STDERR.txt').write_text(stderr)
except BaseException as e:
    failure=type(e).__name__+':'+str(e)
    if child.poll() is None and birth(pid)==start:child.terminate()
    try:stdout,stderr=child.communicate(timeout=min(3,max(.01,clock['hard_deadline_unix']-time.time())))
    except subprocess.TimeoutExpired:
        if child.poll() is None and birth(pid)==start:child.kill()
        stdout,stderr=child.communicate(timeout=max(.01,clock['hard_deadline_unix']-time.time()))
    (O/'HELPER-STDOUT.txt').write_text(stdout);(O/'HELPER-STDERR.txt').write_text(stderr)
finally:
    kids=pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()
    save('HELPER-CLOSURE.json',{'worker':{'pid':pid,'start_ticks':start},'admitted':admitted,'exit_code':child.returncode,'wait_completed':child.poll() is not None,'fresh_start_ticks':birth(pid),'exact_birth_absent':birth(pid) is None,'supervisor_children':kids,'failure':failure,'closed_unix':time.time(),'runtime_grant':False})
    print(json.dumps({'exit_code':child.returncode,'failure':failure,'exact_birth_absent':birth(pid) is None,'children':kids}))
