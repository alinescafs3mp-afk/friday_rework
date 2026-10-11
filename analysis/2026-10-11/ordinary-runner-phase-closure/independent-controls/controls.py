import ast, copy, datetime, hashlib, importlib.util, json, os, pathlib, re, resource, signal, stat, sys, threading, time, types
O=pathlib.Path(__file__).parent
resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(45,45));resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2));signal.alarm(120)
cpus=sorted(os.sched_getaffinity(0));clock=json.loads((O/'CLOCK.json').read_text())
def birth(pid):
    try:
        t=pathlib.Path(f'/proc/{pid}/stat').read_text();return int(t[t.rfind(')')+2:].split()[19])
    except FileNotFoundError:return None
print(json.dumps({'pid':os.getpid(),'start_ticks':birth(os.getpid()),'affinity':cpus,'AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),'file_size_bytes':list(resource.getrlimit(resource.RLIMIT_FSIZE)),'children':[],'threads':[t.name for t in threading.enumerate()]}),flush=True)
assert sys.stdin.readline()=='ADMITTED\n'
beg=time.time();fds=len(list(pathlib.Path('/proc/self/fd').iterdir()))
def own_audit(event,args):
    if event.startswith(('socket.','subprocess.','os.exec','os.system','os.posix_spawn','os.fork','pty.','ctypes.','os.kill')):raise AssertionError('inert_helper_effect_forbidden:'+event)
    if event=='open' and isinstance(args[0],(str,bytes)):
        mode,flags=args[1] or '',args[2] or 0
        if any(x in mode for x in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            p=pathlib.Path(os.fsdecode(args[0]));assert not p.is_absolute() or p.is_relative_to(O),('write_scope',p)
sys.addaudithook(own_audit)
P=pathlib.Path('PRIVATE_PHASE_SOURCE')
cases=[];findings=[]
def save(n,d):
    p=O/n;p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');p.chmod(0o600)
def ref(p):
    assert not p.is_symlink();b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def verify(r):
    p=pathlib.Path(r['path']);assert not p.is_symlink();b=p.read_bytes();assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],r['path'];return b
def yes(n,fn):
    assert time.time()<clock['useful_deadline_unix'];v=fn();assert v is True,(n,v);cases.append({'name':n,'status':'PASS','value':v})
def denied(n,fn,cause=None):
    assert time.time()<clock['useful_deadline_unix']
    try:fn()
    except (ValueError,AssertionError,TypeError,KeyError,OSError) as e:
        if cause:assert cause in str(e),(n,cause,str(e))
        cases.append({'name':n,'status':'PASS_REFUSED','refusal':type(e).__name__+':'+str(e)});return
    raise AssertionError('not_refused:'+n)
pins={'RESULT.json':'e8c2a33a7665ff6b363ff655418d6e49a52edb007638fca4a2addc2324ad202b','SOURCE-MANIFEST.json':'4653dae23d866f958c02fd102db11ba55fc4db53729646fc711eaef741ef3baa','PACKAGE-MANIFEST.json':'eb8f89b212a674e4d9183703cc1c3d48e3200db98e47860d3c121162eec52e02'}
for n,h in pins.items():yes('exact_'+n,lambda n=n,h=h:ref(P/n)['sha256']==h)
S=json.loads((P/'SOURCE-MANIFEST.json').read_text());package=json.loads((P/'PACKAGE-MANIFEST.json').read_text())
entries=[]
for n,r in package['entries'].items():
    p=P/n;st=p.lstat();kind=r['kind']
    if kind=='symlink':assert stat.S_ISLNK(st.st_mode) and os.readlink(p)==r['target'];entries.append({'name':n,'kind':kind,'target_checked_readlink_only':True})
    elif kind=='directory':assert stat.S_ISDIR(st.st_mode) and format(stat.S_IMODE(st.st_mode),'04o')==r.get('mode',r.get('final_mode'));entries.append({'name':n,'kind':kind})
    else:assert stat.S_ISREG(st.st_mode) and st.st_nlink==1 and format(stat.S_IMODE(st.st_mode),'04o')==r.get('mode',r.get('final_mode'));assert ref(p)['sha256']==r['sha256'] and st.st_size==r['bytes'];entries.append({'name':n,'kind':kind,'sha256':r['sha256']})
yes('whole_protected_package_1050_neverfollow',lambda:len(entries)==1050 and {k:sum(x['kind']==k for x in entries) for k in ('file','directory','symlink')}=={'file':872,'directory':170,'symlink':8})
refs={}
def walk(v):
    if isinstance(v,dict):
        if {'path','bytes','sha256'}.issubset(v) and isinstance(v['path'],str):
            key=(v['path'],v['sha256']);verify(v);refs[key]={'path':v['path'],'sha256':v['sha256'],'bytes':v['bytes']}
        else:
            for x in v.values():walk(x)
    elif isinstance(v,list):
        for x in v:walk(x)
for n in ['DEPENDENCY-PINS.json','PATCH-RECONSTRUCTION.json','SOURCE-MANIFEST.json','RESULT.json']:walk(json.loads((P/n).read_text()))
for n,r in S['sources'].items():verify(r);compile(verify(r),r['path'],'exec')
previous=json.loads(verify(S['exact_previous_whole11'])); previous_sources=previous['sources']
yes('exact_whole11_compile_changed5_same6',lambda:len(S['sources'])==11 and len(S['changed'])==5 and len(S['unchanged'])==6 and all(verify(S['sources'][n])==verify(previous_sources[n]) for n in S['unchanged']) and all(verify(S['sources'][n])!=verify(previous_sources[n]) for n in S['changed']))
def reconstruct(base,patch):
    bodies={n:verify(r).decode().splitlines(keepends=True) for n,r in base.items()};ls=verify(patch).decode().splitlines(keepends=True);i=0
    while i<len(ls):
        if not ls[i].startswith('--- '):i+=1;continue
        old=ls[i][4:].strip();new=ls[i+1][4:].strip();name=new.split('/')[-1];original=bodies.get(name,[]);out=[];pos=0;i+=2
        while i<len(ls) and ls[i].startswith('@@ '):
            m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',ls[i]);assert m
            oldnum,oldlen,newnum,newlen=int(m[1]),int(m[2] or 1),int(m[3]),int(m[4] or 1);target=oldnum-1 if oldnum else 0
            assert pos<=target;out+=original[pos:target];pos=target;i+=1;oc=nc=0
            while i<len(ls) and ls[i][:1] in (' ','+','-') and not ls[i].startswith(('--- ','+++ ')):
                marker=ls[i][0];line=ls[i][1:]
                if marker in (' ','-'):assert pos<len(original) and original[pos]==line,(name,pos);pos+=1;oc+=1
                if marker in (' ','+'):out.append(line);nc+=1
                i+=1
            assert oc==oldlen and nc==newlen,(name,oc,nc,oldlen,newlen)
        out+=original[pos:];bodies[name]=out
    for n,r in S['sources'].items():assert ''.join(bodies[n]).encode()==verify(r),n
    return True
result=json.loads((P/'RESULT.json').read_text())
yes('delta_patch_reconstruct_exact11',lambda:reconstruct(previous_sources,result['patch']))
reconstructed=json.loads(verify(result['reconstruction']))
yes('producer_reconstruction_exact11',lambda:all(verify(r)==verify(S['sources'][n]) for n,r in reconstructed['sources'].items()))
yes('original_full_gate_no_transfer',lambda:result['actual_existing_host']=='UNBOUND_NOT_QUALIFIED_NOT_RUN' and result['actual_loaded_interpreter']=='UNBOUND_NOT_QUALIFIED' and result['runtime_grant'] is False and result['independent_acceptance'] is False and result['full_gate']=='NOT_RUN_NOT_GRANTED')
ret=json.loads((P/'CATALOG-AC-RETENTION.json').read_text());catalog=verify(ret['catalog']);yes('catalog_three_byte_exact',lambda:catalog==verify(ret['previous'])==verify(ret['original']))
cat=json.loads(catalog);yes('catalog_counts_preserved',lambda:cat['summary']=={'repo_files':128,'Python_test_definitions':1496,'literal_parametrize_cases':1905,'unresolved_parametrizations':39,'accepted_composition_filter_controls':30})
yes('AC59_and_both_AC055_NOT_RUN',lambda:len(cat['acceptance']['rows'])==59 and len(ret['two_AC055_rows'])==2 and {r['worker'] for r in ret['two_AC055_rows']}=={'A0','Harness'} and all(r['status']=='NOT_RUN' for r in ret['two_AC055_rows']))
save('BINDING.json',{'whole11':S['sources'],'changed5':S['changed'],'package_entries':entries,'verified_dependency_refs':list(refs.values()),'catalog_summary':cat['summary'],'AC055':ret['two_AC055_rows'],'author435_control_credit':0,'target_imports':0,'target_execution':0,'strict30_SOURCE_FAIL_UNESTABLISHED':'PRESERVED_NOT_RERUN_UNCHANGED_GATE_INPUTS'})
F=O/'fixtures';F.mkdir(mode=0o700);cohort=F/'cohort';cohort.mkdir(mode=0o700)
buffers={n:verify(r) for n,r in S['sources'].items()}
for n,b in buffers.items():(cohort/n).write_bytes(b)
def load(n):
    p=cohort/(n+'.py');spec=importlib.util.spec_from_loader('independent_'+n,loader=None);m=importlib.util.module_from_spec(spec);m.__file__=str(p);exec(compile(buffers[n+'.py'],str(p),'exec'),m.__dict__);return m
C=load('runner_contract');R=load('source_runner');W=load('runner_worker')
implementation={n:C.pin(cohort/n) for n in ('source_runner.py','gate_inputs.py','runner_contract.py','runner_worker.py')};implementation['interpreter']=C.pin(pathlib.Path(sys.executable).resolve())
class Loader:
    def __init__(self,bad=None):self.bad=bad;self.calls=[];self.buffers={n:buffers[n] for n in implementation if n!='interpreter'}
    def capture_loaded_implementation(self,*,context,namespace):
        assert namespace is (R.__dict__ if context['actor']=='parent' else W.__dict__);self.calls.append(copy.deepcopy(context))
        names={'source_runner.py','gate_inputs.py','runner_contract.py'} if context['actor']=='parent' else {'runner_worker.py','runner_contract.py'}
        sources=tuple((n,str(cohort/n),b,'loaded' if n in names else 'retained_launch_image') for n,b in sorted(self.buffers.items()))
        joined=copy.deepcopy(context);interp=C.canonical(implementation['interpreter'])
        if self.bad in ('phase','actor','process','worker','binding'):
            joined[self.bad]={'changed':True} if self.bad not in ('phase','actor') else 'wrong'
        if self.bad=='interpreter':interp=b'{}'
        if self.bad=='mutable':sources=tuple((n,p,bytearray(b),s) for n,p,b,s in sources)
        if self.bad=='state':sources=tuple((n,p,b,'wrong') for n,p,b,s in sources)
        if self.bad=='membership':sources=sources[:-1]
        return C.canonical(joined),sources,interp
L=Loader();bind={'binding_sha256':'a'*64,'grant':{'path':'fixture','bytes':0,'sha256':'b'*64}}
yes('loaded_parent_exact_immutable_namespace_context',lambda:R.implementation_pins(implementation,loader=L,binding=bind)==C.canonical(implementation))
for bad in ('phase','actor','process','worker','binding','interpreter','mutable','state','membership'):
    denied('loaded_refuses_'+bad,lambda bad=bad:R.implementation_pins(implementation,loader=Loader(bad),binding=bind))
for n in ('source_runner.py','gate_inputs.py','runner_worker.py','runner_contract.py'):
    b=Loader();b.buffers[n]+=b'\n# retained loaded drift\n';denied('loaded_retained_drift_'+n,lambda b=b:R.implementation_pins(implementation,loader=b,binding=bind),'loaded_implementation_changed:'+n)
old=(cohort/'source_runner.py').read_bytes();(cohort/'source_runner.py').write_bytes(old+b'\n# late disk re-pin\n');repin=copy.deepcopy(implementation);repin['source_runner.py']=C.pin(cohort/'source_runner.py')
denied('loaded_old_parent_late_file_repin_refused',lambda:R.implementation_pins(repin,loader=L,binding=bind),'loaded_implementation_changed:source_runner.py');(cohort/'source_runner.py').write_bytes(old)
for label,v in [('bool',[True]),('string',['1']),('negative',[-1]),('duplicate',[cpus[0]]*2),('empty',[]),('too_many',[0,1,2]),('unsorted',cpus[::-1]),('out_of_scope',[max(cpus)+1])]:denied('typed_CPU_'+label,lambda v=v:C.cpu_affinity(v,2,cpus))
yes('typed_CPU_approved_positive',lambda:C.cpu_affinity(cpus,2,cpus)==cpus)
own_clock=F/'EXECUTION-CLOCK.json';own_clock.write_text(json.dumps({'accepted_msk':clock['accepted_msk'],'original_seconds':900,'cleanup_seconds':90,'hard_epoch':clock['hard_deadline_unix']}));clock_ref=C.pin(own_clock)
budget={'start_epoch':clock['accepted_unix'],'seconds':900,'cleanup_seconds':90,'hard_epoch':clock['hard_deadline_unix'],'clock_ref':clock_ref}
limits={'CPUs':2,'worker_address_space_bytes':1024**3,'aggregate_address_space_bytes':1024**3+96*1024**2,'output_bytes':1024**2}
accepted=F/'accepted';accepted.mkdir();(accepted/'catalog').mkdir();checker=accepted/'catalog/pure_checker.py';checker.write_text('ROOT='+repr(str(accepted))+'\nVALUE="INERT"\n');checker_ref=C.pin(checker)
anchor=F/'anchor.json';anchor.write_text('{}');anchor_ref=C.pin(anchor)
binding={'binding_sha256':'c'*64};inputs={'INDEPENDENT_TINY_FIXTURE':True};slot_doc=F/'slot.json';slot={'receipt':None,'owner_pid':os.getpid(),'owner_start_ticks':birth(os.getpid())}
slot_doc.write_text(json.dumps({'state':'HELD','binding_sha256':binding['binding_sha256'],'owner_pid':slot['owner_pid'],'owner_start_ticks':slot['owner_start_ticks']}));slot['receipt']=C.pin(slot_doc)
rel=F/'relocation.json';rel.write_text(json.dumps({'binding_sha256':binding['binding_sha256'],'checkers':[{'kind':'catalog','after':checker_ref}]}));rel_ref=C.pin(rel)
grant={'schema':'friday.known-source-checker-grant-root-received.v2','independent_source_accepted':True,'runtime_grant':False,'binding_sha256':binding['binding_sha256'],'relocation':rel_ref,'allowed_kinds':['catalog-filtered'],'output_root':str(F/'prepared'),'root_only_output_relocation_accepted':True,'original_budget':budget,'resources':limits,'exclusive_slot':slot,'implementation':implementation,'approved_affinity':cpus,'read_scope':{'files':[checker_ref,*implementation.values()],'roots':[]},'auxiliary_inputs':{}}
gp=F/'grant.json';gp.write_bytes(C.canonical(grant));gr=C.pin(gp)
preflight_calls=[]
def tiny_preflight(i,b,a):assert i==inputs and b==binding and a==anchor_ref;preflight_calls.append(True)
R.gate.source_preflight=tiny_preflight
def admit(loader=L,gref=gr):return R.admit(inputs,binding,anchor_ref,rel_ref,gref,gref,'catalog-filtered',grant['output_root'],loader=loader)
token=admit();a=R.decode_admission(token)
yes('actual_admit_immutable_token_positive',lambda:type(token) is bytes and a['approved_affinity']==cpus)
yes('actual_revalidate_all_parent_phases_positive',lambda:all(R.revalidate(token,loader=L,phase=p)==a for p in ('before_materialize','before_launch','parent_boundary','parent_cancel','parent_cleanup')))
denied('actual_admit_absent_loader',lambda:admit(None),'authenticated_existing_loader_unavailable')
denied('actual_execute_absent_loader',lambda:R.execute(token),'authenticated_existing_loader_unavailable')
denied('actual_execute_absent_custody_before_output',lambda:R.execute(token,loader=L),'existing_host_custody_adapter_unavailable')
yes('absent_capabilities_zero_output_effect',lambda:not pathlib.Path(a['output_root']).exists())
job_ref=R.prepare_job(token,loader=L);job,checker_buffer=C.verify_job(job_ref,a['output_root'],C.digest(token))
yes('actual_prepare_JOB_exact_token_and_buffer',lambda:checker_buffer==verify(job['checker']) and C.canonical(job['admission'])==token)
denied('worker_missing_loader_before_READY_or_limits',lambda:W.run(a['output_root'],job_ref,C.digest(token)),'authenticated_existing_loader_unavailable')
yes('worker_missing_loader_zero_READY',lambda:not (pathlib.Path(a['output_root'])/'READY.json').exists())
target=pathlib.Path(job['checker']['path']);saved=target.read_bytes();target.write_bytes(saved+b'\nCHANGED=True\n');denied('JOB_original_checker_drift_refused',lambda:C.verify_job(job_ref,a['output_root'],C.digest(token)),'changed_ref:job_checker');target.write_bytes(saved)
wp={'pid':1234567,'start_ticks':777};observed={'affinity':cpus,'address_space_bytes':[1024**3]*2,'CPU_seconds':[60]*2,'file_size_bytes':[1024**2]*2}
trusted={'worker':wp,'job':job_ref,'approved_affinity':cpus,'available_affinity':cpus,'observed_limits':observed}
rec={'exit_code':0,'failure':None,'worker_reaped':True};closure={'schema':'friday.source-worker-closure.v2','worker':wp,'job':job_ref,'completed':True,'children':[],'threads':['MainThread'],'FD_delta':0,'approved_affinity':cpus,'observed_limits':observed,'resources':limits,'original_budget':budget,'runtime_grant':False,'independent_acceptance':False,'ended_epoch':time.time(),'output_bytes':100}
def finish(cl=closure,tr=trusted,absent=True,kids=[],record=rec,now=None):return C.completion(record,cl,job_ref,wp,budget,limits,time.time() if now is None else now,absent,kids,trusted_resources=tr,approved_affinity=cpus)
yes('completion_exact_host_join_positive_SYNTHETIC',lambda:finish())
denied('completion_target_JSON_only_refused',lambda:finish(tr=None),'trusted_resource_observation_required')
for key,val in [('worker',{'pid':1234568,'start_ticks':777}),('job',dict(job_ref,sha256='0'*64)),('approved_affinity',[cpus[0]]),('available_affinity',[cpus[0]]),('observed_limits',None)]:
    bad=copy.deepcopy(trusted);bad[key]=val;denied('completion_host_join_'+key,lambda bad=bad:finish(tr=bad))
for label,vals in [('bool',[False,True]),('string',['CPU']),('duplicate',[cpus[0]]*2),('negative',[-1]),('outside',[max(cpus)+1]),('changed',[cpus[0]]),('unsorted',cpus[::-1])]:
    bad=copy.deepcopy(trusted);bad['observed_limits']['affinity']=vals;denied('completion_trusted_affinity_'+label,lambda bad=bad:finish(tr=bad))
    bad=copy.deepcopy(closure);bad['observed_limits']['affinity']=vals;denied('completion_closure_affinity_'+label,lambda bad=bad:finish(cl=bad))
for key,val in [('address_space_bytes',[True,True]),('CPU_seconds',[60,61]),('file_size_bytes',[1024**2-1]*2)]:
    bad=copy.deepcopy(trusted);bad['observed_limits'][key]=val;denied('completion_resource_'+key,lambda bad=bad:finish(tr=bad))
for key,val in [('worker',{'pid':1234567,'start_ticks':778}),('job',dict(job_ref,bytes=job_ref['bytes']+1)),('completed',False),('FD_delta',True),('threads',['MainThread','late']),('children',['1']),('output_bytes',True),('ended_epoch',budget['hard_epoch']+1),('runtime_grant',True),('original_budget',dict(budget,seconds=901))]:
    bad=copy.deepcopy(closure);bad[key]=val;denied('completion_closure_'+key,lambda bad=bad:finish(cl=bad))
denied('completion_live_birth_remains',lambda:finish(absent=False));denied('completion_supervisor_child_remains',lambda:finish(kids=['42']))
denied('completion_after_original_hard',lambda:finish(now=budget['hard_epoch']+1))
class Custody:
    def __init__(self,mutation=None):self.calls=[];self.mutation=mutation
    def verify_retained(self,context):
        self.calls.append(copy.deepcopy(context));w=context['worker'];ob={'context':context,'owner':{'pid':slot['owner_pid'],'start_ticks':slot['owner_start_ticks']},'resource_observation':{'worker':w,'job':context['job'],'approved_affinity':cpus,'available_affinity':cpus,'observed_limits':None if w is None or context['phase']=='worker_before_configure' else copy.deepcopy(observed)}}
        for key in ('actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins','kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap'):ob[key]=True
        if self.mutation:self.mutation(ob,context)
        return ob
yes('custody_exact_context_and_resources_positive_SYNTHETIC',lambda:C.require_custody(Custody(),a,'before_barrier',wp,job_ref)['context']==C.custody_context(a,'before_barrier',wp,job_ref))
for key in ('phase','worker','job','original_budget','loaded_identity','approved_affinity','implementation_sha256'):
    def mut(ob,ctx,key=key):ob['context']=copy.deepcopy(ctx);ob['context'][key]='CHANGED'
    denied('custody_context_'+key,lambda mut=mut:C.require_custody(Custody(mut),a,'before_barrier',wp,job_ref),'custody_context_mismatch')
# Fresh independent probes of the changed whole parent and worker bodies.
# All children below are inert objects, every authority/resource observation
# synthetic. They never launch, signal, execute a checker or grant runtime.
phase_details=[]

def parent_probe(label, defect=None, success_path=False):
    local=copy.deepcopy(a);local['output_root']=str(F/label);token=C.canonical(local)
    state={'alive':True,'stops':0,'waits':0,'events':[]};fakepid=99999981;fakebirth=987777
    l=Loader();l.bad=None
    class InertChild:
        pid=fakepid;returncode=None
        def poll(self):return None if state['alive'] else self.returncode
        def wait(self,timeout=None):
            state['events'].append('wait');state['waits']+=1
            if defect=='wait_refusal':raise ValueError('INERT_EXACT_WAIT_REFUSAL')
            state['alive']=False;self.returncode=0 if success_path else -15;return self.returncode
    child=InertChild()
    class ParentCustody(Custody):
        def launch_owned_source_worker(self,*,admission,job_ref):
            state['job']=job_ref;state['events'].append('launch')
            if defect in l.buffers:l.buffers[defect]+=b'\n# independent loaded-image drift\n'
            if defect in ('phase','actor','process','worker','binding','interpreter'):l.bad=defect
            if defect=='original_input':anchor.write_bytes(b'{"changed":true}')
            if defect=='expired_clock':R.contract.time=types.SimpleNamespace(time=lambda:budget['hard_epoch']+1)
            if defect=='unknown_launch':raise ValueError('INERT_UNKNOWN_LAUNCH_NO_REPLAY')
            C.save(pathlib.Path(local['output_root']),'READY.json',{'worker':{'pid':fakepid,'start_ticks':fakebirth},'job':job_ref,'resources':limits,'affinity':cpus if success_path else [False,True]})
            return child
        def verify_retained(self,ctx):
            ob=super().verify_retained(ctx);state['events'].append('custody:'+ctx['phase'])
            if ctx['phase'] in ('parent_cancel','parent_cleanup'):
                if not success_path:assert state['stops']==1
                if defect=='host_context':ob['context']=dict(ctx,output_root='INERT_DRIFT')
                if defect=='host_lock':ob['actual_exclusive_lock']=False
                if defect=='cleanup_only' and ctx['phase']=='parent_cleanup':ob['retained_until_reap']=False
            return ob
        def capture_worker_closure(self,*,worker,job_ref):
            assert success_path and not state['alive'];state['events'].append('capture_closure')
            cl={'schema':'friday.source-worker-closure.v2','worker':worker,'job':job_ref,'completed':True,'children':[],'threads':['MainThread'],'FD_delta':0,'approved_affinity':cpus,'observed_limits':observed,'resources':limits,'original_budget':budget,'runtime_grant':False,'independent_acceptance':False,'ended_epoch':time.time(),'output_bytes':100}
            cr=C.save(pathlib.Path(local['output_root']),'WORKER-CLOSURE.json',cl)
            ro={'worker':worker,'job':job_ref,'approved_affinity':cpus,'available_affinity':cpus,'observed_limits':observed}
            return {'worker':worker,'job':job_ref,'owned_obligations_observed':True,'closure_ref':cr,'resource_observation':ro}
        def stop_owned(self,*,worker,job_ref):
            state['stops']+=1;state['events'].append('stop');assert job_ref==state['job']
            assert worker in (None,{'pid':fakepid,'start_ticks':fakebirth})
            if defect=='stop_refusal':raise ValueError('INERT_EXACT_STOP_REFUSAL')
            state['alive']=False;child.returncode=-15
            return {'status':'STOP_CONFIRMED','exact_owned_only':True}
    cust=ParentCustody();original_pid=R.pid_start;original_time=R.contract.time;anchor_bytes=anchor.read_bytes()
    def pid(pid):
        if pid==fakepid:
            state['events'].append('fresh_birth');return fakebirth if state['alive'] else None
        return original_pid(pid)
    R.pid_start=pid
    try:rec=R.execute(token,custody=cust,loader=l)
    finally:R.pid_start=original_pid;R.contract.time=original_time;anchor.write_bytes(anchor_bytes)
    phases=[x['phase'] for x in l.calls];detail={'name':label,'record':rec,'events':state['events'],'loader_phases':phases,'custody_phases':[x['phase'] for x in cust.calls],'alive':state['alive'],'stops':state['stops'],'waits':state['waits']};phase_details.append(detail)
    if success_path and defect is None:
        yes(label+'_positive_source_body',lambda:rec['success'] is True and state['stops']==0 and rec['worker_reaped'] and rec['worker_identity_absent'] and 'parent_cleanup' in phases)
    elif success_path:
        yes(label+'_cleanup_refusal_cannot_suppress_exact_stop',lambda:rec['success'] is False and state['stops']==1 and state['waits']==2 and rec['worker_identity_absent'] and 'retained_until_reap' in str(rec['provenance_refusals']))
    else:
        expected='INERT_UNKNOWN_LAUNCH_NO_REPLAY' if defect=='unknown_launch' else 'affinity_cpu_type'
        yes(label+'_primary_preserved_single_exactstop',lambda:expected in rec['failure'] and state['stops']==1 and rec['success'] is False)
        yes(label+'_loaded_and_custody_both_phases',lambda:'parent_cancel' in phases and 'parent_cleanup' in phases and all(p in detail['custody_phases'] for p in ('parent_cancel','parent_cleanup')))
        yes(label+'_stop_precedes_provenance',lambda:state['events'].index('stop')<state['events'].index('custody:parent_cancel'))
        if defect not in (None,'stop_refusal','wait_refusal','unknown_launch'):
            yes(label+'_secondary_refusal_retained',lambda:bool(rec.get('provenance_refusals')))
        if defect=='stop_refusal':yes(label+'_unconfirmed_wait_still_attempted',lambda:rec['status']=='STOP_UNCONFIRMED' and state['waits']==1 and rec['worker_reaped'] and 'INERT_EXACT_STOP_REFUSAL' in rec['cleanup_failure'])
        elif defect=='wait_refusal':yes(label+'_wait_refusal_status_and_fresh_witness',lambda:rec['status']=='STOP_UNCONFIRMED' and 'INERT_EXACT_WAIT_REFUSAL' in rec['reap_failure'] and rec['worker_identity_absent'])
        elif defect=='unknown_launch':yes(label+'_unknown_no_guess_no_replay_no_falseclosure',lambda:rec['status']=='STOP_UNCONFIRMED' and state['waits']==0 and not rec['worker_reaped'] and 'BARRIER.json' not in {p.name for p in pathlib.Path(local['output_root']).iterdir()})
        else:yes(label+'_retained_handle_wait_fresh_birth',lambda:state['waits']==1 and rec['worker_reaped'] and rec['worker_identity_absent'] and state['events'][-1]=='fresh_birth')
    return detail
parent_probe('parent_positive',success_path=True)
parent_probe('parent_success_cleanup_refusal','cleanup_only',True)
for bad in (None,'source_runner.py','runner_worker.py','runner_contract.py','gate_inputs.py','interpreter','phase','actor','process','worker','binding','original_input','expired_clock','host_context','host_lock','stop_refusal','wait_refusal','unknown_launch'):
    parent_probe('cancel_'+str(bad),bad)

# Exact Worker.run goes only as far as the marked after-barrier probe. The
# mutations happen in the custody seam, before the second retained capture.
def worker_probe(label, drift=None, mutate_barrier=None, availability=None):
    local=copy.deepcopy(a);local['output_root']=str(F/label);token=C.canonical(local)
    jr=R.materialize_job(local);out=pathlib.Path(local['output_root']);worker={'pid':os.getpid(),'start_ticks':birth(os.getpid())}
    hard,useful=C.budget_limits(local['budget']);b={'worker':worker,'job':jr,'admission_sha256':C.digest(token),'useful_epoch':useful,'hard_epoch':hard,'approved_affinity':cpus}
    b=copy.deepcopy(b)
    if mutate_barrier:mutate_barrier(b)
    C.save(out,'BARRIER.json',b)
    class BarrierLoader(Loader):
        def capture_loaded_implementation(self,*,context,namespace):
            if context['phase']=='worker_after_barrier':
                self.calls.append(copy.deepcopy(context));raise ValueError('INDEPENDENT_AFTER_BARRIER_BEFORE_CHECKER')
            return super().capture_loaded_implementation(context=context,namespace=namespace)
    l=BarrierLoader()
    class ReadyCustody(Custody):
        def verify_retained(self,ctx):
            ob=super().verify_retained(ctx)
            if ctx['phase']=='worker_before_ready':
                if drift in l.buffers:l.buffers[drift]+=b'\n# independent pre-READY retained image drift\n'
                else:l.bad=drift
            return ob
    cust=ReadyCustody();oldos=W.os;oldresource=W.resource
    W.os=types.SimpleNamespace(getpid=os.getpid,sched_setaffinity=lambda *x:None,sched_getaffinity=lambda *x:set(cpus if availability is None else availability))
    W.resource=types.SimpleNamespace(RLIMIT_AS=resource.RLIMIT_AS,RLIMIT_CPU=resource.RLIMIT_CPU,RLIMIT_FSIZE=resource.RLIMIT_FSIZE,setrlimit=lambda *x:None)
    refusal=None
    try:W.run(out,jr,C.digest(token),custody=cust,loader=l)
    except (ValueError,AssertionError,TypeError,KeyError) as e:refusal=type(e).__name__+':'+str(e)
    finally:W.os=oldos;W.resource=oldresource
    assert refusal is not None
    detail={'name':label,'refusal':refusal,'loader_phases':[v['phase'] for v in l.calls],'custody_phases':[v['phase'] for v in cust.calls],'READY':(out/'READY.json').exists(),'checker_executed':False,'resource_setters':'INERT','job':jr};phase_details.append(detail);return detail
for bad in ('source_runner.py','runner_worker.py','runner_contract.py','gate_inputs.py','interpreter','phase','actor','process','worker','binding','mutable','state','membership'):
    d=worker_probe('pre_READY_'+bad,bad)
    yes('RI_F2_'+bad+'_refused_after_custody_before_READY',lambda d=d:not d['READY'] and d['loader_phases']==['worker_before_configure','worker_before_ready'] and d['custody_phases']==['worker_before_configure','worker_before_ready'] and ('loaded_' in d['refusal'] or 'immutable_' in d['refusal']))
d=worker_probe('worker_canonical_barrier_positive')
yes('RI_F2_F3_positive_all_three_loaded_phases',lambda:d['READY'] and d['refusal']=='ValueError:INDEPENDENT_AFTER_BARRIER_BEFORE_CHECKER' and d['loader_phases']==['worker_before_configure','worker_before_ready','worker_after_barrier'])
for label,value,cause in [('boolean',[False,True],'affinity_cpu_type'),('float',[float(c) for c in cpus],'affinity_cpu_type'),('numeric_strings',[str(c) for c in cpus],'affinity_cpu_type'),('negative',[-2],'affinity_cpu_type'),('duplicate',[cpus[0],cpus[0]],'affinity_duplicate_cpu'),('reversed',cpus[::-1],'affinity_noncanonical_order'),('empty',[],'affinity_shape'),('foreign',[max(cpus)+100],'affinity_outside_host_scope'),('partial',[cpus[0]],'barrier_affinity_mismatch'),('tuple',tuple(cpus),'affinity_shape')]:
    d=worker_probe('BARRIER_CPU_'+label,mutate_barrier=lambda b,value=value:b.update(approved_affinity=value))
    # JSON turns tuple into list, so a tuple transport is canonical and accepted.
    if label=='tuple':yes('RI_F3_tuple_JSON_normalizes_to_positive',lambda d=d:d['refusal']=='ValueError:INDEPENDENT_AFTER_BARRIER_BEFORE_CHECKER')
    else:yes('RI_F3_'+label+'_refused_before_checker_callback',lambda d=d,cause=cause:cause in d['refusal'] and 'worker_after_barrier' not in d['loader_phases'])
for label,mut in [('PID_float',lambda b:b['worker'].update(pid=float(os.getpid()))),('birth_float',lambda b:b['worker'].update(start_ticks=float(birth(os.getpid())))),('bytes_float',lambda b:b['job'].update(bytes=float(b['job']['bytes']))),('JOB_SHA',lambda b:b['job'].update(sha256='9'*64)),('admission_SHA',lambda b:b.update(admission_sha256='9'*64)),('useful_int',lambda b:b.update(useful_epoch=int(b['useful_epoch']))),('hard_int',lambda b:b.update(hard_epoch=int(b['hard_epoch']))),('hard_change',lambda b:b.update(hard_epoch=b['hard_epoch']+3)),('foreign_member',lambda b:b.update(FOREIGN=True))]:
    d=worker_probe('BARRIER_join_'+label,mutate_barrier=mut)
    yes('RI_F3_'+label+'_typed_canonical_refusal',lambda d=d:'barrier_identity_or_budget_mismatch' in d['refusal'] and 'worker_after_barrier' not in d['loader_phases'])
d=worker_probe('BARRIER_actual_available_drift',availability=[cpus[0]])
yes('RI_F3_fresh_available_scope_not_old_READY',lambda:'affinity_outside_host_scope' in d['refusal'] and 'worker_after_barrier' not in d['loader_phases'])

# Whole11 joins to the concrete retained loader and concrete host adapter.
# This is a source fixture; actual host/interpreter authority stays UNBOUND.
RL=load('retained_loader');H=load('host_gate_adapter')
loader_binding={'binding_sha256':a['binding_sha256'],'grant':a['pins']['grant']}
actual_buffers={n:buffers[n] for n in RL.NAMES}
def actual_loader(actor='parent'):
    return RL.RetainedLoader(buffers=actual_buffers,implementation=implementation,interpreter_provenance=C.canonical(implementation['interpreter']),binding=loader_binding,actor=actor)
for actor,phases in [('parent',('parent_cancel','parent_cleanup')),('worker',('worker_before_ready','worker_after_barrier','worker_before_closure'))]:
    al=actual_loader(actor);entry=al.load_entrypoint();wp=slot['owner_pid'];w={'pid':wp,'start_ticks':slot['owner_start_ticks']} if actor=='worker' else None
    for phase in phases:
        yes('concrete_retained_'+actor+'_'+phase,lambda phase=phase:C.loaded_implementation(al,implementation,phase,actor,entry.__dict__,loader_binding,w)==C.canonical(implementation))
    fn=entry.run if actor=='worker' else entry.cleanup_provenance;original_code=fn.__code__;fn.__code__=(lambda:None).__code__
    denied('concrete_retained_actual_code_'+actor,lambda:C.loaded_implementation(al,implementation,phases[0],actor,entry.__dict__,loader_binding,w),'retained_loaded_namespace_changed');fn.__code__=original_code
    entry.__dict__['INDEPENDENT_NAMESPACE_DRIFT']=True
    denied('concrete_retained_context_namespace_'+actor,lambda:C.loaded_implementation(al,implementation,phases[0],actor,entry.__dict__,loader_binding,w),'retained_loaded_namespace_changed');del entry.__dict__['INDEPENDENT_NAMESPACE_DRIFT']

class AdapterContract:
    def __init__(self):self.fakepid=99999961;self.fakebirth=555555;self.absent=False
    def __getattr__(self,k):return getattr(C,k)
    def pid_start(self,p):return (None if self.absent else self.fakebirth) if p==self.fakepid else C.pid_start(p)
class AdapterChild:
    def __init__(self,c):self.pid=c.fakepid;self.returncode=None
    def poll(self):return self.returncode
    def wait(self,timeout=None):return self.returncode
class InertBoundary(H.ExistingHostBoundary):
    def __init__(self,c,unknown=False):self.c=c;self.calls=[];self.child=AdapterChild(c);self.unknown=unknown;self.bad=None
    def observe_retained(self,ctx):
        self.calls.append('observe:'+ctx['phase']);ob=Custody().verify_retained(ctx)
        if self.bad:ob[self.bad]=False
        return ob
    def launch_retained(self,token,jr,loader):
        self.calls.append('launch')
        if self.unknown:raise ValueError('INERT_ADAPTER_UNKNOWN_LAUNCH')
        return self.child,{'pid':self.c.fakepid,'start_ticks':self.c.fakebirth}
    def observe_closed(self,worker,job):raise AssertionError('UNEXPECTED_INERT_CLOSURE_CALLBACK')
    def stop_owned(self,w,jr,hard):
        self.calls.append('stop');self.c.absent=True;self.child.returncode=-15
        return {'status':'STOP_CONFIRMED','worker':w,'job':jr,'original_hard_epoch':hard,'exact_owned_only':True,'pending_launch_settled':True,'owned_children':[],'retained_until_reap':True,'exact_worker_absent':True,'worker_reaped':True}
def adapter(unknown=False):
    al=actual_loader();entry=al.load_entrypoint();c=AdapterContract();b=InertBoundary(c,unknown);ad=H.GateHostAdapter(contract=c,admission=token,loader=al,boundary=b);return ad,b,c,al,entry
# token/jr refer to the admitted private baseline JOB only.
token=C.canonical(a);jr=job_ref
ad,b,c,al,entry=adapter();ctx=C.custody_context(a,'before_launch')
yes('host_beforelaunch_original_join',lambda:ad.verify_retained(ctx)['actual_exclusive_lock'] is True)
ch=ad.launch_owned_source_worker(admission=token,job_ref=jr);wp={'pid':c.fakepid,'start_ticks':c.fakebirth}
for phase in ('parent_cancel','parent_cleanup'):
    yes('host_newphase_'+phase+'_exact_join',lambda phase=phase:ad.verify_retained(C.custody_context(a,phase,wp,jr))['context']['phase']==phase)
    for key,val in [('worker',dict(wp,start_ticks=c.fakebirth+1)),('job',dict(jr,sha256='8'*64)),('loaded_identity','DRIFT')]:
        badctx=C.custody_context(a,phase,wp,jr);badctx[key]=val;calls=len(b.calls)
        denied('host_newphase_'+phase+'_'+key+'_refuses',lambda badctx=badctx:ad.verify_retained(badctx))
        yes('host_newphase_'+phase+'_'+key+'_no_callback',lambda calls=calls:len(b.calls)==calls)
entry.__dict__['INDEPENDENT_NAMESPACE_DRIFT']=True
denied('host_newphase_loaded_namespace_drift',lambda:ad.verify_retained(C.custody_context(a,'parent_cancel',wp,jr)),'retained_loaded_namespace_changed')
yes('host_original_exact_stop_not_suppressed_by_loaded_drift',lambda:ad.stop_owned(worker=wp,job_ref=jr)['status']=='STOP_CONFIRMED' and b.calls.count('stop')==1)
del entry.__dict__['INDEPENDENT_NAMESPACE_DRIFT']
denied('host_stop_single_consumed_no_replay',lambda:ad.stop_owned(worker=wp,job_ref=jr),'host_stop_consumed_no_replay')
ad,b,c,al,entry=adapter(True);ad.verify_retained(ctx)
denied('host_unknown_launch_preserved',lambda:ad.launch_owned_source_worker(admission=token,job_ref=jr),'INERT_ADAPTER_UNKNOWN_LAUNCH')
denied('host_unknown_newphase_secondary_refusal',lambda:ad.verify_retained(C.custody_context(a,'parent_cleanup',None,jr)),'host_session_failed_no_replay')
yes('host_unknown_original_exact_stop_without_guessed_PID',lambda:ad.stop_owned(worker=None,job_ref=jr)['status']=='STOP_CONFIRMED' and b.calls.count('launch')==1 and b.calls.count('stop')==1)
unbound=H.GateHostAdapter(contract=C,admission=token,loader=al)
denied('genuine_host_still_UNBOUND_no_fixturegrant',lambda:unbound.verify_retained(ctx),'existing_gate_host_counterpart_UNBOUND')

assert len(list(pathlib.Path('/proc/self/fd').iterdir()))==fds
assert not pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip() and [t.name for t in threading.enumerate()]==['MainThread']
save('PHASE-CONTROLS.json',{'cases':phase_details,'exact_bodies':['source_runner.execute','runner_worker.run','GateHostAdapter','RetainedLoader'],'inert_seams_only':True,'checker_execution':0,'actual_host_interpreter_authority':'UNBOUND_NOT_QUALIFIED_NOT_RUN'})
save('CONTROLS.json',{'status':'INDEPENDENT_SOURCE_CONTROLS_PASS','count':len(cases),'cases':cases,'findings':findings,'tested_whole11':S['sources'],'source_fixture_cohort':{n:ref(cohort/n) for n in buffers},'author435_credit':0,'target_checkers_executed':0,'native19':'NOT_RUN','runtime_grant':False,'elapsed_seconds':time.time()-beg,'actual_own_resources':{'affinity':sorted(os.sched_getaffinity(0)),'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),'RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},'FD_delta':0,'children':[],'threads':['MainThread']})
print(json.dumps({'controls':len(cases),'findings':len(findings),'checker_execution':0}),flush=True)
