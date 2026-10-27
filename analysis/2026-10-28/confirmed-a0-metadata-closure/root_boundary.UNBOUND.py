"""Exact Root metadata-maintenance boundary, no service/model/worker effects.

Uses the existing runtime and active-session locks, then the supplied canonical
association consumer. Import has no effects. This file alone grants no mutation.
"""
from pathlib import Path
from dataclasses import asdict
from contextlib import contextmanager, ExitStack
import fcntl, hashlib, importlib, json, os, stat, subprocess, time

H = Path('UNBOUND_PROFILE_ROOT')
U = H / 'profiles/UNBOUND_PROFILE'
R = Path('UNBOUND_A0_RUNTIME')
L = Path('UNBOUND_DAEMON_ROOT')
STOP = Path('UNBOUND_STOP_HELPER')
STOP_SHA = 'UNBOUND_STOP_HELPER_SHA256'
SERVICE = Path('UNBOUND_SERVICE_ACCEPTANCE')
SERVICE_SHA = 'UNBOUND_SERVICE_ACCEPTANCE_SHA256'
DAEMON = 'UNBOUND_DAEMON.service'


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def ident(s):
    return [getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')]


def checked_ref(p, expected=None, *, limit=16*1024**2):
    p=Path(p)
    need(p.is_absolute() and p.resolve()==p and '..' not in p.parts, 'canonical_path')
    for q in p.parents:
        s=q.lstat()
        historical_runtime = q in {H/'profiles/UNBOUND_HISTORICAL_PROFILE/runtime', U/'runtime'}
        permitted = not s.st_mode&0o022 or (historical_runtime and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o775)
        need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,os.getuid()) and permitted,'protected_parent')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        s=os.fstat(fd)
        need(type(limit) is int and 0<limit<=64*1024**2,'bounded_ref_limit')
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and s.st_size<=limit,'owned_regular_file')
        parts=[];size=0
        while True:
            b=os.read(fd,65536)
            if not b:break
            parts.append(b);size+=len(b)
            need(size<=limit,'bounded_file')
        data=b''.join(parts)
        need(ident(s)==ident(os.fstat(fd))==ident(p.lstat()),'file_identity_changed')
        sha=hashlib.sha256(data).hexdigest()
        need(expected is None or sha==expected,'source_sha_changed')
        return {'path':str(p),'bytes':len(data),'sha256':sha,'identity':ident(s)},data
    finally:os.close(fd)


def same_ref(ref):
    current,_=checked_ref(ref['path'],ref['sha256'])
    need(current==ref,'ref_identity_changed')


def absent(p):
    need(not os.path.lexists(p),'must_remain_absent')


def process(pid):
    try:
        s=Path('/proc',str(pid),'stat').read_text();v=s[s.rfind(')')+2:].split()
        return {'pid':pid,'start_ticks':int(v[19]),'state':v[0]}
    except (FileNotFoundError,ProcessLookupError):return None


def group_snapshot(group):
    p=Path('/sys/fs/cgroup')/group.lstrip('/')
    need(group.startswith('/') and p.resolve()==p,'cgroup_path')
    if not p.exists():return {'group':group,'populated':False,'processes':[]}
    entries=[x.split() for x in (p/'cgroup.events').read_text().splitlines()]
    need(all(len(x)==2 for x in entries) and len(dict(entries))==len(entries),'cgroup_events')
    flags=dict(entries);need(flags.get('populated') in {'0','1'},'cgroup_populated')
    ids=set()
    for f in p.rglob('cgroup.procs'):
        try:ids.update(map(int,f.read_text().split()))
        except FileNotFoundError:pass
    return {'group':group,'populated':flags['populated']=='1','processes':[v for pid in sorted(ids) if (v:=process(pid))]}


def ceased(sample):
    survivors=[]
    for x in sample['processes']:
        cur=process(x['pid'])
        if cur and str(cur['start_ticks'])==str(x['start_ticks']) and cur['state']!='Z':survivors.append(cur)
    after=group_snapshot(sample['group'])
    need(not survivors and not after['populated'] and not after['processes'],'owned_descendants_survive')
    return {'confirmed':True,'before':sample,'survivors':[],'after':after}


def unit_show(unit, deadline):
    props=('LoadState','InvocationID','ActiveState','SubState','Result','MainPID','ControlPID','ControlGroup','Job','FragmentPath')
    seconds=min(3,deadline-time.monotonic());need(seconds>0,'original_closure_deadline')
    x=subprocess.run(['/usr/bin/systemctl','--user','--no-pager','show',unit,'--property='+','.join(props)],
        capture_output=True,text=True,check=True,timeout=seconds,
        env={'PATH':'/usr/bin:/bin','XDG_RUNTIME_DIR':'UNBOUND_XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS':'UNBOUND_DBUS_SESSION_BUS_ADDRESS','LC_ALL':'C'})
    pairs=[line.split('=',1) for line in x.stdout.splitlines()]
    need(all(len(x)==2 for x in pairs) and len(dict(pairs))==len(pairs),'unit_fields')
    d=dict(pairs);need(set(d)==set(props),'complete_unit_fields')
    need(d['LoadState']=='loaded' and d['MainPID']==d['ControlPID']=='0' and d['ControlGroup']==d['Job']=='','unit_busy')
    return d


def key_files(row):
    state=Path(row['host']['a0']['launch']['plan']['state_dir'])
    need(state==R/row['host']['a0']['launch']['plan']['identity']/'usr','key_state_path')
    result=[]
    for p in (state/'.env',state/'web/secret.env'):
        # Do not hash/log secret values. Verify exact owned fd and introduced
        # assignments absent, preserving unrelated native .env contents.
        for q in p.parents:
            s=q.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,os.getuid()) and not s.st_mode&0o022,'key_parent')
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and s.st_size<1024**2,'key_custody')
            b=os.read(fd,1024**2);need(len(b)==s.st_size,'key_short_read');need(ident(s)==ident(os.fstat(fd))==ident(p.lstat()),'key_changed')
            names=set()
            for line in b.decode().splitlines():
                line=line.strip()
                if line.startswith('export '):line=line[7:].lstrip()
                if '=' in line and not line.startswith('#'):names.add(line.split('=',1)[0].strip())
            need(not names.intersection({'API_KEY_OPENAI','API_KEY_OTHER','SEARXNG_SECRET'}),'introduced_keys_present')
            result.append({'path':str(p),'identity':ident(s),'introduced_assignments_absent':True,'unrelated_contents_preserved':True})
        finally:os.close(fd)
    return result


@contextmanager
def held_boundary(row, deadline, *, c, binding, helper, output):
    hr=c['load_native'].__globals__['hr'];processes=c['EXPECTED_CURRENT_PROCESSES']
    records={k:hr.read_record(role,include_stale=True) for k,role in [('gateway',hr.ROLE_GATEWAY),('dashboard',hr.ROLE_SERVE)]}
    for k,r in records.items():
        need(r and r.pid==processes[k]['pid'] and not hr.record_is_stale(r) and hr.liveness_is_proven(r) and hr.record_token_is_consistent(r),'service_custody')
    need(hr.read_record('desktop-serve',include_stale=True) is None,'foreign_desktop_serve')
    pins=[checked_ref(SERVICE,SERVICE_SHA)[0],checked_ref(STOP,STOP_SHA)[0],*binding['sources'].values()]
    source_refs=c['CURRENT_EXACT_CAS_REFS']
    for ref in source_refs.values():c['read_pin'](ref)
    for k,p in processes.items():need(c['proc'](p['pid'])==p,'current_process_changed')
    sessions=importlib.import_module('hermes_cli.active_sessions')
    lock_pins=[];registries=[]
    with ExitStack() as stack:
        # Existing runtime ownership boundary. Do not create a new lock file.
        for p,shared in [(R/'runtime.lock',False),*[(h/'runtime/active_sessions.lock',True) for h in [H]+[H/'profiles'/n for n in records['gateway'].profiles if n!='default']]]:
            pin,_=checked_ref(p);s=p.lstat()
            need(stat.S_IMODE(s.st_mode) in ({0o600,0o644,0o664} if shared else {0o600}),'lock_permissions')
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            stack.callback(os.close,fd)
            need(ident(os.fstat(fd))==pin['identity'],'lock_identity')
            fcntl.flock(fd,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            stack.callback(fcntl.flock,fd,fcntl.LOCK_UN)
            lock_pins.append((pin,fd))
        for home in [H]+[H/'profiles'/n for n in records['gateway'].profiles if n!='default']:
            pin,_=checked_ref(home/'runtime/active_sessions.json')
            entries=sessions._read_entries(Path(pin['path']),strict=True)
            live=sessions._prune_dead(entries,strict=True)
            need(not live,'active_session_present');same_ref(pin);pins.append(pin)
            registries.append({'home':str(home),'registry':pin,'live_entries':0,'entries':len(entries)})
        # Freshness starts before the first held live sample, not when the
        # last sample happens to finish. A slow observation must fail closed.
        observed_monotonic=time.monotonic();observed_unix=time.time()
        control=importlib.import_module('gateway.control_socket').query_gateway_control(H,'status',timeout=min(3,deadline-time.monotonic()))
        need(control['active_agents']==0 and control.get('active_work') is None and control.get('restart_requested') is False and control.get('pid',control.get('answering_pid'))==processes['gateway']['pid'],'gateway_busy')
        status=importlib.import_module('gateway.status');ns=status.read_runtime_status(H/'gateway_state.json')
        need(ns['active_agents']==0 and ns.get('active_work') is None and ns.get('restart_requested') is False and not status.runtime_status_is_stale(ns),'gateway_status_busy')
        sup=importlib.import_module('hermes_cli.friday_native_supervision')
        worker=asdict(sup.NativeSupervisor().observe(row,deadline=deadline))
        w=unit_show(row['supervisor']['unit'],deadline);d=unit_show(DAEMON,deadline)
        need(worker['invocation_id']==w['InvocationID']==row['host']['a0']['grant']['invocation_id'],'worker_invocation_changed')
        daemon={'unit':DAEMON,'invocation_id':d['InvocationID'],'active_state':d['ActiveState'],'sub_state':d['SubState'],'result':d['Result'],'main_pid':0,'control_group':'','populated':False,'missing':False}
        target=L/'supervisor'/DAEMON;link=Path('UNBOUND_SYSTEMD_USER_DIR')/DAEMON
        need(d['FragmentPath']==str(link) and link.is_symlink() and link.resolve()==target,'daemon_fragment_changed')
        ls=link.lstat();need(ls.st_uid==os.getuid() and ls.st_nlink==1,'daemon_link_owner')
        unit_ref,_=checked_ref(target,row['host']['a0']['launch']['plan']['daemon_unit_sha256']);pins.append(unit_ref)
        native_path=R/row['host']['a0']['launch']['plan']['identity']/'native.json'
        native_ref,native_raw=checked_ref(native_path);native=helper.strict_json(native_raw);pins.append(native_ref)
        checks=[ceased(s) for s in native['observations']]
        retained_checks=[ceased(s) for s in row['host']['a0']['observations']['samples']]
        route=row['host']['a0']['route'];settled=route['settlement']
        need(settled['status']=='STOP_CONFIRMED' and all(settled[x] is True for x in ('guard_removed','network_removed','request_removed')) and route['network_removed'] is True,'route_not_settled')
        daemon_checks=[ceased(s['before']) for s in settled['daemon_checks']]
        for p in (L/'config/local-route.json',Path('UNBOUND_ROUTE_GUARD')):absent(p)
        keys=key_files(row);helper.absent_intent(row)
        current_checks={'registries':registries,'units':{row['supervisor']['unit']:w,DAEMON:d},'daemon_unit_file':unit_ref,'daemon_unit_link':{'path':str(link),'target':str(target),'identity':ident(ls)},'daemon_descendant_checks':daemon_checks,'introduced_keys':keys,'gateway_process':processes['gateway'],'gateway_idle':True,'route_removed_ack_retained':True}
        daemon_stopped_binding=({'load_state':d['LoadState'],'control_pid':int(d['ControlPID']),
            'processes':[],'fragment_path':d['FragmentPath'],'symlink_target':os.readlink(link),
            'symlink_identity':ident(ls),'fragment_ref':unit_ref,'descendant_checks':daemon_checks}
            if d['InvocationID']=='' else None)
        proof={'schema':'frw.Root.a0-confirmed-cessation-proof.v3','observed_unix':observed_unix,'observed_monotonic':observed_monotonic,'boot_id':binding['boot_id'],'row_sha256':helper.digest(row),'store_sha256':binding['store_sha256'],'worker_unit':worker,'worker_job':w['Job'],'daemon_unit':daemon,'daemon_job':d['Job'],'native_receipt':native,'native_receipt_ref':native_ref,'container_checks':checks,'native_cessation':True,'keys_removed':True,'route_removed':True,'gateway_idle':True,'evidence_reference':str(output/'ROOT-CURRENT-RESOURCE-PROOF.json'),'historical_effects':'UNKNOWN_NO_REPLAY','daemon_stopped_binding':daemon_stopped_binding,'retained_container_checks':retained_checks}
        need(time.monotonic()-observed_monotonic<=5,'proof_sampling_expired')
        helper.create(output/'ROOT-CURRENT-RESOURCE-PROOF.json',{'proof':proof,'current_checks':current_checks})
        class Held:
            def __init__(self):self.proof=proof
            def check(self):
                need(time.monotonic()<deadline and time.monotonic()-proof['observed_monotonic']<=5,'proof_expired')
                for pin in pins:same_ref(pin)
                for pin,fd in lock_pins:
                    need(ident(os.fstat(fd))==pin['identity']==ident(Path(pin['path']).lstat()),'held_lock_changed')
                need(ident(link.lstat())==ident(ls) and link.resolve()==target,'daemon_link_changed')
                for p in processes.values():need(c['proc'](p['pid'])==p,'service_process_changed')
                for s in native['observations']:ceased(s)
                for s in row['host']['a0']['observations']['samples']:ceased(s)
                for s in settled['daemon_checks']:ceased(s['before'])
                key_files(row)
                for p in (L/'config/local-route.json',Path('UNBOUND_ROUTE_GUARD')):absent(p)
                for ref in source_refs.values():c['read_pin'](ref)
        yield Held()
