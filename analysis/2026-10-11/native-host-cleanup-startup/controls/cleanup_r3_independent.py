import os,sys,ast,json,math,time,hashlib,resource,select,types,stat
from pathlib import Path
O=Path(__file__).parent; S=O.parent/'cleanup-r3-source/source'; NS=types.SimpleNamespace
os.umask(0o077); os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
def put(n,v):
 fd=os.open(O/n,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def birth(pid):
 try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
pid=os.getpid();token=birth(pid);clock_record=json.loads((O/'CLOCK.json').read_text())
put('PREGO.json',{'pid':pid,'start_token':token,'affinity':sorted(os.sched_getaffinity(0)),'observed_RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'observed_RLIMIT_CPU':resource.getrlimit(resource.RLIMIT_CPU),'observed_RLIMIT_NOFILE':resource.getrlimit(resource.RLIMIT_NOFILE),'single_process_no_subprocess':True,'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'recorded_unix':time.time()})
print(json.dumps({'PREGO':pid,'start':token}),flush=True)
if not select.select([sys.stdin],[],[],55)[0] or sys.stdin.readline().strip()!='GO':sys.exit(2)
assert time.time()<clock_record['useful_deadline_unix'];put('GO.json',{'pid':pid,'start_token':token,'go_unix':time.time()})
tests=[];findings=[]
def check(n,v,d=None):tests.append({'name':n,'passed':v is True,'detail':d})
def err(fn):
 try:fn()
 except BaseException as e:return e
 return None
raw=(S/'native_host_adapter.py').read_bytes();tree=ast.parse(raw)
def defs(path,namespace):
 t=ast.parse(Path(path).read_bytes());nodes=[n for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace);return namespace
# Exact bodies unchanged; no module import/top-level execution and no AST guard removal.
base={'os':os,'math':math,'time':time,'stat':stat,'hashlib':hashlib,'select':select,'MAX_CPU':2,'MAX_MEMORY':1024**3}
h=defs(S/'native_host_adapter.py',dict(base))
check('actual_admission_refuses',isinstance(err(h['require_native_admission']),h['Unbound']))
for flag in (False,True,None,{'approved':True}):
 h['SOURCE_ONLY']=flag;h['NATIVE_ADMISSION']=flag
 check('flags_cannot_grant:'+repr(flag),isinstance(err(h['require_native_admission']),h['Unbound']))
# Dependency stubs are confined to inert selected-body controls; unmodified gate separately checked above.
q=defs(S/'native_host_adapter.py',dict(base));q['require_native_admission']=lambda:None
b=defs(S/'launch_boundary.py',{'os':os,'sys':sys,'time':time,'math':math,'json':json,'stat':stat,'hashlib':hashlib,'Path':Path,'HOST_CUSTODY':None})
good={'closed':True,'worker_reaped':True,'process_absence':True,'path_absence':True,'endpoint_absence':True,'cleanup_elapsed_seconds':1.0}
for x in (True,False,None,-1,120.0001,float('nan'),float('inf'),'1'):
 check('NF4_reject:'+repr(x),b['finite_cleanup_within_original120'](x) is False)
for x in (0,0.25,120):check('NF4_accept:'+str(x),b['finite_cleanup_within_original120'](x) is True)
for x in (1,'true',None,False):check('NF4_exact_closed:'+repr(x),b['exact_closure_complete']({**good,'closed':x}) is False)
for x in (1.0000000000000002,1791722654.1234567):
 y=b['strict_json'](json.dumps({'x':x}))['x'];check('NF1_exact_float:'+repr(x),type(y) is float and y.hex()==x.hex())
for x in ('{"x":NaN}','{"x":Infinity}','{"x":1e999}','{"x":1,"x":2}'):
 check('NF1_strict_negative:'+x,err(lambda:b['strict_json'](x)) is not None)
# Boundary witnesses must remain unconditional, including stop failure and invalid closure.
for have_custody in (False,True):
 for stopfail in (False,True):
  for obsfail in (False,True):
   ev=[];primary=ValueError('PRIMARY');se=PermissionError('STOP');oe=RuntimeError('WITNESS')
   def stop(*a):
    ev.append('stop')
    if stopfail:raise se
   def obs(*a,**kw):
    ev.append('fresh')
    if obsfail:raise oe
    return dict(good)
   host=NS(retained_owned_launch_identity=lambda c:{'pid':42},stop_owned_returned_child_before_original_final_deadline=stop,stop_reap_exact_before_original_final_deadline=stop,fresh_owned_returned_absence=obs)
   e=err(lambda:b['cleanup_returned_child'](host,object(),NS(identity={'pid':42}) if have_custody else None,primary))
   check('R1_boundary:'+str((have_custody,stopfail,obsfail)),ev==['stop','fresh'] and (e is None if not(stopfail or obsfail) else isinstance(e,b['CleanupUnconfirmed']) and e.primary_error is primary and (not stopfail or any(v is se for _,v in e.cleanup_errors)) and (not obsfail or any(v is oe for _,v in e.cleanup_errors))))
# Returned child: exhaustive signal/unitstop/wait failure combinations and coupled fresh witness.
for signal_fail in (False,True):
 for stop_fail in (False,True):
  for wait_fail in (False,True):
   ev=[];host=object.__new__(q['FiniteNativeHostAdapter']);host._owned=object();host.clock=NS(remaining=lambda **k:60.0,cleanup_seconds=60)
   child=object.__new__(q['KernelChild']);child.owner=host._owned;child.clock=host.clock;child.closed=False;child.pidfd=5;child._launch_identity=(42,os.getpid(),'1',(0,));child.process=NS(pid=42,poll=lambda:None,returncode=-9)
   def send(*a):
    ev.append('signal')
    if signal_fail:raise PermissionError('SIGNAL')
   def stop():
    ev.append('unitstop')
    if stop_fail:raise PermissionError('UNITSTOP')
   def wait(**kw):
    ev.append('wait')
    if wait_fail:raise TimeoutError('WAIT')
    return -9
   child.wait=wait;env=object.__new__(q['IndependentlyHeldUnitEnvelope']);env.stop=stop;env.observe=lambda:ev.append('outside_fresh') or {'closed':False};host._outside_unit_envelope=env;q['signal']=NS(SIGKILL=9,pidfd_send_signal=send)
   e=err(lambda:host.stop_owned_returned_child_before_original_final_deadline(child));stages=[s for s,_ in e.cleanup_errors] if e else []
   check('R3_returned_order:'+str((signal_fail,stop_fail,wait_fail)),ev==['signal','unitstop','wait'],ev.copy())
   check('R3_returned_causes:'+str((signal_fail,stop_fail,wait_fail)),stages==(['owned_pidfd_stop'] if signal_fail else [])+(['outside_unit_stop'] if stop_fail else [])+(['direct_wait'] if wait_fail else []),stages)
   q['read_kernel_identity_component']=lambda p:ev.append('process_fresh') or None
   w=err(lambda:host.fresh_owned_returned_absence(child));check('R1_host_unconditional_fresh:'+str((signal_fail,stop_fail,wait_fail)),ev.count('outside_fresh')==1 and ev.count('unitstop')==1 and 'process_fresh' in ev and isinstance(w,q['StopUnconfirmed']))
# Identity mismatch must not signal/wait an unowned child; independently held envelope still stops.
ev=[];child.owner=object();e=err(lambda:host.stop_owned_returned_child_before_original_final_deadline(child));check('unowned_no_signal_or_wait',ev==['unitstop'] and isinstance(e,q['StopUnconfirmed']),ev)
# A long SUCCESSFUL direct wait occurs strictly after exact outside stop minimum is checked.
ev=[];remaining=[60.0];host.clock=NS(cleanup_seconds=60,remaining=lambda **kw:remaining[0] if remaining[0]>kw.get('minimum',0) else (_ for _ in ()).throw(q['Unbound']('EXHAUSTED')));child.owner=host._owned;child.clock=host.clock
child.wait=lambda **kw:ev.append(('wait',kw['timeout'])) or remaining.__setitem__(0,3.1)
q['signal']=NS(SIGKILL=9,pidfd_send_signal=lambda *a:ev.append('signal'))
def bounded_stop():host.clock.remaining(cleanup=True,minimum=24.2);ev.append('unitstop')
env.stop=bounded_stop
e=err(lambda:host.stop_owned_returned_child_before_original_final_deadline(child));check('late_success_wait_preserves_outside_stop',e is None and ev[:2]==['signal','unitstop'] and remaining[0]==3.1,ev)
# Exact cgroup parser uses inert I/O primitives only; reject malformed/oversized/nonunified input.
parser=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_kernel_cgroup_component')
pns={'require':q['require'],'Unbound':q['Unbound']};exec(compile(ast.Module(body=[parser],type_ignores=[]),str(S/'native_host_adapter.py'),'exec'),pns)
for payload,accept in [(b'0::/\n',True),(b'0::/other/job.service\n',True),(b'0::/owned/job.service\n',True),(b'',False),(b'0::/a/../b\n',False),(b'0::/a/./b\n',False),(b'0::/a//b\n',False),(b'0::/a/\n',False),(b'0::relative\n',False),(b'0::/a\n0::/b\n',False),(b'1:cpu:/a\n',False),(b'0::/a\n1:cpu:/a\n',False),(b'\xff',False),(b'0::/'+b'x'*65537,False)]:
 io=[];pns['os']=NS(O_RDONLY=0,O_CLOEXEC=0,O_NOFOLLOW=0,open=lambda *a:io.append('open') or 5,read=lambda *a:payload,close=lambda *a:io.append('close'))
 e=err(lambda:pns['read_kernel_cgroup_component'](42));check('canonical_unified:'+repr(payload[:45]),(e is None)==accept and io==['open','close'])
for pidbad in (True,0,1,'42',-1):check('cgroup_pid_exact:'+repr(pidbad),err(lambda:pns['read_kernel_cgroup_component'](pidbad)) is not None)
# Membership and birth verification on construction, verify, stop: samegroup/descendants refused.
for actual,reject in [('/owned/job.service',True),('/owned/job.service/child',True),('/owned/job.service/child/deep',True),('/owned/job.serviceX',False),('/other',False),('/',False)]:
 ident={'pid':os.getpid(),'start_token':'1'};q['read_kernel_identity_component']=lambda p:dict(ident);q['read_kernel_cgroup_component']=lambda p:actual
 e=err(lambda:q['require_owner_outside_group'](os.getpid(),'/owned/job.service'));check('owner_entire_envelope:'+actual,(e is not None)==reject)
 native=object.__new__(q['ExistingNativeBoundary']);group=object.__new__(q['HeldCgroup']);cl=NS(remaining=lambda **kw:60)
 group.group='/owned/job.service';group.invocation='a'*32;group.unit='job.service';group.verify=lambda:None
 native.observe=lambda:NS(main_pid=999,control_group=group.group,invocation_id=group.invocation)
 e=err(lambda:q['IndependentlyHeldUnitEnvelope'](native,group,cl));check('constructor_owner_membership:'+actual,(e is not None)==reject)
q['read_kernel_cgroup_component']=lambda p:'/other'
for identities in ([None], [{'pid':42,'start':'1'},{'pid':42,'start':'2'}], [{'pid':42,'start':'1'},None]):
 it=iter(identities);q['read_kernel_identity_component']=lambda p:next(it);e=err(lambda:q['require_owner_outside_group'](42,'/owned/job.service'));check('birth_absence_or_drift:'+str(identities),e is not None)
for target in ('/','relative','/owned/../job','/owned//job','/owned/./job'):
 check('invalid_target:'+target,err(lambda:q['require_owner_outside_group'](42,target)) is not None)
ident={'pid':os.getpid(),'start_token':'1'};q['read_kernel_identity_component']=lambda p:dict(ident);outside=q['IndependentlyHeldUnitEnvelope'](native,group,cl)
for actual in ('/owned/job.service','/owned/job.service/desc'):
 q['read_kernel_cgroup_component']=lambda p:actual;check('verify_new_inside_membership:'+actual,isinstance(err(outside.verify),q['Unbound']))
q['read_kernel_cgroup_component']=lambda p:'/other';q['read_kernel_identity_component']=lambda p:{**ident,'start_token':'2'};check('verify_held_birth_drift',isinstance(err(outside.verify),q['Unbound']))
# Partial launcher: no actual Popen/pidfd/signal/service. Exact body fixtures exercise owned lifecycle.
for fault in ('none','popen','pidfd','before_identity','after_identity','select','late_buffer','signal_stop_wait_observe'):
 ev=[];clock=NS(remaining=lambda **kw:60.0,cleanup_seconds=60);proc=NS(pid=42,returncode=-9,poll=lambda:None)
 def procwait(**kw):
  ev.append('wait')
  if fault=='signal_stop_wait_observe':raise TimeoutError('WAIT')
  return -9
 proc.wait=procwait
 def po(*a,**kw):
  ev.append('popen')
  if fault=='popen':raise OSError('POPEN')
  return proc
 def pidfd(*a):
  ev.append('pidfd')
  if fault=='pidfd':raise OSError('PIDFD')
  return 5
 io=NS(getpid=lambda:100,sched_getaffinity=lambda p:{0,1},pidfd_open=pidfd,close=lambda fd:ev.append('closefd'))
 native=object.__new__(q['ExistingNativeBoundary']);group=object.__new__(q['HeldCgroup']);group.group='/owned/job.service';group.invocation='a'*32
 def observe():
  ev.append('native')
  if fault=='signal_stop_wait_observe' and ev.count('native')>1:raise OSError('OBSERVE')
  return NS(main_pid=100,control_group=group.group,invocation_id=group.invocation)
 native.observe=observe;group.observe_caps=lambda:{'populated':True,'effective_cpus':[0,1]};group.confirm_empty=lambda:ev.append('empty') or True
 env=object.__new__(q['IndependentlyHeldUnitEnvelope']);env.invocation=group.invocation;env.cgroup=group
 def stop():
  ev.append('unitstop')
  if fault=='signal_stop_wait_observe':raise PermissionError('STOP')
 env.stop=stop;env.observe=lambda:ev.append('outsidefresh') or {'closed':False}
 def sig(*a):
  ev.append('signal')
  if fault=='signal_stop_wait_observe':raise PermissionError('SIGNAL')
 counter=[0]
 def read(p):
  counter[0]+=1
  if fault=='before_identity' and counter[0]==1:return None
  if fault=='after_identity' and counter[0]==2:return {'pid':42,'ppid':100,'start_token':'2','affinity':[0,1]}
  return {'pid':42,'ppid':100,'start_token':'1','affinity':[0,1]}
 interp=object.__new__(q['HeldExecutableBuffer']);boot=object.__new__(q['HeldExecutableBuffer']);interp.binary=True;boot.binary=False;interp.fd=10;boot.fd=11;boot.raw=b'pass';interp.verify=lambda:None;bc=[0]
 def bv():
  bc[0]+=1
  if fault in ('late_buffer','signal_stop_wait_observe') and bc[0]==2:raise ValueError('PRIMARY_LATE_BUFFER')
 boot.verify=bv
 q['os']=io;q['subprocess']=NS(Popen=po,DEVNULL=-1);q['signal']=NS(SIGKILL=9,pidfd_send_signal=sig);q['read_kernel_identity_component']=read;q['select']=NS(select=lambda *a:([5],[],[]) if fault=='select' else ([],[],[]))
 returned=[]
 def launch():returned.append(q['launch_owned_direct_fd_child_component'](interp,boot,[],[],native=native,cgroup=group,owner=object(),clock=clock,stdout=None,stderr=None,outside_owner=env))
 e=err(launch)
 if fault=='none':check('launcher_success_exact_handle',e is None and len(returned)==1 and returned[0].pidfd==5 and 'unitstop' not in ev)
 elif fault=='popen':check('launcher_no_creation_no_cleanup',isinstance(e,OSError) and ev==['native','popen'],ev)
 else:
  check('launcher_partial_stop_wait_fresh:'+fault,e is not None and ev.count('unitstop')==1 and ev.count('wait')==1 and ev.count('outsidefresh')==1 and ev.index('unitstop')<ev.index('wait'),ev.copy())
  check('launcher_no_numeric_pidkill:'+fault,'pidfd' not in fault or 'signal' not in ev)
  if fault=='signal_stop_wait_observe':
   stages=[s for s,_ in e.cleanup_errors];check('launcher_primary_all_cleanup_causes',isinstance(e,q['StopUnconfirmed']) and str(e.primary_error)=='PRIMARY_LATE_BUFFER' and all(s in stages for s in ('owned_pidfd_stop','outside_unit_stop','direct_wait','native_observe')),stages)
# Composition: exact seven source pins again, unchanged six source rows and native admission gates.
m=json.loads((O.parent/'cleanup-r3-source/MANIFEST.json').read_text())
for n,row in m['source'].items():
 check('final_exact_row:'+n,hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'] and Path(row['path']).stat().st_size==row['bytes'])
 if n!='native_host_adapter.py':check('unchanged_six_exact:'+n,row['sha256']==row['previous_sha256'])
source_text={n:Path(r['path']).read_text() for n,r in m['source'].items() if n.endswith('.py')}
check('native_live_not_granted',"raise Unbound('INACTIVE_SOURCE_ONLY_NO_NATIVE_ADMISSION')" in source_text['native_host_adapter.py'] and '_outside_unit_envelope = None' in source_text['native_host_adapter.py'])
check('driver_original_cleanup_witness', 'cleanup_returned_child' in source_text['root_transaction_driver_rpc.py'] and 'cleanup_returned_child' in source_text['run_exact_staged_rpc.py'])
put('CONTROLS.json',{'passed':sum(t['passed'] for t in tests),'failed':sum(not t['passed'] for t in tests),'tests':tests,'source_only':True,'exact_AST_bodies_not_rewritten':True,'inert_dependency_stubs':True,'target_imports':0,'native_effects':0,'source_mutations':0,'runtime_authority':False,'prior_author_or_independent_execution_credit':0})
put('HELPER-EXIT.json',{'pid':pid,'start_token':token,'expected_exit_code':0 if all(t['passed'] for t in tests) else 1,'finished_unix':time.time(),'within_original_useful':time.time()<clock_record['useful_deadline_unix'],'descendants_created':[]})
print(json.dumps({'passed':sum(t['passed'] for t in tests),'failed':sum(not t['passed'] for t in tests),'failed_names':[t['name'] for t in tests if not t['passed']]}),flush=True)
sys.exit(0 if all(t['passed'] for t in tests) else 1)
