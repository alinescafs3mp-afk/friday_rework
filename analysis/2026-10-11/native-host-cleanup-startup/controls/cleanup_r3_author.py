import os, sys, resource, time, json, ast, types, select, hashlib
from pathlib import Path

O = Path(__file__).parent
os.umask(0o077)
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (2*1024**2, 2*1024**2))
birth = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
def put(name, value):
    fd=os.open(O/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
clock_record=json.loads((O.parent/'CLOCK.json').read_text())
put('AUTHOR-PREGO.json',{'pid':os.getpid(),'start':birth,'affinity':sorted(os.sched_getaffinity(0)),
    'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'RLIMIT_CPU':resource.getrlimit(resource.RLIMIT_CPU),
    'parent_original_clock':clock_record,'single_process_no_subprocess':True,'before_controls':True})
print(json.dumps({'PREGO_PID':os.getpid(),'start':birth}),flush=True)
assert select.select([sys.stdin],[],[],10)[0] and sys.stdin.readline().strip()=='GO'
assert time.time()<clock_record['useful_deadline_unix']
source=O/'source/native_host_adapter.py'
raw=source.read_bytes();tree=ast.parse(raw)
h={'os':os,'time':time,'math':__import__('math'),'MAX_CPU':2,'MAX_MEMORY':1024**3}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))],type_ignores=[]),str(source),'exec'),h)
tests=[]
def check(name, value):tests.append({'name':name,'passed':value is True})
def error(fn):
    try:fn()
    except BaseException as e:return e
    return None
check('actual_source_admission_stays_unbound',isinstance(error(h['require_native_admission']),h['Unbound']))
# Only inert exact-body namespaces use dependency fixtures. No native capability.
h['require_native_admission']=lambda:None
ns=types.SimpleNamespace
for fail_signal, fail_wait, fail_unit in ((False,False,False),(True,False,False),(False,True,False),(True,True,False),(True,True,True)):
    events=[]
    clock=ns(remaining=lambda **k:60.0,cleanup_seconds=60)
    host=object.__new__(h['FiniteNativeHostAdapter']);host._owned=object();host.clock=clock
    child=object.__new__(h['KernelChild']);child.owner=host._owned;child.clock=clock;child.closed=False;child.pidfd=5
    child._launch_identity=(42,os.getpid(),'1',(0,));child.process=ns(pid=42,poll=lambda:None)
    def wait(**k):
        events.append('wait')
        if fail_wait:raise TimeoutError('WAIT_FAIL')
        return -9
    child.wait=wait
    envelope=object.__new__(h['IndependentlyHeldUnitEnvelope'])
    def stop():
        events.append('unitstop')
        if fail_unit:raise PermissionError('UNIT_FAIL')
    envelope.stop=stop;host._outside_unit_envelope=envelope
    def send(*a):
        events.append('signal')
        if fail_signal:raise PermissionError('SIGNAL_FAIL')
    h['signal']=ns(SIGKILL=9,pidfd_send_signal=send)
    e=error(lambda:host.stop_owned_returned_child_before_original_final_deadline(child))
    check('independent_stop_order:'+str((fail_signal,fail_wait,fail_unit)),events==['signal','unitstop','wait'])
    failures=fail_signal+fail_wait+fail_unit
    check('all_causes_retained:'+str((fail_signal,fail_wait,fail_unit)),
        e is None if not failures else isinstance(e,h['StopUnconfirmed']) and len(e.cleanup_errors)==failures)
# A permitted long wait cannot starve a stop already performed before wait.
remaining=[60.0];events=[];host.clock=ns(remaining=lambda **k:remaining[0],cleanup_seconds=60);child.clock=host.clock
child.wait=lambda **k:events.append('wait') or remaining.__setitem__(0,3.1)
envelope.stop=lambda:events.append('unitstop')
h['signal']=ns(SIGKILL=9,pidfd_send_signal=lambda *a:events.append('signal'))
e=error(lambda:host.stop_owned_returned_child_before_original_final_deadline(child))
check('late_successful_wait_does_not_starve_unitstop',e is None and events==['signal','unitstop','wait'] and remaining[0]==3.1)

# Kernel cgroup parser and owner membership checks execute exact source bodies.
for actual, rejected in (('/owned/job.service',True),('/owned/job.service/child',True),('/owned/job.serviceX',False),('/other',False),('/',False)):
    h['read_kernel_identity_component']=lambda p:{'pid':p,'start_token':'1'}
    h['read_kernel_cgroup_component']=lambda p:actual
    e=error(lambda:h['require_owner_outside_group'](os.getpid(),'/owned/job.service'))
    check('actual_owner_membership:'+actual,(e is not None)==rejected)
original_reader=h['read_kernel_cgroup_component']
# Recompile the actual parser, replacing only its proc read primitives.
parser=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_kernel_cgroup_component')
exec(compile(ast.Module(body=[parser],type_ignores=[]),str(source),'exec'),h)
for value,rejected in ((b'0::/outside\n',False),(b'0::/\n',False),(b'0::/a/../b\n',True),(b'0::/a//b\n',True),(b'0::/a\n0::/b\n',True),(b'1:cpu:/a\n',True),(b'\xff',True)):
    h['os']=ns(O_RDONLY=0,O_CLOEXEC=0,O_NOFOLLOW=0,open=lambda *a:5,read=lambda *a:value,close=lambda *a:None)
    e=error(lambda:h['read_kernel_cgroup_component'](42))
    check('strict_unified_cgroup:'+repr(value),(e is not None)==rejected)
check('source_native_effects_unqualified', 'raise Unbound' in raw.decode() and 'UNBOUND_NATIVE_INTERPRETER_ELF_LOADER_STARTUP_HELD_PROVENANCE' in raw.decode())
put('AUTHOR-CONTROLS.json',{'passed':sum(t['passed'] for t in tests),'failed':sum(not t['passed'] for t in tests),
    'tests':tests,'source_sha256':hashlib.sha256(raw).hexdigest(),'source_only':True,'inert_dependency_fixtures':True,
    'native_effects':0,'runtime_credit':0,'old_author_deadline_limitation_retained':True})
put('AUTHOR-EXIT.json',{'pid':os.getpid(),'start':birth,'control_exit_code':0 if all(t['passed'] for t in tests) else 1,
    'finished_unix':time.time(),'within_parent_useful':time.time()<clock_record['useful_deadline_unix'],'descendants':[]})
print(json.dumps({'passed':sum(t['passed'] for t in tests),'failed':sum(not t['passed'] for t in tests)}),flush=True)
sys.exit(0 if all(t['passed'] for t in tests) else 1)
