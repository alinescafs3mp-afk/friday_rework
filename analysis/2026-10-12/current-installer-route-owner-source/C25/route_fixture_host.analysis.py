"""Finite variant of Root's admitted fixture_host-v5 stock outside wait adapter.
Private test only. Not a service/installed issuer. Exact Root admission required.
"""
import os,sys,time,json,hashlib,signal,subprocess,ctypes,resource
from pathlib import Path
OUT=Path(__file__).absolute().parent
AS=268435456
def identity(pid):
    s=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'birth':s[19],'ppid':int(s[1]),'pgid':int(s[2]),'sid':int(s[3])}
def pin(path):
    raw=Path(path).read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def put(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def absent(row):
    try:return identity(row['pid'])['birth']!=row['birth']
    except FileNotFoundError:return True
def main():
    assert resource.getrlimit(resource.RLIMIT_AS)==(AS,AS)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(60,60)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(67108864,67108864)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    assert sorted(os.sched_getaffinity(0))==[0,1]
    libc=ctypes.CDLL(None,use_errno=True);assert libc.prctl(36,1,0,0,0)==0
    clock=json.loads((OUT/'CLOCK.json').read_bytes());host=identity(os.getpid());outer=identity(os.getppid())
    assert Path('/proc/'+str(outer['pid'])+'/comm').read_text().strip()=='timeout'
    assert host['pgid']==outer['pgid']
    assert time.monotonic()<clock['started_at_monotonic']+1020-20
    (OUT/'execution').mkdir(mode=0o700)
    put(OUT/'HOST-BIRTH.json',{'host':host,'outer':outer,'actual_host_limits':Path('/proc/self/limits').read_text(),
        'outer_actual_limits':Path('/proc/'+str(outer['pid'])+'/limits').read_text(),
        'affinity':sorted(os.sched_getaffinity(0)),'outer_stock_wall_seconds':120,
        'Source_caller_worker_hard_AS_sum':2*AS,'stock_host_guard_additional_hard_AS_sum':2*AS})
    # AST reads case names; never load control Source in the stock host.
    import ast
    raw=(OUT/'Controls/route_controls.py').read_bytes();tree=ast.parse(raw)
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='CASES' for x in n.targets))
    cases=ast.literal_eval(node.value);results=[]
    for case in cases:
        assert time.monotonic()<clock['started_at_monotonic']+1020-10
        rec=OUT/'observations'/case;rec.mkdir(parents=True,mode=0o700)
        cfg={'case':case,'record':str(rec),'root':str(OUT/'execution'/case),'host':host,'outer':outer,
             'host_program':pin(OUT/'fixture_host.py'),'caller':pin(OUT/'fixture_caller.py'),
             'source':pin(OUT/'Source/install_result_rpc.py'),'controls':pin(OUT/'Controls/route_controls.py'),
             'clock':pin(OUT/'CLOCK.json'),'deadline_monotonic':min(time.monotonic()+4,clock['started_at_monotonic']+1020-3)}
        put(rec/'CONFIG.json',cfg)
        with open(rec/'stdout.log','xb') as stdout,open(rec/'stderr.log','xb') as stderr:
            proc=subprocess.Popen([sys.executable,'-B',str(OUT/'fixture_caller.py'),str(rec/'CONFIG.json')],
                stdout=stdout,stderr=stderr,close_fds=True,start_new_session=False)
            caller=identity(proc.pid);put(rec/'HOST-CALLER-BIRTH.json',caller)
            timed_out=False
            try:code=proc.wait(timeout=max(0,cfg['deadline_monotonic']-time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out=True;assert identity(proc.pid)['birth']==caller['birth']
                fd=os.pidfd_open(proc.pid);signal.pidfd_send_signal(fd,signal.SIGKILL);os.close(fd)
                code=proc.wait(timeout=2)
        (rec/'stdout.log').chmod(0o400);(rec/'stderr.log').chmod(0o400)
        adopted=[];until=min(time.monotonic()+3,clock['started_at_monotonic']+1200)
        while True:
            try:pid,status=os.waitpid(-1,os.WNOHANG)
            except ChildProcessError:break
            if pid:adopted.append({'pid':pid,'returncode':os.waitstatus_to_exitcode(status)});continue
            if time.monotonic()>=until:raise RuntimeError('STOP_UNCONFIRMED fixture adopted child')
            for value in Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().split():
                row=identity(int(value));assert row['pgid']==caller['pgid']
                fd=os.pidfd_open(row['pid']);signal.pidfd_send_signal(fd,signal.SIGKILL);os.close(fd)
            import select
            select.select([],[],[],0.01)
        known=[caller]
        if (rec/'WORKER-BIRTH.json').exists():known.append(json.loads((rec/'WORKER-BIRTH.json').read_bytes())['worker'])
        closure=[dict(x,fresh_absent=absent(x)) for x in known]
        assert all(x['fresh_absent'] for x in closure)
        assert not Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
        expected=code==0 and not timed_out and (rec/'CALLER-DIRECT-RETURN.json').exists()
        row={'case':case,'returncode':code,'timed_out':timed_out,'expected_observation_confirmed':expected,
             'outside_directwait':True,'known_fresh_closure':closure,'adopted_directwait':adopted}
        put(rec/'OUTSIDE-CLOSURE.json',row);results.append(row)
        if not expected:break
    put(OUT/'ROUTE-SUMMARY.json',{'cases':results,'expected_count':len(cases),'all_requested':len(results)==len(cases),
         'confirmed':sum(x['expected_observation_confirmed'] for x in results),'author_only':True,
         'Source_current_runtime_admission':False,'host_exit':'Root fresh absence after direct tool return required'})
    print(json.dumps({'run':len(results),'confirmed':sum(x['expected_observation_confirmed'] for x in results)}))
    raise SystemExit(0 if len(results)==len(cases) and all(x['expected_observation_confirmed'] for x in results) else 1)
if __name__=='__main__':main()
