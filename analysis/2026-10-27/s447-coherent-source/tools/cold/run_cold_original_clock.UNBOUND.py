# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Root-owned one-shot carrier. RUN_REQUEST is deliberately unbound.

Uses the existing accepted remaining-original-clock GNU carrier mechanism.
Root binds only a protected copy's RUN_REQUEST to its real final request ref.
No native/product module is imported by the carrier itself.
"""
from pathlib import Path
import hashlib,json,math,os,stat,sys,time

RUN_REQUEST = None
ENTRY = {'path':'<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/cold/cold_root_entry.py','sha256':'PRIVATE_REF_862a295b2594c785'}
CARRIER = 'FRW_S447_COLD_ORIGINAL_CARRIER'


def need(value, reason):
    if value is not True:raise RuntimeError(reason)


def read(ref):
    need(type(ref) is dict and set(ref)=={'path','sha256'},'exact_reference_required')
    path=Path(ref['path']);need(path.is_absolute() and path.resolve()==path,'canonical_reference_required')
    for parent in path.parents:
        info=parent.lstat();need(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.getuid())
            and not info.st_mode&0o022,'protected_parent_required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
            and before.st_gid==os.getegid()==12345 and before.st_nlink==1
            and not before.st_mode&0o077 and before.st_size<=2*1024**2,
            'private_regular_reference_required')
        raw=os.pread(fd,2*1024**2+1,0);after=os.fstat(fd);named=path.lstat()
        fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(len(raw)<=2*1024**2 and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in fields)
            and hashlib.sha256(raw).hexdigest()==ref['sha256'],'reference_changed')
        return raw
    finally:os.close(fd)


def document(ref):
    def unique(rows):
        result={}
        for key,value in rows:
            need(key not in result,'duplicate_key');result[key]=value
        return result
    return json.loads(read(ref),object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_json')))


def main():
    need(type(RUN_REQUEST) is dict and set(RUN_REQUEST)=={'path','sha256'},'unbound_Root_request')
    request=document(RUN_REQUEST);clock=document(request['original_clock'])
    need(request['schema']=='friday.a0-closed-s443-successor-root-once.v1'
        and request['operation_directory']=='<PRIVATE_CACHE>/PRIVATE_REF_79d2ca6c48dd51a8'
        and sys.flags.isolated and sys.dont_write_bytecode and sys.executable==request['python'],
        'fresh_lexical_native_runner_required')
    need(set(clock)=={'schema','boot_id','started_monotonic','deadline_monotonic','budget_seconds','reserve_seconds'}
        and clock['schema']=='friday.a0-closed-s443-successor-clock.v1'
        and type(clock['budget_seconds']) is int and clock['budget_seconds']==600
        and type(clock['reserve_seconds']) is int and clock['reserve_seconds']==30
        and all(type(clock[k]) in (int,float) and math.isfinite(clock[k])
            for k in ('started_monotonic','deadline_monotonic'))
        and clock['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        and 0<clock['started_monotonic']<=time.monotonic()<clock['deadline_monotonic']-30
        and clock['deadline_monotonic']==clock['started_monotonic']+600,
        'same_finite_original600_required')
    raw=read(ENTRY)
    # Root launches a protected bound copy with this dedicated marker absent.
    # Reexec retains the exact bound request/clock/grant and same lexical Python.
    if os.environ.get(CARRIER)!='1':
        # Two-second forced-stop grace is inside the same original deadline.
        left=clock['deadline_monotonic']-time.monotonic()-2.0
        need(28<left<=598,'original_clock_exhausted')
        env=dict(os.environ);env[CARRIER]='1'
        argv=['/usr/bin/gnutimeout','--signal=TERM','--kill-after=2s',format(left,'.9f')+'s',
            sys.executable,'-I','-B',str(Path(__file__).resolve())]
        os.execve(argv[0],argv,env)
    namespace={'__file__':ENTRY['path'],'__name__':'_Root_S447_closed_S443_cold_once'}
    exec(compile(raw,ENTRY['path'],'exec'),namespace)
    need(namespace['ROOT_RUN'] is None,'unbound_entry_required')
    namespace['ROOT_RUN']={'request':RUN_REQUEST}
    return namespace['main']()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(2)
