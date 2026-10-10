import sys,os,resource,json,copy,ast,hashlib,importlib.util,subprocess,time,argparse
from pathlib import Path
if sys.flags.optimize: raise SystemExit('optimized control execution refused')
os.umask(0o077);sys.dont_write_bytecode=True;os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
parser=argparse.ArgumentParser(description='Finite data-only changed planning/setup controls; no runtime acceptance.')
parser.add_argument('--product-root',type=Path,required=True)
parser.add_argument('--archive-root',type=Path,required=True)
parser.add_argument('--corpus-root',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();P=args.product_root.resolve();A=args.archive_root.resolve();C=(args.corpus_root or P/'fixtures/daily-use').resolve();V=Path(__file__).with_name('validate_daily_data.py')
assert args.output.is_absolute() and not args.output.exists() and not args.output.is_symlink() and not args.output.resolve().is_relative_to(P) and not args.output.resolve().is_relative_to(A)
os.environ['GIT_OPTIONAL_LOCKS']='0'
BASE='66e57c147649979a7794c5c323c409a385cb79f7'
def base_bytes(name):
    return subprocess.run(['git','--no-optional-locks','-C',str(P),'show',BASE+':'+name],check=True,capture_output=True,timeout=10).stdout
start=time.monotonic();checks=[]
spec=importlib.util.spec_from_file_location('daily_candidate',V);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
d=m.load((C/'tasks.json').read_bytes());pins=m.load((C/'source-pins.json').read_bytes());roots={'product':P,'archive':A}
def valid(doc=d,sp=pins,corpus=C):return m.validate(doc,sp,corpus,roots)
new=valid();assert new['soak_parameters']=='SELECTED_PLANNING_NOT_ADMITTED' and new['long_initial_setup']=='SELECTED_INSTRUCTIONS_NOT_EXECUTED' and new['runtime_executed'] is False and new['attests_runtime_truth'] is False
checks.append({'name':'actual_new32pin12task_selected_candidate','status':'PASS'})
old=valid(m.load(base_bytes('fixtures/daily-use/tasks.json')),m.load(base_bytes('fixtures/daily-use/source-pins.json')),C);assert old['soak_parameters']=='PENDING_ADMISSION' and old['long_initial_setup']=='PENDING_EXPLICIT_SETUP';checks.append({'name':'actual_unchanged_prior_selected_long_pending_soak_corpus','status':'PASS'})
long_index=next(i for i,x in enumerate(d['tasks']) if x['category']=='long_coding')
def change(path,value,name=None):
 x=copy.deepcopy(d);target=x
 for key in path[:-1]:target=target[key]
 target[path[-1]]=value
 try:valid(x)
 except (ValueError,TypeError,KeyError) as e:checks.append({'name':name or '.'.join(map(str,path)), 'status':'PASS_EXPECTED_REFUSAL','reason':str(e)});return
 raise AssertionError('unexpected accept '+str(path))
for key,bads in [('duration_seconds',[0,-1,True,7200.0,86401]),('concurrent_chats',[0,True,9]),('queue_depth_bound',[0,True,9]),('resource_sample_interval_seconds',[0,True,61,11])]:
 for bad in bads:change(['soak',key],bad,key+'_'+repr(bad))
for key in ('resource_baseline','accepted_recovery_retry_policy','candidate_fingerprint','selected_local_profile'):change(['soak',key],{'invented':'PASS'},'invented_'+key)
change(['soak','state'],'READY_TO_RUN');change(['soak','planning','runtime_authority'],True);change(['soak','planning','observations'],'PASS');change(['soak','planning','current_baselines'],'MEASURED');change(['soak','planning','prepared_isolation'],'PROVEN');change(['soak','planning','version'],True)
for key in ('baseline_seconds','task_occurrences','baseline_request_total','sample_minimum_per_resource_window','gateway_restart_offset_seconds'):
 change(['soak','planning',key],True,key+'_bool')
change(['soak','planning','baseline_seconds'],7000);change(['soak','planning','baseline_resource_window_seconds'],1000);change(['soak','planning','sample_minimum_per_resource_window'],31);change(['soak','planning','baseline_requests','chat-settings'],0);change(['soak','planning','baseline_request_total'],11)
change(['soak','planning','preflight_requirements'],['fabricated']*7);change(['soak','planning','restart_precondition'],'restart even if stop unconfirmed')
for index,key,bad in [(0,'offset_seconds',899),(23,'offset_seconds',6900),(2,'sequence',1),(0,'chat_slot',3),(0,'task_id','invented'),(1,'admission','ALLOW'),(1,'late_or_unready','REPLAY'),(19,'timing','TARGET_OFFSET')]:change(['soak','arrival_schedule',index,key],bad,'event_'+str(index)+'_'+key)
sched=copy.deepcopy(d['soak']['arrival_schedule']);sched[1]['offset_seconds']=sched[0]['offset_seconds'];change(['soak','arrival_schedule'],sched,'duplicate_offsets')
change(['soak','planned_mix',0,'occurrences'],True);change(['soak','planned_mix',0,'occurrences'],3);change(['soak','planned_mix'],d['soak']['planned_mix'][:-1],'missing_category');change(['soak','mix_weights','chat-settings','denominator'],25);change(['soak','mix_weights','chat-settings','numerator'],True)
change(['soak','planning','gateway_restart_offset_seconds'],5700);change(['soak','heavy_worker_capacity','canonical_active_slots'],2)
for key in ('automatic_retry_on_unknown','automatic_retry_after_operator_stop','deadline_reset','job_reexecution_for_delivery'):change(['soak','planning','proposed_recovery_policy',key],True,key)
for key in ('worker_retry_max','delivery_retry_max','restarts_max'):change(['soak','planning','proposed_recovery_policy',key],2,key)
change(['soak','planning','proposed_recovery_policy','authority'],'THIS ENABLES RETRY')
for key in ('owned_worker_processes_after_cleanup','task_outcomes_missing_max'):change(['soak','planning','resource_thresholds',key],1,key)
change(['soak','planning','resource_thresholds','gateway_rss_growth_max_fraction'],True);change(['soak','planning','resource_thresholds','gateway_rss_growth_max_fraction'],float('nan'));change(['soak','planning','resource_thresholds','rss_rule'],'ignore original limit')
change(['soak','latency_thresholds','stop_seconds'],120);change(['soak','latency_thresholds','baseline_multiplier'],0);change(['soak','latency_thresholds','chat_reply_seconds'],float('inf'))
change(['soak','required_interruptions'],d['soak']['required_interruptions'][:1]);change(['soak','observations','resource_samples'],[]);change(['soak','observations','acceptance'],'PASS')
change(['tasks',long_index,'initial_setup'],None,'selected_soak_missing_setup')
for key,bad in [('state','EXECUTED'),('runtime_authority',True),('prefix',d['tasks'][long_index]['initial_setup']['prefix'].replace('Add owner-write only','Make everything writable')),('prefix_sha256','0'*64),('composed_brief_bytes',8024),('composed_brief_bytes',True),('composition','read attached file automatically')]:change(['tasks',long_index,'initial_setup',key],bad,'setup_'+key+'_'+type(bad).__name__)
change(['tasks',0,'initial_setup'],d['tasks'][long_index]['initial_setup'],'setup_on_wrong_task')
# Review regressions: omissions, unknown authority and typed original evidence.
for i in range(len(d['soak']['planned_mix'])):
 change(['soak','planned_mix',i,'minimum_coverage'],'Missing or NOT_RUN is accepted','mix_coverage_waiver_'+str(i))
 change(['soak','planned_mix',i,'runtime_authority'],True,'mix_unknown_authority_'+str(i))
for i in range(2):
 change(['soak','required_interruptions',i,'minimum_count'],True,'required_interruption_bool_'+str(i))
 change(['soak','required_interruptions',i,'expected'],'No actual evidence needed','required_interruption_evidence_waiver_'+str(i))
 change(['soak','required_interruptions',i,'runtime_authority'],True,'required_interruption_unknown_authority_'+str(i))
change(['soak','required_interruptions',1,'task_id'],'chat-settings','failure_wrong_owned_task')
change(['soak','required_interruptions'],[d['soak']['required_interruptions'][0]]*2,'duplicate_required_interruption')
for key in ('definition_sources','later_evidence'):
 change(['soak',key],[],key+'_empty')
 for i in range(len(d['soak'][key])):
  values=copy.deepcopy(d['soak'][key]);values.pop(i);change(['soak',key],values,key+'_missing_'+str(i))
for ref in d['soak']['definition_sources']:
 sp=copy.deepcopy(pins);sp['sources']=[row for row in sp['sources'] if row['id']!=ref]
 try:valid(d,sp)
 except (ValueError,TypeError,KeyError) as e:checks.append({'name':'unbound_definition_'+ref,'status':'PASS_EXPECTED_REFUSAL','reason':str(e)})
 else:raise AssertionError('unpinned policy definition accepted '+ref)
x=copy.deepcopy(d);x['soak']['required_interruptions'].reverse();assert valid(x)['soak_parameters']=='SELECTED_PLANNING_NOT_ADMITTED';checks.append({'name':'equivalent_interruption_order_accepted','status':'PASS'})
# Same exact source rows: only source-association commit metadata changed.
prior_pins=m.load(base_bytes('fixtures/daily-use/source-pins.json'));assert pins['sources']==prior_pins['sources'];checks.append({'name':'all32_source_row_pins_unchanged','status':'PASS'})
oldtasks=m.load(base_bytes('fixtures/daily-use/tasks.json'));assert all(x==y for x,y in zip(d['tasks'],oldtasks['tasks']) if x['category']!='long_coding');x=copy.deepcopy(d['tasks'][long_index]);x.pop('initial_setup');assert x==oldtasks['tasks'][long_index];checks.append({'name':'all_original_task_contracts_unchanged_except_explicit_setup','status':'PASS'})
for key in ('original_limits','fixture_checker_limits','acceptance','fixture_boundary'):assert d[key]==oldtasks[key]
checks.append({'name':'original_runtime_limits_owner_checks_full_acceptance_and_privacy_unchanged','status':'PASS'})
base=ast.parse(base_bytes('validation/validate_daily_data.py'));cand=ast.parse((V).read_text());bf={x.name:ast.dump(x,include_attributes=False) for x in base.body if isinstance(x,ast.FunctionDef)};cf={x.name:ast.dump(x,include_attributes=False) for x in cand.body if isinstance(x,ast.FunctionDef)}
assert all(cf[k]==v for k,v in bf.items() if k!='validate');checks.append({'name':'all_existing_reader_JSON_path_CLI_helpers_AST_unchanged','status':'PASS'})
cmd=[sys.executable,'-I','-S','-B',str(V),'--product-root',str(P),'--archive-root',str(A),'--corpus-root',str(C)];r=subprocess.run(cmd,capture_output=True,text=True,timeout=10);assert r.returncode==0,r.stderr;assert json.loads(r.stdout)==new;checks.append({'name':'actual_CLI_selected_data_source_only','status':'PASS'})
out={'state':'PASS_CHANGED_CORPUS_PLANNING_AND_SETUP_SOURCE_ONLY','checks':checks,'count':len(checks),'new':new,'old':old,'elapsed_seconds':time.monotonic()-start,'validator_sha256':hashlib.sha256((V).read_bytes()).hexdigest(),'prior91_and_long128_reused':'unchanged source semantics, not rerun or counted here','root_setup9':'separate actual UID/data-copy/composed-brief author observations','runtime_executed':False,'handles':0}
with args.output.open('x') as stream:stream.write(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ('state','count','elapsed_seconds','handles')}))
