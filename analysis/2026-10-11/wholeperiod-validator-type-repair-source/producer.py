#!/usr/bin/env python3
"""Finite, readonly full Git period preparation; no publication or admission."""
import os,sys,json,time,hashlib,pathlib,resource,signal,subprocess,select,re,posixpath,traceback
if sys.flags.optimize:raise SystemExit('REFUSED: SOURCE requires Python assertions enabled')
from datetime import datetime
from zoneinfo import ZoneInfo

from composition import trusted_path
from bounded_transport import validate_clock
from verify_fullperiod import STATUS_LITERALS, STATUS_BYTE_POLICY
import argparse
ap=argparse.ArgumentParser()
for key in ('run-dir','repo','base','end','builder','clock','delta-base'):ap.add_argument('--'+key,required=True)
args=ap.parse_args()
B=trusted_path(args.run_dir)
R=trusted_path(args.repo)
BASE=args.base;END=args.end;BUILDER=trusted_path(args.builder)
MSK=ZoneInfo('Europe/Moscow')
CLOCK=validate_clock(json.loads(trusted_path(args.clock).read_text()))
TASK={'prepare_monotonic':CLOCK['actual_task_started_monotonic'],'prepare_unix':CLOCK['actual_task_started_unix']}
ROOT={'useful_deadline_monotonic':CLOCK['useful_monotonic'],'final_deadline_monotonic':CLOCK['final_monotonic']}
USEFUL=CLOCK['useful_monotonic'];FINAL=CLOCK['final_monotonic']
CPUS=sorted(os.sched_getaffinity(0))[:2]
assert CPUS and time.monotonic()<USEFUL
os.umask(0o077)
os.sched_setaffinity(0,CPUS)
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(300,300))
resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(max(1,int(USEFUL-time.monotonic())))
OWN=[]

def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def birth(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
def save(name,value,receipt=True):
 data=enc(value)
 if receipt:assert len(data)<=65536,(name,len(data))
 p=B/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 p.chmod(0o400)
 return {'path':str(p),'bytes':len(data),'sha256':sha(data),'artifact_class':'RECEIPT' if receipt else 'SOURCE_INVENTORY_NOT_RECEIPT'}
def pin(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':sha(b)}
def read(p):
 try:return pathlib.Path(p).read_text()
 except OSError:return 'UNKNOWN_UNREADABLE'
def observe():
 cgroup=read('/proc/self/cgroup')
 cg=next((x.split(':',2)[2] for x in cgroup.splitlines() if x.startswith('0::')),None)
 root=pathlib.Path('/sys/fs/cgroup')/(cg or '').lstrip('/')
 return {'at_msk':datetime.now(MSK).isoformat(),'affinity':sorted(os.sched_getaffinity(0)),
 'cpu_count':os.cpu_count(),'cgroup':cgroup,'cpu_max':read(root/'cpu.max'),
 'cpuset_effective':read(root/'cpuset.cpus.effective'),'memory_max':read(root/'memory.max'),
 'memory_current':read(root/'memory.current'),'meminfo':read('/proc/meminfo'),
 'cpu_pressure':read('/proc/pressure/cpu'),'io_pressure':read('/proc/pressure/io'),
 'memory_pressure':read('/proc/pressure/memory'),'pressure_interpretation':'POINT_OBSERVATION_ONLY; unavailable=UNKNOWN'}

from bounded_transport import aggregate_proof, run_owned

ENV={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
ENV.update(GIT_OPTIONAL_LOCKS='0',GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1',
 GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',LC_ALL='C')
def gitrun(*args,data=None):
 number=len(OWN)+1
 out,err,record=run_owned(CLOCK,['git','--no-optional-locks','-C',str(R),*args],B/'execution',f'{number:03d}',env=ENV,data=data)
 OWN.append(record)
 if record['returncode']:raise RuntimeError('Git readonly operation failed: '+args[0])
 return out

def snapshot():
 index=R/'.git/index'
 return {'head':gitrun('rev-parse','HEAD').decode().strip(),'index':pin(index),
  'index_observation_scope':'ROOT_SOLE_INTEGRATOR; interval differences do not imply this readonly preparer mutated it'}

def comprehensive_links(module,g,tree,touched):
 rows=[];refs=[];jsons=0
 for p in sorted(touched):
  if p not in tree or tree[p]['type']!='blob' or not p.endswith(('.json','.md')):continue
  b=g.cache.get(tree[p]['git_blob'])
  if b is None:g.blobs([tree[p]['git_blob']]);b=g.cache[tree[p]['git_blob']]
  text=b.decode('utf-8')
  if p.endswith('.md'):
   found=[]
   for m in re.finditer(r'!?\[[^\]\n]*\]\(([^\)\n]+)\)',text):found.append(('INLINE',m.group(1).split(' "',1)[0].strip().strip('<>'),m.start()))
   definitions={m.group(1).lower():m.group(2).strip('<>') for m in re.finditer(r'^\s{0,3}\[([^\]]+)\]:\s*(\S+)',text,re.M)}
   for m in re.finditer(r'(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]',text):
    label=(m.group(2) or m.group(1)).lower();found.append(('REFERENCE_STYLE',definitions.get(label,'UNRESOLVED_REFERENCE:'+label),m.start()))
   for m in re.finditer(r'<((?:https?://|mailto:)[^>\s]+)>',text):found.append(('AUTOLINK',m.group(1),m.start()))
   for label,target in definitions.items():found.append(('REFERENCE_DEFINITION',target,0))
   for kind,target,offset in found:
    if target.startswith(('http:','https:','mailto:')):classification='EXTERNAL_URL_NOT_FETCHED';resolved=None
    elif target.startswith('#'):classification='LOCAL_FRAGMENT_OBSERVED_NOT_ANCHOR_ACCEPTED';resolved=p
    elif target.startswith('UNRESOLVED_REFERENCE:'):classification='UNRESOLVED_REFERENCE_STYLE';resolved=None
    else:
     resolved=module.resolve(p,target,link=True)
     present=resolved in tree or (resolved is not None and any(x.startswith(resolved.rstrip('/')+'/') for x in tree))
     classification='LOCAL_PRESENT' if present else 'LOCAL_MISSING_OR_UNSAFE'
    rows.append({'source':p,'kind':kind,'line':text[:offset].count('\n')+1,'target':target,'resolved':resolved,'classification':classification})
  else:
   jsons+=1;obj=json.loads(text)
   # Every path/URL-looking JSON string is enumerated, including provenance;
   # these are observations, never promoted to current public hash assertions.
   def walk(v,trail=()):
    if isinstance(v,dict):
     for k,x in v.items():yield from walk(x,trail+(str(k),))
    elif isinstance(v,list):
     for i,x in enumerate(v):yield from walk(x,trail+(str(i),))
    elif isinstance(v,str):yield trail,v
   for trail,target in walk(obj):
    key=trail[-1] if trail else ''
    looks=key in ('path','file','ref','source','target','repository_file','public_file','public_path','logical_source','snapshot_commit') or target.startswith(('analysis/','docs/','scripts/','tests/','validation/','http://','https://','./','../','/'))
    if not looks:continue
    if key=='snapshot_commit' and re.fullmatch('[0-9a-f]{40}',target):classification='HISTORICAL_COMMIT_FIELD';resolved=None
    elif target.startswith(('http:','https:')):classification='EXTERNAL_URL_NOT_FETCHED';resolved=None
    elif key=='logical_source':classification='PROVENANCE_NAMESPACE_NOT_PUBLIC_LINK';resolved=None
    elif target.startswith('/') or '\n' in target:classification='NONLOCAL_OR_TEXT_PROVENANCE_NOT_OPENED';resolved=None
    else:
     resolved=module.resolve(p,target)
     present=resolved in tree or (resolved is not None and any(x.startswith(resolved.rstrip('/')+'/') for x in tree))
     classification='LOCAL_PRESENT_OBSERVED' if present else 'HISTORICAL_PROVENANCE_OR_NONLOCAL_UNVERIFIED'
    refs.append({'source':p,'json_pointer':module.pointer(trail),'target':target,'resolved':resolved,'classification':classification})
 return {'scope':'ALL final touched JSON/MD bytes; explicit Markdown forms and every path/URL-looking JSON string; no filesystem external-root reads',
 'json_files':jsons,'markdown_links':rows,'json_path_or_url_strings':refs,
 'limitations':['Prose and inline code can resemble links; all detections remain inspectable.','Fragments observed; anchor resolution is not asserted.','Generic JSON provenance values are not promoted to public byte assertions.','Private supplement only; PUBLIC candidate uses canonical current-reference reports plus sanitized counts.']}

def main():
 start=time.time();save('EXECUTION-PREGO.json',{'pid':os.getpid(),'birth':birth(os.getpid()),
 'AS':list(resource.getrlimit(resource.RLIMIT_AS)),'CPU':list(resource.getrlimit(resource.RLIMIT_CPU)),
 'FSIZE':list(resource.getrlimit(resource.RLIMIT_FSIZE)),'affinity':CPUS,'before_first_GO':True,
 'aggregate_AS_ceiling_bytes':896*1024**2,'actual_aggregate_HARD':aggregate_proof(CLOCK,os.getpid()),'original_task_clock':TASK,'parent_original_clock':ROOT,
 'useful_monotonic':USEFUL,'final_monotonic':FINAL,'accepted_msk':datetime.fromtimestamp(TASK['prepare_unix'],MSK).isoformat()})
 save('RESOURCES-BEFORE.json',observe())
 before=snapshot();save('GIT-OBSERVED-BEFORE.json',before)
 source=gitrun('show',END+':scripts/daily-analysis/daily_finalizer.py')
 assert source==BUILDER.read_bytes(),'pinned builder differs from exact cutoff Git blob'
 # Installed writer remains unchanged. This exact pinned stdlib builder runs in
 # a private namespace; only its Git transport receives our stronger finite gate.
 save('BUILDER-PROVENANCE.json',{'logical_source':'scripts/daily-analysis/daily_finalizer.py',
  'snapshot_commit':END,'bytes':len(source),'sha256':sha(source),'runtime_source_installed_changed':False,
  'old_PASS_transferred':False,'transport_override':'pre-GO PID/birth/caps; finite wall/CPU; directwait/freshclose'})
 p=BUILDER;assert p.read_bytes()==source
 import types
 m=types.ModuleType('pinned_daily_finalizer');m.__file__=str(p)
 exec(compile(source,str(p),'exec'),m.__dict__)
 class ManagedGit(m.Git):
  def __init__(self,repo):
   super().__init__(repo);self.deadline=min(self.deadline,USEFUL)
  def run(self,*args,data=None):
   self.calls+=1
   return gitrun(*args,data=data)
 m.Git=ManagedGit
 summary=m.build(R,BASE,END,B/'reports')
 for f in (B/'reports').iterdir():f.chmod(0o400)
 (B/'reports').chmod(0o700)
 save('GENERATION-RECEIPT.json',summary)
 index=json.loads((B/'reports/daily-period-index.json').read_text())
 integrity=json.loads((B/'reports/publication-integrity.json').read_text())
 assert index['base_commit']==BASE and index['end_commit']==END
 assert index['counts']['commits']>0 and index['counts']['net_changed_paths']>0
 assert not index['daily_checkpoint_complete'] and not index['publication_accepted']
 g=ManagedGit(R);tree=g.tree(END);touched={r['path'] for r in index['changed_paths']}
 g.blobs(tree[p]['git_blob'] for p in touched if p in tree and tree[p]['type']=='blob')
 # Fresh factual final-byte check for every touched surviving blob, separate
 # from report generation; current worktree bytes are not substituted for d6.
 checked=[]
 for row in index['changed_paths']:
  if row.get('present_at_end') and row.get('type')=='blob':
   b=g.cache[row['git_blob']]
   assert sha(b)==row['sha256'] and len(b)==row['bytes']
   checked.append({'path':row['path'],'sha256':sha(b),'bytes':len(b)})
 all_links=comprehensive_links(m,g,tree,touched)
 linkpin=save('supplements/all-json-md-links.source-inventory.json',all_links,False)
 # Historical classes remain verbatim published fields. No status inference or
 # acceptance transfer across versions, classes, candidates, harnesses, live.
 blocks=[]
 keys={'stage','status','verdict','runtime_grant','runtime_admission','product_accepted','release_accepted','daily_checkpoint_complete','publication_accepted','classification','source_accepted','accepted'}
 for block in index['logical_blocks']:
  claims=[]
  for p in block['paths']:
   if p in tree and p.endswith('.json'):
    try:obj=json.loads(g.cache[tree[p]['git_blob']])
    except (ValueError,KeyError):continue
    for trail,node in m.walk(obj):
     selected={k:v for k,v in node.items() if k in keys and isinstance(v,(str,bool,int,float,type(None)))}
     if selected:claims.append({'source':p,'json_pointer':m.pointer(trail),'literal_fields':selected})
  blocks.append({'block':block['block'],'file_count':block['file_count'],'commits':block['commits'],
   'literal_published_status_claims':claims,'policy':'HISTORICAL_ONLY; no global/current acceptance inference'})
 classpin=save('supplements/documented-status-classes.source-inventory.json',{'blocks':blocks,'runtime_boundary':'SOURCE_ANALYSIS_ONLY; no grants/installation/native/live/journey/release acceptance'},False)
 delta=g.diff(args.delta_base,END)
 assert len(delta)>0
 from collections import Counter
 linkcounts=dict(Counter(r['classification'] for r in all_links['markdown_links']))
 status={
  'schema':'friday.analysis.fullperiod.preparation-status.v1','stage':'PROVISIONAL_NOT_DAILY_COMPLETE',
  'base_commit':BASE,'end_commit':END,'date_msk':'2026-10-11',
  'counts':index['counts'],'delta_from_prior_f544_paths':len(delta),
  'daily_checkpoint_complete':False,'publication_accepted':False,'runtime_grant':False,'product_accepted':False,
  'current_source_status':STATUS_LITERALS,
  'current_source_status_validation':STATUS_BYTE_POLICY,
  'runtime_boundaries':{'G7':'FAIL_NO_REPLAY','G8':'PHYSICAL_OWNER_TERMINAL_PENDING',
   'kernel_120_seconds':'NOT_GRANTED','normal_3600_seconds':'UNSTARTED',
   'full_native_19':'NOT_ACCEPTED','seven_journeys':'NOT_ACCEPTED','release':'NOT_ACCEPTED'},
  'scope_limits':['New actual local Git object inventory; previous validation results are provenance only.',
   'All commit parent edges, intermediate changes, deleted and current blobs carry Git IDs, SHA256 and byte counts.',
   'Canonical link/hash/manifest checks are SOURCE publication integrity; they confer no product or runtime acceptance.',
   'Additional Markdown reference/autolink and JSON path/provenance observations are retained privately; fragment anchors and external URLs unaccepted.',
   'Fixed supplied cutoff inventory remains historical if main advances. Actual daily cutoff/publication is owned by Astra.'],
  'expanded_link_observation_counts':{'markdown':len(all_links['markdown_links']),'json_path_or_url_strings':len(all_links['json_path_or_url_strings']),'markdown_classes':linkcounts},
  'remaining':['Reconcile the actual 21:00 cutoff with the preserved baseline; include later period work.',
   'Independent complete-period final artifact/status/privacy review.',
   'Integrator publication and exact final remote SHA verification.']}
 public=B/'PUBLIC';public.mkdir(mode=0o700)
 for f in (B/'reports').iterdir():
  if f.name=='MANIFEST.json':continue
  target=public/f.name;target.write_bytes(f.read_bytes());target.chmod(0o400)
 (public/'source-status.json').write_bytes(enc(status));(public/'source-status.json').chmod(0o400)
 md=('Full historical Git period preparation: '+BASE+' → '+END+'.\n\n'
  'This is SOURCE analysis of a fixed historical supplied cutoff. The daily checkpoint, publication, runtime, product and release are not accepted.\n\n'
  '[Inventory](daily-period-index.json), [integrity](publication-integrity.json), and [current SOURCE status](source-status.json) bind the exact historical objects and preserve failures and limits.\n\n'
  'C17 has 633 independent controls for its exact pinned SOURCE domain. Its broader malformed-schema API remains unaccepted. The original main ELF prototype has historical 44 author controls; later C18 has 109 author controls with exact manual receipt and independent acceptance pending. The typed maps LF/ASCII fix has 192 independent controls for exact SOURCE only. C18 author SOURCE was received manually; original delivery UNKNOWN. C19 has 942 author controls and 302 independent controls accepted for exact SOURCE domain only. Loader, imports, DSO and cgroup authority remain unbound.\n\n'
  'G7 remains FAIL / NO_REPLAY; G8 needs the physical owner terminal. The 120-second kernel check is not granted, the 3600-second normal check is unstarted, and full native 19, seven journeys and release remain NOT_ACCEPTED.\n\n'
  'Nested status annotations are checked as inherited literal bytes only. This gate does not validate their semantic authority or independent acceptance.\n\n'
  'The actual daily final cutoff, independent final privacy review and exact remote publication verification remain with Astra. This fixed range stays historical if main advances. No release forecast or old validation transfer is made.\n')
 (public/'README.md').write_text(md);(public/'README.md').chmod(0o400)
 publicfiles=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),
  'artifact_class':'SOURCE_INVENTORY_NOT_RECEIPT' if p.stat().st_size>65536 else 'SOURCE_ANALYSIS_NOT_RECEIPT'} for p in sorted(public.iterdir())]
 mf={'schema':'friday.analysis.daily.v1','baseline_commit':BASE,'end_commit':END,'date_msk':'2026-10-11',
  'stage':'PROVISIONAL_NOT_DAILY_COMPLETE','daily_checkpoint_complete':False,'publication_accepted':False,
  'runtime_grant':False,'product_accepted':False,'manifest_excludes_itself':True,'files':publicfiles}
 (public/'MANIFEST.json').write_bytes(enc(mf));(public/'MANIFEST.json').chmod(0o400)
 # Pattern observation is preparation, not an independent privacy acceptance.
 forbidden={'private_absolute_path':rb'/home/|/run/user/|\.jericho/|\.config/codex',
  'uuid':rb'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
  'private_key':rb'-----BEGIN [A-Z ]*PRIVATE KEY-----',
  'secret_value':rb'(?i)(?:api[_-]?key|access[_-]?token|password)\s*[=:]\s*["\x27]?[A-Za-z0-9_/-]{16,}',
  'raw_pid':rb'"(?:pid|ppid|child_pid|supervisor_pid)"\s*:\s*\d+',
  'private_transport':rb'(?i)(?:native[-_/]inbox|handoff[-_/]snapshot|\.codex/|hooks\.json|config\.toml)'}
 privacy={name:[] for name in forbidden}
 for f in public.iterdir():
  for name,pattern in forbidden.items():
   if re.search(pattern,f.read_bytes()):privacy[name].append(f.name)
 assert not any(privacy.values()),privacy
 save('PUBLIC-PREPARATION-OBSERVATION.json',{'pattern_hits':privacy,'public_files':publicfiles,
  'independent_privacy_acceptance':False,'public_manifest':pin(public/'MANIFEST.json')})
 defects=integrity['findings']+integrity['publication_gaps']
 extra=[r for r in all_links['markdown_links'] if r['classification'] in ('UNRESOLVED_REFERENCE_STYLE','LOCAL_MISSING_OR_UNSAFE')]
 save('DEFECTS.json',{'canonical_integrity_defects':defects,'expanded_markdown_link_defects':extra,
  'counts':{'canonical':len(defects),'expanded_markdown':len(extra)},
  'exclusions':['External URLs not fetched; fragment anchors not accepted.','Generic JSON provenance not silently promoted to current local links.'],
  'reproduction':'Use exact supplied cutoff objects and pinned builder plus independently runnable verify_fullperiod.py; fresh finite clock required.'})
 after=snapshot();save('GIT-OBSERVED-AFTER.json',after);save('RESOURCES-AFTER.json',observe())
 assert all(r['directwait'] and r['exact_birth_absent'] and r['returncode']==0 for r in OWN)
 save('PREPARATION-CLOSED.json',{'state':'FULLPERIOD_PREPARATION_GENERATED_NOT_INDEPENDENTLY_ACCEPTED',
  'base_commit':BASE,'end_commit':END,'counts':index['counts'],'delta_f544_paths':len(delta),
  'current_blob_rechecked_count':len(checked),'current_blob_rechecked_bytes':sum(x['bytes'] for x in checked),
  'supplements':[linkpin,classpin],'public_manifest':pin(public/'MANIFEST.json'),
  'public_payload_bytes':sum(x['bytes'] for x in publicfiles),
  'own_readers':len(OWN),'all_directwait_freshclose':True,'aggregate_AS_ceiling_bytes':896*1024**2,
  'CPU_affinity_bound':CPUS,'descendant_custody_scope':'DIRECT_OWN_READERS_ONLY; no whole-host claim',
  'index_before':before['index'],'index_after':after['index'],'index_same':before['index']['sha256']==after['index']['sha256'],
  'HEAD_before':before['head'],'HEAD_after':after['head'],'fixed_end_remains_historical':True,
  'elapsed_since_original_prepare_seconds':time.time()-TASK['prepare_unix'],
  'completed_msk':datetime.now(MSK).isoformat(),'within_original_useful':time.monotonic()<USEFUL,
  'within_original_final':time.monotonic()<FINAL,'daily_checkpoint_complete':False,
  'independent_wholeperiod_acceptance':False,'runtime_grant':False,'product_accepted':False,
  'supervisor_fresh_closure':'PENDING_TOOL_RETURN_AND_EXTERNAL_FRESH_PROC_CHECK'})
 print(json.dumps({'generated':True,'counts':index['counts'],'public_manifest_sha256':sha((public/'MANIFEST.json').read_bytes()),
  'supervisor_pid':os.getpid(),'supervisor_birth':birth(os.getpid()),'within_original_useful':time.monotonic()<USEFUL}))

if __name__=='__main__':
 try:main()
 except BaseException as exc:
  save('PREPARATION-FAILURE.json',{'error':str(exc),'traceback':traceback.format_exc(),'owned_readers':OWN,
   'original_clock_not_reset':True,'within_final':time.monotonic()<FINAL})
  raise
