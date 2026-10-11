import os,sys,time,json,ast,math,resource,select,types,hashlib
from pathlib import Path
O=Path(__file__).parent/'reserve-retry'
O.mkdir(mode=0o700)
S=Path('/PORTABLE_UNBOUND/PATH_0200')
os.umask(0o077);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
def put(n,v):
 fd=os.open(O/n,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:os.write(fd,(json.dumps(v,sort_keys=True,indent=2)+'\n').encode());os.fsync(fd)
 finally:os.close(fd)
pid=os.getpid();birth=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
children=Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip()
put('RESERVE-PREGO.json',{'pid':pid,'start_token':birth,'affinity':sorted(os.sched_getaffinity(0)),'AS':resource.getrlimit(resource.RLIMIT_AS),'CPU':resource.getrlimit(resource.RLIMIT_CPU),'actual_proc_children':children,'preGO_unix':time.time(),'original_useful_deadline':1791722217.0})
print(json.dumps({'pid':pid,'start_token':birth,'PREGO':str(O/'RESERVE-PREGO.json')}),flush=True)
assert select.select([sys.stdin],[],[],55)[0] and sys.stdin.readline().strip()=='GO'
assert time.time()<1791722217.0
put('RESERVE-GO.json',{'pid':pid,'start_token':birth,'go_unix':time.time(),'original_clock_not_reset':True})
tree=ast.parse(S.read_bytes());names={'Unbound','StopUnconfirmed','require','cleanup_failure','identity_dict','KernelChild','FiniteNativeHostAdapter','IndependentlyHeldUnitEnvelope'}
h={'os':os,'time':time,'math':math,'signal':types.SimpleNamespace(SIGKILL=9,pidfd_send_signal=lambda *a:None),'require_native_admission':lambda:None,'read_kernel_identity_component':lambda p:{'pid':p}}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names],type_ignores=[]),str(S),'exec'),h)
events=[]
class Clock:
 left=60.0
 def remaining(self,cleanup=False,minimum=0):
  if self.left<=minimum:raise h['Unbound']('ORIGINAL_BOUND_EXHAUSTED')
  return self.left
clock=Clock();host=object.__new__(h['FiniteNativeHostAdapter']);host._owned=object();host.clock=clock
child=object.__new__(h['KernelChild']);child.owner=host._owned;child.clock=clock;child.closed=False;child.pidfd=5;child._launch_identity=(42,pid,'1',(0,));child.process=types.SimpleNamespace(pid=42,poll=lambda:None,returncode=0)
def wait(timeout):
 events.append({'direct_wait_timeout':timeout});clock.left-=timeout;return 0
child.wait=wait
envelope=object.__new__(h['IndependentlyHeldUnitEnvelope']);envelope.clock=clock;envelope.verify=lambda:None;envelope.native=types.SimpleNamespace(stop=lambda:events.append('actual_outside_stop'))
host._outside_unit_envelope=envelope
try:host.stop_owned_returned_child_before_original_final_deadline(child);err=None
except BaseException as e:err={'type':type(e).__name__,'message':str(e)}
reproduced=err is not None and clock.left<24.2 and 'actual_outside_stop' not in events
put('RESERVE-CONTROL.json',{'name':'returned_direct_wait_reserves3.1_but_later_outside_stop_needs24.2','exact_source_sha256':hashlib.sha256(S.read_bytes()).hexdigest(),'exact_bodies':['FiniteNativeHostAdapter.stop_owned_returned_child_before_original_final_deadline','IndependentlyHeldUnitEnvelope.stop'],'reproduced':reproduced,'events':events,'remaining_original_cleanup':clock.left,'outside_stop_minimum':24.2,'error':err,'uses_inert_clock_no_actual_wait':True,'source_mutations':0,'runtime_credit':0,'signal_effects':0})
put('RESERVE-EXIT.json',{'pid':pid,'start_token':birth,'finished_unix':time.time(),'actual_proc_children':Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip(),'exit_code':0 if reproduced else 1})
print(json.dumps({'reproduced':reproduced,'events':events,'remaining':clock.left}),flush=True)
sys.exit(0 if reproduced else 1)
