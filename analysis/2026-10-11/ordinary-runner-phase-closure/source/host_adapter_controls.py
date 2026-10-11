#!/usr/bin/env python3
"""Bounded AUTHOR source controls. Real loader mechanics, synthetic host seams.
No genuine host/kernel/interpreter authority or gate execution is exercised.
"""
import copy,datetime,importlib.util,json,os,resource,sys,threading,time
from pathlib import Path
OUT=Path(sys.argv[1]).absolute();INPUT=Path(sys.argv[2]).absolute();PKG=Path(__file__).parent
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024**2,4*1024**2));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
cpus=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,cpus)
s=Path('/proc/self/stat').read_text();start=int(s[s.rfind(')')+2:].split()[19]);process={'pid':os.getpid(),'start_ticks':start}
(OUT/'READY.json').write_text(json.dumps(dict(pid=os.getpid(),start_ticks=start,affinity=cpus,address_space_bytes=384*1024**2)))
while not (OUT/'BARRIER.json').exists():time.sleep(.01)
barrier=json.loads((OUT/'BARRIER.json').read_text());assert barrier['pid']==os.getpid() and barrier['start_ticks']==start
begin=time.monotonic();fds=len(list(Path('/proc/self/fd').iterdir()))
def audit(event,args):
 if event.startswith(('socket.','subprocess.','os.exec','os.system','os.posix_spawn','os.fork','pty.','ctypes.')):raise AssertionError('inert_helper_effect_forbidden:'+event)
 if event=='open' and isinstance(args[0],(str,bytes)):
  mode,flags=args[1] or '',args[2] or 0
  if any(c in mode for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
   p=Path(os.fsdecode(args[0]));assert not p.is_absolute() or p.resolve().is_relative_to(OUT),('outside_private_helper',p)
sys.addaudithook(audit)
def load(name):
 p=PKG/(name+'.py');m=importlib.util.module_from_spec(importlib.util.spec_from_file_location('author_'+name,p));m.__spec__.loader.exec_module(m);return m
C=load('runner_contract');L=load('retained_loader');H=load('host_gate_adapter');cases=[]
def yes(name,fn):
 assert time.monotonic()<barrier['hard_monotonic'];value=fn();assert value is True,(name,value);cases.append(dict(name=name,status='AUTHOR_INERT_SOURCE_PASS'))
def denied(name,fn,cause):
 assert time.monotonic()<barrier['hard_monotonic']
 try:fn()
 except (ValueError,TypeError,KeyError,OSError) as e:
  assert cause in str(e),(name,cause,str(e));cases.append(dict(name=name,status='AUTHOR_INERT_SOURCE_PASS',refusal=str(e)));return
 raise AssertionError('DID_NOT_REFUSE:'+name)
fixtures=OUT/'fixtures';fixtures.mkdir(mode=0o700)
def write(name,data):p=fixtures/name;p.write_bytes(data);return C.pin(p)
grant=write('grant.json',b'{"SOURCE_FIXTURE_ONLY":true}\n');anchor=write('anchor.json',b'{"SOURCE_FIXTURE_ONLY":true}\n');slot=write('slot.json',b'{"SOURCE_FIXTURE_ONLY":true}\n')
binding={'binding_sha256':'a'*64,'grant':grant}
buffers={n:(PKG/n).read_bytes() for n in L.NAMES};implementation={n:C.pin(PKG/n) for n in L.NAMES};implementation['interpreter']=C.pin(Path(sys.executable).resolve())
# Fresh executable pin here is an explicit synthetic interpreter input. It is
# never called genuine loaded-interpreter provenance or used for product launch.
interpreter_fixture=C.canonical(implementation['interpreter'])
def loader(actor='parent',**changes):
 args=dict(buffers=buffers,implementation=implementation,interpreter_provenance=interpreter_fixture,binding=binding,actor=actor);args.update(changes);return L.RetainedLoader(**args)
parent_loader=loader();parent=parent_loader.load_entrypoint()
def context(actor='parent',phase='before_admission',**changes):
 value=dict(phase=phase,actor=actor,process=process,worker=process if actor=='worker' else None,implementation=implementation,binding=binding);value.update(changes);return value
def observation(l=parent_loader,p=parent,ctx=None):return l.capture_loaded_implementation(context=context() if ctx is None else ctx,namespace=p.__dict__)
yes('actual_four_buffers_captured_before_parent_exec',lambda:len(observation()[1])==4 and set(parent_loader._modules)=={'source_runner.py','runner_contract.py','gate_inputs.py'})
yes('actual_parent_dependencies_same_retained_module_objects',lambda:parent.contract is parent_loader._modules['runner_contract.py'] and parent.gate is parent_loader._modules['gate_inputs.py'])
yes('contract_accepts_concrete_retained_loader_original_binding',lambda:C.loaded_implementation(parent_loader,implementation,'before_admission','parent',parent.__dict__,binding)==C.canonical(implementation))
yes('capture_revalidates_without_reopening_source_paths',lambda:all(b is buffers[n] for n,p,b,state in observation()[1]))
for key,value,cause in [('actor','worker','loader_actor_process_mismatch'),('process',dict(process,start_ticks=start+1),'loader_actor_process_mismatch'),('binding',dict(binding,binding_sha256='0'*64),'loader_original_binding_changed'),('phase','','loader_phase_required')]:
 denied('retained_loader_context_'+key+'_drift',lambda key=key,value=value:observation(ctx=context(**{key:value})),cause)
bad=copy.deepcopy(implementation);bad['source_runner.py']['sha256']='0'*64
denied('retained_loader_impl_repin_refuses',lambda:observation(ctx=context(implementation=bad)),'loader_original_implementation_changed')
denied('retained_loader_foreign_namespace_refuses',lambda:parent_loader.capture_loaded_implementation(context=context(),namespace=dict(parent.__dict__)),'loader_foreign_executing_namespace')
denied('retained_loader_second_entrypoint_refuses',lambda:parent_loader.load_entrypoint(),'loader_entrypoint_already_loaded')
denied('retained_loader_arbitrary_dependency_refuses',lambda:parent_loader.load_dependency('os'),'unapproved_loader_dependency')
denied('loader_mutable_interpreter_refuses',lambda:loader(interpreter_provenance=bytearray(interpreter_fixture)),'preload_interpreter_provenance_required')
denied('loader_missing_interpreter_refuses',lambda:loader(interpreter_provenance=None),'preload_interpreter_provenance_required')
for name in sorted(buffers):
 bad=dict(buffers);bad[name]=bytearray(bad[name]);denied('loader_mutable_buffer_'+name,lambda bad=bad:loader(buffers=bad),'immutable_preload_buffer_required')
 bad=dict(buffers);bad[name]+=b'\n# original drift\n';denied('loader_preexec_SHA_'+name,lambda bad=bad:loader(buffers=bad),'preload_source_pin_changed')
for name in ['source_runner.py','runner_contract.py','gate_inputs.py']:
 l=loader();p=l.load_entrypoint();module=l._modules[name];func=next(v for v in module.__dict__.values() if callable(v) and getattr(v,'__globals__',None) is module.__dict__)
 old=func.__code__;func.__code__=(lambda:None).__code__
 denied('loaded_actual_code_drift_'+name,lambda l=l,p=p:l.capture_loaded_implementation(context=context(),namespace=p.__dict__),'retained_loaded_namespace_changed')
 func.__code__=old
 l=loader();p=l.load_entrypoint();module=l._modules[name];module.__dict__['AUTHOR_ADDED_DRIFT']=1
 denied('loaded_namespace_addition_'+name,lambda l=l,p=p:l.capture_loaded_implementation(context=context(),namespace=p.__dict__),'retained_loaded_namespace_changed')
# Old loaded source cannot accept a repinned fresh source cohort, even if the
# fresh pin/map is internally consistent. No historical immutable file changed.
bad=copy.deepcopy(implementation);newbuf=dict(buffers);newbuf['source_runner.py']+=b'\n# new cohort\n';bad['source_runner.py'].update(bytes=len(newbuf['source_runner.py']),sha256=C.digest(newbuf['source_runner.py']))
denied('old_loaded_cohort_rejects_new_self_repin',lambda:observation(ctx=context(implementation=bad)),'loader_original_implementation_changed')
worker_loader=loader('worker');worker_module=worker_loader.load_entrypoint();wctx=context('worker',phase='worker_before_configure')
yes('actual_worker_contract_is_retained_module',lambda:worker_module.contract is worker_loader._modules['runner_contract.py'])
yes('actual_worker_loaded_capture_matches_original_parent_images',lambda:C.loaded_implementation(worker_loader,implementation,'worker_before_configure','worker',worker_module.__dict__,binding,process)==C.canonical(implementation))
denied('worker_birth_drift_before_GO',lambda:worker_loader.capture_loaded_implementation(context=context('worker',worker=dict(process,start_ticks=start+1)),namespace=worker_module.__dict__),'loader_worker_birth_mismatch')
for phase in ['before_launch','before_materialize','parent_boundary','before_barrier','after_reap','parent_cancel','parent_cleanup']:
 yes('actual_loaded_parent_barrier_'+phase,lambda phase=phase:C.loaded_implementation(parent_loader,implementation,phase,'parent',parent.__dict__,binding)==C.canonical(implementation))
for phase in ['worker_before_configure','worker_before_ready','worker_after_barrier','worker_before_closure']:
 yes('actual_loaded_worker_barrier_'+phase,lambda phase=phase:C.loaded_implementation(worker_loader,implementation,phase,'worker',worker_module.__dict__,binding,process)==C.canonical(implementation))
clockref=C.pin(INPUT);clock=C.document(clockref);budget=dict(start_epoch=datetime.datetime.fromisoformat(clock['accepted_msk']).timestamp(),seconds=clock['original_seconds'],cleanup_seconds=clock['cleanup_seconds'],hard_epoch=clock['hard_epoch'],clock_ref=clockref)
limits=dict(CPUs=2,worker_address_space_bytes=1024**3,aggregate_address_space_bytes=1024**3+96*1024**2,output_bytes=1024**2)
root=fixtures/'checker-source';(root/'catalog').mkdir(parents=True);checker=root/'catalog/pure_checker.py';checker.write_text('ROOT='+repr(str(root))+"\nVALUE='SOURCE_FIXTURE'\n");checkerref=C.pin(checker)
relocation=dict(binding_sha256='a'*64,checkers=[dict(kind='catalog',after=checkerref)]);relref=write('relocation.json',C.canonical(relocation))
pins=dict(grant=grant,relocation=relref,source_anchor=anchor,slot_receipt=slot,clock=clockref);pins.update({'implementation:'+n:r for n,r in implementation.items()})
a=dict(schema='friday.source-run-admission.v2',kind='catalog-filtered',binding_sha256='a'*64,checker=checkerref,auxiliary={},pins=pins,read_scope=dict(files=[checkerref,*pins.values()],roots=[]),implementation=implementation,loaded_identity=C.canonical(implementation).decode(),approved_affinity=cpus,relocation=relocation,budget=budget,resources=limits,exclusive_slot=dict(receipt=slot,owner_pid=os.getpid(),owner_start_ticks=start),output_root=str(fixtures/'prepared'),runtime_grant=False,independent_acceptance=False,SOURCE_FIXTURE_ONLY=True)
token=C.canonical(a);jobref=parent.materialize_job(a) # only tiny private pure checker copy, never execute it
class SyntheticContract:
 def __init__(self):self.absent=False;self.fake_pid=2**30;self.fake_start=123456
 def __getattr__(self,k):return getattr(C,k)
 def pid_start(self,pid):return (None if self.absent else self.fake_start) if pid==self.fake_pid else C.pid_start(pid)
class SyntheticChild:
 def __init__(self,c):self.pid=c.fake_pid;self.returncode=None
 def poll(self):return self.returncode
 def wait(self,timeout=None):return self.returncode
class FixtureBoundary(H.ExistingHostBoundary):
 def __init__(self,c):self.c=c;self.child=SyntheticChild(c);self.calls=[];self.bad=None
 def observe_retained(self,ctx):
  self.calls.append('observe:'+ctx['phase']);observed=None
  if ctx['worker'] is not None and ctx['phase']!='worker_before_configure':observed=dict(affinity=cpus,address_space_bytes=[limits['worker_address_space_bytes']]*2,CPU_seconds=[60,60],file_size_bytes=[limits['output_bytes']]*2)
  r=dict(context=ctx,owner=process,resource_observation=dict(worker=ctx['worker'],job=ctx['job'],approved_affinity=cpus,available_affinity=cpus,observed_limits=observed))
  for key in ['actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins','kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap']:r[key]=True
  if self.bad:
   key,val=self.bad
   if key.startswith('resource:'):r['resource_observation'][key.split(':')[1]]=val
   else:r[key]=val
  return r
 def launch_retained(self,admission,job_ref,loader):
  self.calls.append('launch');return self.child,dict(pid=self.c.fake_pid,start_ticks=self.c.fake_start)
 def observe_closed(self,worker,job):
  self.calls.append('closure');ctx=C.custody_context(a,'after_reap',worker,job);ro=self.observe_retained(ctx)['resource_observation']
  return dict(worker=worker,job=job,owned_obligations_observed=True,retained_until_reap=True,exact_worker_absent=True,worker_reaped=True,owned_children=[],closure_ref=C.pin(Path(a['output_root'])/'WORKER-CLOSURE.json'),resource_observation=ro)
 def stop_owned(self,worker,job,deadline):
  self.calls.append('stop');return dict(status='STOP_CONFIRMED',worker=worker,job=job,original_hard_epoch=deadline,exact_owned_only=True,pending_launch_settled=True,owned_children=[],retained_until_reap=True,exact_worker_absent=True,worker_reaped=True)
def session():
 c=SyntheticContract();b=FixtureBoundary(c);adapter=H.GateHostAdapter(contract=c,admission=token,loader=parent_loader,boundary=b);return adapter,b,c
unbound=H.GateHostAdapter(contract=C,admission=token,loader=parent_loader)
ctx=C.custody_context(a,'before_launch');before=list(fixtures.rglob('*'))
denied('default_host_UNBOUND_before_observer_effects',lambda:unbound.verify_retained(ctx),'existing_gate_host_counterpart_UNBOUND')
denied('default_host_UNBOUND_before_launch',lambda:unbound.launch_owned_source_worker(admission=token,job_ref=jobref),'existing_gate_host_counterpart_UNBOUND')
yes('default_UNBOUND_zero_private_output_effect',lambda:list(fixtures.rglob('*'))==before)
for value in [None,{},object()]:
 denied('untrusted_boundary_'+type(value).__name__,lambda value=value:H.GateHostAdapter(contract=C,admission=token,loader=parent_loader,boundary=value).verify_retained(ctx),'existing_gate_host_counterpart_UNBOUND')
for key in ['binding_sha256','grant_sha256','implementation_sha256','read_scope_sha256','output_root','original_budget','resources','approved_affinity','loaded_identity']:
 bad=copy.deepcopy(ctx);bad[key]='DRIFT';ad,b,c=session();denied('host_exact_admission_'+key,lambda bad=bad,ad=ad:ad.verify_retained(bad),'host_original_admission_context_changed')
for key in ['actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins','kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap']:
 ad,b,c=session();b.bad=(key,False);denied('host_missing_'+key,lambda ad=ad:ad.verify_retained(ctx),'host_obligation_unavailable:'+key)
for key,value,cause in [('owner',dict(process,start_ticks=start+1),'host_original_owner_changed'),('resource:approved_affinity',[cpus[0]],'host_approved_affinity_changed'),('resource:available_affinity',['CPU'],'affinity_cpu_type'),('resource:worker',dict(process),'resource_worker_job_mismatch'),('resource:job',jobref,'resource_worker_job_mismatch')]:
 ad,b,c=session();b.bad=(key,value);denied('live_observer_'+key,lambda ad=ad:ad.verify_retained(ctx),cause)
ad,b,c=session();yes('source_synthetic_before_launch_contract_only',lambda:ad.verify_retained(ctx)['actual_exclusive_lock'] is True)
for key,val in [('worker',process),('job',jobref)]:
 bad=copy.deepcopy(ctx);bad[key]=val
 denied('unowned_'+key+'_join',lambda bad=bad:ad.verify_retained(bad),'host_unowned_worker' if key=='worker' else 'host_original_JOB_changed')
denied('unapproved_host_phase',lambda:ad.verify_retained(dict(ctx,phase='INSTALL')),'host_phase_not_admitted')
# Parent verifies the exact prepared JOB before calling adapter launch: ensure
# this joins once and cannot be replaced at the next boundary.
immediate=C.custody_context(a,'immediately_before_launch',job_ref=jobref)
yes('exact_JOB_bind_before_existing_launch',lambda:ad.verify_retained(immediate)['context']['job']==jobref)
child=ad.launch_owned_source_worker(admission=token,job_ref=jobref);w=dict(pid=c.fake_pid,start_ticks=c.fake_start)
yes('source_synthetic_single_launch_joined',lambda:child is b.child and b.calls.count('launch')==1)
denied('launch_no_replay',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'host_launch_consumed_no_replay')
for phase in ['before_barrier','worker_before_configure','worker_before_ready','worker_after_barrier','worker_before_closure','parent_cancel','parent_cleanup']:
 yes('source_synthetic_worker_JOB_'+phase,lambda phase=phase:ad.verify_retained(C.custody_context(a,phase,w,jobref))['resource_observation']['approved_affinity']==cpus)
for key,value,cause in [('worker',dict(w,start_ticks=w['start_ticks']+1),'host_unowned_worker'),('job',dict(jobref,sha256='0'*64),'host_original_JOB_changed')]:
 bad=C.custody_context(a,'before_barrier',w,jobref);bad[key]=value;denied('before_GO_'+key+'_drift',lambda bad=bad:ad.verify_retained(bad),cause)
for value in [[True],[str(cpus[0])],[cpus[0],cpus[0]],[-1],[4096]]:
 b.bad=('resource:approved_affinity',value);denied('adapter_CPU_typed_'+repr(value),lambda:ad.verify_retained(C.custody_context(a,'before_barrier',w,jobref)),'affinity_' if value!=[4096] else 'affinity_outside_host_scope')
b.bad=None
denied('closure_before_reap_absence_refuses',lambda:ad.capture_worker_closure(worker=w,job_ref=jobref),'host_exact_worker_not_reaped_absent')
child.returncode=0;c.absent=True;ro=b.observe_retained(C.custody_context(a,'after_reap',w,jobref))['resource_observation']
closure=dict(schema='friday.source-worker-closure.v2',worker=w,job=jobref,completed=True,children=[],threads=['MainThread'],FD_delta=0,approved_affinity=cpus,observed_limits=ro['observed_limits'],original_budget=budget,resources=limits,ended_epoch=time.time(),output_bytes=0,runtime_grant=False,independent_acceptance=False)
Path(a['output_root'],'WORKER-CLOSURE.json').write_bytes(C.canonical(closure))
yes('source_synthetic_closure_full_join_only',lambda:ad.capture_worker_closure(worker=w,job_ref=jobref)['owned_obligations_observed'] is True)
denied('closure_no_replay',lambda:ad.capture_worker_closure(worker=w,job_ref=jobref),'host_closure_consumed_no_replay')
yes('source_synthetic_retained_stop_original_deadline',lambda:ad.stop_owned(worker=w,job_ref=jobref)['original_hard_epoch']==budget['hard_epoch'])
denied('stop_no_replay',lambda:ad.stop_owned(worker=w,job_ref=jobref),'host_stop_consumed_no_replay')
class UnknownLaunch(FixtureBoundary):
 def launch_retained(self,*args):self.calls.append('launch');raise ValueError('SOURCE_FIXTURE_UNKNOWN_LAUNCH')
c=SyntheticContract();b=UnknownLaunch(c);ad=H.GateHostAdapter(contract=c,admission=token,loader=parent_loader,boundary=b)
denied('uncertain_launch_retains_one_way_reservation',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'SOURCE_FIXTURE_UNKNOWN_LAUNCH')
denied('uncertain_launch_no_retry',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'host_launch_consumed_no_replay')
yes('unknown_launch_original_retained_stop_not_guessed_PID',lambda:ad.stop_owned(worker=None,job_ref=jobref)['worker'] is None and b.calls.count('launch')==1)
class Store:
 def __init__(self,row):self.row=row;self.calls=[]
 def get(self,task,owner):self.calls.append((task,owner));return copy.deepcopy(self.row)
class ControllerFixture:
 def __init__(self,row):self.associations=Store(row);self.effects=0
 def prepare(self,*args):self.effects+=1;raise AssertionError('prepare_forbidden')
 def submit(self,*args):self.effects+=1;raise AssertionError('submit_forbidden')
owner={k:'SOURCE_FIXTURE_'+k for k in ['bot_id','user_id','chat_id','thread_id','message_id','session_id','session_key','profile']}
row=dict(existing_task_id='OWN',owner=owner,worker_kind='dsh',stop_intent=None,deadline_unix=budget['hard_epoch'])
ctl=ControllerFixture(row)
denied('existing_controller_DSH_NOT_gate_substitute',lambda:H.bind_existing_controller(ctl,task_id='OWN',owner=owner),'existing_gate_host_counterpart_UNBOUND')
yes('existing_controller_mapping_read_only_no_prepare_submit',lambda:ctl.effects==0 and ctl.associations.calls==[('OWN',owner)])
for key,value,cause in [('owner','OTHER','existing_association_owner_changed'),('stop_intent','pause','existing_association_stopped'),('deadline_unix',time.time()-1,'existing_association_original_deadline'),('deadline_unix',True,'existing_association_original_deadline')]:
 ctl=ControllerFixture(dict(row,**{key:value}));denied('existing_controller_'+key+'_'+str(value),lambda ctl=ctl:H.bind_existing_controller(ctl,task_id='OWN',owner=owner),cause)
# Attachment, closure and cleanup negatives remain pure synthetic host seams.
ad,b,c=session();ad.loader=worker_loader
ad.attach_worker(worker=process,job_ref=jobref)
yes('worker_controlled_attachment_before_configure_source_only',lambda:ad._worker==process and 'launch' not in b.calls)
denied('worker_attachment_no_replay',lambda:ad.attach_worker(worker=process,job_ref=jobref),'worker_attachment_consumed')
ad,b,c=session();ad.loader=worker_loader
denied('worker_attachment_wrong_actual_birth',lambda:ad.attach_worker(worker=dict(process,start_ticks=start+1),job_ref=jobref),'worker_attachment_actual_birth_mismatch')
def closed_session():
 ad,b,c=session();ad.launch_owned_source_worker(admission=token,job_ref=jobref);b.child.returncode=0;c.absent=True;return ad,b,c,dict(pid=c.fake_pid,start_ticks=c.fake_start)
for key,value,cause in [('worker',process,'host_actual_closure_observation_required'),('job',dict(jobref,sha256='0'*64),'host_actual_closure_observation_required'),('owned_obligations_observed',False,'host_actual_closure_observation_required'),('retained_until_reap',False,'host_closure_unclosed'),('exact_worker_absent',False,'host_closure_unclosed'),('worker_reaped',False,'host_closure_unclosed'),('owned_children',[123],'host_closure_unclosed'),('closure_ref',dict(jobref,path=str(fixtures/'outside.json')),'host_foreign_closure')]:
 ad,b,c,w2=closed_session();original=b.observe_closed
 b.observe_closed=lambda worker,job,key=key,value=value,original=original:dict(original(worker,job),**{key:value})
 denied('captured_host_closure_'+key,lambda ad=ad,w2=w2:ad.capture_worker_closure(worker=w2,job_ref=jobref),cause)
 denied('failed_host_closure_no_retry_'+key,lambda ad=ad,w2=w2:ad.capture_worker_closure(worker=w2,job_ref=jobref),'host_closure_consumed_no_replay')
for key,value,cause in [('FD_delta',True,'worker_obligations_unclosed'),('children',[123],'worker_obligations_unclosed'),('threads',['MainThread','left'],'worker_obligations_unclosed'),('approved_affinity',['CPU'],'closure_approved_affinity_changed'),('output_bytes',limits['output_bytes']+1,'closure_output_bound'),('ended_epoch',budget['hard_epoch']+1,'closure_outside_original_budget'),('runtime_grant',True,'closure_false_authority')]:
 bad=dict(closure,**{key:value});Path(a['output_root'],'WORKER-CLOSURE.json').write_bytes(C.canonical(bad));ad,b,c,w2=closed_session()
 denied('worker_authored_closure_'+key+'_fails_join',lambda ad=ad,w2=w2:ad.capture_worker_closure(worker=w2,job_ref=jobref),cause)
Path(a['output_root'],'WORKER-CLOSURE.json').write_bytes(C.canonical(closure))
for key,value in [('worker',process),('job',dict(jobref,sha256='0'*64)),('original_hard_epoch',budget['hard_epoch']+1),('pending_launch_settled',False),('exact_owned_only',False),('retained_until_reap',False),('owned_children',[123]),('worker_reaped',False),('exact_worker_absent',False)]:
 ad,b,c,w2=closed_session();original=b.stop_owned
 b.stop_owned=lambda worker,job,deadline,key=key,value=value,original=original:dict(original(worker,job,deadline),**{key:value})
 denied('retained_cleanup_'+key+'_unconfirmed',lambda ad=ad,w2=w2:ad.stop_owned(worker=w2,job_ref=jobref),'STOP_UNCONFIRMED')
 denied('uncertain_cleanup_no_retry_'+key,lambda ad=ad,w2=w2:ad.stop_owned(worker=w2,job_ref=jobref),'host_stop_consumed_no_replay')
ad,b,c=session();ad.loader=worker_loader
denied('worker_loader_cannot_launch_parent_subtree',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'host_parent_loader_required')
ad,b,c=session()
denied('parent_loader_cannot_attach_as_worker',lambda:ad.attach_worker(worker=process,job_ref=jobref),'host_worker_loader_required')
# Direct adapter APIs also bind the real concrete loader before delegated effects.
other_binding=dict(binding,binding_sha256='b'*64)
other_loader=loader(binding=other_binding);other_loader.load_entrypoint()
ad,b,c=session();ad.loader=other_loader
denied('direct_adapter_stale_loader_before_launch',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'loader_original_binding_changed')
yes('stale_loader_prevents_boundary_launch',lambda:'launch' not in b.calls)
class ShapeLoader:
 def capture_loaded_implementation(self,**kw):return ()
ad,b,c=session();ad.loader=ShapeLoader()
denied('direct_adapter_method_shape_not_concrete_attachment',lambda:ad.verify_retained(ctx),'concrete_retained_loader_attachment_required')
for key,val in [('path','/wrong/interpreter'),('bytes',True),('sha256','bad')]:
 bad=copy.deepcopy(implementation);bad['interpreter'][key]=val
 denied('preload_interpreter_schema_'+key,lambda bad=bad:loader(implementation=bad,interpreter_provenance=C.canonical(bad['interpreter'])),'preload_interpreter_pin_schema')
ad,b,c,w2=closed_session();ad.loader=ShapeLoader()
yes('retained_owned_stop_survives_damaged_loader',lambda:ad.stop_owned(worker=dict(pid=c.fake_pid,start_ticks=c.fake_start),job_ref=jobref)['status']=='STOP_CONFIRMED' and b.calls[-1]=='stop')
ad,b,c,w2=closed_session();ad.boundary=object()
yes('retained_owned_stop_uses_original_owner_after_routing_damage',lambda:ad.stop_owned(worker=dict(pid=c.fake_pid,start_ticks=c.fake_start),job_ref=jobref)['status']=='STOP_CONFIRMED' and b.calls[-1]=='stop')
ad,b,c=session();ad.boundary=FixtureBoundary(c)
denied('boundary_replacement_cannot_launch',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jobref),'existing_host_boundary_replaced')
ad,b,c=session()
denied('no_checked_owner_cannot_mint_cleanup',lambda:ad.stop_owned(worker=None,job_ref=jobref),'retained_owned_cleanup_unavailable')
yes('actual_host_status_remains_UNBOUND',lambda:H.existing_host_source_status()['status']=='UNBOUND' and H.existing_host_source_status()['runtime_grant'] is False)
yes('helper_actual_FD_count_restored',lambda:len(list(Path('/proc/self/fd').iterdir()))==fds)
yes('helper_actual_children_threads_closed',lambda:Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip()=='' and len(threading.enumerate())==1)
report=dict(schema='friday.sol.host-adapter-author-controls.v1',status='AUTHOR_INERT_SOURCE_PASS',count=len(cases),cases=cases,elapsed_seconds=time.monotonic()-begin,source_snapshot={p.name:C.pin(p) for p in PKG.glob('*.py')},original_clock=clockref,actual_loaded_buffers='concrete RetainedLoader loads exact retained original4 into its own namespaces; code/namespace/binding drift refuses',interpreter_provenance='SYNTHETIC_SOURCE_INPUT_NOT_REAL_HOST_AUTHENTICATION',host_boundary_and_child_observations='SYNTHETIC_PURE_SOURCE_STATE_MACHINE_NOT_AUTHORITY',actual_existing_host_adapter='UNBOUND',target_checkers_executed=0,product_imports=0,whole_gate='NOT_RUN_NOT_GRANTED',independent_acceptance=False,runtime_grant=False,FD_delta=0,children=0,threads=1,resources=dict(affinity=cpus,AS_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
(OUT/'AUTHOR-CONTROLS.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(count=len(cases),status=report['status'])))
