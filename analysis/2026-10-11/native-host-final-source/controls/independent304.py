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
cpus=tuple(sorted(os.sched_getaffinity(0)))
# The source admission guard remains unchanged even in this fixture namespace.
reject('residual_source_admission_stays_UNBOUND',F.require_native_admission,F.Unbound,contains='SOURCE_ONLY_UNBOUND')
dm=types.ModuleType('independent_descriptor_matrix')
def target(*args): return len(args)
def setter(self,value): pass
def deleter(self): pass
box=type('Box',(),{'__module__':dm.__name__,'static':staticmethod(target),'klass':classmethod(target),'value':property(target,setter,deleter)})
dm.Box=box
dm.module_static=staticmethod(target);dm.module_class=classmethod(target);dm.module_property=property(target,setter,deleter)
saved=H.namespace_state(dm)
check('descriptor_exact_positive_snapshot',H.same_namespace(dm,saved))
for member,kind in [('static',staticmethod),('klass',classmethod),('value',property)]:
 d=vars(box)[member]
 path=('Box',member,'__descriptor__')
 check('descriptor_object_kind_retained_'+member,saved[1][path][0] is d and saved[1][path][1] is kind)
 factories=[('same_kind',lambda d=d,kind=kind:kind(d.__func__) if kind in (staticmethod,classmethod) else property(d.fget,d.fset,d.fdel)),('replace_callable',lambda:target),('remove',lambda:None)]
 if kind in (staticmethod,classmethod):factories.append(('opposite_kind',lambda d=d,kind=kind:(classmethod if kind is staticmethod else staticmethod)(d.__func__)))
 for label,make in factories:
  if label=='remove':delattr(box,member)
  else:setattr(box,member,make())
  try:check('descriptor_drift_refuses_'+member+'_'+label,not H.same_namespace(dm,saved))
  finally:setattr(box,member,d)
  check('descriptor_restore_positive_'+member+'_'+label,H.same_namespace(dm,saved))
for name in ('module_static','module_class','module_property'):
 d=getattr(dm,name);kind=type(d)
 setattr(dm,name,kind(d.__func__) if kind in (staticmethod,classmethod) else property(d.fget,d.fset,d.fdel))
 try:check('module_descriptor_identity_drift_'+name,not H.same_namespace(dm,saved))
 finally:setattr(dm,name,d)
hits=[]
class StaticSubclass(staticmethod):
 def __getattribute__(self,name):
  if name=='__func__':hits.append(name);raise RuntimeError('descriptor accessor must not run')
  return super().__getattribute__(name)
class ClassSubclass(classmethod):
 def __getattribute__(self,name):
  if name=='__func__':hits.append(name);raise RuntimeError('descriptor accessor must not run')
  return super().__getattribute__(name)
class PropertySubclass(property):
 def __getattribute__(self,name):
  if name in ('fget','fset','fdel'):hits.append(name);raise RuntimeError('descriptor accessor must not run')
  return super().__getattribute__(name)
for name,d in [('static',StaticSubclass(target)),('klass',ClassSubclass(target)),('property',PropertySubclass(target,setter,deleter))]:
 reject('descriptor_subclass_refuses_before_access_'+name,lambda d=d:H.python_function_state({'member':d}),H.Unbound,contains='UNBOUND_DESCRIPTOR_SUBCLASS')
 check('descriptor_subclass_no_accessor_effect_'+name,not hits)
check('descriptor_namespace_unchanged_after_negative_controls',H.same_namespace(dm,saved))

# Exact cleanup and Grant bodies. Inert operations own only private directory FDs.
# Neither require_native_admission nor any live path is substituted or invoked.
realos=F.os;clock=[1.,1.];F.time=types.SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[1])
fdlabels=['controller_pidfd_close','worker_pidfd_close','direct_tool_pidfd_close','cgroup_fds_close','owned_socket_directory_fd_close']
mainlabels=['inventory','stop','signal','wait','sockets','unlink','native','cgroup','birth','path','endpoint']
def fixture(cross=None,fail=None,exception=OSError,moment=101.,clockkind='both',bad=None,metadata_cross=False,nested=None):
 clock[:]=[1.,1.]
 q=F.Grant(token='a'*64,unit='friday-rework-worker-'+'b'*32+'.service',admission_hash='c'*64,accepted_unix=0.,accepted_monotonic=0.,useful_unix=40.,final_unix=100.,useful_monotonic=40.,final_monotonic=100.,parent_useful_unix=40.,parent_final_unix=100.,reservation=(1,2),cpus=cpus).validate()
 o=object.__new__(F.FiniteOutsideOwner);o.grant=q;o.tool=None;o.closed=False
 events=[];closed=[];owned={};meta_events=[];nested_events=[]
 def move():
  if clockkind in ('both','unix'):clock[0]=moment
  if clockkind in ('both','monotonic'):clock[1]=moment
 def addfd(attr,label):
  fd=realos.open(OUT,realos.O_RDONLY|realos.O_DIRECTORY|realos.O_CLOEXEC);setattr(o,attr,fd);owned[fd]=label
 for attr,label in [('controller_pidfd',fdlabels[0]),('worker_pidfd',fdlabels[1]),('tool_pidfd',fdlabels[2]),('dirfd',fdlabels[4])]:addfd(attr,label)
 def finish(label):
  closed.append(label)
  if label==cross:move()
  if label==fail:raise exception('isolated close failure:'+label)
 def close(fd):
  label=owned[fd];realos.close(fd)
  if label.startswith('nested_'):
   nested_events.append(label)
   if nested and label==nested[1]:
    if nested[0]=='cross':move()
    else:raise OSError('isolated nested close failure')
  else:finish(label)
 F.os=types.SimpleNamespace(close=close)
 if nested:
  cg=object.__new__(F.CgroupCustody);cg.chain=[]
  for i in range(3):
   fd=realos.open(OUT,realos.O_RDONLY|realos.O_DIRECTORY|realos.O_CLOEXEC);owned[fd]='nested_'+str(i);cg.chain.append((fd,None,None,None))
  def cclose():
   closed.append(fdlabels[3]);return cg.close()
 else:
  def cclose():return finish(fdlabels[3])
 o.cgroup=types.SimpleNamespace(named_absent=lambda:False,close=cclose)
 class NativeRow:
  @property
  def quiescent(self):
   meta_events.append('quiescent')
   if metadata_cross:move()
   return True
 values={'native':NativeRow(),'cgroup':True,'birth':{'worker':True,'controller':True,'tool':True},'path':True,'endpoint':True}
 if bad:values[bad[0]]=bad[1]
 for method,label in [('inventory_current_tree','inventory'),('_stop_unit','stop'),('_kill_tool','signal'),('_wait_tool','wait'),('_close_sockets','sockets'),('_unlink_owned_socket','unlink'),('observe_owned','native'),('_fresh_cgroup_empty','cgroup'),('_births_absent','birth'),('_path_absent','path'),('_endpoints_absent','endpoint')]:
  def action(label=label):
   events.append(label)
   if label==cross:move()
   if label==fail:raise exception('isolated stage failure:'+label)
   return values.get(label,{})
  setattr(o,method,action)
 return o,events,closed,owned,meta_events,nested_events
def attempt(name,**kw):
 o,events,closed,owned,meta_events,nested_events=fixture(**kw);primary=ValueError('retained independent primary:'+name)
 try:
  try:result=o.cleanup(primary)
  except F.CleanupUnconfirmed as e:
   check(name+'_refused',e.primary_error is primary and e.__cause__ is primary and e.observations['closed'] is False and o.closed is False,errors=[{'stage':s,'type':type(x).__name__,'message':str(x)} for s,x in e.cleanup_errors])
   result=e.observations;error=e
  else:error=None
  check(name+'_all_main_and_FD_attempts',events==mainlabels and closed==fdlabels)
  check(name+'_actual_owned_FD_absence',all(not exists_fd(fd) for fd in owned))
  return o,result,error,meta_events,nested_events
 finally:
  for fd in owned:
   if exists_fd(fd):realos.close(fd)
  F.os=realos
def exists_fd(fd):
 try:realos.fstat(fd);return True
 except OSError:return False
o,r,e,_,_=attempt('final_FD_positive')
check('final_FD_positive_closure',e is None and r['closed'] is True and o.closed is True and r['cleanup_elapsed_seconds']==0 and set(r['final_fd_cleanup'])==set(fdlabels))
for stage in fdlabels:
 for axis in ('unix','monotonic','both'):
  o,r,e,_,_=attempt('FD_deadline_'+stage+'_'+axis,cross=stage,clockkind=axis)
  check('FD_deadline_after_and_final_'+stage+'_'+axis,e is not None and stage+':original_final' in dict(e.cleanup_errors) and 'final_closure:original_final' in dict(e.cleanup_errors))
 for kind in (OSError,KeyboardInterrupt,SystemExit):
  o,r,e,_,_=attempt('FD_failure_'+stage+'_'+kind.__name__,fail=stage,exception=kind)
  check('FD_failure_retained_'+stage+'_'+kind.__name__,e is not None and stage in dict(e.cleanup_errors) and isinstance(dict(e.cleanup_errors)[stage],kind))
for stage in mainlabels:
 o,r,e,_,_=attempt('stage_overrun_'+stage,cross=stage)
 check('main_witness_overrun_refuses_'+stage,e is not None)
for stage in fdlabels:
 o,r,e,_,_=attempt('exact_original_final_'+stage,cross=stage,moment=100.)
 check('exact_final_exhaustion_'+stage,e is not None and r['cleanup_elapsed_seconds']==99.)
o,r,e,_,_=attempt('elapsed_60_boundary',cross=fdlabels[3],moment=61.)
check('elapsed_exactly60_positive',e is None and r['closed'] is True and r['cleanup_elapsed_seconds']==60.)
o,r,e,_,_=attempt('elapsed_61_refuses',cross=fdlabels[3],moment=62.)
check('elapsed_includes_finalFD',e is not None and r['cleanup_elapsed_seconds']==61. and 'fresh_closure' in dict(e.cleanup_errors))
o,r,e,meta,_=attempt('metadata_crosses_final_after_FDs',metadata_cross=True)
check('final_check_after_metadata',e is not None and meta==['quiescent'] and 'final_closure:original_final' in dict(e.cleanup_errors))
for stage,value in [('native',None),('birth',None),('birth',[]),('cgroup',False),('cgroup',1),('path',False),('path',1),('endpoint',False),('endpoint',1),('birth',{'worker':False})]:
 label='malformed_witness_'+stage+'_'+repr(value)
 o,r,e,_,_=attempt(label,bad=(stage,value))
 check(label+'_closed_refused',e is not None)
for operation in ('cross','fail'):
 for inner in ('nested_2','nested_1','nested_0'):
  o,r,e,_,ne=attempt('nested_cgroup_'+operation+'_'+inner,nested=(operation,inner))
  check('nested_cgroup_all_owned_attempted_'+operation+'_'+inner,ne==['nested_2','nested_1','nested_0'] and e is not None)
F.time=time;F.os=realos
reject('after_fixtures_source_admission_still_UNBOUND',F.require_native_admission,F.Unbound,contains='SOURCE_ONLY_UNBOUND')
check('all_FDs_restored',set(os.listdir('/proc/self/fd'))==initial_fds)
check('no_helper_children',not Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip())
check('single_thread',len(os.listdir('/proc/self/task'))==1)
write('CONTROLS.json',{'schema':'friday.independent.native.r2.residual-controls.v1','assertions':len(rows),'observations':rows,'selected_exact_AST':selected,'full_dangerous_file_imports':0,'guard_substitutions':0,'runtime':'UNBOUND_NOT_RUN','synthetic_clocks':'source inference only, no actual native timing claim','nativeRPC_systemd_Git_product_settings_effects':0,'all_owned_FDs_closed':True})
write('FINDINGS.json',{'verdict':'PASS_SOURCE_ONLY' if not findings else 'REQUEST_CHANGES','findings':findings,'runtime':'UNBOUND_NOT_RUN'})
print(json.dumps({'assertions':len(rows),'findings':len(findings)}))
