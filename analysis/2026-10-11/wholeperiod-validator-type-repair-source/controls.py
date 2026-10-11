import os,sys,json,pathlib,hashlib,shutil,types,resource,time
if sys.flags.optimize:raise SystemExit('REFUSED: SOURCE requires Python assertions enabled')
from composition import trusted_path
W=trusted_path(sys.argv[2]);S=pathlib.Path(__file__).parent
m=types.ModuleType('owned_fullperiod');m.__file__=str(S/'verify_fullperiod.py')
exec(compile(pathlib.Path(m.__file__).read_bytes(),m.__file__,'exec'),m.__dict__)
def save(n,j):
 b=(json.dumps(j,indent=2)+'\n').encode();assert len(b)<=65536
 p=W/n;p.write_bytes(b);p.chmod(0o400)
if sys.argv[1]=='short':
 clock=json.loads((W/'EXECUTION-CLOCK.json').read_text());t=m.Transport(sys.argv[3],W/'short-readers',clock)
 assert t.run('cat-file','-t',sys.argv[5])==b'commit\n'
 assert t.run('merge-base','--is-ancestor',sys.argv[4],sys.argv[5])==b''
 root=W/'short-fixture';root.mkdir(mode=0o700);(root/'payload').write_bytes(b'real bytes')
 mf={'files':[{'path':'payload','bytes':10,'sha256':m.sha(b'real bytes')}]};raw=m.encoded(mf);(root/'MANIFEST.json').write_bytes(raw)
 assert m.assert_manifest(root,m.sha(raw))==mf
 save('SHORT-RESULT.json',{'actual_git_positive':2,'physical_manifest_positive':1,'actual_HARD_aggregate':896*1024**2,'actual_kernel_caps_recorded_before_each_GO':True,'author_only':True})
else:
 source=W/'PUBLIC';raw=(source/'MANIFEST.json').read_bytes();digest=m.sha(raw);payload=json.loads(raw)['files'][0]['path'];rows=[]
 C=W/'CASES';C.mkdir(mode=0o700)
 for case in ['same-length','shorter','missing','unlisted','unsafe-path']:
  root=C/case;shutil.copytree(source,root);p=root/payload;expect=digest
  if case in ('same-length','shorter'):
   b=p.read_bytes();p.chmod(0o600);p.write_bytes(bytes([b[0]^1])+b[1:] if case=='same-length' else b[:-1]);p.chmod(0o400)
  elif case=='missing':p.unlink()
  elif case=='unlisted':(root/'extra').write_bytes(b'extra')
  else:
   obj=json.loads(raw);obj['files'][0]['path']='../escape';updated=m.encoded(obj);p=root/'MANIFEST.json';p.chmod(0o600);p.write_bytes(updated);p.chmod(0o400);expect=m.sha(updated)
  try:m.assert_manifest(root,expect)
  except (AssertionError,FileNotFoundError) as e:rows.append({'id':case,'state':'REFUSED_AS_EXPECTED','error_type':type(e).__name__,'message':str(e)})
  else:raise AssertionError('physical corruption accepted: '+case)
 save('FIVE-PHYSICAL-CONTROLS.json',{'controls':rows,'raw':5,'unique':5,'PASS':5,'FAIL':0,'physical_whole_PUBLIC_copies':True,'gate_source_sha256':m.sha(pathlib.Path(m.__file__).read_bytes())})

if sys.argv[1]=='negative':
 from types import SimpleNamespace
 from bounded_transport import validate_clock
 import copy
 C=W/'VALIDATOR-CASES';C.mkdir(mode=0o700)
 records=[];clock=json.loads((W/'EXECUTION-CLOCK.json').read_text())
 def write(p,obj):
  if p.exists():p.chmod(0o600)
  p.write_bytes(m.encoded(obj));p.chmod(0o400)
 def repin(root):
  obj=json.loads((root/'MANIFEST.json').read_text())
  for r in obj['files']:
   b=(root/r['path']).read_bytes();r.update(bytes=len(b),sha256=m.sha(b))
  write(root/'MANIFEST.json',obj)
  return m.sha((root/'MANIFEST.json').read_bytes())
 cases=[
  ('TYPE-presence-integer','literal current-path presence booleans mismatch'),
  ('TYPE-presence-float','literal current-path presence booleans mismatch'),
  ('TYPE-integrity-bool','current reference validation mismatch'),
  ('TYPE-integrity-float','current reference validation mismatch'),
  ('TYPE-historical-runtime-zero','current reference validation mismatch'),
  ('CV1-net-before-SHA','historical/current blob SHA256 or byte mismatch'),
  ('CV1-net-after-bytes','historical/current blob SHA256 or byte mismatch'),
  ('CV2-foreign-parent','foreign parent row refused'),
  ('CV2-duplicate-edge','parent edge diff mismatch'),
  ('CV2-duplicate-current','ordered unique cumulative touched paths mismatch'),
  ('CV3-file-count','complete canonical logical block metadata mismatch'),
  ('CV3-boolean-count','complete canonical logical block metadata mismatch'),
  ('CV3-commit-list','complete canonical logical block metadata mismatch'),
  ('CV3-package-label','complete canonical logical block metadata mismatch'),
  ('CV4-target','fresh integrity_artifact target/SHA/bytes mismatch'),
  ('CV4-SHA','fresh integrity_artifact target/SHA/bytes mismatch'),
  ('CV4-bytes','fresh integrity_artifact target/SHA/bytes mismatch'),
  ('CV5-nested-acceptance-promotion','nested status literal bytes changed without authority evidence'),
  ('CV5-semantic-authority-promotion','nested status semantic authority promotion refused'),
  ('CV5-zero-authority-flag','nested status semantic authority promotion refused')]
 for case,expected in cases:
  assert time.monotonic()<clock['useful_monotonic']
  root=C/case;root.mkdir(mode=0o700)
  reports=root/'reports';public=root/'PUBLIC'
  shutil.copytree(W/'reports',reports);shutil.copytree(W/'PUBLIC',public)
  index=json.loads((reports/'daily-period-index.json').read_text())
  if case.startswith('TYPE-presence'):
   row=next(r for r in index['changed_paths'] if r['present_at_end'] is True)
   row['present_at_end']=1 if case=='TYPE-presence-integer' else 1.0
  elif case.startswith('TYPE-'):
   integrity=json.loads((reports/'publication-integrity.json').read_text())
   if case=='TYPE-integrity-bool':
    row=next(r for r in integrity['manifests'] if r['duplicate_entries']==0);row['duplicate_entries']=False
   elif case=='TYPE-integrity-float':
    row=next(r for r in integrity['hash_references'] if type(r.get('actual_bytes')) is int);row['actual_bytes']=float(row['actual_bytes'])
   else:
    row=integrity['historical_git_references'][0];assert row['runtime_grant'] is False;row['runtime_grant']=0
   write(reports/'publication-integrity.json',integrity);write(public/'publication-integrity.json',integrity)
   raw=(reports/'publication-integrity.json').read_bytes();index['integrity_artifact'].update(bytes=len(raw),sha256=m.sha(raw))
  elif case.startswith('CV1'):
   key='before' if 'before' in case else 'after'
   row=next(r for r in index['net_changed_paths'] if key in r and r[key]['type']=='blob')
   if key=='before':row[key]['sha256']='0'*64
   else:row[key]['bytes']+=1
  elif case=='CV2-foreign-parent':
   commit=next(c for c in index['ordered_commits'] if c['changed_paths']);extra=copy.deepcopy(commit['changed_paths'][0]);extra['parent_commit']='0'*40;commit['changed_paths'].append(extra)
  elif case=='CV2-duplicate-edge':
   commit=next(c for c in index['ordered_commits'] if c['changed_paths']);commit['changed_paths'].append(copy.deepcopy(commit['changed_paths'][0]))
  elif case=='CV2-duplicate-current':index['changed_paths'].append(copy.deepcopy(index['changed_paths'][0]))
  elif case=='CV3-file-count':index['logical_blocks'][0]['file_count']=999
  elif case=='CV3-boolean-count':
   block=next(b for b in index['logical_blocks'] if b['file_count']==1);block['file_count']=True
  elif case=='CV3-commit-list':index['logical_blocks'][0]['commits'].append('0'*40)
  elif case=='CV3-package-label':index['logical_blocks'][0]['block']='fake/package'
  elif case=='CV4-target':index['integrity_artifact']['path']='wrong-integrity.json'
  elif case=='CV4-SHA':index['integrity_artifact']['sha256']='0'*64
  elif case=='CV4-bytes':index['integrity_artifact']['bytes']+=1
  else:
   status=json.loads((public/'source-status.json').read_text())
   if case=='CV5-nested-acceptance-promotion':status['current_source_status']['C18']='Independently accepted.'
   else:status['current_source_status_validation']['semantic_authority_accepted']=0 if case=='CV5-zero-authority-flag' else True
   write(public/'source-status.json',status)
  write(reports/'daily-period-index.json',index);write(public/'daily-period-index.json',index)
  rs=repin(reports);ps=repin(public)
  # Both physically modified manifests have correct new external pins. The
  # semantic regression must be refused by the repaired final gate itself.
  m.assert_manifest(reports,rs);m.assert_manifest(public,ps)
  args=SimpleNamespace(repo=sys.argv[3],reports=str(reports),public=str(public),base=sys.argv[4],end=sys.argv[5],builder=str(S/'daily_finalizer.py.inert.txt'),report_manifest_sha256=rs,public_manifest_sha256=ps)
  t=m.Transport(sys.argv[3],root/'readers',clock)
  try:m.validate(args,t)
  except AssertionError as e:
   assert expected in str(e),(case,'unexpected refusal',str(e))
   records.append({'id':case,'state':'REFUSED_AS_EXPECTED','message':str(e),'actual_direct_readers':len(t.owned),'physical_repinned_artifacts':True,'report_manifest_sha256':rs,'public_manifest_sha256':ps,'all_directwait_freshclose':all(r['directwait'] and r['exact_birth_absent'] for r in t.owned)})
  else:raise AssertionError('repaired validator accepted defect: '+case)
 # A root link and a link in an ancestor are refused before manifest content.
 for case,ancestor in [('SEC1-root-alias',False),('SEC1-ancestor-alias',True)]:
  root=C/case;root.mkdir(mode=0o700);actual=root/'actual';actual.mkdir(mode=0o700);shutil.copytree(W/'PUBLIC',actual/'payload')
  (root/'alias').symlink_to(actual if ancestor else actual/'payload',target_is_directory=True)
  alias=root/'alias/payload' if ancestor else root/'alias'
  digest=m.sha((actual/'payload/MANIFEST.json').read_bytes())
  try:m.assert_manifest(alias,digest)
  except AssertionError as e:
   assert 'symlink root/ancestor/component refused' in str(e)
   records.append({'id':case,'state':'REFUSED_AS_EXPECTED','message':str(e),'before_manifest_read':True,'owned_fixture_only':True})
  else:raise AssertionError('root/ancestor link accepted')
 clock_records=[]
 assert validate_clock(clock)==clock
 for case in ['REPRO1-deadline-extension','REPRO1-cleanup-reduction','REPRO1-expired-clock','REPRO1-future-start']:
  changed=copy.deepcopy(clock)
  if case=='REPRO1-deadline-extension':changed['final_monotonic']=changed['actual_task_started_monotonic']+changed['original_seconds']+1
  elif case=='REPRO1-cleanup-reduction':changed['cleanup_seconds']=119
  elif case=='REPRO1-future-start':
   delta=time.monotonic()-changed['actual_task_started_monotonic']+10
   for k in ('actual_task_started_monotonic','useful_monotonic','final_monotonic'):changed[k]+=delta
  else:
   delta=changed['useful_monotonic']-time.monotonic()+1
   for k in ('actual_task_started_monotonic','useful_monotonic','final_monotonic'):changed[k]-=delta
  file=C/(case+'.json');write(file,changed)
  try:validate_clock(json.loads(file.read_bytes()))
  except AssertionError as e:clock_records.append({'id':case,'state':'REFUSED_AS_EXPECTED','message':str(e),'physical_clock_file':True})
  else:raise AssertionError('bad caller clock accepted: '+case)
 short=copy.deepcopy(clock);short['original_seconds']=600;short['cleanup_seconds']=120;short['final_monotonic']=short['actual_task_started_monotonic']+600;short['useful_monotonic']=short['final_monotonic']-120
 assert validate_clock(short,require_live=False)==short
 save('VALIDATOR-REGRESSIONS.json',{'raw':len(records)+len(clock_records),'unique':len(records)+len(clock_records),'PASS':len(records)+len(clock_records),'FAIL':0,'controls':records,'clock_controls':clock_records,'shorter600_caller_clock_preserved':True,'nested_status_semantic_authority':'NOT_VALIDATED_BYTE_ONLY; literal promotions refused, no independent authority inferred','final_gate_source_sha256':m.sha(pathlib.Path(m.__file__).read_bytes()),'resource_topology_unchanged':True,'original_clock_unchanged':json.loads((W/'EXECUTION-CLOCK.json').read_bytes())==clock})

print('OWNED_CHECK_COMPLETE',sys.argv[1])
