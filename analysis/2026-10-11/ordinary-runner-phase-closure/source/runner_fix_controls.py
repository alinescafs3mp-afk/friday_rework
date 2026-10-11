#!/usr/bin/env python3
"""Finite AUTHOR pure stdlib controls. Synthetic receipts are never authority."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time

OUT = Path(sys.argv[1]).absolute(); INPUT = Path(sys.argv[2]).absolute(); PKG = Path(__file__).parent
resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (60, 60)); resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
cpus = sorted(os.sched_getaffinity(0))[:2]; os.sched_setaffinity(0, cpus)
stat_text = Path('/proc/self/stat').read_text(); start = int(stat_text[stat_text.rfind(')') + 2:].split()[19])
(OUT/'READY.json').write_text(json.dumps({'pid': os.getpid(), 'start_ticks': start, 'affinity': cpus, 'address_space_bytes': 384*1024**2}))
while not (OUT/'BARRIER.json').exists(): time.sleep(.01)
barrier = json.loads((OUT/'BARRIER.json').read_text()); assert barrier['pid'] == os.getpid() and barrier['start_ticks'] == start
begin = time.monotonic(); initial_fds = len(list(Path('/proc/self/fd').iterdir()))

def own_audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.system', 'os.posix_spawn', 'os.fork', 'pty.')):
        raise AssertionError('own_helper_effect_forbidden:' + event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        mode, flags = args[1] or '', args[2] or 0
        if any(c in mode for c in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            raw = Path(os.fsdecode(args[0]))
            # Rooted writer dir_fd uses a basename; these descriptors come only
            # from tested own helper inside OUT. It is no product/kernel proof.
            if raw.is_absolute(): assert raw.resolve().is_relative_to(OUT), ('outside_own_output', raw)
    if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod') and isinstance(args[0], (str, bytes)):
        raw = Path(os.fsdecode(args[0])); assert not raw.is_absolute() or raw.resolve().is_relative_to(OUT)

sys.addaudithook(own_audit)
def load(name):
    p = PKG/(name+'.py'); spec = importlib.util.spec_from_file_location('fix_'+name,p)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
# Retain immutable source bytes BEFORE loading the modules. This is an OWN
# pure loader fixture, never an authenticated existing-host implementation.
SOURCE_BUFFERS = {n:(PKG/n).read_bytes() for n in
                  ('runner_contract.py', 'source_runner.py', 'runner_worker.py', 'gate_inputs.py')}
C=load('runner_contract');R=load('source_runner');W=load('runner_worker')
INTERPRETER_PROVENANCE = C.canonical(C.pin(Path('/proc/self/exe').resolve()))
class SourceFixtureLoader:
    def __init__(self, root=PKG, buffers=None, parent=R, worker_module=W, bad=None):
        self.root=root; self.buffers=dict(SOURCE_BUFFERS if buffers is None else buffers)
        self.parent=parent; self.worker_module=worker_module; self.bad=bad; self.calls=[]
    def capture_loaded_implementation(self, *, context, namespace):
        assert namespace is (self.parent.__dict__ if context['actor']=='parent' else self.worker_module.__dict__)
        self.calls.append(context['phase'])
        loaded={'source_runner.py','gate_inputs.py','runner_contract.py'} if context['actor']=='parent' else {'runner_worker.py','runner_contract.py'}
        sources=tuple((name,str(self.root/name),buffer,'loaded' if name in loaded else 'retained_launch_image')
                      for name,buffer in sorted(self.buffers.items()))
        if self.bad in self.buffers:
            sources=tuple((n,p,b+b'\n# loaded drift\n',st) if n==self.bad else (n,p,b,st) for n,p,b,st in sources)
        joined=C.canonical(context)
        interpreter=INTERPRETER_PROVENANCE
        if self.bad=='interpreter': interpreter=b'{}'
        if self.bad=='context': joined=b'{}'
        if self.bad in ('grant','process'):
            stale=copy.deepcopy(context)
            if self.bad=='grant': stale['binding']['grant']['sha256']='0'*64
            else: stale['process']['start_ticks']-=1
            joined=C.canonical(stale)
        if self.bad=='state': sources=tuple((n,p,b,'retained_launch_image') for n,p,b,st in sources)
        if self.bad=='mutable': return {'SELF_AUTHORED_JSON':True}
        if self.bad=='mutable_buffer': sources=tuple((n,p,bytearray(b),st) for n,p,b,st in sources)
        return joined,sources,interpreter
LOADER=SourceFixtureLoader()
CASES=[]
def check(name, fn):
    assert time.monotonic() < barrier['hard_monotonic'], 'original_helper_deadline'
    value=fn(); CASES.append({'name':name,'status':'AUTHOR_PURE_SOURCE_PASS','observation':value})
def yes(name, fn):
    def run():
        v=fn();assert v is True,(name,v);return True
    check(name,run)
def denied(name, fn, cause):
    def run():
        try:fn()
        except (ValueError,OSError,KeyError,TypeError) as e:
            assert cause in str(e),(name,cause,str(e));return {'refusal':str(e)}
        raise AssertionError('did_not_refuse:'+name)
    check(name,run)
def write(path,data):path.write_bytes(data);return C.pin(path)

fixtures=OUT/'fixtures';fixtures.mkdir(mode=0o700)
source_root=fixtures/'accepted-checkers';source_root.mkdir(mode=0o700);(source_root/'catalog').mkdir(mode=0o700)
checker=source_root/'catalog/pure_checker.py'
checker_ref=write(checker,("ROOT="+repr(str(source_root))+"\nVALUE='ORIGINAL'\n").encode())
aux_ref=write(fixtures/'A.json',b'{"value":"original"}\n')
clock_ref=C.pin(INPUT);clock=C.document(clock_ref)
budget={'start_epoch':__import__('datetime').datetime.fromisoformat(clock['accepted_msk']).timestamp(),
        'seconds':clock['original_seconds'],'cleanup_seconds':clock['cleanup_seconds'],
        'hard_epoch':clock['hard_epoch'],'clock_ref':clock_ref}
limits={'CPUs':2,'worker_address_space_bytes':1024**3,'aggregate_address_space_bytes':1024**3+96*1024**2,'output_bytes':1024**2}
relocation={'binding_sha256':'a'*64,'checkers':[{'kind':'catalog','after':checker_ref}]}
relocation_ref=write(fixtures/'relocation.json',C.canonical(relocation))
grant_ref=write(fixtures/'grant.json',b'{"SOURCE_FIXTURE_ONLY":true}\n')
anchor=write(fixtures/'anchor.json',b'{"SOURCE_FIXTURE_ONLY":true}\n')
slot_ref=write(fixtures/'slot.json',b'{"SOURCE_FIXTURE_ONLY":true}\n')
implementation={name:C.pin(PKG/name) for name in ('source_runner.py','runner_worker.py','runner_contract.py','gate_inputs.py')}
implementation['interpreter']=C.pin(Path(sys.executable).resolve())
pins={'grant':grant_ref,'relocation':relocation_ref,'source_anchor':anchor,'slot_receipt':slot_ref,'clock':clock_ref,
      **{'implementation:'+n:r for n,r in implementation.items()}}
scope={'files':[checker_ref,aux_ref,*pins.values()],'roots':[]}
# clock appears only once; implementation refs and fixtures have unique paths.
base={'schema':'friday.source-run-admission.v2','kind':'catalog-filtered','binding_sha256':'a'*64,
      'checker':checker_ref,'auxiliary':{'A.json':aux_ref},'pins':pins,'read_scope':scope,
      'implementation':implementation,'loaded_identity':C.canonical(implementation).decode(), 'approved_affinity':cpus,
      'relocation':relocation,'budget':budget,'resources':limits,
      'exclusive_slot':{'receipt':slot_ref,'owner_pid':os.getpid(),'owner_start_ticks':start},
      'output_root':str(OUT/'prepared'), 'runtime_grant':False,'independent_acceptance':False,
      'SOURCE_FIXTURE_ONLY':True}

yes('original_budget_and_1GiB_checker_resources_retained', lambda:C.budget_limits(budget)[0]==budget['hard_epoch'] and C.resources(limits)==limits)
check('original_pins_verified_immutable_buffer', lambda:C.revalidate_inputs(base).decode())
check('exact_admitted_implementation_and_interpreter',lambda:R.implementation_pins(implementation,loader=LOADER).decode())
job_ref=R.materialize_job(base);job,buffer=C.verify_job(job_ref,base['output_root'],C.digest(C.canonical(base)))
yes('materialized_exact_rebinding_positive',lambda:job['root_edits']==[{'old':str(source_root),'new':base['output_root']}])
yes('copied_auxiliary_keeps_original_digest_size',lambda:job['auxiliary']['A.json']['sha256']==aux_ref['sha256'] and job['auxiliary']['A.json']['bytes']==aux_ref['bytes'])
yes('pure_synthetic_checker_original_body_executes',lambda:W.execute_bytes(buffer,job['checker']['path'])['VALUE']=='ORIGINAL')
main_before=sys.modules['__main__']; argv_before=sys.argv[:]
state=W.execute_bytes(b"import sys\nSAME = sys.modules['__main__'].__dict__ is globals()\nARG0 = sys.argv[0]\nraise SystemExit(0)\n",job['checker']['path'])
yes('verified_exec_retains_main_and_argv_semantics',lambda:state['SAME'] and state['ARG0']==job['checker']['path'] and sys.modules['__main__'] is main_before and sys.argv==argv_before)
denied('verified_exec_nonzero_exit_refuses',lambda:W.execute_bytes(b'raise SystemExit(1)\n',job['checker']['path']),'checker_nonzero_exit')
json_path=fixtures/'immutable-json.json';original_json=write(json_path,b'{"value":"ORIGINAL"}\n');reader=R.gate.bytes_at;calls=[]
def read_then_mutate(path):
    data=reader(path);calls.append(str(path));json_path.write_bytes(b'{"value":"CHANGED"}\n');return data
R.gate.bytes_at=read_then_mutate
try:value=R.gate.check_ref(original_json,'immutable_buffer')
finally:R.gate.bytes_at=reader
yes('gate_JSON_single_verified_buffer_no_reopen',lambda:value=={'value':'ORIGINAL'} and len(calls)==1)
denied('next_JSON_use_rejects_drift_not_repin',lambda:R.gate.check_ref(original_json),'changed_ref')
original=checker.read_bytes();checker.write_bytes(original.replace(b'ORIGINAL',b'CHANGED!'))
denied('checker_changed_after_admission_before_barrier',lambda:C.verify_job(job_ref,base['output_root'],C.digest(C.canonical(base))),'changed_ref:approved_read_input')
checker.write_bytes(original)
for name,ref in [('auxiliary',aux_ref),('grant',grant_ref),('relocation',relocation_ref),('anchor',anchor),('slot',slot_ref)]:
    p=Path(ref['path']);data=p.read_bytes();p.write_bytes(data+b' ')
    denied(name+'_drift_before_barrier_never_repinned',lambda:C.revalidate_inputs(base),'changed_ref')
    p.write_bytes(data)
private_checker=Path(job['checker']['path']);saved=private_checker.read_bytes();private_checker.write_bytes(saved.replace(b'ORIGINAL',b'CHANGED!'))
denied('private_checker_changed_after_barrier',lambda:C.verify_job(job_ref,base['output_root'],C.digest(C.canonical(base))),'changed_ref:job_checker')
yes('verified_source_buffer_cannot_be_reopened_to_mutant',lambda:W.execute_bytes(buffer,job['checker']['path'])['VALUE']=='ORIGINAL')
private_checker.write_bytes(saved)
copy_aux=Path(job['auxiliary']['A.json']['path']);saved=copy_aux.read_bytes();copy_aux.write_bytes(b'{}\n')
denied('copied_auxiliary_drift_after_barrier',lambda:C.verify_job(job_ref,base['output_root'],C.digest(C.canonical(base))),'changed_ref:job_auxiliary')
copy_aux.write_bytes(saved)
p=Path(job_ref['path']);saved=p.read_bytes();p.write_bytes(saved+b' ')
denied('JOB_bytes_changed_after_parent_pin',lambda:C.verify_job(job_ref,base['output_root'],C.digest(C.canonical(base))),'changed_ref:job')
p.write_bytes(saved)
denied('admission_digest_changed_refuses',lambda:C.verify_job(job_ref,base['output_root'],'0'*64),'changed_admission')
mutant=copy.deepcopy(job);mutant['auxiliary']['A.json']['sha256']='0'*64
mut_ref=write(fixtures/'mutant-job.json',C.canonical(mutant))
denied('repinned_JOB_auxiliary_not_authority',lambda:C.verify_job(mut_ref,base['output_root'],C.digest(C.canonical(base))),'job_auxiliary_repin')
mutant=copy.deepcopy(base);mutant['resources']['CPUs']=1
mut_ref=write(fixtures/'mutant-limits-job.json',C.canonical(dict(job,admission=mutant)))
denied('changed_resources_bound_to_original_admission',lambda:C.verify_job(mut_ref,base['output_root'],C.digest(C.canonical(base))),'changed_admission')
denied('repeat_output_refuses_before_replay',lambda:R.materialize_job(base),'owned_run_output_exists_no_replay')
# Test private copies for implementation drift; accepted source files stay intact.
worker_copy=write(fixtures/'worker-copy.py',b'VALUE=1\n');m=copy.deepcopy(base);m['pins']['implementation:runner_worker.py']=worker_copy
Path(worker_copy['path']).write_bytes(b'VALUE=2\n')
denied('worker_drift_after_barrier',lambda:C.revalidate_inputs(m),'changed_ref:implementation:runner_worker.py')
for key in ('source_runner.py','gate_inputs.py','runner_contract.py','interpreter'):
    values=copy.deepcopy(implementation);values[key]['sha256']='0'*64
    denied('pinned_'+key+'_digest_refuses',lambda values=values:R.implementation_pins(values),'changed_ref')

write_root=fixtures/'write-root';write_root.mkdir(mode=0o700);outside=fixtures/'outside';outside.mkdir(mode=0o700)
write_ref=C.rooted_write(write_root,'document.bin',b'EXACT')
yes('rooted_real_positive_bytes',lambda:C.verify(write_ref)==b'EXACT')
denied('rooted_output_no_replay',lambda:C.rooted_write(write_root,'document.bin',b'changed'),'File exists')
for name in ('../outside/escape','sub/../../outside/escape'):
    denied('rooted_traversal_'+name,lambda name=name:C.rooted_write(write_root,name,b'NO'),'path_traversal')
denied('nonexclusive_write_cannot_truncate_hardlink',lambda:C.rooted_write(write_root,'document.bin',b'NO',exclusive=False),'nonexclusive_rooted_write_forbidden')
denied('absolute_output_name',lambda:C.rooted_write(write_root,str(outside/'escape'),b'NO'),'absolute_output_name')
(write_root/'link').symlink_to(outside,target_is_directory=True)
denied('symlink_parent_escape',lambda:C.rooted_write(write_root,'link/escape',b'NO'),'symlink_component')
(write_root/'final-link').symlink_to(outside/'never')
denied('symlink_final_escape',lambda:C.rooted_write(write_root,'final-link',b'NO'),'symlink_component')
yes('negative_write_canaries_untouched',lambda:not (outside/'escape').exists() and not (outside/'never').exists())
policy=C.AuditPolicy(write_root,{'files':[aux_ref],'roots':[str(source_root)]})
yes('approved_exact_read_positive',lambda:policy.read(aux_ref['path'])==Path(aux_ref['path']))
yes('approved_root_read_positive',lambda:policy.read(checker)==checker)
denied('foreign_read_refuses',lambda:policy.read(outside/'secret'),'outside_approved_read_scope')
denied('relative_read_cannot_hide_dir_fd',lambda:policy.check('open',('file', 'r',os.O_RDONLY)),'relative_or_descriptor_read_forbidden')
denied('relative_write_cannot_hide_open_dir_fd',lambda:policy.check('open',('file','w',os.O_WRONLY|os.O_CREAT)),'relative_or_descriptor_mutation_forbidden')
denied('foreign_descriptor_open',lambda:policy.check('open',(99,'w',os.O_WRONLY)),'foreign_descriptor_open')
for event,args in [('os.mkdir',(str(write_root/'new'),0o700,99)),('os.remove',(str(write_root/'document.bin'),99)),
                   ('os.rename',(str(write_root/'document.bin'),str(write_root/'renamed'),99,-1)),
                   ('os.link',(str(write_root/'document.bin'),str(write_root/'linked'),-1,99)),
                   ('os.chmod',(str(write_root/'document.bin'),0o600,99))]:
    denied(event+'_foreign_dir_fd',lambda event=event,args=args:policy.check(event,args),'foreign_dir_fd_mutation')
check('absolute_owned_mkdir_audit_positive',lambda:policy.check('os.mkdir',(str(write_root/'new'),0o700,-1)))
denied('fd_truncate_refuses',lambda:policy.check('os.truncate',(99,0)),'relative_or_descriptor_mutation_forbidden')
denied('new_symlink_refuses',lambda:policy.check('os.symlink',(str(outside),str(write_root/'another'),-1)),'symlink_mutation_forbidden')
for event in ('socket.connect','subprocess.Popen','os.fork','os.exec','ctypes.dlopen','mmap.__new__', 'fcntl.fcntl', 'os.kill', 'os.chroot'):
    denied(event+'_effect_refuses',lambda event=event:policy.check(event,()),'native_runtime_effect_forbidden')
for event in ('os.setxattr', 'os.removexattr', 'os.chflags'):
    denied(event+'_foreign_descriptor_mutation',lambda event=event:policy.check(event,(99,)), 'relative_or_descriptor_mutation_forbidden')
denied('read_root_slash_unbounded',lambda:C.read_scope({'files':[aux_ref],'roots':['/']}),'unbounded_or_missing_read_root')
denied('read_scope_source_drift',lambda:C.read_scope({'files':[dict(aux_ref,sha256='0'*64)],'roots':[]}),'changed_ref')

for adapter in (None,{'state':'HELD','owner_pid':os.getpid(),'owner_start_ticks':start,'kernel_custody':True}):
    denied('JSON_livePID_is_not_actual_custody_'+str(type(adapter)),lambda adapter=adapter:C.require_custody(adapter,base,'before_launch'),'existing_host_custody_adapter_unavailable')
# Actual runner/worker refusal paths, with a declared synthetic admission
# preflight seam for the parent only. No positive execution grant is supplied.
revalidate_original=R.revalidate; prepare_original=R.prepare_job; effects=[]
R.revalidate=lambda token,**kwargs:base
R.prepare_job=lambda token:effects.append('FORBIDDEN_PREPARE_EFFECT')
try:
    denied('parent_execute_without_custody_before_any_output',lambda:R.execute(C.canonical(base)),'existing_host_custody_adapter_unavailable')
finally:
    R.revalidate=revalidate_original;R.prepare_job=prepare_original
before_names=sorted(Path(base['output_root']).iterdir());before_as=resource.getrlimit(resource.RLIMIT_AS)
denied('worker_run_without_custody_before_ready_or_limits',lambda:W.run(base['output_root'],job_ref,C.digest(C.canonical(base)),loader=LOADER),'existing_host_custody_adapter_unavailable')
yes('both_refusals_have_zero_launch_write_or_limit_effect',lambda:not effects and sorted(Path(base['output_root']).iterdir())==before_names and resource.getrlimit(resource.RLIMIT_AS)==before_as)
class SourceFixtureVerifier:
    """Synthetic interface unit seam. No actual host lock/custody/runtime grant."""
    def __init__(self,bad=None):self.bad=bad
    def verify_retained(self,context):
        o={'context':context,'owner':{'pid':os.getpid(),'start_ticks':start}}
        for k in ('actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins',
                  'kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap'):o[k]=True
        if self.bad=='context':o['context']=dict(context,output_root='foreign')
        elif self.bad=='owner':o['owner']={'pid':os.getpid(),'start_ticks':start-1}
        elif self.bad:o[self.bad]=False
        worker=context['worker']
        o['resource_observation']={'worker':worker,'job':context['job'], 'approved_affinity':cpus,
            'available_affinity':cpus, 'observed_limits':None if worker is None else
            {'affinity':cpus,'address_space_bytes':[limits['worker_address_space_bytes']]*2,
             'CPU_seconds':[60]*2,'file_size_bytes':[limits['output_bytes']]*2}}
        return o
check('custody_interface_context_positive_SYNTHETIC_ONLY',lambda:C.require_custody(SourceFixtureVerifier(),base,'before_barrier',{'pid':123,'start_ticks':456})['context'])
for key in ('actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins',
            'kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap'):
    denied('custody_'+key+'_missing',lambda key=key:C.require_custody(SourceFixtureVerifier(key),base,'before_barrier'),'custody_not_proven:'+key)
denied('custody_context_stale',lambda:C.require_custody(SourceFixtureVerifier('context'),base,'before_barrier'),'custody_context_mismatch')
denied('custody_owner_stale',lambda:C.require_custody(SourceFixtureVerifier('owner'),base,'before_barrier'),'custody_owner_mismatch')

worker={'pid':123,'start_ticks':456};now=time.time()
closure={'schema':'friday.source-worker-closure.v2','worker':worker,'job':job_ref,'completed':True,
         'approved_affinity':cpus,'children':[],'threads':['MainThread'],'FD_delta':0,'resources':limits,'original_budget':budget,
         'ended_epoch':now,'output_bytes':100,'runtime_grant':False,'independent_acceptance':False,
         'observed_limits':{'affinity':cpus,'address_space_bytes':[1024**3]*2,'CPU_seconds':[60]*2,'file_size_bytes':[1024**2]*2}}
record={'exit_code':0,'worker_reaped':True}
def finish(c=closure,r=record,absent=True,children=None,at=None):
    return C.completion(r,c,job_ref,worker,budget,limits,now+.01 if at is None else at,absent,[] if children is None else children,
        trusted_resources={'worker':worker,'job':job_ref,'approved_affinity':cpus,'available_affinity':cpus,'observed_limits':closure['observed_limits']}, approved_affinity=cpus)
yes('exact_closure_completion_positive_SYNTHETIC_ONLY',lambda:finish())
denied('early_zero_exit_no_closure_is_failure',lambda:finish(None),'missing_or_invalid_worker_closure')
for key,value,cause in [('worker',{'pid':124,'start_ticks':456},'stale_worker_closure'),
                        ('job',dict(job_ref,sha256='0'*64),'stale_worker_closure'),('completed',False,'worker_obligations_unclosed'),
                        ('children',['child'],'worker_obligations_unclosed'),('threads',['MainThread','late'],'worker_obligations_unclosed'),
                        ('FD_delta',1,'worker_obligations_unclosed'),('resources',dict(limits,CPUs=1),'closure_limits_changed'),
                        ('original_budget',dict(budget,seconds=2401),'closure_limits_changed'),('runtime_grant',True,'closure_false_authority'),
                        ('output_bytes',limits['output_bytes']+1,'closure_output_bound'),('ended_epoch',budget['hard_epoch']+1,'closure_outside_original_budget'),
                        ('observed_limits',{},'worker_resource_observation_mismatch')]:
    c=copy.deepcopy(closure);c[key]=value
    denied('closure_'+key+'_negative',lambda c=c:finish(c),cause)
denied('exit_zero_unreaped_fails',lambda:finish(r={'exit_code':0,'worker_reaped':False}),'worker_exit_not_success')
denied('failure_even_with_zero_exit_fails',lambda:finish(r=dict(record,failure='early')),'worker_exit_not_success')
denied('worker_birth_still_present_fails',lambda:finish(absent=False),'worker_or_supervisor_birth_remaining')
denied('supervisor_children_remain_fails',lambda:finish(children=['123']),'worker_or_supervisor_birth_remaining')
denied('hard_deadline_overrun_fails',lambda:finish(at=budget['hard_epoch']+1),'closure_outside_original_budget')
for key,value,cause in [('start_epoch',budget['start_epoch']+1,'original_clock_start_reset'),
                        ('seconds',budget['seconds']+1,'original_clock_budget_mismatch'),
                        ('hard_epoch',budget['hard_epoch']+1,'original_budget_changed'),('cleanup_seconds',60,'original_clock_budget_mismatch')]:
    b=copy.deepcopy(budget);b[key]=value
    denied('original_budget_'+key+'_no_reset',lambda b=b:C.budget_limits(b),cause)
for key,value,cause in [('CPUs',1,'source_checker_original_1GiB_resource_unavailable'),
                        ('worker_address_space_bytes',384*1024**2,'source_checker_original_1GiB_resource_unavailable'),
                        ('aggregate_address_space_bytes',1024**3,'aggregate_resource_undeclared'),('output_bytes',1,'output_bound_schema')]:
    l=dict(limits);l[key]=value
    denied('resource_'+key+'_no_weakening',lambda l=l:C.resources(l),cause)
yes('output_inventory_actual_positive',lambda:C.output_inventory(Path(base['output_root']),limits['output_bytes'])['total_bytes']>0)
denied('output_actual_aggregate_bound',lambda:C.output_inventory(Path(base['output_root']),1),'aggregate_output_bound')
denied('output_symlink_inventory_refuses',lambda:C.output_inventory(write_root,limits['output_bytes']),'symlink_component')

# New integrity negatives and valid source positives; no adapter-positive target
# execution. All observations below are explicit author fixture seams.
for absent_loader in (None, {'capture_loaded_implementation': 'SELF_AUTHORED_JSON'}):
    denied('loaded_source_cannot_be_inferred_without_live_loader_'+str(type(absent_loader)),
           lambda absent_loader=absent_loader:R.implementation_pins(implementation,loader=absent_loader),
           'authenticated_existing_loader_unavailable')
for bad,cause in [('source_runner.py','loaded_implementation_changed:source_runner.py'),
                  ('runner_worker.py','loaded_implementation_changed:runner_worker.py'),
                  ('runner_contract.py','loaded_implementation_changed:runner_contract.py'),
                  ('gate_inputs.py','loaded_implementation_changed:gate_inputs.py'),
                  ('interpreter','loaded_interpreter_changed'),('context','loaded_context_mismatch'),
                  ('state','loaded_image_state'),('mutable','immutable_loader_observation_required'),
                  ('mutable_buffer','immutable_loaded_buffer_required')]:
    denied('parent_loaded_'+bad+'_before_admission',lambda bad=bad:R.implementation_pins(implementation,loader=SourceFixtureLoader(bad=bad)),cause)
for actor,namespace in [('parent',R.__dict__),('worker',W.__dict__)]:
    yes(actor+'_retained_loader_buffer_positive_SOURCE_FIXTURE_ONLY',
        lambda actor=actor,namespace=namespace:C.loaded_implementation(LOADER,implementation,'after_barrier',actor,namespace,'a'*64,worker)==C.canonical(implementation))
    for bad in ('source_runner.py','runner_worker.py','interpreter'):
        cause='loaded_interpreter_changed' if bad=='interpreter' else 'loaded_implementation_changed:'+bad
        denied(actor+'_loaded_drift_after_barrier_'+bad,
            lambda actor=actor,namespace=namespace,bad=bad:C.loaded_implementation(SourceFixtureLoader(bad=bad),implementation,'after_barrier',actor,namespace,'a'*64,worker),cause)
# Exercise the actual admit and revalidate entrypoints with only the product
# inventory source_preflight replaced by exact declared tiny-fixture assertions.
admit_root=fixtures/'full-admit';admit_root.mkdir(mode=0o700)
slot=write(admit_root/'slot.json',C.canonical({'state':'HELD','binding_sha256':'a'*64,'owner_pid':os.getpid(),'owner_start_ticks':start}))
full_grant={'schema':'friday.known-source-checker-grant-root-received.v2','independent_source_accepted':True,
    'SOURCE_FIXTURE_ONLY':True,'runtime_grant':False,'binding_sha256':'a'*64,'relocation':relocation_ref,
    'allowed_kinds':['catalog-filtered'],'output_root':str(admit_root/'prepared'),
    'root_only_output_relocation_accepted':True,'original_budget':budget,'resources':limits,
    'exclusive_slot':{'receipt':slot,'owner_pid':os.getpid(),'owner_start_ticks':start},
    'implementation':implementation,'approved_affinity':cpus,'read_scope':{'files':[checker_ref,*implementation.values()],'roots':[]},
    'auxiliary_inputs':{}}
full_grant_ref=write(admit_root/'grant.json',C.canonical(full_grant))
tiny_inputs={'SOURCE_FIXTURE_ONLY':True};tiny_binding={'binding_sha256':'a'*64};preflight_calls=[]
def tiny_preflight(inputs,binding,source_anchor):
    assert inputs==tiny_inputs and binding==tiny_binding and source_anchor==anchor
    preflight_calls.append('tiny-fixture-preflight')
preflight=R.gate.source_preflight;R.gate.source_preflight=tiny_preflight
try:
    def full_admit(loader=LOADER):
        return R.admit(tiny_inputs,tiny_binding,anchor,relocation_ref,full_grant_ref,full_grant_ref,
            'catalog-filtered',full_grant['output_root'],loader=loader)
    token=full_admit()
    yes('actual_admit_valid_loader_positive_SOURCE_FIXTURE_ONLY',lambda:R.decode_admission(token)['loaded_identity']==C.canonical(implementation).decode())
    yes('actual_revalidate_valid_loader_positive_SOURCE_FIXTURE_ONLY',lambda:R.revalidate(token,loader=LOADER,phase='after_barrier')['approved_affinity']==cpus)
    for bad in ('grant','process'):
        denied('actual_admit_stale_loader_'+bad,lambda bad=bad:full_admit(SourceFixtureLoader(bad=bad)),'loaded_context_mismatch')
        denied('actual_revalidate_stale_loader_'+bad+'_after_barrier',lambda bad=bad:R.revalidate(token,loader=SourceFixtureLoader(bad=bad),phase='after_barrier'),'loaded_context_mismatch')
    denied('actual_admit_parent_loaded_drift_before_admit',lambda:full_admit(SourceFixtureLoader(bad='source_runner.py')),'loaded_implementation_changed:source_runner.py')
    denied('actual_revalidate_parent_loaded_drift_after_barrier',lambda:R.revalidate(token,loader=SourceFixtureLoader(bad='source_runner.py'),phase='after_barrier'),'loaded_implementation_changed:source_runner.py')
    denied('actual_revalidate_worker_launch_image_drift_after_barrier',lambda:R.revalidate(token,loader=SourceFixtureLoader(bad='runner_worker.py'),phase='after_barrier'),'loaded_implementation_changed:runner_worker.py')
    for label,aff,cause in [('bool',[True],'affinity_cpu_type'),('string',['CPU'],'affinity_cpu_type'),('negative',[-1],'affinity_cpu_type'),('duplicates',[cpus[0],cpus[0]],'affinity_duplicate_cpu')]:
        bad_grant=dict(full_grant,approved_affinity=aff)
        bad_ref=write(admit_root/('bad-affinity-'+label+'.json'),C.canonical(bad_grant))
        denied('actual_admit_malformed_approved_affinity_'+label,lambda bad_ref=bad_ref:R.admit(tiny_inputs,tiny_binding,anchor,relocation_ref,bad_ref,bad_ref,'catalog-filtered',full_grant['output_root'],loader=LOADER),cause)
    calls_before=len(preflight_calls)
    denied('actual_admit_absent_authenticated_loader_before_preflight',lambda:full_admit(None),'authenticated_existing_loader_unavailable')
    yes('missing_loader_has_zero_preflight_or_output_effect',lambda:len(preflight_calls)==calls_before and not Path(full_grant['output_root']).exists())
    denied('actual_execute_absent_loader_before_prepare_launch',lambda:R.execute(token),'authenticated_existing_loader_unavailable')
    denied('actual_execute_loader_positive_but_custody_missing_before_output',lambda:R.execute(token,loader=LOADER),'existing_host_custody_adapter_unavailable')
    yes('execute_refusals_do_not_create_output',lambda:not Path(full_grant['output_root']).exists())
finally:R.gate.source_preflight=preflight
# Loaded original parent + later changed disk + repinned grant is the original
# independent counterexample. Run it against a PRIVATE module cohort only.
copy_root=fixtures/'loaded-cohort';copy_root.mkdir(mode=0o700)
for n,b in SOURCE_BUFFERS.items():(copy_root/n).write_bytes(b)
parent_spec=importlib.util.spec_from_file_location('private_parent',copy_root/'source_runner.py')
parent_module=importlib.util.module_from_spec(parent_spec)
exec(compile(SOURCE_BUFFERS['source_runner.py'],str(copy_root/'source_runner.py'),'exec'),parent_module.__dict__)
copy_loader=SourceFixtureLoader(root=copy_root,buffers=SOURCE_BUFFERS,parent=parent_module)
copy_pins={n:C.pin(copy_root/n) for n in SOURCE_BUFFERS};copy_pins['interpreter']=implementation['interpreter']
yes('private_original_parent_loaded_identity_positive',lambda:parent_module.implementation_pins(copy_pins,loader=copy_loader)==C.canonical(copy_pins))
original=(copy_root/'source_runner.py').read_bytes();(copy_root/'source_runner.py').write_bytes(original+b'\n# later changed disk source\n')
repinned=dict(copy_pins);repinned['source_runner.py']=C.pin(copy_root/'source_runner.py')
denied('loaded_old_parent_fresh_disk_repin_cannot_claim_identity',lambda:parent_module.implementation_pins(repinned,loader=copy_loader),'loaded_implementation_changed:source_runner.py')
copy_grant=copy.deepcopy(full_grant);copy_grant['implementation']=repinned;copy_grant['read_scope']={'files':[checker_ref,*repinned.values()],'roots':[]}
copy_grant_ref=write(admit_root/'repinned-grant.json',C.canonical(copy_grant))
parent_module.gate.source_preflight=tiny_preflight
denied('actual_full_admit_rejects_loaded_old_parent_repinned_disk_and_grant',
    lambda:parent_module.admit(tiny_inputs,tiny_binding,anchor,relocation_ref,copy_grant_ref,copy_grant_ref,'catalog-filtered',full_grant['output_root'],loader=copy_loader),
    'loaded_implementation_changed:source_runner.py')
(copy_root/'source_runner.py').write_bytes(original)
# Typed CPU negatives on both the closure and trusted launch/READY join.
trusted={'worker':worker,'job':job_ref,'approved_affinity':cpus,'available_affinity':cpus,'observed_limits':copy.deepcopy(closure['observed_limits'])}
for label,aff,cause in [('string',['not-a-CPU'],'affinity_cpu_type'),('bool',[True],'affinity_cpu_type'),
                       ('negative',[-1],'affinity_cpu_type'),('duplicates',[cpus[0],cpus[0]],'affinity_duplicate_cpu'),
                       ('empty',[],'affinity_shape'),('too_many',[0,1,2],'affinity_shape'),
                       ('out_of_scope',[max(cpus)+1],'affinity_outside_host_scope'),
                       ('changed',[cpus[0]],'worker_affinity_changed'),('unsorted',cpus[::-1],'affinity_noncanonical_order')]:
    bad=copy.deepcopy(trusted);bad['observed_limits']['affinity']=aff
    denied('trusted_completion_affinity_'+label,lambda bad=bad:C.completion(record,closure,job_ref,worker,budget,limits,now+.01,True,[],trusted_resources=bad,approved_affinity=cpus),cause)
    bad_closure=copy.deepcopy(closure);bad_closure['observed_limits']['affinity']=aff
    # Different closure values may fail equality before its typed validator.
    denied('closure_affinity_'+label,lambda bad_closure=bad_closure:finish(bad_closure),
           'affinity_cpu_type' if label=='bool' and cpus==[0,1] and aff==[False,True] else 'worker_resource_observation_mismatch')
bool_closure=copy.deepcopy(closure);bool_closure['observed_limits']['affinity']=[False,True]
denied('closure_bool_int_equality_cannot_smuggle_CPUs',lambda:finish(bool_closure),'affinity_cpu_type' if cpus==[0,1] else 'worker_resource_observation_mismatch')
for key,value,cause in [('approved_affinity',[cpus[0]],'host_approved_affinity_changed'),
                       ('available_affinity',[cpus[0]],'affinity_outside_host_scope'),
                       ('worker',{'pid':124,'start_ticks':456},'resource_worker_job_mismatch'),
                       ('job',dict(job_ref,sha256='0'*64),'resource_worker_job_mismatch'),
                       ('observed_limits',None,'worker_resource_observation_mismatch')]:
    bad=copy.deepcopy(trusted);bad[key]=value
    denied('trusted_closure_'+key+'_join_refuses',lambda bad=bad:C.completion(record,closure,job_ref,worker,budget,limits,now+.01,True,[],trusted_resources=bad,approved_affinity=cpus),cause)
denied('self_authored_closure_without_live_host_observation_refuses',lambda:C.completion(record,closure,job_ref,worker,budget,limits,now+.01,True,[]),'trusted_resource_observation_required')
for key,value in [('address_space_bytes',[True,True]),('CPU_seconds',[60,61]),('file_size_bytes',[limits['output_bytes']-1]*2)]:
    bad=copy.deepcopy(trusted);bad['observed_limits'][key]=value
    denied('trusted_'+key+'_resource_drift',lambda bad=bad:C.resource_observation(bad,limits,worker,job_ref,cpus),'worker_resource_observation_mismatch')
for label,changes,cause in [('changed_CPU',{'approved_affinity':[cpus[0]]},'host_approved_affinity_changed'),
                          ('bad_scope',{'available_affinity':['CPU']},'affinity_cpu_type'),
                          ('wrong_worker',{'worker':{'pid':124,'start_ticks':456}},'resource_worker_job_mismatch'),
                          ('wrong_JOB',{'job':dict(job_ref,sha256='0'*64)},'resource_worker_job_mismatch')]:
    class BadResourceVerifier(SourceFixtureVerifier):
        def verify_retained(self,context):
            result=super().verify_retained(context);result['resource_observation'].update(changes);return result
    denied('host_launch_READY_join_'+label,lambda:C.require_custody(BadResourceVerifier(),base,'before_barrier',worker,job_ref),cause)
# Worker absent loader: verifies source/JOB only, before RLIMIT, affinity, READY.
names_before=sorted(Path(base['output_root']).iterdir());as_before=resource.getrlimit(resource.RLIMIT_AS);aff_before=sorted(os.sched_getaffinity(0))
denied('actual_worker_missing_loader_before_configure_or_READY',lambda:W.run(base['output_root'],job_ref,C.digest(C.canonical(base))),'authenticated_existing_loader_unavailable')
yes('worker_missing_loader_zero_resource_output_effect',lambda:sorted(Path(base['output_root']).iterdir())==names_before and resource.getrlimit(resource.RLIMIT_AS)==as_before and sorted(os.sched_getaffinity(0))==aff_before)

# RI-F1/F2/F3: run the actual parent/worker bodies against declared inert
# interfaces. No target checker, native launch/signal or resource setter runs.
import types
PHASE_CASES=[]
def phase_case(label, details):
    PHASE_CASES.append(dict(name=label, **details))
    (OUT/'PHASE-PARTIAL.json').write_text(json.dumps(PHASE_CASES,indent=2)+'\n')

for bad in (None, 'source_runner.py', 'runner_worker.py', 'runner_contract.py',
            'gate_inputs.py', 'interpreter', 'context', 'grant', 'process',
            'original_input', 'host_context', 'host_lock', 'stop_failure', 'unknown_launch'):
    label='parent_cancel_'+str(bad)
    a=copy.deepcopy(base);a.update(output_root=str(fixtures/label), inputs=tiny_inputs,
                                 binding=tiny_binding, source_anchor=anchor)
    token=C.canonical(a);cl=SourceFixtureLoader();state={'alive':True,'stops':0,'waits':0}
    fake_pid=2**30;fake_start=987654
    class InertChild:
        pid=fake_pid;returncode=None
        def poll(self):return None if state['alive'] else self.returncode
        def wait(self,timeout=None):
            state['waits']+=1;state['alive']=False;self.returncode=-15;return self.returncode
    child=InertChild()
    class CancelVerifier(SourceFixtureVerifier):
        def verify_retained(self,ctx):
            value=super().verify_retained(ctx)
            if ctx['phase'].startswith('parent_'):
                assert state['stops']==1 and not state['alive'], 'stop_before_provenance'
                if bad=='host_context':value['context']=dict(ctx,output_root='DRIFT')
                if bad=='host_lock':value['actual_exclusive_lock']=False
            return value
        def launch_owned_source_worker(self,*,admission,job_ref):
            self.job_ref=job_ref
            if bad in SOURCE_BUFFERS or bad in ('interpreter','context','grant','process'):cl.bad=bad
            if bad=='original_input':Path(aux_ref['path']).write_bytes(b'CHANGED ORIGINAL INPUT')
            if bad=='unknown_launch':raise C.Refusal('UNKNOWN_LAUNCH_NO_REPLAY')
            C.save(Path(a['output_root']),'READY.json',dict(worker=dict(pid=fake_pid,start_ticks=fake_start),
                job=job_ref,resources=limits,affinity=['INVALID_CPU']))
            return child
        def capture_worker_closure(self,**kwargs):raise AssertionError('unexpected_checker_closure')
        def stop_owned(self,*,worker,job_ref):
            state['stops']+=1
            assert job_ref==self.job_ref and worker in (None,dict(pid=fake_pid,start_ticks=fake_start))
            if bad=='stop_failure':raise C.Refusal('EXACT_STOP_FAILURE')
            child.wait()
            return dict(status='STOP_CONFIRMED',exact_owned_only=True)
    old_start=R.pid_start;old_preflight=R.gate.source_preflight;aux_bytes=Path(aux_ref['path']).read_bytes()
    R.pid_start=lambda pid:fake_start if pid==fake_pid and state['alive'] else (None if pid==fake_pid else old_start(pid))
    R.gate.source_preflight=tiny_preflight
    try:result=R.execute(token,custody=CancelVerifier(),loader=cl)
    finally:
        R.pid_start=old_start;R.gate.source_preflight=old_preflight;Path(aux_ref['path']).write_bytes(aux_bytes)
    expected='UNKNOWN_LAUNCH_NO_REPLAY' if bad=='unknown_launch' else 'affinity_cpu_type'
    yes(label+'_original_cause_and_exact_stop',lambda result=result,expected=expected:
        expected in result['failure'] and state['stops']==1 and not state['alive'] and not result['success'])
    yes(label+'_both_loaded_phases_observed',lambda:
        'parent_cancel' in cl.calls and 'parent_cleanup' in cl.calls)
    if bad not in (None,'stop_failure','unknown_launch'):
        yes(label+'_secondary_refusal_retained',lambda result=result:bool(result.get('provenance_refusals')))
    if bad=='stop_failure':
        yes(label+'_unconfirmed_retained',lambda result=result:
            result['status']=='STOP_UNCONFIRMED' and 'EXACT_STOP_FAILURE' in result['cleanup_failure'])
    if bad not in ('unknown_launch',):
        yes(label+'_inert_worker_reaped_birth_absent',lambda result=result:
            result['worker_reaped'] and result['worker_identity_absent'])
    phase_case(label,dict(original_cause=result['failure'],loader_phases=cl.calls,
        provenance_refusals=result.get('provenance_refusals',[]),stops=state['stops'],status=result['status']))

def worker_probe(label, *, drift=None, barrier_change=None, available=None):
    a=copy.deepcopy(base);a['output_root']=str(fixtures/label);token=C.canonical(a)
    jr=R.materialize_job(a);out=Path(a['output_root']);worker=dict(pid=os.getpid(),start_ticks=start)
    hard,useful=C.budget_limits(a['budget'])
    b=dict(worker=worker,job=jr,admission_sha256=C.digest(token),useful_epoch=useful,
           hard_epoch=hard,approved_affinity=cpus)
    b=copy.deepcopy(b)
    if barrier_change:barrier_change(b)
    C.save(out,'BARRIER.json',b)
    class ProbeLoader(SourceFixtureLoader):
        def capture_loaded_implementation(self,*,context,namespace):
            if context['phase']=='worker_after_barrier':
                self.calls.append(context['phase']);raise C.Refusal('AFTER_BARRIER_BEFORE_CHECKER')
            return super().capture_loaded_implementation(context=context,namespace=namespace)
    l=ProbeLoader()
    class ReadyVerifier(SourceFixtureVerifier):
        def verify_retained(self,ctx):
            value=super().verify_retained(ctx)
            if ctx['phase']=='worker_before_configure':value['resource_observation']['observed_limits']=None
            if ctx['phase']=='worker_before_ready':l.bad=drift
            return value
    old_os,old_resource=W.os,W.resource
    W.os=types.SimpleNamespace(getpid=os.getpid,sched_setaffinity=lambda *args:None,
                              sched_getaffinity=lambda *args:set(cpus if available is None else available))
    W.resource=types.SimpleNamespace(RLIMIT_AS=resource.RLIMIT_AS,RLIMIT_CPU=resource.RLIMIT_CPU,
                                    RLIMIT_FSIZE=resource.RLIMIT_FSIZE,setrlimit=lambda *args:None)
    refusal=None
    try:W.run(out,jr,C.digest(token),custody=ReadyVerifier(),loader=l)
    except ValueError as error:refusal=str(error)
    finally:W.os,W.resource=old_os,old_resource
    assert refusal is not None
    details=dict(refusal=refusal,loader_phases=l.calls,READY=(out/'READY.json').exists(),
                 checker_executed=False,resource_setters='INERT_ONLY',job=jr)
    phase_case(label,details);return details

for bad,cause in [('source_runner.py','loaded_implementation_changed:source_runner.py'),
                  ('runner_worker.py','loaded_implementation_changed:runner_worker.py'),
                  ('runner_contract.py','loaded_implementation_changed:runner_contract.py'),
                  ('gate_inputs.py','loaded_implementation_changed:gate_inputs.py'),
                  ('interpreter','loaded_interpreter_changed'),('context','loaded_context_mismatch'),
                  ('grant','loaded_context_mismatch'),('process','loaded_context_mismatch')]:
    details=worker_probe('worker_preREADY_'+bad,drift=bad)
    yes('RI_F2_'+bad+'_refused_before_READY',lambda details=details,cause=cause:
        cause in details['refusal'] and not details['READY'] and
        details['loader_phases']==['worker_before_configure','worker_before_ready'])
details=worker_probe('worker_valid_integer_barrier')
yes('RI_F2_F3_integer_positive_reaches_retained_after_barrier_probe',lambda:
    details['READY'] and details['refusal']=='AFTER_BARRIER_BEFORE_CHECKER' and
    details['loader_phases']==['worker_before_configure','worker_before_ready','worker_after_barrier'])
for name,value,cause in [('bool',[False,True],'affinity_cpu_type'),
                        ('float',[float(c) for c in cpus],'affinity_cpu_type'),
                        ('string',[str(c) for c in cpus],'affinity_cpu_type'),
                        ('negative',[-1],'affinity_cpu_type'),
                        ('duplicate',[cpus[0],cpus[0]],'affinity_duplicate_cpu'),
                        ('order',list(reversed(cpus)),'affinity_noncanonical_order'),
                        ('outside',[4096],'affinity_outside_host_scope'),
                        ('empty',[],'affinity_shape'),
                        ('partial',[cpus[0]],'barrier_affinity_mismatch')]:
    details=worker_probe('barrier_affinity_'+name,barrier_change=lambda b,value=value:b.update(approved_affinity=value))
    yes('RI_F3_'+name+'_refused_before_checker',lambda details=details,cause=cause:
        cause in details['refusal'] and 'worker_after_barrier' not in details['loader_phases'])
for name,change in [('worker_pid_type',lambda b:b['worker'].update(pid=float(os.getpid()))),
                    ('worker_birth_type',lambda b:b['worker'].update(start_ticks=float(start))),
                    ('job_bytes_type',lambda b:b['job'].update(bytes=float(b['job']['bytes']))),
                    ('job_pin',lambda b:b['job'].update(sha256='0'*64)),
                    ('admission',lambda b:b.update(admission_sha256='0'*64)),
                    ('useful_type',lambda b:b.update(useful_epoch=float(b['useful_epoch']))),
                    ('hard_type',lambda b:b.update(hard_epoch=float(b['hard_epoch']))),
                    ('useful_deadline',lambda b:b.update(useful_epoch=b['useful_epoch']+1)),
                    ('hard_deadline',lambda b:b.update(hard_epoch=b['hard_epoch']+1)),
                    ('extra_member',lambda b:b.update(FOREIGN_CONTEXT=True))]:
    details=worker_probe('barrier_join_'+name,barrier_change=change)
    yes('RI_F3_'+name+'_strict_canonical_join',lambda details=details:
        details['refusal']=='barrier_identity_or_budget_mismatch' and 'worker_after_barrier' not in details['loader_phases'])
details=worker_probe('barrier_actual_cpu_scope_changed',available=[cpus[0]])
yes('RI_F3_actual_cpu_scope_refuses',lambda:'affinity_outside_host_scope' in details['refusal'])
(OUT/'PHASE-CONTROLS.json').write_text(json.dumps(dict(cases=PHASE_CASES,
    actual_parent_worker_bodies=True,all_source_fixture_only=True,checker_execution=0,
    native_process_signals=0,live_authority=False),indent=2)+'\n')

yes('helper_descriptor_count_restored',lambda:len(list(Path('/proc/self/fd').iterdir()))==initial_fds)
yes('helper_no_children_or_threads',lambda:not Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip() and len(threading.enumerate())==1)
report={'schema':'friday.gate-runner-fix-author-controls.v1','status':'AUTHOR_PURE_SOURCE_CONTROLS_PASS',
        'count':len(CASES),'cases':CASES,'elapsed_seconds':time.monotonic()-begin,
        'worker':{'pid':os.getpid(),'start_ticks':start},'resources':{'affinity':cpus,'AS_bytes':resource.getrlimit(resource.RLIMIT_AS)[0],
        'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'CPU_user_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime,
        'CPU_system_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_stime},'FD_delta':0,'children':0,'threads':1,
        'target_checkers_executed':0,'native_imports':0,'actual_host_custody':'NOT_RUN_ADAPTER_UNAVAILABLE',
        'synthetic_interface_and_closure_seams':'SOURCE_FIXTURE_ONLY_NOT_AUTHORITY',
        'whole_gate':'NOT_RUN','independent_acceptance':False,'runtime_grant':False,
        'source_snapshot':{p.name:C.pin(p) for p in PKG.glob('*.py')},'original_task_clock':clock_ref}
(OUT/'AUTHOR-CONTROLS.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'count':len(CASES),'status':report['status'],'target_execution':0}))
