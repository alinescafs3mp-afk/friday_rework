#!/usr/bin/env python3
"""Whole historical period byte gate. Preparation only; never runtime acceptance.

Requires an explicit original clock JSON with useful/final monotonic deadlines.
Creates only a new private receipts directory. Reads pinned Git objects, report
and PUBLIC files; no checkout, Git index write, model, network, or product import.
"""
import argparse,hashlib,json,os,pathlib,re,resource,select,signal,subprocess,sys,time,types

if sys.flags.optimize:
 raise SystemExit('REFUSED: artifact gate requires Python assertions enabled')

def sha(b):return hashlib.sha256(b).hexdigest()
def birth(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def assert_manifest(root,expected):
 root=pathlib.Path(root)
 raw=(root/'MANIFEST.json').read_bytes();assert sha(raw)==expected,'external manifest pin mismatch'
 obj=json.loads(raw);entries=obj['files'];seen=set()
 for e in entries:
  p=e['path'];assert isinstance(p,str) and p and not p.startswith('/')
  assert all(x not in ('','..','.') for x in p.split('/')) and p not in seen
  seen.add(p);f=root/p;assert f.is_file() and not f.is_symlink()
  b=f.read_bytes();assert len(b)==e['bytes'],'payload byte count mismatch'
  assert sha(b)==e['sha256'],'payload SHA256 mismatch'
 assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==seen|{'MANIFEST.json'},'unlisted/missing payload'
 return obj

def hard_as(pid):
 lines=pathlib.Path(f'/proc/{pid}/limits').read_text().splitlines()
 row=next(x for x in lines if x.startswith('Max address space'))
 token=row.split()[4]
 assert token!='unlimited','unbounded named process'
 return int(token)
def aggregate_proof(clock,worker_pid,reader_pid=None):
 owner=clock['launcher'];assert birth(owner['pid'])==owner['birth'],'launcher birth drift'
 assert os.getppid()==owner['pid'],'not owned by designated launcher'
 ids=[owner['pid'],worker_pid]+([reader_pid] if reader_pid is not None else [])
 hard={str(pid):hard_as(pid) for pid in ids}
 expected=[128*1024**2,576*1024**2]+([192*1024**2] if reader_pid is not None else [])
 assert list(hard.values())==expected,'actual hard cap differs from topology'
 assert sum(hard.values())<=1024**3,'aggregate hard limit above 1GiB'
 cpus=clock['shared_cpus']
 assert all(sorted(os.sched_getaffinity(pid))==cpus for pid in ids),'CPU affinity mismatch'
 return {'named_process_HARD_AS_bytes':hard,'aggregate_HARD_AS_bytes':sum(hard.values()),'bound_bytes':1024**3,'shared_affinity':cpus,'actual_kernel_read_before_GO':True,'unobserved_descendants':'UNKNOWN_NOT_ADMITTED'}

GATE=r'''
import os,sys,json,resource,signal
rf,gf=int(sys.argv[1]),int(sys.argv[2]);cmd=json.loads(sys.argv[3]);signal.alarm(int(float(sys.argv[4])) or 1)
birth=open('/proc/self/stat').read().rsplit(')',1)[1].split()[19]
os.write(rf,json.dumps({'pid':os.getpid(),'birth':birth,'AS':list(resource.getrlimit(resource.RLIMIT_AS)),
'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),
'affinity':sorted(os.sched_getaffinity(0)),'before_GO':True,'command_executed':False}).encode());os.close(rf)
if os.read(gf,1)!=b'G':sys.exit(91)
os.close(gf);os.execvpe(cmd[0],cmd,os.environ)
'''

class Transport:
 def __init__(self,repo,receipts,clock):
  self.repo=str(pathlib.Path(repo).resolve(strict=True));self.receipts=pathlib.Path(receipts)
  assert not self.receipts.exists();self.receipts.mkdir(mode=0o700)
  self.clock=clock;self.useful=clock['useful_monotonic'];self.final=clock['final_monotonic'];assert time.monotonic()<self.useful
  self.cpus=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,self.cpus)
  resource.setrlimit(resource.RLIMIT_AS,(576*1024**2,576*1024**2))
  resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(max(1,int(self.useful-time.monotonic())))
  self.owned=[];self.env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
  self.env.update(GIT_OPTIONAL_LOCKS='0',GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1',GIT_TERMINAL_PROMPT='0',
   GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',LC_ALL='C')
  self.save('SUPERVISOR-PREGO.json',{'pid':os.getpid(),'birth':birth(os.getpid()),'AS':list(resource.getrlimit(resource.RLIMIT_AS)),
   'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),
   'affinity':self.cpus,'before_first_GO':True,'aggregate_AS_ceiling_bytes':896*1024**2,'actual_aggregate_HARD':aggregate_proof(self.clock,os.getpid()),'original_clock':clock})
 def save(self,name,v):
  b=encoded(v);assert len(b)<=65536
  p=self.receipts/name
  with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  p.chmod(0o400)
 def limits(self):
  os.sched_setaffinity(0,self.cpus);resource.setrlimit(resource.RLIMIT_AS,(192*1024**2,192*1024**2))
  resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
 def run(self,*args,data=None):
  assert time.monotonic()<self.useful
  seq=len(self.owned)+1;rr,rw=os.pipe();gr,gw=os.pipe();wall=min(60,self.useful-time.monotonic())
  cmd=['git','--no-optional-locks','-C',self.repo,*args]
  p=subprocess.Popen([sys.executable,'-c',GATE,str(rw),str(gr),json.dumps(cmd),str(wall)],stdin=subprocess.PIPE,
   stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=self.env,pass_fds=(rw,gr),start_new_session=True,preexec_fn=self.limits)
  os.close(rw);os.close(gr);bd=birth(p.pid);out=b'';err=b''
  row={'sequence':seq,'pid':p.pid,'birth':bd,'operation':args[0]};self.owned.append(row)
  try:
   assert select.select([rr],[],[],min(5,wall))[0],'missing readiness'
   ready=json.loads(os.read(rr,65536));os.close(rr);rr=-1
   assert ready['pid']==p.pid and ready['birth']==bd and ready['affinity']==self.cpus
   assert ready['AS']==[192*1024**2]*2 and ready['CPU']==[30]*2 and ready['FSIZE']==[64*1024**2]*2
   self.save(f'{seq:03d}-PREGO.json',{**row,'ready':ready,'limits_actual':pathlib.Path(f'/proc/{p.pid}/limits').read_text(),
    'aggregate_AS_ceiling_bytes':896*1024**2,'actual_aggregate_HARD':aggregate_proof(self.clock,os.getpid(),p.pid),'before_GO':True})
   assert birth(p.pid)==bd and time.monotonic()<self.useful
   os.write(gw,b'G');os.close(gw);gw=-1
   out,err=p.communicate(input=data,timeout=min(wall+2,self.final-time.monotonic()))
  except BaseException:
   if p.returncode is None:
    if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGTERM)
    try:out,err=p.communicate(timeout=3)
    except subprocess.TimeoutExpired:
     if birth(p.pid)==bd:os.killpg(p.pid,signal.SIGKILL)
     out,err=p.communicate(timeout=3)
   raise
  finally:
   if rr>=0:os.close(rr)
   if gw>=0:os.close(gw)
   if p.returncode is None:p.wait(timeout=3)
   row.update(returncode=p.returncode,directwait=True,fresh_birth=birth(p.pid),exact_birth_absent=birth(p.pid)!=bd,
    stdout_bytes=len(out),stdout_sha256=sha(out),stderr_bytes=len(err),stderr_sha256=sha(err))
   self.save(f'{seq:03d}-CLOSED.json',row);assert row['exact_birth_absent']
  assert p.returncode==0,'readonly Git refusal: '+args[0]
  return out

def raw_diff(raw):
 parts=raw.split(b'\0');rows=[]
 for i in range(0,len(parts)-1,2):
  fields=parts[i].decode().split();assert len(fields)==5 and fields[0].startswith(':')
  om,nm,oo,no,status=fields;row={'status':status,'path':parts[i+1].decode()}
  for key,mode,oid in [('before',om[1:],oo),('after',nm,no)]:
   if mode!='000000':row[key]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','git_blob':oid}
  rows.append(row)
 return rows
def strip_hash(row):
 return {k:({x:y for x,y in v.items() if x not in ('sha256','bytes')} if isinstance(v,dict) else v)
  for k,v in row.items() if k!='parent_commit'}
def parse_tree(raw):
 rows={}
 for v in raw.split(b'\0'):
  if not v:continue
  h,p=v.split(b'\t',1);mode,typ,oid=h.decode().split();rows[p.decode()]={'mode':mode,'type':typ,'git_blob':oid}
 return rows
def blobs(run,oids):
 ordered=sorted(set(oids));raw=run('cat-file','--batch',data=('\n'.join(ordered)+'\n').encode());result={};pos=0
 for oid in ordered:
  eol=raw.index(b'\n',pos);h=raw[pos:eol].decode().split();assert h[:2]==[oid,'blob'] and len(h)==3
  n=int(h[2]);pos=eol+1;b=raw[pos:pos+n];assert len(b)==n and raw[pos+n:pos+n+1]==b'\n'
  result[oid]={'sha256':sha(b),'bytes':n};pos+=n+1
 assert pos==len(raw);return result

def validate(a,t):
 reports=pathlib.Path(a.reports);public=pathlib.Path(a.public)
 reportmf=assert_manifest(reports,a.report_manifest_sha256);publicmf=assert_manifest(public,a.public_manifest_sha256)
 index=json.loads((reports/'daily-period-index.json').read_text());integrity=json.loads((reports/'publication-integrity.json').read_text())
 assert re.fullmatch('[0-9a-f]{40}',a.base) and re.fullmatch('[0-9a-f]{40}',a.end)
 assert index['base_commit']==integrity['base_commit']==a.base and index['end_commit']==integrity['end_commit']==a.end
 for obj in [index,integrity,reportmf,publicmf]:
  assert not obj['daily_checkpoint_complete'] and not obj['publication_accepted'] and not obj['runtime_grant'] and not obj['product_accepted']
 assert (public/'daily-period-index.json').read_bytes()==(reports/'daily-period-index.json').read_bytes()
 assert (public/'publication-integrity.json').read_bytes()==(reports/'publication-integrity.json').read_bytes()
 t.run('merge-base','--is-ancestor',a.base,a.end)
 commitlines=t.run('rev-list','--reverse','--topo-order','--parents',a.base+'..'+a.end).decode().splitlines()
 commits=[line.split() for line in commitlines]
 assert [(c['commit'],c['parents']) for c in index['ordered_commits']]==[(r[0],r[1:]) for r in commits],'commit chain mismatch'
 flags=['--raw','-z','--no-abbrev','--no-renames','--no-ext-diff','--no-textconv','--no-relative','--no-color']
 observed=[];by_path={};allmeta=[];edge_count=0
 for published,commit in zip(index['ordered_commits'],commits):
  details=t.run('show','-s','--no-show-signature','--encoding=UTF-8','--format=%cI%x00%s',commit[0]).decode().rstrip('\n').split('\0',1)
  assert published['committed_at']==details[0] and published['subject']==details[1],'commit metadata mismatch'
  rows=[]
  for parent in commit[1:] or [None]:
   edge_count+=1
   raw=t.run('diff',*flags,parent,commit[0]) if parent else t.run('diff-tree','--root','--no-commit-id','-r',*flags,commit[0])
   actual=raw_diff(raw)
   recorded=[r for r in published['changed_paths'] if r['parent_commit']==parent]
   assert [strip_hash(r) for r in recorded]==actual,'parent edge diff mismatch'
   for r in recorded:
    allmeta.extend(r[k] for k in ('before','after') if k in r and r[k]['type']=='blob')
   for r in actual:
    by_path.setdefault(r['path'],[]).append({'commit':commit[0],'parent_commit':parent,'status':r['status']})
   rows.extend(actual)
  observed.extend(rows)
 net=raw_diff(t.run('diff',*flags,a.base,a.end))
 assert [strip_hash(r) for r in index['net_changed_paths']]==net,'net diff mismatch'
 current=parse_tree(t.run('ls-tree','-r','-z',a.end));old=parse_tree(t.run('ls-tree','-r','-z',a.base))
 assert {r['path'] for r in index['changed_paths']}==set(by_path),'cumulative touched path mismatch'
 netstatus={r['path']:r['status'] for r in net}
 for row in index['changed_paths']:
  p=row['path'];assert row['commits']==by_path[p] and row['status']==netstatus.get(p,'INTERMEDIATE_ONLY')
  assert row['present_at_base']==(p in old) and row['present_at_end']==(p in current)
  if p in current:
   assert {k:row[k] for k in ('mode','type','git_blob')}==current[p]
   if row['type']=='blob':allmeta.append(row)
 actualblobs=blobs(t.run,[m['git_blob'] for m in allmeta])
 for m in allmeta:assert actualblobs[m['git_blob']]=={'sha256':m['sha256'],'bytes':m['bytes']},'historical/current blob SHA256 or byte mismatch'
 intermediate=sorted(set(by_path)-set(netstatus));assert index['intermediate_only_paths']==intermediate
 partition=[p for b in index['logical_blocks'] for p in b['paths']]
 assert len(partition)==len(set(partition)) and set(partition)==set(by_path)
 assert index['counts']['commits']==len(commits) and index['counts']['touched_paths']==len(by_path) and index['counts']['net_changed_paths']==len(net)
 # Independently rerun current manifests, public byte references, typed
 # historical references and links from the exact same pinned builder bytes.
 code=pathlib.Path(a.builder).read_bytes();gitcode=t.run('show',a.end+':scripts/daily-analysis/daily_finalizer.py')
 assert code==gitcode,'builder is not exact Git cutoff source'
 m=types.ModuleType('pinned_byte_validator');m.__file__=a.builder;exec(compile(code,a.builder,'exec'),m.__dict__)
 class ReadGit(m.Git):
  def run(self,*args,data=None):self.calls+=1;return t.run(*args,data=data)
 g=ReadGit(t.repo);g.deadline=t.useful
 checks=m.verify_public(g,current,by_path,end_commit=a.end)
 assert not checks['findings'] and not checks['publication_gaps']
 for key,value in checks.items():assert integrity[key]==value,'current reference validation mismatch: '+key
 expectedcounts={'commits':len(commits),'net_changed_paths':len(net),'touched_paths':len(by_path),'intermediate_only_paths':len(intermediate),'logical_blocks':len(index['logical_blocks']),**{k:len(checks[k]) for k in ('manifests','hash_references','local_markdown_links','local_json_links','external_root_references','historical_git_references')},'json_files_parsed':checks['json_files_parsed'],'publication_gaps':len(checks['publication_gaps'])}
 assert index['counts']==integrity['counts']==expectedcounts,'full count mapping mismatch'
 for f in public.iterdir():
  raw=f.read_bytes()
  assert not re.search(rb'/home/|/run/user/|\.jericho/|\.codex/|-----BEGIN [A-Z ]*PRIVATE KEY-----|\"(?:pid|ppid|child_pid|supervisor_pid)\"\s*:\s*\d+',raw),'public private marker'
 status=json.loads((public/'source-status.json').read_text())
 assert status['base_commit']==a.base and status['end_commit']==a.end and status['counts']==index['counts']
 assert status['runtime_boundaries']=={'G7':'FAIL_NO_REPLAY','G8':'PHYSICAL_OWNER_TERMINAL_PENDING','kernel_120_seconds':'NOT_GRANTED',
  'normal_3600_seconds':'UNSTARTED','full_native_19':'NOT_ACCEPTED','seven_journeys':'NOT_ACCEPTED','release':'NOT_ACCEPTED'}
 assert not status['daily_checkpoint_complete'] and not status['publication_accepted'] and not status['runtime_grant'] and not status['product_accepted']
 assert all(r['returncode']==0 and r['directwait'] and r['exact_birth_absent'] for r in t.owned)
 return {'state':'WHOLEPERIOD_PREPARATION_GATE_PASS_NOT_INDEPENDENT_ACCEPTANCE','base_commit':a.base,'end_commit':a.end,
  'counts':index['counts'],'parent_edges':edge_count,'observed_edge_path_events':len(observed),
  'distinct_historical_and_current_blobs':len(actualblobs),'historical_and_current_blob_reference_count':len(allmeta),
  'historical_and_current_blob_bytes':sum(v['bytes'] for v in actualblobs.values()),'direct_readers':len(t.owned),
  'all_directwait_freshclose':True,'aggregate_AS_ceiling_bytes':896*1024**2,'actual_aggregate_HARD':aggregate_proof(t.clock,os.getpid()),'affinity':t.cpus,
  'public_manifest_sha256':a.public_manifest_sha256,'report_manifest_sha256':a.report_manifest_sha256,
  'builder_sha256':sha(code),'gate_source_sha256':sha(pathlib.Path(__file__).read_bytes()),'python_assertions_enabled':sys.flags.optimize==0,
  'daily_checkpoint_complete':False,'independent_privacy_acceptance':False,
  'independent_wholeperiod_acceptance':False,'runtime_grant':False,'product_accepted':False,
  'supervisor_pid':os.getpid(),'supervisor_birth':birth(os.getpid()),'within_original_useful':time.monotonic()<t.useful,
  'supervisor_fresh_closure':'PENDING_EXTERNAL_TOOL_RETURN_AND_PROC_CHECK'}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('repo','reports','public','base','end','builder','clock','receipts','report-manifest-sha256','public-manifest-sha256'):p.add_argument('--'+name,required=True)
 a=p.parse_args();os.umask(0o077);t=Transport(a.repo,a.receipts,json.loads(pathlib.Path(a.clock).read_text()))
 try:
  result=validate(a,t);t.save('RESULT.json',result);print(json.dumps(result));return 0
 except BaseException as exc:
  t.save('FAILURE.json',{'state':'PREPARATION_GATE_FAILED','error':str(exc),'owned_readers':t.owned});raise

if __name__=='__main__':sys.exit(main())
