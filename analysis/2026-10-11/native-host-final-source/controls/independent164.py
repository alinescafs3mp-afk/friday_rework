"""Independent finite SOURCE controls; selected exact AST definitions only."""
import ast, array, builtins, dataclasses, hashlib, json, math, os, re, resource, select, signal, socket, stat, struct, sys, time, types
from pathlib import Path
from dataclasses import dataclass, replace
OUT=Path(sys.argv[1]); INPUT=Path(sys.argv[2]); readyfd=int(sys.argv[3]); gofd=int(sys.argv[4]); deadline=float(sys.argv[5])
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
def birth(pid):
 try:
  s=Path(f'/proc/{pid}/stat').read_text();return int(s[s.rfind(')')+2:].split()[19])
 except FileNotFoundError:return None
def write(name,value):
 p=OUT/name;p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');p.chmod(0o400)
ready={'pid':os.getpid(),'start_ticks':birth(os.getpid()),'cpus':sorted(os.sched_getaffinity(0)),'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'finite_deadline_monotonic':deadline}
os.write(readyfd,json.dumps(ready,sort_keys=True,separators=(',',':')).encode());os.close(readyfd)
assert select.select([gofd],[],[],max(0,deadline-time.monotonic()))[0],'GO_TIMEOUT'
go=json.loads(os.read(gofd,65536));os.close(gofd);assert go['pid']==os.getpid() and go['start_ticks']==birth(os.getpid()) and go['deadline']==deadline and time.monotonic()<deadline
def audit(event,args):
 if event.startswith(('subprocess.','os.exec','os.system','os.posix_spawn','os.fork','pty.','ctypes.')):raise RuntimeError('FORBIDDEN_EFFECT:'+event)
 if event in ('socket.bind','socket.connect','socket.getaddrinfo'):raise RuntimeError('FORBIDDEN_ENDPOINT:'+event)
 if event=='socket.__new__':assert args[1]==socket.AF_UNIX and (args[2]&15)==socket.SOCK_SEQPACKET
 if event=='open' and isinstance(args[0],(str,bytes)):
  mode,flags=args[1] or '',args[2] or 0
  if any(c in mode for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
   p=Path(os.fsdecode(args[0]));assert p.is_absolute() and p.resolve().is_relative_to(OUT),'WRITE_SCOPE:'+str(p)
sys.addaudithook(audit)
rows=[];findings=[];selected=[]
def check(name,ok,**facts):
 assert ok,name;assert time.monotonic()<deadline,'ORIGINAL_USEFUL_DEADLINE';rows.append({'name':name,'passed':True,**facts})
def reject(name,fn,kind=Exception,contains=None):
 try:fn()
 except kind as e:
  if contains:assert contains in str(e),(name,str(e))
  check(name,True,refusal=type(e).__name__+':'+str(e));return e
 raise AssertionError('DID_NOT_REFUSE:'+name)
def verify(ref):
 raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];return raw
inp=json.loads(INPUT.read_bytes());snapshot=json.loads(verify(inp['source_manifest']));original_inputs=json.loads(verify(inp['original_inputs']));raws={n:verify(r) for n,r in snapshot['source'].items()}
for n,r in raws.items():
 if n.endswith('.py'):compile(r,n,'exec',dont_inherit=True)
 else:json.loads(r)
check('whole9_compile8_json1',len(raws)==9 and sum(n.endswith('.py') for n in raws)==8)
safe={k:v for k,v in globals().items() if k in ('array','ast','builtins','dataclass','replace','hashlib','json','math','os','Path','re','select','signal','socket','stat','struct','time','types','sys')}
def component(name,raw,labels,constants=()):
 tree=ast.parse(raw);nodes=[]
 for node in tree.body:
  if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in labels:nodes.append(node)
  elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets):nodes.append(node)
 assert set(labels)=={n.name for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef))},('missing',name)
 m=types.ModuleType(name);m.__dict__.update(safe);sys.modules[name]=m
 unit=ast.Module(body=nodes,type_ignores=[]);exec(compile(unit,'<selected-exact:'+name+'>','exec',dont_inherit=True),m.__dict__)
 selected.append({'module':name,'source_sha256':hashlib.sha256(raw).hexdigest(),'definitions':sorted(labels),'constants':list(constants),'full_file_imported':False,'guard_removals':False})
 return m
flabels={'Unbound','CleanupUnconfirmed','need','require_native_admission','signature','read_fd','canonical_json','exact_json','exact_packet','exact_birth_packet','ready_packet_bytes','unix_endpoint_inodes','process_birth','process_group','bounded_path','is_within','exact_cpus','parse_cpuset','Grant','CgroupCustody','send_packet','recv_packet','peer_credential','command_vector','independent_attempts','FiniteOutsideOwner','controller_main','WorkerHeldChannel'}
fconstants=('SOURCE_ONLY','MAX_WIRE','MAX_FDS','MAX_FILES','MAX_PIDS','MEMORY','UNIT_RE','CONTROLLER_BOOTSTRAP')
hlabels={'Unbound','require','bounded_fd','signature','directory_signature','HeldFile','absolute_import','source_import_audit','python_function_state','same_function_state','namespace_state','same_namespace','HeldImportGraph','HostProvenance','interpreter_pt_interp','proc_read','verify_before_effects'}
F=component('_independent_nfh',raws['finite_outside_unit.py'],flabels,fconstants);H=component('_independent_held',raws['held_startup_imports.py'],hlabels,('ESCAPES','CALL_ESCAPES'))
initial_fds=set(os.listdir('/proc/self/fd'))
reject('audit_prevents_process_effects',lambda:sys.audit('subprocess.Popen','forbidden',[],{},None),RuntimeError,contains='FORBIDDEN_EFFECT')
for flag in (True,False,None):
 F.SOURCE_ONLY=flag
 for name,fn in [('launch',lambda:F.FiniteOutsideOwner.launch_held(object())),('release',lambda:F.FiniteOutsideOwner.release_once(object(),{})),('stop',lambda:F.FiniteOutsideOwner._stop_unit(object())),('controller',lambda:F.controller_main('', '',0,0)),('worker',lambda:F.WorkerHeldChannel.from_bootstrap_arguments(0,'',0,0,0))]:reject('unconditional_runtime_gate_'+name+'_'+str(flag),fn,F.Unbound,contains='SOURCE_ONLY_UNBOUND')
F.SOURCE_ONLY=True
host=object.__new__(H.HostProvenance);host.verify_observations=lambda:None;reject('loaded_ELF_proof_never_grants_effects',host.verify_before_effects,H.Unbound,contains='UNBOUND_INDEPENDENT_STARTUP')
u,mo=time.time(),time.monotonic();cpus=tuple(sorted(os.sched_getaffinity(0)))
grant=F.Grant(token='a'*64,unit='friday-rework-worker-'+'b'*32+'.service',admission_hash='c'*64,accepted_unix=u,accepted_monotonic=mo,useful_unix=u+300,final_unix=u+360,useful_monotonic=mo+300,final_monotonic=mo+360,parent_useful_unix=u+400,parent_final_unix=u+500,reservation=(1,2),cpus=cpus).validate()
association={'supervisor':{'scope':'user','unit':grant.unit},'admission_hash':grant.admission_hash,'native':None}
aggregate=object.__new__(F.CgroupCustody);aggregate.grant=grant;directory=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 for name in ('a.sock','worker-ready.sock','0.sock','a'*48+'.sock'):
  owner=F.FiniteOutsideOwner(object(),association,grant,directory,name,None,None,None,aggregate)
  try:check('NFH-F1_positive_'+name,owner.socket_name==name and owner.ready_packet is None)
  finally:os.close(owner.dirfd)
 for name in ('../a.sock','a/b.sock','a.SOCK','a'*49+'.sock','a.sock\n','a.sock\x00','',True):reject('NFH-F1_invalid_'+repr(name),lambda name=name:F.FiniteOutsideOwner(object(),association,grant,directory,name,None,None,None,aggregate),F.Unbound,contains='EXACT_OWN_SOCKET_NAME')
finally:os.close(directory)
reject('NFH-F1_socketpath_over107_refuses',lambda:F.command_vector(3,4,'d'*64,F.process_birth(os.getpid()),'/'+'a'*107,grant,'friday-rework-'+'e'*32+'.slice'),F.Unbound)
check('NFH-F1_valid_socketpath_argv_only',F.command_vector(3,4,'d'*64,F.process_birth(os.getpid()),'/inert.sock',grant,'friday-rework-'+'e'*32+'.slice')[0]=='/usr/bin/systemd-run')
fixture=OUT/'fixtures';fixture.mkdir(mode=0o700);held=[]
def hold(name,raw):
 p=fixture/name;p.write_bytes(raw);p.chmod(0o400);h=H.HeldFile(str(p),hashlib.sha256(raw).hexdigest(),owners=(0,os.getuid()),mode=0o400);held.append(h);return h
alpha=hold('alpha.py',b'import independent_beta\ndef answer(): return independent_beta.VALUE\nclass Box:\n def plain(self): return 1\n @staticmethod\n def static(*args): return len(args)\n @classmethod\n def klass(cls): return 2\n @property\n def value(self): return 3\n @value.setter\n def value(self,x): pass\n @value.deleter\n def value(self): pass\n');beta=hold('beta.py',b'VALUE=17\n')
records={'independent_alpha':{'held':alpha,'package':False,'imports':('independent_beta',),'dynamic_unbound':()},'independent_beta':{'held':beta,'package':False,'imports':(),'dynamic_unbound':()}}
g=H.HeldImportGraph(records).install()
try:
 m=g.load('independent_alpha');check('NFH-F2_real_heldgraph_positive',m.answer()==17 and g.verify_loaded()['bytes_and_object_identity_verified'] is True)
 def replacement():return 999
 for label in ('answer','plain','static','klass','fget','fset','fdel'):
  fn=m.answer if label=='answer' else vars(m.Box)['plain'] if label=='plain' else vars(m.Box)[label].__func__ if label in ('static','klass') else getattr(vars(m.Box)['value'],label)
  code=fn.__code__;fn.__code__=replacement.__code__
  try:reject('NFH-F2_code_mutation_'+label,g.verify_loaded,H.Unbound,contains='LOADED_NAMESPACE_OR_CODE_DRIFT')
  finally:fn.__code__=code
  check('NFH-F2_restored_'+label,g.verify_loaded()['bytes_and_object_identity_verified'] is True)
 for action in ('add','replace','remove'):
  value=m.answer
  if action=='add':m.EXTRA=object()
  elif action=='replace':m.answer=replacement
  else:del m.answer
  try:reject('NFH-F2_full_namespace_'+action,g.verify_loaded,H.Unbound,contains='LOADED_NAMESPACE_OR_CODE_DRIFT')
  finally:
   if action=='add':del m.EXTRA
   else:m.answer=value
 guard=m.__builtins__['__import__'];code=guard.__code__
 def makeguard():
  owner=None;self=None
  def bad(name,globals=None,locals=None,fromlist=(),level=0):
   if owner is self:pass
   return None
  return bad
 bad=makeguard();assert len(bad.__code__.co_freevars)==len(code.co_freevars);guard.__code__=bad.__code__
 try:reject('NFH-F2_importguard_code_mutation',g.verify_loaded,H.Unbound,contains='BUILTINS_IMPORT_GUARD_DRIFT')
 finally:guard.__code__=code
 reject('NFH-F2_undeclared_import',lambda:guard('unknown_edge'),H.Unbound,contains='UNDECLARED_IMPORT_EDGE')
 # Additional executable-descriptor control: switching binding while retaining function/code.
 desc=vars(m.Box)['static'];before=m.Box.static();m.Box.static=classmethod(desc.__func__)
 try:
  after=m.Box.static()
  try:g.verify_loaded()
  except H.Unbound:check('descriptor_binding_kind_drift_refuses',True)
  else:
   check('descriptor_binding_counterexample_observed',before==0 and after==1)
   findings.append({'id':'NFH-R1','severity':'HIGH_SOURCE_LOADED_CODE_PROVENANCE','source':'held_startup_imports.py','line':212,'trigger':'Replace Box.static staticmethod with classmethod of the same retained Python function and unchanged code object.','actual':'HeldImportGraph.verify_loaded returns bytes_and_object_identity_verified=True while Box.static() changes from 0 to 1.','expected':'Executable descriptor binding kind and descriptor object drift must refuse before READY/GO.','cause':'python_function_state records __func__ at the same path for staticmethod and classmethod; wrapper identity/type is not retained.','runtime':'UNBOUND_NOT_RUN'})
 finally:m.Box.static=desc
 check('NFH-F2_graph_restored',g.verify_loaded()['bytes_and_object_identity_verified'] is True)
finally:g.close()
check('NFH-F2_routes_restored',not g.active and 'independent_alpha' not in sys.modules)
for h in held:h.close()
# Secondary isolated namespace changes only explicit inert dependencies, never source guards.
X=component('_independent_nfh_inert',raws['finite_outside_unit.py'],flabels,fconstants);X.require_native_admission=lambda:None
clock=[0.];X.time=types.SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0])
def freshclock():
 clock[0]=0.;return X.Grant(token='a'*64,unit=grant.unit,admission_hash='c'*64,accepted_unix=0.,accepted_monotonic=0.,useful_unix=40.,final_unix=100.,useful_monotonic=40.,final_monotonic=100.,parent_useful_unix=40.,parent_final_unix=100.,reservation=(1,2),cpus=cpus).validate()
def stop_fixture(start,observe_seconds=3.,stop_seconds=21.):
 q=freshclock();clock[0]=start;events=[];owner=object.__new__(X.FiniteOutsideOwner);owner.grant=q;owner.unit_start_requested=True;owner.invocation='d'*32;owner.group='/inert/unit';owner.association={}
 row=types.SimpleNamespace(missing=False,unit=q.unit,invocation_id=owner.invocation,control_group=owner.group,main_pid=100,quiescent=True)
 def observe():events.append('observe');clock[0]+=observe_seconds;return row
 def stop(a):events.append('stop');clock[0]+=stop_seconds;return row
 owner.observe_owned=observe;owner.check_outside=lambda group:events.append('outside');owner.supervisor=types.SimpleNamespace(stop=stop)
 return owner,events,row
for start in (78.,75.81,75.8001):
 owner,events,row=stop_fixture(start);reject('NFH-F3_insufficient_full24.2_'+str(start),owner._stop_unit,X.Unbound,contains='ORIGINAL_BOUND_EXHAUSTED');check('NFH-F3_no_observe_or_stop_'+str(start),not events)
owner,events,row=stop_fixture(75.7);check('NFH-F3_full24.3_positive',owner._stop_unit() is row and clock[0]==99.7 and events==['observe','outside','stop'])
owner,events,row=stop_fixture(75.,stop_seconds=23.);reject('NFH-F3_stop_overrun_postcheck',owner._stop_unit,X.Unbound,contains='ORIGINAL_BOUND_EXHAUSTED')
owner,events,row=stop_fixture(75.,observe_seconds=5.);reject('NFH-F3_observe_slack_consumed_before_stop',owner._stop_unit,X.Unbound,contains='ORIGINAL_BOUND_EXHAUSTED');check('NFH-F3_no_stop_after_observe_overrun','stop' not in events)
def cleanup_fixture(fail=None,expired=False):
 q=freshclock();clock[0]=101. if expired else 1.;owner=object.__new__(X.FiniteOutsideOwner);owner.grant=q;owner.cgroup=None;owner.tool=None;owner.tool_pidfd=owner.worker_pidfd=owner.controller_pidfd=None;owner.dirfd=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY);events=[]
 row=types.SimpleNamespace(quiescent=True)
 for method,label,result in [('_stop_unit','stop',None),('_kill_tool','signal',None),('_wait_tool','wait',None),('_close_sockets','sockets',None),('_unlink_owned_socket','unlink',None),('observe_owned','native',row),('_fresh_cgroup_empty','cgroup',True),('_births_absent','birth',{'worker':True}),('_path_absent','path',True),('_endpoints_absent','endpoint',True)]:
  def action(label=label,result=result):
   events.append(label)
   if label==fail:raise OSError('inert:'+label)
   return result
  setattr(owner,method,action)
 return owner,events
allstages=['stop','signal','wait','sockets','unlink','native','cgroup','birth','path','endpoint']
owner,events=cleanup_fixture();check('NFH-F3_cleanup_positive_separate_fresh_witnesses',owner.cleanup()['closed'] is True and events==allstages)
for stage in allstages:
 owner,events=cleanup_fixture(stage);primary=ValueError('retained primary');e=reject('NFH-F3_cleanup_independent_failure_'+stage,lambda:owner.cleanup(primary),X.CleanupUnconfirmed);check('NFH-F3_all_wait_fresh_after_'+stage,events==allstages and e.primary_error is primary and owner.closed is False)
owner,events=cleanup_fixture(expired=True);e=reject('NFH-F3_expired_final_refuses_closure',owner.cleanup,X.CleanupUnconfirmed);check('NFH-F3_expired_all_branches_executed',events==allstages and len(e.cleanup_errors)>=11 and not owner.closed)
X.time=time
sent=[];X.send_packet=lambda sock,message:sent.append(message)
def release_owner():
 owner=object.__new__(X.FiniteOutsideOwner);owner.released=False;owner.connection=object();owner.worker_birth=(400,300,200);owner.controller_birth=(300,2,100);owner.grant=grant;owner.bundle={'original':'fixture'};owner.group='/inert/unit';owner.cgroup=types.SimpleNamespace(caps=lambda:None);owner.observe_owned=lambda:types.SimpleNamespace(main_pid=300,control_group=owner.group);owner.check_aggregate=lambda group:None;owner.verify_buffers=lambda:None;owner.inventory_current_tree=lambda:{300:owner.controller_birth,400:owner.worker_birth}
 ready={'phase':'READY','token':grant.token,'worker_birth':[400,300,200],'limit_as':384*1024**2,'bundle_sha256':hashlib.sha256(X.canonical_json(owner.bundle)).hexdigest()};owner.ready_packet=X.ready_packet_bytes(ready,owner.worker_birth,grant.token,ready['limit_as'],ready['bundle_sha256']);return owner,ready
owner,ready=release_owner();X.process_birth=lambda p:{400:owner.worker_birth,300:owner.controller_birth}[p]
badready=[{**ready,'worker_birth':[400.,300.,200.]},{**ready,'worker_birth':[True,300,200]},{**ready,'worker_birth':(400,300,200)},{**ready,'limit_as':float(384*1024**2)},{**ready,'limit_as':1},{**ready,'extra':1},{**ready,'phase':'BAD'},{**ready,'token':'e'*64}]
badready += [{k:v for k,v in ready.items() if k!=missing} for missing in ready]
for i,bad in enumerate(badready):reject('NFH-F4_bad_READY_'+str(i),lambda bad=bad:owner._release_checked(bad),X.Unbound);check('NFH-F4_no_GO_bad_READY_'+str(i),not owner.released and not sent)
saved=owner.ready_packet;ready['limit_as']=1;reject('NFH-F4_caller_mutation_refuses',lambda:owner._release_checked(ready),X.Unbound);check('NFH-F4_accepted_READY_is_immutable',owner.ready_packet==saved);ready['limit_as']=384*1024**2
owner._release_checked(ready);check('NFH-F4_exact_owner_single_GO',owner.released and len(sent)==1);reject('NFH-F4_owner_second_GO',lambda:owner._release_checked(ready),X.Unbound)
release=sent[-1];X.process_birth=lambda pid:(400,300,200)
badrelease=[{**release,'worker_birth':[400.,300.,200.]},{**release,'worker_birth':[True,300,200]},{**release,'grant':{**grant.wire(),'reservation':[1.,2.]}},{**release,'grant':{**grant.wire(),'cpus':[float(c) for c in cpus]}},{**release,'extra':True}]
badrelease += [{k:v for k,v in release.items() if k!=missing} for missing in release]
def channel():
 c=object.__new__(X.WorkerHeldChannel);c.released=False;c.grant=grant;c.birth=(400,300,200);c.digest=release['bundle_sha256'];c.socket=types.SimpleNamespace(settimeout=lambda seconds:None);return c
for i,bad in enumerate(badrelease):
 c=channel();X.recv_packet=lambda sock,bad=bad:(bad,());reject('NFH-F4_bad_RELEASE_'+str(i),c.ready_and_wait_release,X.Unbound);check('NFH-F4_no_GO_bad_RELEASE_'+str(i),not c.released)
c=channel();X.recv_packet=lambda sock:(json.loads(json.dumps(release)),());check('NFH-F4_exact_worker_single_GO',c.ready_and_wait_release()==release and c.released);reject('NFH-F4_worker_second_GO',c.ready_and_wait_release,X.Unbound)
header=b'Num       RefCount Protocol Flags    Type St Inode Path\n';row=b'0000000000000000: 00000003 00000000 00000000 0005 01 444\n';owner=object.__new__(X.FiniteOutsideOwner);owner.endpoint_inodes={444}
for i,raw in enumerate((b'',b'\n',b'x\n',header[:-1],header+b'partial\n',header+row[:-1],header+row+row,header+b'\n',header+row.replace(b'444',b'0'),header+row.replace(b'0005',b'bad!'),header+row.replace(b'00000003',b'zzzzzzzz'))):
 X.bounded_path=lambda p,n,raw=raw:raw;reject('NFH-F5_unknown_inventory_'+str(i),owner._endpoints_absent)
for label,raw,expected in [('complete_empty',header,True),('exact_inode_present',header+row,False),('different_inode',header+row.replace(b'444',b'555'),True),('path_with_spaces',header+row[:-1]+b' /inert/a b.sock\n',False)]:
 X.bounded_path=lambda p,n,raw=raw:raw;check('NFH-F5_'+label,owner._endpoints_absent() is expected)
check('NFH-F5_fresh_actual_kernel_inventory',type(F.unix_endpoint_inodes(F.bounded_path('/proc/net/unix',4*1024**2))) is set)
left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET|socket.SOCK_CLOEXEC)
fd=os.open(fixture/'beta.py',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
 F.send_packet(left,{'phase':'CUSTODY','token':'a'*64},(fd,));packet,rights=F.recv_packet(right,True)
 try:
  check('actual_isolated_anonymous_SCM_RIGHTS',packet=={'phase':'CUSTODY','token':'a'*64} and len(rights)==1 and F.read_fd(rights[0],32)==b'VALUE=17\n')
  check('received_descriptor_CLOEXEC',not os.get_inheritable(rights[0]));check('anonymous_kernel_peer_birth',F.peer_credential(left)[0]==os.getpid())
 finally:
  for received in rights:os.close(received)
 F.send_packet(left,{'phase':'READY'});reject('missing_descriptor_rights_refuses',lambda:F.recv_packet(right,True),F.Unbound)
 F.send_packet(left,{'phase':'READY'},(fd,));reject('unexpected_descriptor_rights_refuses',lambda:F.recv_packet(right,False),F.Unbound)
finally:os.close(fd);left.close();right.close()
check('all_FDs_restored',set(os.listdir('/proc/self/fd'))==initial_fds);check('no_children',not Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip());check('one_thread',len(os.listdir('/proc/self/task'))==1)
write('CONTROLS.json',{'schema':'friday.independent.native9.controls.v1','assertions':len(rows),'observations':rows,'selected_exact_AST':selected,'original_runtime_gate_UNBOUND':True,'synthetic_dependencies_no_runtime_credit':True,'nativeRPC_systemd_product_Git_account_model_effects':0,'full_dangerous_file_imports':0,'all_FD_delta':0,'own_children':0,'deadline_monotonic':deadline})
write('FINDINGS.json',{'verdict':'REQUEST_CHANGES' if findings else 'PASS_SOURCE_ONLY','findings':findings,'five_original_findings_controls_completed':True,'runtime':'UNBOUND_NOT_RUN'})
print(json.dumps({'assertions':len(rows),'findings':len(findings),'verdict':'REQUEST_CHANGES' if findings else 'PASS_SOURCE_ONLY'}))
