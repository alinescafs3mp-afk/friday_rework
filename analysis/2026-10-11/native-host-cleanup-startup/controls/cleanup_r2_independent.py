import os, sys, time, json, ast, hashlib, resource, select, math, types
from pathlib import Path
from datetime import datetime, timezone, timedelta

O = Path(__file__).parent
S = Path('/PORTABLE_UNBOUND/PATH_0199')
A = 1791721677.0  # first tool-observed acceptance, 15:27:57 MSK
os.umask(0o077)
os.chmod(O, 0o700)
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
MSK = timezone(timedelta(hours=3))
def put(name, value):
    p = O / name
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw); os.fsync(fd)
    finally: os.close(fd)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def birth(pid):
    try:
        tail = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
        return tail[19]
    except FileNotFoundError: return None
pid = os.getpid(); token = birth(pid)
put('CLOCK.json', {'accepted_unix': A, 'accepted_msk': datetime.fromtimestamp(A, MSK).isoformat(), 'original_seconds':600, 'cleanup_seconds':60, 'useful_deadline_unix': A+540, 'final_deadline_unix':A+600, 'root_useful_cap':1791722857.1216948,'root_final_cap':1791722977.1216948})
put('PREGO.json', {'pid':pid,'start_token':token,'recorded_unix':time.time(),'affinity':sorted(os.sched_getaffinity(0)),'observed_RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'observed_RLIMIT_CPU':resource.getrlimit(resource.RLIMIT_CPU),'observed_RLIMIT_NOFILE':resource.getrlimit(resource.RLIMIT_NOFILE),'descendants':[],'single_process_no_subprocess':True,'helper_sha256':sha(__file__)})
print(json.dumps({'PREGO':str(O/'PREGO.json'),'pid':pid,'start_token':token,'affinity':sorted(os.sched_getaffinity(0)),'AS':resource.getrlimit(resource.RLIMIT_AS)}), flush=True)
if not select.select([sys.stdin], [], [], 55)[0] or sys.stdin.readline().strip() != 'GO':
    put('HELPER-EXIT.json', {'pid':pid,'start_token':token,'exit_code':2,'reason':'NO_GO','finished_unix':time.time()}); sys.exit(2)
assert time.time() < A+540
put('GO.json', {'pid':pid,'start_token':token,'go_unix':time.time(),'original_useful_deadline':A+540})
tests=[]; counterexamples=[]
def check(name, condition, detail=None):
    tests.append({'name':name,'pass':condition is True,'detail':detail})
def counter(name, reproduced, detail):
    counterexamples.append({'name':name,'reproduced':reproduced is True,'detail':detail})
def call_error(fn):
    try: fn()
    except BaseException as e: return e
    return None
def load_defs(path, names=None, namespace=None):
    raw = Path(path).read_bytes(); tree=ast.parse(raw)
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and (names is None or n.name in names)]
    ns = {'__name__':'inert_review','__file__':str(path)} if namespace is None else namespace
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns
manifest=json.loads((S/'MANIFEST.json').read_bytes())
check('manifest_exact_pin',sha(S/'MANIFEST.json')=='382d616b21591b787c88cd40a413b79586da9801380d36781586f754fa7c3df5')
check('author_result_exact_pin',sha(S/'RESULT.json')=='6eb87694bdfdfd53f24b97f115d4cff19148d00405ed01509318111aa86d517f')
check('manifest_exact_seven_source_rows',set(manifest['source'])=={'launch_boundary.py','native_host_adapter.py','root_transaction_driver_rpc.py','run_exact_staged_rpc.py','gated_installer.py','source-final/install_native_send_rpc.py','source-final/DEPENDENCY-AUDIT.json'})
check('delta_exact_four_rows',set(manifest['delta'])=={'launch_boundary.py','native_host_adapter.py','root_transaction_driver_rpc.py','run_exact_staged_rpc.py'})
pins={}
for name,row in manifest['source'].items():
    p=Path(row['path']); orig=Path(row['original_path'])
    ok=sha(p)==row['sha256'] and p.stat().st_size==row['bytes'] and sha(orig)==row['original_sha256']
    check('exact_row:'+name,ok)
    if p.suffix=='.py': ast.parse(p.read_bytes())
    pins[name]={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'original_sha256':sha(orig)}
    if name in manifest['delta']: check('delta_row_matches_source:'+name,row==manifest['delta'][name])
put('MANIFEST.json', {'input_manifest_sha256':sha(S/'MANIFEST.json'),'input_result_sha256':sha(S/'RESULT.json'),'source':pins,'source_read_only':True,'runtime':'UNBOUND_NOT_RUN'})
b=load_defs(S/'source/launch_boundary.py',namespace={'os':os,'sys':sys,'time':time,'math':math,'json':json,'stat':__import__('stat'),'hashlib':hashlib,'Path':Path,'signal':__import__('signal'),'HOST_CUSTODY':None})
ns=types.SimpleNamespace
good={'closed':True,'worker_reaped':True,'process_absence':True,'path_absence':True,'endpoint_absence':True,'cleanup_elapsed_seconds':1.0}
primary=ValueError('ORIGINAL_READY_ERROR'); stop_error=TimeoutError('STOP_ERROR'); witness_error=RuntimeError('WITNESS_ERROR')
for custody_present in (False,True):
    for fail_stop in (False,True):
        for fail_witness in (False,True):
            events=[]
            def retained(c): events.append('retain'); return {'pid':42}
            def stop(*args):
                events.append('stop')
                if fail_stop: raise stop_error
            def witness(*args,**kwargs):
                events.append('witness')
                if fail_witness: raise witness_error
                return dict(good)
            host=ns(retained_owned_launch_identity=retained,stop_owned_returned_child_before_original_final_deadline=stop,stop_reap_exact_before_original_final_deadline=stop,fresh_owned_returned_absence=witness)
            e=call_error(lambda:b['cleanup_returned_child'](host,object(),ns(identity={'pid':42}) if custody_present else None,primary=primary))
            expected=fail_stop or fail_witness
            check(f'boundary_unconditional:{custody_present}:{fail_stop}:{fail_witness}',events.count('stop')==1 and events.count('witness')==1 and ((e is None) if not expected else isinstance(e,b['CleanupUnconfirmed']) and e.primary_error is primary and (not fail_stop or any(x is stop_error for _,x in e.cleanup_errors)) and (not fail_witness or any(x is witness_error for _,x in e.cleanup_errors))))
events=[]
host=ns(retained_owned_launch_identity=lambda c:(_ for _ in ()).throw(ValueError('UNKNOWN_OWNER')),stop_owned_returned_child_before_original_final_deadline=lambda c:events.append('signal'),fresh_owned_returned_absence=lambda *a,**k:events.append('witness') or dict(good))
e=call_error(lambda:b['cleanup_returned_child'](host,object(),None,primary=primary))
check('unknown_owner_no_signal_independent_witness',events==['witness'] and isinstance(e,b['CleanupUnconfirmed']))
for value in (True,False,None,float('nan'),float('inf'),-1,120.01,'1'):
    check('NF4_reject:'+repr(value),b['finite_cleanup_within_original120'](value) is False)
for value in (0,120,0.125): check('NF4_accept:'+repr(value),b['finite_cleanup_within_original120'](value) is True)
for value in (1,'true',None,False): check('NF4_closed_exact:'+repr(value),b['exact_closure_complete']({**good,'closed':value}) is False)
for value in (time.monotonic()+120.123456789,1.0000000000000002):
    parsed=b['strict_json'](json.dumps({'clock':value},allow_nan=False));check('NF1_binary64_roundtrip:'+repr(value),type(parsed['clock']) is float and parsed['clock'].hex()==value.hex())
for raw in ('{"v":NaN}','{"v":Infinity}','{"v":1e9999}','{"v":1,"v":2}'):
    check('NF1_strict_refusal:'+raw,call_error(lambda:b['strict_json'](raw)) is not None)
check('native_admission_remains_unbound',call_error(lambda:b['require_host_custody']()) is not None)

h=load_defs(S/'source/native_host_adapter.py',namespace={'os':os,'sys':sys,'time':time,'math':math,'signal':__import__('signal'),'select':select,'hashlib':hashlib,'subprocess':__import__('subprocess'),'stat':__import__('stat'),'MAX_CPU':2,'MAX_MEMORY':1024**3})
check('host_native_admission_remains_unbound',isinstance(call_error(h['require_native_admission']),h['Unbound']))
# Only the isolated inert namespace gate is replaced; no source mutation or live capability.
h['require_native_admission']=lambda:None
clock=ns(remaining=lambda **k:60.0,cleanup_seconds=60)
for fail_witness in (False,True):
    events=[]
    child=object.__new__(h['KernelChild']);child.process=ns(pid=42,returncode=0);child._launch_identity=(42,os.getpid(),'10',(0,));child.owner=object();child.clock=clock;child.closed=False;child.pidfd=5
    child.wait=lambda **k:events.append('wait') or 0
    native=object.__new__(h['ExistingNativeBoundary']);group=object.__new__(h['HeldCgroup'])
    def fail_native(): events.append('stop');raise stop_error
    native.stop=fail_native
    def observe():
        events.append('native')
        if fail_witness:raise witness_error
        return ns(quiescent=True)
    native.observe=observe;group.confirm_empty=lambda:events.append('group') or True
    def read(p):events.append('process');return None
    e=call_error(lambda:h['bounded_owned_cleanup_component'](child,child.launch_identity,native,group,read,clock))
    check('host_component_stop_failure_unconditional:'+str(fail_witness),events==['stop','native','group','wait','process'] and isinstance(e,h['StopUnconfirmed']) and any(x is stop_error for _,x in e.cleanup_errors) and (not fail_witness or any(isinstance(x,h['StopUnconfirmed']) for _,x in e.cleanup_errors)),events)

# Exact changed driver/supervisor functions, with inert dependency seams only.
class Context:
    def __init__(self,*a,**k):self.fd=10;self.identity=[];self.sha256='inert'
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def verify(self):pass
for filename,func in (('root_transaction_driver_rpc.py','bounded_run_once'),('run_exact_staged_rpc.py','supervisor')):
    for failure_stage in ('identity','secondary_pidfd','READY'):
        for fail_stop in (False,True):
            events=[]
            def stop(*a):
                events.append('stop')
                if fail_stop:raise stop_error
            def witness(*a,**k):events.append('witness');return dict(good)
            host=ns(reserved_root_identity=[],gated_helper_sha256='x',staged_validator_sha256='x',run_token='x',parent_final_deadline_unix=time.time()+100,parent_useful_deadline_unix=time.time()+90,launch_verified_source_held=lambda *a:ns(pid=42),retained_owned_launch_identity=lambda c:events.append('retained') or {'pid':42},stop_owned_returned_child_before_original_final_deadline=stop,stop_reap_exact_before_original_final_deadline=stop,fresh_owned_returned_absence=witness,validate_original_clock=lambda *a,**k:{'final_deadline_unix':time.time()+100,'useful_deadline_unix':time.time()+90})
            def custody(c):
                if failure_stage!='READY':raise primary
                return ns(identity={'pid':42},close=lambda:events.append('custody_close'),bind_ready=lambda r:None)
            def ready(*a):raise primary
            host.validate_actual_ready=ready
            boundary=ns(require_host_custody=lambda:host,SecureDirectory=Context,VerifiedBytes=Context,LaunchCustody=custody,cleanup_returned_child=b['cleanup_returned_child'])
            d={'source_boundary':lambda:boundary,'Path':Path,'__file__':str(S/'source'/filename),'SOURCE':Path('/inert'),'uuid':ns(uuid4=lambda:ns(hex='x')),'time':time,'CLOCK':{},'OUT':O,'sys':sys}
            load_defs(S/'source'/filename,{func},d)
            e=call_error(lambda:d[func]([],O,None,None,'x') if func=='bounded_run_once' else d[func]())
            check(f'exact_callsite:{filename}:{failure_stage}:{fail_stop}',events.count('stop')==1 and events.count('witness')==1 and ((e is primary) if not fail_stop else isinstance(e,b['CleanupUnconfirmed']) and e.primary_error is primary),events)

# Counterexample: source envelope does not prove the owner is outside the unit.
events=[]
native=object.__new__(h['ExistingNativeBoundary']);group=object.__new__(h['HeldCgroup'])
group.group='/owned/inert.service';group.invocation='a'*32;group.unit='inert.service';group.verify=lambda:events.append('verify_group');group.confirm_empty=lambda:False
native.observe=lambda:ns(main_pid=os.getpid()+1,control_group=group.group,invocation_id=group.invocation,quiescent=False)
h['read_kernel_identity_component']=lambda p:{'pid':p,'start_token':'1'}
envelope=h['IndependentlyHeldUnitEnvelope'](native,group,clock)
e=call_error(envelope.verify)
counter('outside_envelope_accepts_unproven_same_unit_nonMainPID_owner',e is None and envelope.owner_pid==os.getpid(),{'owner_pid':envelope.owner_pid,'main_pid':os.getpid()+1,'checks_owner_cgroup_membership':False,'same_unit_descendant_is_not_excluded':True,'exact_class_body_executed':True})

# Counterexample: a direct wait failure skips the independent descendant stop.
events=[];host=object.__new__(h['FiniteNativeHostAdapter']);host._owned=object();host.clock=clock
child=object.__new__(h['KernelChild']);child.owner=host._owned;child.clock=clock;child.closed=False;child.pidfd=5;child._launch_identity=(42,os.getpid(),'1',(0,));child.process=ns(pid=42,returncode=None,poll=lambda:None)
def fail_wait(**k):events.append('direct_wait');raise TimeoutError('DIRECT_WAIT_FAILED')
child.wait=fail_wait
envelope.stop=lambda:events.append('outside_stop');envelope.observe=lambda:events.append('outside_observe') or {'closed':False}
host._outside_unit_envelope=envelope
h['signal']=ns(SIGKILL=9,pidfd_send_signal=lambda *a:events.append('owned_pidfd_signal'))
e=call_error(lambda:host.stop_owned_returned_child_before_original_final_deadline(child))
fresh=call_error(lambda:host.fresh_owned_returned_absence(child,child.launch_identity))
counter('retained_direct_wait_exception_skips_outside_descendant_stop',isinstance(e,TimeoutError) and 'outside_stop' not in events and 'outside_observe' in events,events)
check('fresh_host_observer_does_not_repeat_signal_or_stop',events.count('owned_pidfd_signal')==1 and events.count('outside_observe')==1 and isinstance(fresh,h['StopUnconfirmed']))

# Counterexample: signal failure in pre-return launcher skips outside stop as well.
events=[]
native.observe=lambda:ns(main_pid=os.getpid(),control_group=group.group,invocation_id=group.invocation,quiescent=False)
group.observe_caps=lambda:{'populated':True,'effective_cpus':sorted(os.sched_getaffinity(0))};group.confirm_empty=lambda:events.append('fresh_group') or False
interpreter=object.__new__(h['HeldExecutableBuffer']);interpreter.binary=True;interpreter.fd=10;interpreter.verify=lambda:None
bootstrap=object.__new__(h['HeldExecutableBuffer']);bootstrap.binary=False;bootstrap.fd=11;bootstrap.raw=b'inert';bootstrap.verify=lambda:None
process=ns(pid=42,returncode=None,poll=lambda:None,wait=lambda **k:events.append('direct_wait') or 0)
h['subprocess']=ns(Popen=lambda *a,**k:process,DEVNULL=-3)
h['os']=ns(getpid=os.getpid,sched_getaffinity=os.sched_getaffinity,pidfd_open=lambda *a:5,close=lambda fd:events.append('close_pidfd'))
h['select']=ns(select=lambda *a:([],[],[]))
h['read_kernel_identity_component']=lambda p:events.append('fresh_process') or None
def fail_signal(*a):events.append('pidfd_signal');raise PermissionError('PIDFD_STOP_FAILED')
h['signal']=ns(SIGKILL=9,pidfd_send_signal=fail_signal)
envelope.stop=lambda:events.append('outside_stop');envelope.observe=lambda:events.append('outside_observe') or {'closed':False}
e=call_error(lambda:h['launch_owned_direct_fd_child_component'](interpreter,bootstrap,[],[],native=native,cgroup=group,owner=object(),clock=clock,stdout=None,stderr=None,outside_owner=envelope))
counter('partial_launcher_signal_exception_skips_outside_descendant_stop',isinstance(e,h['StopUnconfirmed']) and 'pidfd_signal' in events and 'outside_stop' not in events and 'outside_observe' in events,events)
check('partial_launch_stop_failure_still_wait_and_fresh_witness',all(x in events for x in ('direct_wait','fresh_group','fresh_process','outside_observe')) and isinstance(e,h['StopUnconfirmed']),events)

# Preservation is checked against the pinned original bytes, never old execution credit.
preservation={}
for name in ('launch_boundary.py','root_transaction_driver_rpc.py','run_exact_staged_rpc.py'):
    row=manifest['source'][name]; old=ast.parse(Path(row['original_path']).read_bytes());new=ast.parse(Path(row['path']).read_bytes())
    def defs(t):return {n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    a,z=defs(old),defs(new)
    allowed={'cleanup_returned_child','CleanupUnconfirmed'} if name=='launch_boundary.py' else ({'bounded_run_once'} if name=='root_transaction_driver_rpc.py' else {'supervisor'})
    same={n:a[n]==z.get(n) for n in a if n not in allowed}
    preservation[name]=same;check('AST_untouched_functions:'+name,all(same.values()))
for name in ('gated_installer.py','source-final/install_native_send_rpc.py','source-final/DEPENDENCY-AUDIT.json'):
    row=manifest['source'][name];check('byte_identical_retained:'+name,sha(row['path'])==sha(row['original_path']))
put('PRESERVATION.json',{'AST':preservation,'full19_validator_18RPCschemas15methods_fouraccountslocks_beforeimages':'UNCHANGED_SOURCE_NOT_RUN','normal3600_cleanup120':'UNCHANGED_SOURCE_NOT_RUN','F1F2F3F4':'retained exact bodies/bytes; no runtime credit','author20_late_finalize_seconds':0.7297466,'old47_and_author20_execution_credit':0})
put('CONTROLS.json',{'tests':tests,'passed':sum(x['pass'] for x in tests),'failed':sum(not x['pass'] for x in tests),'counterexamples':counterexamples,'reproduced_counterexamples':sum(x['reproduced'] for x in counterexamples),'exact_source_AST_body_controls':True,'dependency_seams':'inert isolated namespace only; no actual installer/validator/rootdriver or native launch','runtime_credit':0,'signal_effects':0,'source_mutations':0})
put('HELPER-EXIT.json', {'pid':pid,'start_token':token,'exit_code':0,'finished_unix':time.time(),'descendants':[],'within_original_useful':time.time()<A+540,'no_subprocess':True})
print(json.dumps({'passed':sum(x['pass'] for x in tests),'failed':sum(not x['pass'] for x in tests),'counterexamples':sum(x['reproduced'] for x in counterexamples),'EXIT':str(O/'HELPER-EXIT.json')}),flush=True)
