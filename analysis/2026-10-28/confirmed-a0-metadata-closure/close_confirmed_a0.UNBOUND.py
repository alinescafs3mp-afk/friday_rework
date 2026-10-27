"""ONE Root-only metadata closure. No launch/stop/API/network or retry.

Importing this module imports standard library only. Root supplies its existing
trusted Dashboard graph, scoped Associations, and held live idle/proof boundary.
This source package itself carries no actual proof or authorization to execute.
"""
import copy
from dataclasses import asdict
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

class ClosureRefused(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise ClosureRefused(code)


def encoded(v):
    return (json.dumps(v, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode()


def digest(v):
    # EXACT host_record.digest convention, distinct from compact plan hashing.
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def strict_json(b):
    def pairs(items):
        d=dict(items); need(len(d)==len(items), 'duplicate_json'); return d
    return json.loads(b, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ClosureRefused('nonfinite_json')))


def identity(s):
    return (s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,
            s.st_size,s.st_mtime_ns,s.st_ctime_ns)  # atime may advance on read


def parents(p):
    home=Path.home()
    need(p.is_absolute() and '..' not in p.parts and p.resolve()==p and p.is_relative_to(home), 'canonical_owned_path')
    for q in (p.parent,*p.parent.parents):
        s=q.lstat(); need(stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022
                         and s.st_uid==(os.getuid() if q.is_relative_to(home) else 0),'unsafe_parent')


def read_ref(ref, limit=16*1024*1024):
    need(isinstance(ref,dict) and set(ref)=={'path','bytes','sha256','identity'},'exact_ref')
    p=Path(ref['path']); parents(p)
    need(type(ref['bytes']) is int and 0<ref['bytes']<=limit
         and isinstance(ref['sha256'],str) and re.fullmatch('[0-9a-f]{64}',ref['sha256']), 'bounded_ref')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        s=os.fstat(fd); need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid()
                            and s.st_nlink==1 and list(identity(s))==ref['identity'],'custody_changed')
        parts=[]; n=0
        while True:
            b=os.read(fd,min(65536,limit+1-n))
            if not b: break
            n+=len(b);need(n<=limit,'read_bound');parts.append(b)
        data=b''.join(parts)
        need(identity(s)==identity(os.fstat(fd))==identity(p.lstat()),'read_race')
        need(len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256'],'ref_sha_changed')
        return data
    finally: os.close(fd)


def create(p, value):
    p=Path(p);parents(p)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        b=encoded(value); done=0
        while done<len(b):
            n=os.write(fd,b[done:]); need(n>0,'short_write');done+=n
        os.fsync(fd)
    finally: os.close(fd)
    d=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(d)
    finally:os.close(d)


def absent_intent(row):
    p=Path(row['workspace_reference']); parents(p/'task-post-intent.json')
    s=p.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o022,'unsafe_workspace')
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        try: os.stat('task-post-intent.json',dir_fd=fd,follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise ClosureRefused('task_post_intent_present')
        need(identity(s)==identity(os.fstat(fd))==identity(p.lstat()),'workspace_changed')
    finally: os.close(fd)


def check_row(row, assoc, host):
    assoc._validate_store({'schema_version':1,'jobs':{row['existing_task_id']:row}})
    a=row['host']['a0'];g=a['grant'];route=a['route']
    need(row['worker_kind']=='a0' and row['native'] is None
         and row['submission_observation']=='NOT_SUBMITTED' and row['stop_intent']=='cancel'
         and row['elapsed_seconds']==0 and row['execution_observation'] is None
         and row['goal_verification']=='NOT_RUN' and row['delivery']=='NOT_RUN'
         and row['preparation_reserved'] is True and 'result' not in row and 'notification' not in row,
         'exact_unsubmitted_stopped_row')
    need(all(row['host'][k] is None for k in ('observation','terminal','quiescence')),'outcome_already_present')
    need(isinstance(g,dict) and a['key_cleanup']=='REMOVED' and a['observations']['pending'] is False
         and a['observations']['samples'] and isinstance(route,dict) and route['pending'] is None
         and route['settlement']['status']=='STOP_CONFIRMED','retained_custody_not_closed')
    host.validate_host_record(row)  # full canonical route/grant/owner/clock validation
    need(g['daemon_invocation_id']==route['daemon']['receipt']['context']['invocation_id'],'daemon_grant_join')
    checks=route['settlement']['daemon_checks']
    need(checks and all(v['confirmed'] is True and v['survivors']==[] and v['after']['populated'] is False
                       and v['after']['processes']==[] for v in checks),'daemon_cessation_missing')


def outcome(row, proof, host):
    g=row['host']['a0']['grant']; at=proof['observed_unix'];ev=proof['evidence_reference']
    observation={'invocation_id':'','worker_reference':'','evidence_reference':ev,'elapsed_seconds':0,'state':'stopped'}
    quiet={'kind':'a0','at_unix':at,'observation':{'unit':proof['worker_unit'],
           'container_id':g['container_id'],'grant_sha256':host.digest(g),
           'native_cessation':True,'key_cleanup':'REMOVED'}}
    return observation,{'state':'stopped','evidence_reference':ev,'at_unix':at},quiet


DAEMON_FRAGMENT_LINK = 'UNBOUND_SYSTEMD_USER_DIR/UNBOUND_DAEMON.service'
DAEMON_FRAGMENT_TARGET = 'UNBOUND_DAEMON_ROOT/supervisor/UNBOUND_DAEMON.service'
DAEMON_FRAGMENT_SHA256 = 'UNBOUND_DAEMON_FRAGMENT_SHA256'


def check_stopped_daemon(extra, daemon, row):
    """Only the owned loaded persistent daemon may lose its old InvocationID.

    Root collects these current read-only facts under the SAME held boundary.
    The helper also checks lexical symlink and canonical fragment bytes/custody
    on every proof check; read_ref's general no-symlink rule is unchanged.
    """
    need(isinstance(extra,dict) and set(extra)=={'load_state','control_pid','processes',
         'fragment_path','symlink_target','symlink_identity','fragment_ref','descendant_checks'},
         'stopped_daemon_schema')
    need(daemon.invocation_id=='' and daemon.active_state=='inactive' and daemon.sub_state=='dead'
         and extra['load_state']=='loaded' and type(extra['control_pid']) is int
         and extra['control_pid']==0 and extra['processes']==[], 'stopped_daemon_not_loaded_dead')
    need(extra['fragment_path']==DAEMON_FRAGMENT_LINK
         and extra['symlink_target']==DAEMON_FRAGMENT_TARGET
         and extra['fragment_ref']['path']==DAEMON_FRAGMENT_TARGET
         and extra['fragment_ref']['sha256']==DAEMON_FRAGMENT_SHA256, 'stopped_daemon_fragment_join')
    link=Path(DAEMON_FRAGMENT_LINK)
    # Validate its canonical parents without following the allowed final symlink.
    parents(link.parent/'_fragment_parent_check')
    before=link.lstat()
    need(stat.S_ISLNK(before.st_mode) and before.st_uid==os.getuid()
         and before.st_gid==os.getgid() and before.st_nlink==1
         and list(identity(before))==extra['symlink_identity']
         and os.readlink(link)==DAEMON_FRAGMENT_TARGET, 'stopped_daemon_link_custody')
    read_ref(extra['fragment_ref'],limit=128*1024)
    target=Path(DAEMON_FRAGMENT_TARGET).lstat()
    need(not target.st_mode&0o022 and list(identity(target))==extra['fragment_ref']['identity'],
         'stopped_daemon_fragment_custody')
    need(identity(before)==identity(link.lstat()) and os.readlink(link)==DAEMON_FRAGMENT_TARGET,
         'stopped_daemon_link_changed')
    route=row['host']['a0']['route']
    need(route['pending'] is None and route['settlement']['status']=='STOP_CONFIRMED'
         and row['host']['a0']['key_cleanup']=='REMOVED', 'stopped_daemon_retained_route')
    retained=route['settlement']['daemon_checks'];fresh=extra['descendant_checks']
    need(isinstance(fresh,list) and len(fresh)==len(retained) and retained,
         'stopped_daemon_descendants_missing')
    for old,current in zip(retained,fresh):
        sample=old['before']
        need(set(current)=={'confirmed','before','survivors','after'} and current['before']==sample
             and current['confirmed'] is True and current['survivors']==[]
             and current['after']=={'group':sample['group'],'populated':False,'processes':[]},
             'stopped_daemon_descendants_not_ceased')


def check_proof(proof,row,binding,UnitObservation):
    need(set(proof)=={'schema','observed_unix','observed_monotonic','boot_id','row_sha256',
         'store_sha256','worker_unit','worker_job','daemon_unit','daemon_job','native_receipt',
         'native_receipt_ref','container_checks','native_cessation','keys_removed','route_removed','gateway_idle','evidence_reference',
         'historical_effects','daemon_stopped_binding','retained_container_checks'},'proof_schema')
    now=time.monotonic();g=row['host']['a0']['grant'];r=row['host']['a0']['route'];p=row['host']['a0']['launch']['plan']
    need(proof['schema']=='frw.Root.a0-confirmed-cessation-proof.v3'
         and proof['boot_id']==binding['boot_id']==g['boot_id']
         and proof['row_sha256']==digest(row) and proof['store_sha256']==binding['store_sha256']
         and type(proof['observed_monotonic']) in (int,float) and math.isfinite(proof['observed_monotonic'])
         and binding['started_monotonic']<=proof['observed_monotonic']<=now
         and now-proof['observed_monotonic']<=5
         and type(proof['observed_unix']) in (int,float) and math.isfinite(proof['observed_unix'])
         and abs(time.time()-proof['observed_unix'])<=5
         and proof['native_cessation'] is True and proof['keys_removed'] is True
         and proof['route_removed'] is True and proof['gateway_idle'] is True
         and proof['historical_effects']=='UNKNOWN_NO_REPLAY','fresh_proof_required')
    need(isinstance(proof['evidence_reference'],str) and 0<len(proof['evidence_reference'].encode())<=2048,
         'proof_evidence_reference')
    u=UnitObservation(**proof['worker_unit']);d=UnitObservation(**proof['daemon_unit'])
    for x in (u,d):
        need(type(x.main_pid) is int and x.main_pid==0 and x.missing is False
             and x.populated is False and x.control_group=='' and x.quiescent
             and x.active_state in {'inactive','failed'} and proof['worker_job']==proof['daemon_job']=='',
             'unit_not_exact_quiet')
    need(u.unit==row['supervisor']['unit'] and u.invocation_id==g['invocation_id'],'worker_unit_join')
    need(d.unit=='UNBOUND_DAEMON.service','daemon_unit_join')
    if d.invocation_id=='':
        check_stopped_daemon(proof['daemon_stopped_binding'],d,row)
    else:
        need(d.invocation_id==g['daemon_invocation_id'] and proof['daemon_stopped_binding'] is None,
             'daemon_invocation_join')
    nr=proof['native_receipt']
    ref=proof['native_receipt_ref']
    need(ref['path']==str(Path(p['runtime_root'])/p['identity']/'native.json'),'native_receipt_path')
    need(strict_json(read_ref(ref))==nr,'native_receipt_bytes')
    need(isinstance(nr,dict) and nr.get('container_id')==g['container_id']
         and nr.get('plan_sha256')==row['host']['a0']['launch']['created']['plan_sha256']
         and nr.get('invocation_id')==g['invocation_id'] and nr.get('native_start_attempted') is True, 'native_receipt_join')
    samples=nr.get('observations');checks=proof['container_checks']
    need(isinstance(samples,list) and samples and isinstance(checks,list) and len(checks)==len(samples),'container_samples_missing')
    projected=[]
    for sample,c in zip(samples,checks):
        need(sample['group']==g['container_cgroup'] and sample['populated'] is True and sample['processes'], 'container_sample_join')
        need(set(c)=={'confirmed','before','survivors','after'} and c['before']==sample
             and c['confirmed'] is True and c['survivors']==[]
             and c['after']=={'group':sample['group'],'populated':False,'processes':[]}, 'container_cessation_missing')
        projected.append({'group':sample['group'],'populated':True,'processes':[
            {'pid':x['pid'],'start_ticks':str(x['start_ticks'])} for x in sample['processes']]})
    retained=row['host']['a0']['observations']['samples'];fresh=proof['retained_container_checks']
    need(isinstance(fresh,list) and len(fresh)==len(retained) and retained,'retained_descendants_missing')
    for sample,current in zip(retained,fresh):
        need(sample['group']==g['container_cgroup'] and sample['populated'] is True and sample['processes'],
             'retained_container_join')
        need(set(current)=={'confirmed','before','survivors','after'} and current['before']==sample
             and current['confirmed'] is True and current['survivors']==[]
             and current['after']=={'group':sample['group'],'populated':False,'processes':[]},
             'retained_container_not_ceased')
    # Root's held proof boundary checks actual receipt/path/hash/identity, all
    # recorded container descendants, keys, removed route files/network/guard.
    need(proof['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'boot_changed')


def _apply(binding, *, store, boundary, assoc, host, UnitObservation, commit):
    """Internal engine; fixtures may inject isolated canonical validators.

boundary(row, deadline) is a Root-owned contextmanager. It acquires Root's
EXISTING admission/idle boundary and refreshes actual READ-ONLY proofs BEFORE
association locking. Its yielded object has .proof and .check(): .check is a
quick local held-boundary/identity/freshness check, no commands or network.
No arbitrary stored boolean is accepted as a substitute for this held boundary.
    """
    need(set(binding)=={'schema','task_id','owner','profile_home','row_ref','store_sha256',
                       'native_state_ref','sources','boot_id','started_monotonic','deadline_monotonic','output'},'binding_schema')
    start=binding['started_monotonic'];end=binding['deadline_monotonic'];now=time.monotonic()
    need(binding['schema']=='frw.Root.a0-confirmed-cessation-close.v1'
         and type(start) in (int,float) and type(end) in (int,float)
         and math.isfinite(start) and math.isfinite(end) and start<=now<end<=start+60,'finite_original_closure_clock')
    out=Path(binding['output']);parents(out/'INTENT.json')
    s=out.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid()
                      and stat.S_IMODE(s.st_mode)==0o700,'private_output_required')
    for name in ('BEFORE.json','INTENT.json','AFTER.json','RECEIPT.json','UNKNOWN.json'):
        need(not os.path.lexists(out/name),'existing_operation_no_retry')
    need(Path(binding['native_state_ref']['path'])==Path(store.state.path),'actual_native_state_path')
    need(store.state.quota_bytes==64*1024*1024, 'canonical_friday_state_quota');before_raw=read_ref(binding['native_state_ref'],limit=store.state.quota_bytes);native_before=strict_json(before_raw)
    row=strict_json(read_ref(binding['row_ref']));check_row(row,assoc,host)
    need(row['existing_task_id']==binding['task_id'] and row['owner']==binding['owner'],'original_row_owner')
    data=native_before[assoc.KEY]
    need(digest(data)==binding['store_sha256'] and data['jobs'].get(binding['task_id'])==row,'original_whole_store_cas')
    assoc._validate_store(data)
    need(Path(store.state.data_dir).parent==Path(binding['profile_home'])/'plugin-data'
         and store.state._plugin_id=='friday_rework' and store._storage_readonly is False,'scoped_store_required')
    attempted=False
    try:
        with boundary(copy.deepcopy(row),end) as held:
            proof=copy.deepcopy(held.proof);check_proof(proof,row,binding,UnitObservation)
            absent_intent(row)
            # Existing admitted store lock; no native command while held.
            with store._locked() as actual:
                owned=store._owned(actual,binding['task_id'],binding['owner'])
                need(actual==data and owned==row and digest(actual)==binding['store_sha256'],'whole_store_or_row_changed')
                held.check();check_proof(proof,row,binding,UnitObservation);absent_intent(row)
                need(time.monotonic()<end,'closure_deadline')
                candidate=copy.deepcopy(actual);target=candidate['jobs'][binding['task_id']]
                obs,term,quiet=outcome(row,proof,host)
                target['host']['observation']=obs;target['host']['terminal']=term;target['host']['quiescence']=quiet
                assoc._validate_store(candidate);host.validate_host_record(target)
                # Only these three previously-null host fields may differ.
                restored=copy.deepcopy(candidate)
                for k in ('observation','terminal','quiescence'):restored['jobs'][binding['task_id']]['host'][k]=None
                need(restored==actual,'unexpected_field_delta')
                create(out/'BEFORE.json',{'native_state_bytes_sha256':hashlib.sha256(before_raw).hexdigest(),
                       'associations':actual,'row':owned})
                create(out/'INTENT.json',{'schema':'frw.Root.a0-confirmed-cessation-intent.v1',
                       'before_sha256':digest(actual),'after_sha256':digest(candidate),'task_id':binding['task_id'],
                       'proof':proof,'original_clock':{k:row[k] for k in ('created_at_unix','budget_seconds','deadline_unix','elapsed_seconds')},
                       'historical_effects':'UNKNOWN_NO_REPLAY','retry_authorized':False})
                held.check();check_proof(proof,row,binding,UnitObservation)
                need(time.monotonic()<end,'closure_deadline_before_commit')
                attempted=True
                # Non-CLI Associations._save uses plain set (no atomic compare).
                # Use its canonical validation + native set_commit CAS instead;
                # existing native observer closes custody/durable return witness.
                witness=commit(store,candidate,actual,end)
                fresh=store.state_get(assoc.KEY,None)
                need(fresh==candidate,'postcommit_store_changed')
                create(out/'AFTER.json',candidate)
            # Exit/unlock errors remain UNKNOWN, even if candidate was observed.
        receipt={'schema':'frw.Root.a0-confirmed-cessation-closed.v1','task_id':binding['task_id'],
                 'before_sha256':digest(data),'after_sha256':digest(candidate),
                 'native_witness':witness,'closed_metadata_only':True,'historical_effects':'UNKNOWN_NO_REPLAY',
                 'original_deadline_unix':row['deadline_unix'],'worker_result_accepted':False,
                 'new_operation_authorized':False,'retry_authorized':False}
        create(out/'RECEIPT.json',receipt)
        return receipt
    except BaseException as exc:
        # No rollback, stop, retry, clock reset or assumed absence after any error.
        try:create(out/'UNKNOWN.json',{'status':'UNKNOWN' if attempted else 'REFUSED_NO_COMMIT_ATTEMPT',
                    'exception_class':type(exc).__name__,'commit_entered':attempted,'retry_authorized':False})
        except BaseException:pass
        raise


def apply(binding, *, store, boundary):
    """Root-only entry in the one already-loaded trusted native graph."""
    package='_friday_dashboard_projection'
    need(package in sys.modules and type(store).__module__==package+'.associations','existing_trusted_graph_only')
    assoc=importlib.import_module(package+'.associations');host=importlib.import_module(package+'.host_record')
    supervisor=importlib.import_module('hermes_cli.friday_native_supervision')
    state_module=importlib.import_module('hermes_cli.plugins_state')
    need(type(store) is assoc.Associations and type(store.state) is state_module.PluginState,'exact_existing_consumer_instances')
    for module in (assoc,host,supervisor,importlib.import_module('hermes_cli.plugins_state'),
                   importlib.import_module('hermes_cli.friday_native_state')):
        ref=binding['sources'].get(module.__name__)
        need(ref is not None and Path(module.__file__)==Path(ref['path']),'loaded_module_pin_missing')
        read_ref(ref)
    def commit(s,candidate,expected,end):
        from hermes_cli.friday_native_state import observe_commit_return, require_commit_return
        s._check_local_state()
        with s.lock_budget():
            w=s.state.set_commit(assoc.KEY,candidate,cutoff=end,lock_budget=s._lock_allowance.get(),
                                 expected_value=expected,compare=True)
            returned=observe_commit_return(s.state,w,cutoff=end)
        s._check_local_state()
        closed=require_commit_return(s.state,returned,cutoff=end)
        return {k:getattr(closed,k) for k in ('namespace','directory','lock_inode','previous_inode','inode',
                 'generation','content_sha256','content_bytes','journal','closed_at','cutoff')} | {'observed_at':returned.observed_at}
    return _apply(binding,store=store,boundary=boundary,assoc=assoc,host=host,
                  UnitObservation=supervisor.UnitObservation,commit=commit)

if __name__=='__main__':
    raise SystemExit('Root must call apply inside the existing native scoped entry; UNBOUND is not executable')
