"""One exact retained A0 observation; pure read/proposal, no native effects.

The old failure remains immutable. A separate Root closure must prove all real
resource effects before its STOP_UNCONFIRMED state can progress to settlement.
"""
from pathlib import Path
import base64, copy, hashlib, json, os, stat
HERE=Path(__file__).resolve().parent
H=Path('<INSTALL_HOME>')
U=H/'profiles/telegram-bot-9000000001'
F=U/'workers/a0/postboot-after-closed-s443-s447'
OP=Path('<PRIVATE_CACHE>/PRIVATE_REF_6a736a49ad15c89d')
CONTAINER='PRIVATE_REF_6d96d85a108acd5e'
INVOCATION='PRIVATE_REF_fb2a854c1e2bd907'
NATIVE=Path('<PRIVATE_RUNTIME>/a0-runtime-sol/PRIVATE_REF_069eeb97c22d0a43')
META=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
EVIDENCE_REF = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_2311aa4637a52b04/EVIDENCE.json', 'sha256': 'PRIVATE_REF_6a35b8c29ab4394f'}
FIXED_OPERATION_REFS = {'clock': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_6a736a49ad15c89d/ORIGINAL-CLOCK.json', 'sha256': 'PRIVATE_REF_71d41712e666fc5c'}, 'intent': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_6a736a49ad15c89d/runner-intent.json', 'sha256': 'PRIVATE_REF_4bf1530630c5cc00'}, 'request': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_6a736a49ad15c89d/REQUEST.json', 'sha256': 'PRIVATE_REF_4abdae45b09e01fd'}, 'returned': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_6a736a49ad15c89d/NATIVE-RETURN.json', 'sha256': 'PRIVATE_REF_d927ce009a65f904'}, 'source_acceptance': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8794a61dfd72f61c/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_cd9f0adf624922e3'}}

def need(ok,code):
    if not ok:raise ValueError('same_a0_'+code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(path):
    p=Path(path);need(p.is_absolute() and p.resolve()==p,'canonical_reference')
    parents={}
    for q in p.parents:
        s=q.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,os.getuid()) and not s.st_mode&0o022,'protected_parent');parents[q]=tuple(getattr(s,k) for k in META[:5])
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_gid==os.getgid() and a.st_nlink==1 and stat.S_IMODE(a.st_mode) in (0o400,0o600),'private_reference')
        with os.fdopen(os.dup(fd),'rb') as f:data=f.read(32*1024**2+1)
        b,c=os.fstat(fd),p.lstat();need(len(data)<=32*1024**2 and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in META),'reference_changed')
    finally:os.close(fd)
    need(all(tuple(getattr(q.lstat(),k) for k in META[:5])==v for q,v in parents.items()),'parent_changed');return data

def pin(path):return {'path':str(path),'sha256':sha(raw(path))}
def reference(ref):
    need(type(ref)is dict and set(ref) in ({'path','sha256'},{'path','sha256','identity'}),'exact_reference')
    need(type(ref['path']) is str and type(ref['sha256']) is str and len(ref['sha256'])==64
        and all(x in '0123456789abcdef' for x in ref['sha256']),'reference_shape')
    if 'identity' in ref:
        need(type(ref['identity']) is list and len(ref['identity'])==len(META)
            and all(type(x) is int for x in ref['identity']),'retained_identity_shape')
    return {'path':ref['path'],'sha256':ref['sha256']}

def read(ref):
    reference(ref);data=raw(ref['path']);need(sha(data)==ref['sha256'],'hash_changed')
    if 'identity' in ref:
        st=Path(ref['path']).lstat();need([getattr(st,k) for k in META]==ref['identity'],'retained_identity_changed')
    return data

def pairs(rows):
    out={}
    for k,v in rows:need(k not in out,'duplicate_key');out[k]=v
    return out

def document(ref):return json.loads(read(ref),object_pairs_hook=pairs,parse_constant=lambda _:need(False,'nonfinite'))
def evidence():return document(EVIDENCE_REF)
def original_documents():
    refs=evidence();out={}
    for name,row in refs.items():
        old=read(row['preserved']);need(sha(old)==row['original']['sha256'],'beforeimage_hash')
        if name!='bootstrap/state.json':
            need(read(row['original'])==old,'immutable_attempt_changed')
            st=Path(row['original']['path']).lstat();need(all(getattr(st,k)==v for k,v in row['original_identity'].items()),'immutable_attempt_identity_changed')
        out[name]=json.loads(old,object_pairs_hook=pairs)
    return refs,out

def restored_value(*,custody=None):
    refs,docs=original_documents();checkpoint=docs['observation.unsettled.json'];value=copy.deepcopy(checkpoint['value'])
    need(set(checkpoint)=={'schema','state','readiness','retry_authorized','original','bootstrap_original','value'}
        and checkpoint['schema']=='friday.a0-postboot-unsettled-observation.v1' and checkpoint['state']=='UNSETTLED'
        and checkpoint['readiness']=='NOT_READY' and checkpoint['retry_authorized'] is False
        and checkpoint['original']==refs['original.json']['original']
        and checkpoint['bootstrap_original']==refs['bootstrap/original.json']['original']
        and value['bootstrap_original'] is None and value['custody'] is None
        and value['observation']['container_id']==CONTAINER and value['observation']['invocation_id']==INVOCATION,
        'exact_completed_checkpoint')
    expected=copy.deepcopy(value)
    for k in ('plan','bootstrap_original','custody','observation','observed'):expected[k]=None
    need(docs['original.json']==expected,'original_stage_changed')
    value['bootstrap_original']=checkpoint['bootstrap_original'];value['custody']=custody
    fixed=FIXED_OPERATION_REFS;request=document(fixed['request']);clock=document(fixed['clock']);intent=document(fixed['intent']);returned=document(fixed['returned'])
    claim=value['original_attempt'];original=docs['bootstrap/original.json']
    need(request['original_clock']==fixed['clock'] and request['source_acceptance']==fixed['source_acceptance']
        and request['installed_join']==value['sources']['plugins/friday_rework/user_worker_join.py']
        and intent=={'schema':'friday.a0-after-closed-s443-s447-root-intent.v1','clock':fixed['clock'],'request':fixed['request'],'retry_authorized':False}
        and clock['budget_seconds']==600 and clock['reserve_seconds']==30
        and claim=={'boot_id':clock['boot_id'],'budget_seconds':600,'started_mono':clock['started_monotonic'],'deadline_mono':clock['deadline_monotonic']}
        and claim['deadline_mono']==claim['started_mono']+600
        and claim['started_mono']<=value['observed']['monotonic']<claim['deadline_mono']
        and returned['result'] is None and returned['retry_authorized'] is False and returned['clock']==fixed['clock']
        and returned['failure']['diagnostic']['error_kind']=='stop_unconfirmed'
        and docs['failure.json']['state']=='STOP_UNCONFIRMED' and docs['failure.json']['retry_authorized'] is False
        and docs['failure.json']['original_attempt']==claim
        and original['producer']==value['sources']['plugins/friday_rework/user_worker_join.py']
        and original['deadline_monotonic']==claim['deadline_mono'],'exact_original600_custody')
    return value

def same_value(value,*,settled=False):
    custody={'original':evidence()['bootstrap/original.json']['original'],'settlement':pin(F/'bootstrap/state.json')} if settled else None
    return value==restored_value(custody=custody)

def quiet(checks,required):
    need(type(checks)is list and checks,'cessation_checks_missing')
    for row in checks:
        need(row['confirmed'] is True and row['survivors']==[]
            and row['after']['populated'] is False and row['after']['processes']==[],'cessation_unconfirmed')
    need(all(any(row['before']==sample for row in checks) for sample in required),'sample_not_covered')

def closure_proposal(closure_ref):
    refs,docs=original_documents();closed=document(closure_ref);before=docs['bootstrap/state.json'];value=restored_value()
    need(closed['schema']=='frw.Root.A0.same-observation-resource-closure.v1'
        and closed['state']=='RESOURCES_SETTLED_SAME_OBSERVATION_NO_REPLAY'
        and closed['checkpoint']==refs['observation.unsettled.json']['original']
        and closed['failure']==refs['failure.json']['original']
        and closed['original']==refs['original.json']['original']
        and closed['bootstrap_original']==refs['bootstrap/original.json']['original']
        and closed['state_before']==refs['bootstrap/state.json']['preserved']
        and closed['original_request']==FIXED_OPERATION_REFS['request']
        and closed['original_clock']==FIXED_OPERATION_REFS['clock']
        and closed['container_id']==CONTAINER and closed['invocation_id']==INVOCATION
        and all(closed[k] is False for k in ('new_observation','worker_replayed','old_clock_reset','failure_rewritten')),
        'exact_Root_resource_closure')
    need(before['phase']=='STOP_UNCONFIRMED' and before['settlement'] is None
        and before['pending_sample'] is False and before['sampling_uncertainty'] is False
        and before['keys']=='PREPARED' and before['sample_attempts']
        and all(x['phase']=='OBSERVED' for x in before['sample_attempts']),'preserved_failed_state')
    stop=document(closed['stop']);retirement=document(closed['retirement']);keys=document(closed['keys_removal']);post=document(closed['postcheck'])
    need(closed['stop']['path']==str(NATIVE/'stop.json') and stop['status']=='STOP_CONFIRMED'
        and stop['container_id']==CONTAINER and stop['native_container_stopped'] is True
        and stop['current_sampling']=='OBSERVED_OR_ALREADY_EXITED','actual_native_stop')
    required=[]
    for sample in before['created']['observations']+before['samples']+[value['observation']['native_resources']['cgroup']]:
        if sample not in required:required.append(sample)
    quiet(stop['descendant_checks'],required)
    need(retirement['status']=='INITIAL_PROBE_RETIRED' and retirement['container_id']==CONTAINER
        and closed['retirement']['path']==str(NATIVE/'retirement.json')
        and retirement['host_state_retained'] is True and retirement['image_retained'] is True and retirement['volumes_removed'] is False,'actual_native_retirement')
    route=before['route']['settlement']
    need(route['status']=='STOP_CONFIRMED' and all(route[k] is True for k in ('network_removed','request_removed','guard_removed')),'route_unsettled')
    quiet(route['daemon_checks'],[])
    need(keys['schema']=='friday.root.after-profile-exact-key-cleanup.v1'
        and keys['status']=='INTRODUCED_KEYS_REMOVED' and keys['key_directory']==str(NATIVE/'usr')
        and keys['container_id']==CONTAINER and keys['invocation_id']==INVOCATION
        and reference(keys['native_retirement'])==reference(closed['retirement']) and reference(keys['native_stop'])==reference(closed['stop'])
        and keys['original_state']==refs['bootstrap/state.json']['original']
        and keys['original_failure']==refs['failure.json']['original']
        and keys['worker_or_model_or_auth_effects'] is False and keys['old_clock_reset'] is False
        and all(keys[k] is True for k in ('two_introduced_scoped_keys_removed','native_web_secret_cleared',
            'other_files_and_settings_preserved','original_failed_state_unchanged','source_credentials_unchanged','existing_key_consumer_used')),
        'introduced_key_removal_unconfirmed')
    quiet(keys['current_cessation'],required+[x['before'] for x in route['daemon_checks']])
    read(keys['native_retirement']);read(keys['native_stop'])
    maintenance=document(keys['retirement']);removed=maintenance['container'];after=maintenance['poststop']
    need(maintenance['schema']=='friday.a0.exact-retained-container-cleanup.v1'
        and maintenance['status']=='EXACT_CONTAINER_REMOVED_AND_MAINTENANCE_STOPPED'
        and reference(maintenance['native_retirement'])==reference(closed['retirement']) and reference(maintenance['native_stop'])==reference(closed['stop'])
        and maintenance['original_state']==refs['bootstrap/state.json']['original']
        and maintenance['original_failure']==refs['failure.json']['original']
        and removed['id']==CONTAINER and removed['remove_attempted'] is True
        and removed['no_force'] is True and removed['no_volumes'] is True
        and removed['remove']['returncode']==0
        and base64.b64decode(removed['remove']['stdout_b64'],validate=True).strip()==CONTAINER.encode()
        and maintenance['cleanup_errors']==[] and maintenance['canonical_maintenance_removed'] is True
        and all(after[k] is True for k in ('container_absent','mount_sources_preserved','worker_unchanged'))
        and after['unit']['ActiveState'] in ('inactive','failed') and after['unit']['MainPID']=='0'
        and after['unit']['ControlGroup']==''
        and maintenance['preserved_inventory']['before']==maintenance['preserved_inventory']['after'],
        'actual_native_retirement_maintenance_required')
    quiet(after['cessation'],[]);read(maintenance['native_retirement']);read(maintenance['native_stop'])
    need(post['status']=='EXACT_RESOURCES_CLOSED' and post['container_id']==CONTAINER and post['invocation_id']==INVOCATION
        and reference(post['stop'])==reference(closed['stop']) and reference(post['retirement'])==reference(closed['retirement']) and reference(post['keys_removal'])==reference(closed['keys_removal'])
        and all(post[k] is True for k in ('container_absent','worker_quiet','container_cgroup_empty','daemon_cgroup_empty','route_files_absent','introduced_keys_absent','healthy_gateway_dashboard_Kimi_preserved','source_credentials_unchanged')),
        'actual_resource_postcheck_required')
    result=copy.deepcopy(before);result.update(phase='STOPPED',settlement={'status':'STOP_CONFIRMED','container':stop,'retirement':retirement,'route':route,'keys':'REMOVED'})
    return result

def checked_completion(c,value):
    need(c['runtime_home']==str(U) and same_value(value,settled=True),'exact_settled_value')
    completed=document(pin(F/'same-observation-completion.json'))
    need(set(completed)=={'schema','state','checkpoint','failure','state_before','closure','settlement','original_clock','effects'}
        and completed['schema']=='friday.a0-same-observation-completion.v1'
        and completed['state']=='SAME_OBSERVATION_SETTLED_NO_REPLAY'
        and completed['checkpoint']==evidence()['observation.unsettled.json']['original']
        and completed['failure']==evidence()['failure.json']['original']
        and completed['state_before']==evidence()['bootstrap/state.json']['preserved']
        and completed['original_clock']==FIXED_OPERATION_REFS['clock']
        and completed['effects']=='SETTLEMENT_METADATA_ONLY'
        and completed['settlement']==pin(F/'bootstrap/state.json')
        and document(completed['settlement'])==closure_proposal(completed['closure']),'completion_proof_changed')
    return True
