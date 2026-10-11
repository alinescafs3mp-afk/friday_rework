"""Physical offline full-wall controls, actual one-fork supervisor per case.
No native connector, NativeControl/lifecycle API, CLI, network or extra agent.
"""
import argparse
import ast
import asyncio
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import runpy
import select
import signal
import time
import threading
import uuid

HERE=Path(__file__).resolve().parent
W=HERE.parent
OUT=W/os.environ.get('C26_WHOLE_OUT','execution'); OUT.mkdir(mode=0o700)
COMPAT_OUT=W/os.environ.get('C26_COMPAT_OUT','execution-compat81')
AS=268435456
resource.setrlimit(resource.RLIMIT_AS,(AS,AS))
resource.setrlimit(resource.RLIMIT_CPU,(60,60))
resource.setrlimit(resource.RLIMIT_FSIZE,(67108864,67108864))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
CALLER_END=time.monotonic()+120
signal.alarm(120)
C=json.loads((W/'CLOCK.json').read_bytes())
assert time.time()<C['useful_end_unix']-90
def load(name):
    s=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
S=load('whole_wall'); M=load('result_rpc')
rows=[];known=[]
def save(path,obj):
    b=json.dumps(obj,sort_keys=True,indent=2).encode()+b'\n'
    assert len(b)<=65536
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
save(OUT/'CALLER.json',{'pid':os.getpid(),'birth':S.birth(os.getpid()),'caps':S.caps(),
     'host_RSS':'UNKNOWN','host_before_Source':'UNKNOWN','cpu_count':os.cpu_count(),
     'pressure':{k:Path('/proc/pressure/'+k).read_text() for k in ['cpu','io','memory']},
     'cgroup':{k:((Path('/sys/fs/cgroup')/k).read_text().strip() if (Path('/sys/fs/cgroup')/k).exists() else 'UNKNOWN_UNEXPOSED') for k in ['cpu.max','memory.max','memory.current']}})
def case(name,fn):
    try:
        value=fn(); ok=True
    except BaseException as e:
        value={'class':type(e).__name__,'message':str(e)[:300]};ok=False
    p=OUT/('ROW-'+name+'.json');save(p,value)
    raw=p.read_bytes()
    rows.append({'id':name,'PASS':ok,'evidence':{'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}})
def supervise(name,op,wall=.3,cleanup=.05):
    p=OUT/name;p.mkdir(mode=0o700)
    v=S.supervise(op,p,wall=wall,cleanup=cleanup,hard_end=C['useful_end_monotonic'])
    z=v['whole_wall'];known.append({'pid':z['pid'],'birth':z['birth']})
    save(p/'SUPERVISOR.json',v)
    assert z['status']=='STOP_CONFIRMED' and z['reaped'] and z['fresh_exact_birth_absent'],v
    assert z['elapsed']<wall+.15,(name,z)
    assert not S.PENDING
    assert not Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
    assert z['worker']['caps']['AS']==[AS,AS] and z['caller']['caps']['AS']==[AS,AS]
    return v
def successful(name,op):
    value=supervise(name,op)
    assert value['whole_wall']['direct_wait_returncode']==0,value
    return value
def stopped(name,op):
    v=supervise(name,op);assert v['state']=='UNKNOWN';return v
def hang():
    while True:select.select([],[],[],.05)
def lock_hang(custody):
    p=OUT/('lock-'+str(os.getpid()));one=os.open(p,os.O_RDWR|os.O_CREAT,0o600);two=os.open(p,os.O_RDWR)
    fcntl.flock(one,fcntl.LOCK_EX);fcntl.flock(two,fcntl.LOCK_EX)
def trapped(custody):
    try:raise TimeoutError('private timeout')
    finally:hang()
for name,op in [('preparation_real_flock',lock_hang),('import_load_real_flock',lock_hang),
                ('unwinding_slow_finally',trapped),('validation_blocking',lambda c:hang())]:
    case(name,lambda name=name,op=op:stopped(name,op))
def ignoring(c):
    signal.signal(signal.SIGTERM,lambda *_:None)
    signal.signal(signal.SIGALRM,lambda *_:None)
    hang()
case('trapped_signals_parent_kill_independent',lambda:stopped('signals',ignoring))

class Control:
    thread='OFFLINE';sequence=1
    def __init__(self,p):self.p=p;self.adds=0
    async def open(self,end):pass
    async def rpc(self,method,params):
        assert method=='thread/queue/add';self.adds+=1
        return {'queuedSubmission':{'id':str(uuid.uuid4()),'clientUserMessageId':params['clientUserMessageId'],'input':params['input']}}
    async def close(self,end):pass
def fixture(name):
    d=OUT/('fixture-'+name);d.mkdir(mode=0o700);a=d/'audit';a.mkdir(mode=0o700)
    p=d/'receipt.json';control=Control(p)
    g={'event':'SOL-'+name,'assignment':'OFFLINE','generation':'1',
       'notice':{'sha256':'0'*64,'bytes':2},
       'expected':{'sol':{'generation':'sender'},'astra':{'generation':'peer','thread':control.thread}}}
    return d,a,p,control,g
def send_case(name,kind):
    d,a,p,c,g=fixture(name)
    def op(custody):
        if kind=='audit-lock':
            old=Path.iterdir
            def scan(path):
                if path==a:return lock_hang(custody)
                return old(path)
            Path.iterdir=scan
        if kind=='lifecycle-lock':life=lambda *args:lock_hang(custody)
        else:life=lambda *args:None
        if kind=='commit-cleanup':
            old=M.write_once;oldexists=Path.exists
            def write(path,value):
                if Path(path).name.startswith('.'):select.select([],[],[],1)
                return old(path,value)
            def exists(path):
                if Path(path).name.startswith('.'):hang()
                return oldexists(path)
            M.write_once=write;Path.exists=exists
        if kind=='postrename-fsync':
            old=M.fsync_dir;count=[0]
            def sync(path):
                if Path(path)==d:
                    count[0]+=1
                    if count[0]>=3:hang()
                return old(path)
            M.fsync_dir=sync
        if kind=='durable-close-trap':
            async def close(end):hang()
            c.close=close
        if kind=='durable-final-audit-trap':
            old=M.write_once
            def write(path,value):
                if Path(path).name=='TRANSPORT-FINAL.json':hang()
                return old(path,value)
            M.write_once=write
        if kind=='rpc-ambiguous':
            async def rpc(method,params):
                (d/'REMOTE-ATTEMPT').write_text('one fake remote effect; response absent');hang()
            c.rpc=rpc
        return asyncio.run(M.send_prepared(c,g,'OFFLINE',custody.operation_end,p,a,life,lambda:None,custody=custody))
    short=kind in ['audit-lock','lifecycle-lock']
    v=supervise(name,op,wall=.3 if short else 3.35,cleanup=.05)
    if kind.startswith('durable') or kind=='success':
        assert v['state']=='ENQUEUED' and json.loads(p.read_bytes())['state']=='ENQUEUED',v
    else:assert v['state']=='UNKNOWN',v
    if kind=='success':assert v['whole_wall']['direct_wait_returncode']==0,v
    if kind=='rpc-ambiguous':assert (d/'REMOTE-ATTEMPT').exists()
    if kind=='postrename-fsync':
        assert json.loads(p.read_bytes())['state']=='ENQUEUED' and v['state']=='UNKNOWN'
        # NEW recovery control only fsyncs exact existing receipt; no RPC replay.
        def recover(custody):
            return asyncio.run(M.send_prepared(c,g,'OFFLINE',custody.operation_end,p,a,lambda *a:None,lambda:None,custody=custody))
        r=supervise(name+'-recovery',recover,wall=.3,cleanup=.05)
        assert r['state']=='ENQUEUED' and r['queue_calls']==0
    return v
for name,kind in [('whole_audit_traversal','audit-lock'),('whole_lifecycle_flock','lifecycle-lock'),
                 ('one_shot_cleanup_stall','commit-cleanup'),('postrename_ambiguity_and_durable_recovery','postrename-fsync'),
                 ('confirmed_before_teardown_timeout','durable-close-trap'),('confirmed_before_final_audit_timeout','durable-final-audit-trap'),
                 ('ambiguous_RPC_timeout_no_promote','rpc-ambiguous'),('positive_one_add','success')]:
    case(name,lambda name=name,kind=kind:send_case(name,kind))

def expired(c):
    c.tighten(time.monotonic()-.1);raise AssertionError('expired admitted')
case('expired_original_before_effect',lambda:stopped('expired',expired))
def tighten(c):
    c.tighten(time.monotonic()+.08);hang()
case('grant_clock_tightens_never_resets',lambda:stopped('tightened',tighten))
def nested(c):
    try:os.fork()
    except S.Refusal:return {'state':'UNKNOWN','nested_fork':'REFUSED'}
    raise AssertionError('nested child admitted')
case('no_unregistered_python_descendant',lambda:successful('nested',nested))
def owner_timer(kind):
    before=signal.getsignal(signal.SIGALRM);old=signal.getitimer(signal.ITIMER_REAL)
    timer=(.1,0) if kind=='early' else (2,.1)
    signal.setitimer(signal.ITIMER_REAL,*timer)
    try:
        try:S.supervise(lambda c:{'state':'UNKNOWN'},OUT/'no-use',wall=.3,cleanup=.05)
        except S.Refusal:pass
        else:raise AssertionError('owner timer admitted')
        after=signal.getitimer(signal.ITIMER_REAL)
        assert 0<after[0]<=timer[0] and after[1]==timer[1] and signal.getsignal(signal.SIGALRM)==before
        return {'after':after,'handler_unchanged':True}
    finally:signal.setitimer(signal.ITIMER_REAL,max(.000001,CALLER_END-time.monotonic()),0)
for k in ['early','periodic']:case('owner_timer_'+k,lambda k=k:owner_timer(k))
def later_timer():
    old=signal.getitimer(signal.ITIMER_REAL);handler=signal.getsignal(signal.SIGALRM)
    signal.setitimer(signal.ITIMER_REAL,2)
    try:
        v=supervise('later-timer',lambda c:(select.select([],[],[],.04) and {'state':'UNKNOWN'}))
        assert v['whole_wall']['direct_wait_returncode']==0,v
        timer=signal.getitimer(signal.ITIMER_REAL)
        assert 1.5<timer[0]<2 and timer[1]==0 and signal.getsignal(signal.SIGALRM)==handler
        return {'remaining':timer,'whole_wall':v['whole_wall']}
    finally:signal.setitimer(signal.ITIMER_REAL,max(.000001,CALLER_END-time.monotonic()),0)
case('later_owner_timer_naturally_elapsed_unchanged',later_timer)
def stale():
    saved=S.birth;sent=[];old=signal.pidfd_send_signal
    S.birth=lambda pid:'foreign';signal.pidfd_send_signal=lambda *a:sent.append(a)
    try:assert S.signal_owned(42,'original',999) is False and not sent
    finally:S.birth=saved;signal.pidfd_send_signal=old
    return {'no_signal_on_PID_reuse':True}
case('PID_reuse_never_signals_numeric_replacement',stale)
def no_main():
    result=[]
    def run():
        try:S.supervise(lambda c:{},OUT/'unused')
        except S.Refusal:result.append(True)
    t=threading.Thread(target=run);t.start();t.join(1)
    assert not t.is_alive() and result==[True];return {'joined':True}
case('nonmain_refused_and_joined',no_main)
def pending():
    S.PENDING[0]={'synthetic':'NO_ACTUAL_CHILD'}
    try:
        try:S.supervise(lambda c:{},OUT/'unused')
        except S.Refusal:pass
        else:raise AssertionError('unconfirmed custody admitted')
    finally:S.PENDING.clear()
    return {'unknown_no_admission':True,'synthetic_only':True}
case('STOP_UNCONFIRMED_prevents_next_admission',pending)

def unconfirmed():
    p=OUT/'unconfirmed-wait';p.mkdir(mode=0o700)
    wait=os.waitpid
    os.waitpid=lambda *_a:(0,0)
    try:v=S.supervise(lambda c:hang(),p,wall=.25,cleanup=.05)
    finally:os.waitpid=wait
    z=v['whole_wall'];known.append({'pid':z['pid'],'birth':z['birth']})
    assert z['status']=='STOP_UNCONFIRMED' and not z['reaped'] and z['pid'] in S.PENDING
    save(p/'UNCONFIRMED.json',v)
    held=S.PENDING[z['pid']];end=time.monotonic()+1
    while time.monotonic()<end:
        pid,st=wait(z['pid'],os.WNOHANG)
        if pid:break
        select.select([held['pidfd']],[],[],.01)
    else:raise AssertionError('test-owned cleanup unconfirmed')
    try:assert S.birth(z['pid'])!=z['birth']
    except FileNotFoundError:pass
    os.close(held['pidfd']);del S.PENDING[z['pid']]
    save(p/'OWNED-FRESH-CLOSED.json',{'pid':z['pid'],'birth':z['birth'],'reaped':True,'fresh_absent':True,'no_replay':True})
    return {'initial':'STOP_UNCONFIRMED','closed_only_after_actual_direct_wait':True}
case('actual_killed_worker_wait_ambiguity_retained_then_closed',unconfirmed)

# Real receipt syscalls, positive short writes and refused zero write/rename.
def syscall(kind):
    d=OUT/('syscall-'+kind);d.mkdir(mode=0o700);p=d/'receipt.json'
    def op(c):
        original=M.os.write
        if kind=='short':
            def short(fd,b):return original(fd,b[:max(1,len(b)//3)])
            M.os.write=short
        elif kind=='zero':M.os.write=lambda *_a:0
        elif kind=='fsync':M.os.fsync=lambda *_a:(_ for _ in ()).throw(OSError('offline fsync'))
        if kind in ['short','zero','fsync']:
            M.write_once(p,{'state':'UNKNOWN','padding':'x'*500})
            assert json.loads(p.read_bytes())['state']=='UNKNOWN'
        else:
            M.write_once(p,{'state':'UNKNOWN'})
            M.os.replace=lambda *_a:(_ for _ in ()).throw(OSError('offline rename'))
            M.replace_receipt(p,{'state':'ENQUEUED'})
        return {'state':'UNKNOWN','syscall_positive_complete':True}
    v=supervise('syscall-control-'+kind,op)
    if kind=='short':assert v.get('syscall_positive_complete') is True and v['whole_wall']['direct_wait_returncode']==0
    else:assert v['whole_wall']['direct_wait_returncode']==2
    if kind=='rename':assert json.loads(p.read_bytes())['state']=='UNKNOWN'
    return v
for k in ['short','zero','fsync','rename']:case('physical_receipt_syscall_'+k,lambda k=k:syscall(k))

# Reproduce the complete old submachine contract on changed final transport,
# with an ACTUAL enclosing supervisor; injected API adaptation is explicit.
def compat(c):
    runpy.run_path(str(HERE/'compat_controls.py'),run_name='__main__')
    o=json.loads((COMPAT_OUT/'CONTROLS.json').read_bytes())
    assert o['raw']==81 and o['PASS']==81 and o['FAIL']==0
    return {'state':'UNKNOWN','compat_PASS':81,'compat_FAIL':0,'actual_native_calls':0}
def verify_compat_success(value, report_path):
    assert value['whole_wall']['direct_wait_returncode']==0,value
    assert value.get('compat_PASS')==81 and value.get('compat_FAIL')==0,value
    report=json.loads(report_path.read_bytes())
    assert (report['raw'],report['unique'],report['PASS'],report['FAIL'])==(81,81,81,0),report
    assert len(report['controls'])==81 and all(r['PASS'] for r in report['controls'])
    assert len({r['id'] for r in report['controls']})==81
    assert report['source']['sha256']==hashlib.sha256((HERE/'result_rpc.py').read_bytes()).hexdigest()
    return value
def whole_compat():
    value=supervise('compat81',compat,wall=20,cleanup=2)
    return verify_compat_success(value,COMPAT_OUT/'CONTROLS.json')
case('whole_enclosed_previous_81_contract_controls',whole_compat)
def false_success(kind):
    def operation(c):
        if kind=='SystemExit':raise SystemExit(1)
        raise AssertionError('real child assertion negative')
    value=supervise('false-success-'+kind,operation)
    assert value['whole_wall']['direct_wait_returncode']==2
    try:verify_compat_success(value,COMPAT_OUT/'CONTROLS.json')
    except AssertionError:return {'false_success_refused':True,'failure_kind':kind,'observed':value}
    raise AssertionError('false compatibility success accepted')
for kind in ['SystemExit','AssertionError']:
    case('false_success_'+kind+'_refused',lambda kind=kind:false_success(kind))

def source_selector(c):
    selector=load('result_selector')
    original=selector.hashlib.sha256
    # Real pinned transport Source is loaded, but its deliver entry is an
    # explicitly synthetic offline callable: tests the selector binding only.
    data=b"import json\nfrom pathlib import Path\ndef loads(b):return json.loads(b)\ndef pinned(r):return Path(r['path']).read_bytes()\nasync def deliver_in_worker(p,h,c):return {'state':'UNKNOWN','offline_selector_positive':True}\n"
    p=OUT/'selector-positive-transport.py';p.write_bytes(data);p.chmod(0o600)
    pin={'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    g={'source':pin,'custody_dir':str(OUT/'selector-positive'),'event':'SOL-OFFLINE','assignment':'OFFLINE','generation':'1','notice':{'path':'/private/notice'},
       'dependencies':{'sender':{'path':'/private/sender'},'recipient':{'path':'/private/recipient'}}}
    gp=OUT/'selector-grant.json';gp.write_text(json.dumps(g));gp.chmod(0o600)
    args=argparse.Namespace(kind='RESULT',rpc_grant=gp,rpc_grant_sha=hashlib.sha256(gp.read_bytes()).hexdigest(),
        event=g['event'],assignment_id=g['assignment'],assignment_generation='1',assignment_action='complete',
        large_reason=None,rpc_custody_dir=OUT/'selector-positive',ref=Path('/private/notice'),sender_binding=Path('/private/sender'),recipient_binding=Path('/private/recipient'))
    result=selector.dispatch_in_worker(args,argparse.ArgumentParser(),pin,c)
    assert result['offline_selector_positive'];return result
case('positive_selector_bound_entry_no_legacy_CLI',lambda:successful('selector-positive',source_selector))
def builder():
    b=load('build_sender');raw=(W/'fixtures/canonical-original.py').read_bytes()
    def pin(name):
        p=HERE/name;v=p.read_bytes();return {'path':str(p),'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()}
    built=b.build(raw,pin('result_selector.py'),pin('result_rpc.py'),(HERE/'whole_wall.py').read_bytes())
    (W/'CANONICAL-SENDER.CANDIDATE.py').write_bytes(built);(W/'CANONICAL-SENDER.CANDIDATE.py').chmod(0o600)
    old=ast.parse(raw);new=ast.parse(built)
    oldmain=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    main=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    def inserted(n):
        if isinstance(n,ast.If) and ast.unparse(n.test)=="args.kind == 'RESULT'":return True
        return isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and any(isinstance(a,ast.Constant) and a.value in ['--rpc-grant','--rpc-grant-sha','--rpc-custody-dir'] for a in n.value.args)
    main.body=[n for n in main.body if not inserted(n)]
    assert ast.dump(main)==ast.dump(oldmain)
    return {'non_RESULT_main_AST_identical':True,'candidate_bytes':len(built),'candidate_executed':False}
case('builder_non_RESULT_TASK_CLI_exact_preserved',builder)

def canonical_variant(block=False):
    """Actual generated main with private synthetic transport; no sender API.
    Resident supervisor is loaded before main, exactly as proposed Source.
    """
    import sys
    d=OUT/('canonical-blocked' if block else 'canonical-positive');d.mkdir(mode=0o700)
    custody=d/'custody';custody.mkdir(mode=0o700)
    if block:
        data=("import fcntl,os\np="+repr(str(d/'lock'))+"\na=os.open(p,os.O_RDWR|os.O_CREAT,0o600)\nb=os.open(p,os.O_RDWR)\nfcntl.flock(a,fcntl.LOCK_EX)\nfcntl.flock(b,fcntl.LOCK_EX)\n").encode()
    else:
        data=b"import json\nfrom pathlib import Path\ndef loads(b):return json.loads(b)\ndef pinned(r):return Path(r['path']).read_bytes()\nasync def deliver_in_worker(p,h,c):return {'state':'UNKNOWN','canonical_offline_positive':True}\n"
    transport=d/'transport.py';transport.write_bytes(data);transport.chmod(0o600)
    tp={'path':str(transport),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    selector=HERE/'result_selector.py';sp={'path':str(selector),'bytes':selector.stat().st_size,'sha256':hashlib.sha256(selector.read_bytes()).hexdigest()}
    g={'source':tp,'event':'SOL-CANONICAL','assignment':'OFFLINE','generation':'1','custody_dir':str(custody),
       'notice':{'path':str(d/'notice')},'dependencies':{'sender':{'path':str(d/'sender')},'recipient':{'path':str(d/'recipient')}}}
    grant=d/'grant.json';grant.write_text(json.dumps(g));grant.chmod(0o600)
    b=load('build_sender');built=b.build((W/'fixtures/canonical-original.py').read_bytes(),sp,tp,(HERE/'whole_wall.py').read_bytes())
    (d/'OFFLINE-VARIANT.py').write_bytes(built);(d/'OFFLINE-VARIANT.py').chmod(0o600)
    # Compile and load definitions; __main__ guard is false, no native entry.
    ns={'__name__':'private_offline_canonical','__file__':str(d/'OFFLINE-VARIANT.py')}
    exec(compile(built,str(d/'OFFLINE-VARIANT.py'),'exec'),ns)
    old=sys.argv
    sys.argv=['private-source-fixture','--kind','RESULT','--sender-binding',str(d/'sender'),
              '--recipient-binding',str(d/'recipient'),'--event','SOL-CANONICAL','--ref',str(d/'notice'),
              '--assignment-id','OFFLINE','--assignment-generation','1','--rpc-grant',str(grant),
              '--rpc-grant-sha',hashlib.sha256(grant.read_bytes()).hexdigest(),'--rpc-custody-dir',str(custody)]
    # Trap legacy path before any possible actual binding/native operation.
    ns['binding']=lambda *_a:(_ for _ in ()).throw(AssertionError('legacy binding reached'))
    try:v=ns['main']()
    finally:sys.argv=old
    z=v['whole_wall'];known.append({'pid':z['pid'],'birth':z['birth']});save(d/'SUPERVISOR.json',v)
    assert z['status']=='STOP_CONFIRMED' and z['fresh_exact_birth_absent'] and z['elapsed']<20.15
    assert v['state']=='UNKNOWN'
    if block:assert z['direct_wait_returncode']==-signal.SIGKILL and z['elapsed']>=17.9
    else:assert v['canonical_offline_positive'] and z['direct_wait_returncode']==0
    return {'variant_native_effects':0,'actual_generated_main':True,'state':v['state'],'whole_wall':z,
            'bootstrap_completed_before_entry':True,'block_inside_transport_import':block}
case('actual_generated_canonical_positive_private_variant',canonical_variant)
case('actual_generated_canonical_transport_import_flock_20s_wall',lambda:canonical_variant(True))

for k in known:
    try:assert S.birth(k['pid'])!=k['birth']
    except FileNotFoundError:pass
report={'domain':'AUTHOR_PHYSICAL_OFFLINE_SOURCE_ONLY_UNINSTALLED_INDEPENDENT_PENDING',
        'raw':len(rows),'unique':len({r['id'] for r in rows}),'PASS':sum(r['PASS'] for r in rows),
        'FAIL':sum(not r['PASS'] for r in rows),'rows':rows,'known_worker_births':known,
        'all_known_workers_fresh_closed':True,'extra_agents':0,'native_RPC':0,'native_CLI':0,
        'host_RSS':'UNKNOWN','whole_host_admission':False,
        'children':Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()}
save(OUT/'CONTROLS.json',report)
print(json.dumps({k:report[k] for k in ['raw','unique','PASS','FAIL','children']}))
raise SystemExit(0 if not report['FAIL'] else 1)
