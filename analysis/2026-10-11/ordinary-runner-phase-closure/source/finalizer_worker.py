#!/usr/bin/env python3
import datetime, hashlib, json, os, pathlib, resource, sys, threading, time
OUT=pathlib.Path(sys.argv[1]).absolute();PKG=OUT.parent
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
cpus=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,cpus)
source=pathlib.Path('/proc/self/stat').read_text();ticks=int(source[source.rfind(')')+2:].split()[19])
(OUT/'READY.json').write_text(json.dumps({'pid':os.getpid(),'start_ticks':ticks,'affinity':cpus,'address_space_bytes':384*1024**2}))
while not (OUT/'BARRIER.json').exists():time.sleep(0.01)
barrier=json.loads((OUT/'BARRIER.json').read_text());assert barrier['pid']==os.getpid() and barrier['start_ticks']==ticks
assert time.monotonic()<barrier['hard_monotonic']
def save(name,value):
    (PKG/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
report=json.loads((PKG/'author-run-5/AUTHOR-CONTROLS.json').read_text())
assert report['count']==42 and not report['independent_acceptance']
closures=[]
for run in sorted(PKG.glob('author-run-*')):
    closure=json.loads((run/'CLOSURE.json').read_text())
    assert closure['worker_reaped'] and closure['worker_identity_absent'] and not closure['supervisor_final_children']
    closures.append({'run':run.name,'worker':closure['worker'],'exit_code':closure['exit_code'],
                     'reaped':True,'identity_absent':True,'barrier_released':closure['barrier_released']})
for path in PKG.glob('*.py'):compile(path.read_text(),str(path),'exec')
stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).isoformat()
epoch=time.time();start_epoch=1791709242
save('CLOCK.json',{'assignment':'FRW-ORDINARY-FINAL-GATE-INPUTS-SOURCE-ASTRA-20261011','generation':1,
    'accepted_msk':'2026-10-11T12:00:42+03:00','original_seconds':900,'cleanup_seconds':90,
    'hard_epoch':start_epoch+900,'ended_msk':stamp,'elapsed_seconds':epoch-start_epoch,
    'start_precision':'first actual clock tool observation at one-second precision; never reset'})
missing=[
    'Exact current owner-output Sol implementation/result/manifest and independent whole-path acceptance',
    'Exact stable final candidate/source acceptance and parent trust anchor; no real binding yet',
    'Independent package/relocation/expanded-effect review; AUTHOR controls are not acceptance',
    'Actual admitted dynamic test collection for39 unresolved parametrizations and all source execution receipts',
    'CLI-COMPOSITION-PINS.json for preserved expanded CLI body, independently pinned',
    'Complete main Python/direct/JS execution adapters with each actual effect admission; no fixture blanket',
    'G8 owner-terminal actual execution/stop/cleanup receipt; G7 NO_REPLAY retained',
    'Genuine kernel120/native worker grants and actual exclusive slot/custody/original budgets',
    'Normal3600 actual install/native qualification/authenticated cold start in original budget',
    'Exact authority seven-installed-journey plan and real final-candidate independent observations',
    'Four actual web contexts and cumulative AC record checker + independent runtime truth review']
save('WHOLE-GATE-INPUT-STATUS.json',{'status':'NOT_READY','full_gate_started':False,'normal3600':'UNSTARTED',
    'G8':'PREPARED_NOT_EXECUTED','G7':'NO_REPLAY','kernel120':'NOT_GRANTED','oldFriday':'OFF','Pandora':'OFF',
    'missing_mandatory_inputs':missing,'product_checks':'ALL_NOT_RUN','seven_installed_journeys':'NOT_RUN',
    'four_web_contexts':'NOT_RUN','no_exclusions_or_threshold_reductions':True})
save('RESULT.json',{'schema':'friday.whole-gate-input-source-result.v1',
    'assignment':'FRW-ORDINARY-FINAL-GATE-INPUTS-SOURCE-ASTRA-20261011','generation':1,
    'status':'SOURCE_IMPLEMENTED_AUTHOR_CONTROLS_PASS_INDEPENDENT_REVIEW_PENDING',
    'accepted_msk':'2026-10-11T12:00:42+03:00','ended_msk':stamp,'elapsed_seconds':epoch-start_epoch,
    'original_seconds':900,'cleanup_seconds':90,'accounting_not_reset':True,
    'author_controls':{'count':42,'path':'author-run-5/AUTHOR-CONTROLS.json','snapshot':'gate_inputs/source_runner/runner_worker/source_controls at run5'},
    'collection':{'files':128,'Python_test_definitions':1496,'literal_parametrize_entries':1905,'unresolved_parametrizations':39},
    'acceptance':{'USEFUL_records':47,'USEFUL_unique_checks':46,'DAILY_records':56,'total_parameterized_rows':59,'all_statuses':'NOT_RUN'},
    'implementation':['No-import actual AST/text catalog + source/native/model/OS/fixture effect signals',
       'Exact final source binding/preflight with independently accepted CLI delta over pinned132/17649 base',
       'Known checker output/root relocation, before-afterSHA + normalizedAST/registration/body proofs',
       'Expanded selectors preserve all original loops/bodies/thresholds, explicit unresolved effect/auxiliary boundaries',
       'Exact known-source runner, parent source grant/slot/original clock/ownedPID barrier/stop/reap enforcement',
       'Whole-source coverage preflight rejects omission/staleness/skips/dynamic unknowns',
       'Runtime/native/full-gate invocation always refuses without genuine existing native adapters/grants'],
    'independent_source_acceptance':False,'runtime_grant':False,'full_gate_started':False,
    'target_tests_executed':0,'target_checkers_executed':0,'target_native_imports':0,'models':0,'network':0,'services':0,'actual_OSFD_runtime':0,
    'author_fixture_acceptance_is_refused':True,'write_scope':'OUTPUT only','main_or_frozen_source_writes':0,
    'actual_inventory_hash_reads':{'project':132,'native':17649,'native_layers':30},
    'resources':{'max_CPUs':2,'declared_aggregate_AS_bytes':480*1024**2,'worker_AS_bytes':384*1024**2},
    'helper_closures':closures,'finalizer_identity':{'pid':os.getpid(),'start_ticks':ticks},
    'retained_harness_failures':['run1 inherited hardAS96 pre-readiness; corrected soft96/hard384, worker reaped',
       'run3 harness separate module Refusal type; corrected ValueError catch, worker reaped'],
    'limitations':missing,'full_environment_invariance':False,'atime_not_asserted':True,
    'seal':'MANIFEST generated by owned supervisor after finalizer reap; regular files0400 dirs0500; symlink negative fixtures explicit'})
assert not pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip()
assert len(threading.enumerate())==1
print(json.dumps({'status':'RESULT_WRITTEN_PENDING_SUPERVISOR_REAP_AND_SEAL','ended_msk':stamp}))
