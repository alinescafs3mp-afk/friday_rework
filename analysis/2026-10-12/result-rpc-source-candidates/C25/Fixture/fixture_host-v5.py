"""Private finite adapter around stock subprocess.wait(timeout) + existing timeout120.

This is not a daemon, scheduler, installed owner or new authority protocol.
Run only after Root admits exact bytes. Subreaper is confined to this process.
"""
import os,sys,time,json,hashlib,signal,subprocess,ctypes,fcntl,resource
from pathlib import Path
OUT=Path(__file__).resolve().parent
AS=268435456
def birth(pid):return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
def pin(path):
    raw=Path(path).read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def put(p,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def identity(pid):
    raw=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'birth':raw[19],'ppid':int(raw[1]),'pgid':int(raw[2]),'sid':int(raw[3])}
def main():
    assert resource.getrlimit(resource.RLIMIT_AS)==(AS,AS)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(60,60)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    libc=ctypes.CDLL(None,use_errno=True);assert libc.prctl(36,1,0,0,0)==0
    phase=sys.argv[1]
    author=['positive','duplicate_evidence','missing_owner','incomplete_owner','SIGCHLD_IGN','SIGCHLD_custom','before_GO_denial','entry_flock_stop','descriptor_flock_stop','result_fsync_flock_stop','wait_EIO_after_kill','wait_EIO_after_durable_result','wait_zero_until_final','pending_notification_EIO','caller_final_close_flock','caller_owner_unwound_flock']
    independent=['independent_positive','independent_missing_owner','independent_owner_denial','independent_hold_EIO','independent_durable_wait_EIO','independent_bootstrap_stall','independent_final_evidence_close_stall','independent_callback_stall','independent_before_GO_live_cohort_stall']
    cases=author if phase=='author' else independent
    clock=json.loads((OUT/'CLOCK.json').read_bytes());host=identity(os.getpid())
    put(OUT/(phase+'-v5-HOST-BIRTH.json'),{'host':host,'limits':Path('/proc/self/limits').read_text(),
        'affinity':sorted(os.sched_getaffinity(0)),'stock_outer_wall':'timeout -s KILL 120s before host Python',
        'Source_caller_worker_hard_AS_sum':2*AS,'stock_host_guard_additional_hard_AS_sum':2*AS,'outer_guard':identity(os.getppid()),
        'outer_guard_actual_limits':Path('/proc/'+str(os.getppid())+'/limits').read_text(),
        'RSS_and_initial_unknown_helpers':'UNKNOWN, not zero','only_authorized_fixture':'exact Root-admitted Source test, no installed authority'})
    summary=[]
    for case in cases:
        assert time.monotonic()<clock['started_at_monotonic']+1020
        rec=OUT/'observations-v5'/case;rec.mkdir(parents=True,mode=0o700)
        lock=rec/'outside.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);fcntl.flock(fd,fcntl.LOCK_EX)
        sec=4 if case=='wait_zero_until_final' else 3
        cfg={'case':case,'case_root':str(OUT/'fixtures-v5'/case),'case_record':str(rec),
             'helper':pin(OUT/'Source/bounded_install_helper.py'),'controls':pin(OUT/'Controls/repair_controls.py'),
             'host':host,'host_program':pin(OUT/'fixture_host-v5.py'),'outer_guard':identity(os.getppid()),'outside_stall_path':str(lock),'guard_deadline_monotonic':time.monotonic()+sec,
             'root_admission':'Root external tool review authorizes exact pinned fixture; this field is not a grant'}
        config=rec/'CONFIG.json';put(config,cfg)
        stdout=open(rec/'stdout.log','xb');stderr=open(rec/'stderr.log','xb')
        started=time.monotonic();proc=subprocess.Popen([sys.executable,'-B',str(OUT/'fixture_caller-v4.py'),str(config)],
            stdout=stdout,stderr=stderr,start_new_session=False,close_fds=True)
        guard=identity(proc.pid);put(rec/'GUARD-BIRTH.json',guard)
        caller_timed_out=False;caller_kill_requested=False
        try:code=proc.wait(timeout=max(0,cfg['guard_deadline_monotonic']-time.monotonic()))
        except subprocess.TimeoutExpired:
            caller_timed_out=True
            assert birth(proc.pid)==guard['birth']
            pfd=os.pidfd_open(proc.pid);signal.pidfd_send_signal(pfd,signal.SIGKILL);os.close(pfd)
            caller_kill_requested=True;code=proc.wait(timeout=2)
        stdout.close();stderr.close();adopted=[]
        # Bounded cleanup of only adopted direct children of this owned finite
        # fixture. No model polling, sleeps or unrelated process-group kill.
        cleanup_until=min(time.monotonic()+3,clock['started_at_monotonic']+1200)
        while True:
            try:
                pid,status=os.waitpid(-1,os.WNOHANG)
            except ChildProcessError:break
            if pid:
                adopted.append({'pid':pid,'direct_wait':True,'returncode':os.waitstatus_to_exitcode(status)});continue
            if time.monotonic()>=cleanup_until:raise RuntimeError('STOP_UNCONFIRMED adopted fixture child')
            children=Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().split()
            for value in children:
                child=identity(int(value));assert child['pgid']==guard['pgid']
                pfd=os.pidfd_open(child['pid']);signal.pidfd_send_signal(pfd,signal.SIGKILL);os.close(pfd)
            import select
            select.select([],[],[],0.01)
        known=[]
        caller_file=rec/'CALLER-BEFORE-IMPORT.json'
        worker_file=OUT/'fixtures-v5'/case/'attempt/WORKER-BIRTH.json'
        if caller_file.exists():
            caller_data=json.loads(caller_file.read_bytes())['caller']
            assert caller_data['pid']==guard['pid'] and caller_data['birth']==guard['birth']
            known.append(dict(caller_data,kind='Source_caller'))
        if worker_file.exists():
            worker_data=json.loads(worker_file.read_bytes())
            assert type(worker_data['pid']) is int and isinstance(worker_data['birth'],str)
            known.append(dict(worker_data,kind='Source_worker'))
        absent=[]
        for row in [guard]+known:
            p=Path('/proc/'+str(row['pid'])+'/stat')
            absent.append({'pid':row['pid'],'birth':row['birth'],'fresh_absent':not p.exists() or birth(row['pid'])!=row['birth']})
        assert all(r['fresh_absent'] for r in absent)
        assert not Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        stall=(OUT/'fixtures-v5'/case/'PHYSICAL-STALL-REACHED.json').exists() or (OUT/'fixtures-v5'/case/'INDEPENDENT-STALL-REACHED.json').exists() or (rec/'PREIMPORT-STALL-REACHED.json').exists()
        outside=case in ('wait_zero_until_final','caller_final_close_flock','caller_owner_unwound_flock','independent_bootstrap_stall','independent_final_evidence_close_stall','independent_callback_stall','independent_before_GO_live_cohort_stall')
        expected=(code==-9 and caller_timed_out and caller_kill_requested and stall and not (rec/'CALLER-RETURN-PREPARED.json').exists()) if outside else (code==0 and (rec/'CALLER-RETURN-PREPARED.json').exists())
        if case=='independent_before_GO_live_cohort_stall':
            expected=expected and worker_file.exists() and any(r['pid']==worker_data['pid'] and r['returncode']==-9 for r in adopted)
        result={'case':case,'stock_guard_returncode':code,'outside_guard_is':'Root-reviewed finite host Popen.wait timeout; outer timeout120 remains active through hostexit','outside_stall_expected':outside,'physical_stall_reached':stall,
            'expected_observation_confirmed':expected,'caller_directwait':True,'caller_returncode':code,'caller_timed_out':caller_timed_out,'caller_exact_pidfd_SIGKILL_requested':caller_kill_requested,'adopted_directwait':adopted,'known_fresh_closure':absent,
            'whole_owned_directchild_cohort_closed':True,'elapsed':time.monotonic()-started,
            'inside_unknown_when_guard_killed':outside,'Source_acceptance':'not decided by this adapter'}
        put(rec/'OUTSIDE-CLOSURE.json',result);summary.append(result)
        if not expected:break
    put(OUT/(phase+'-v5-SUMMARY.json'),{'cases':summary,'all_requested':len(summary)==len(cases),'expected_count':len(cases),
        'confirmed':sum(x['expected_observation_confirmed'] for x in summary),'host_exit':'Root observes after direct tool return'})
    print(json.dumps({'phase':phase,'run':len(summary),'confirmed':sum(x['expected_observation_confirmed'] for x in summary)}))
if __name__=='__main__':main()
