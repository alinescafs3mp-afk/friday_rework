"""Portable SOURCE admission launcher:384MiB before fork,128 after child birth.
The caller must authorize a finite SOURCE run and supply its original clock.
Host creation before this entry, TUI and unknown descendants are not admitted.
No hard cap is raised. Smaller inherited caps fail closed.
"""
import os,sys,pathlib,resource,json,time,argparse,hashlib
# Bound this entry before imports of owned SOURCE or any child creation.
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,)*2)
resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
from bounded_transport import save,run_owned,birth,MIB,validate_clock
from composition import verify,trusted_path
p=argparse.ArgumentParser()
for k in ('repo','base','end','delta-base','clock','output','source-manifest-sha256'):p.add_argument('--'+k,required=True)
a=p.parse_args();S=trusted_path(pathlib.Path(__file__).parent);W=trusted_path(a.output,missing_leaf=True);repo=trusted_path(a.repo)
assert not W.exists() and W.parent.is_dir();assert not W.is_relative_to(repo)
C=validate_clock(json.loads(trusted_path(a.clock).read_text()));assert time.monotonic()<C['useful_monotonic']<C['final_monotonic'];assert C['final_monotonic']-C['useful_monotonic']>=120
os.umask(0o077);W.mkdir(mode=0o700)
cpus=sorted(os.sched_getaffinity(0))[:2];assert len(cpus)==2;os.sched_setaffinity(0,cpus)
C.update(launcher={'pid':os.getpid(),'birth':birth(os.getpid()),'hard_AS_bytes':128*MIB},shared_cpus=cpus)
save(W,'EXECUTION-CLOCK.json',C)
save(W,'LAUNCHER-SOURCE-ENTRY.json',{'pid':os.getpid(),'birth':birth(os.getpid()),'entry_limits':pathlib.Path('/proc/self/limits').read_text(),'actual_entry_AS':list(resource.getrlimit(resource.RLIMIT_AS)),'source_entry_before_first_fork':True,'host_process_birth_HARD':'UNOBSERVED_NOT_ZERO; caller admission precedes this SOURCE entry','SOURCE_composition':verify(S,a.source_manifest_sha256)})
cmd=[sys.executable,'-B',str(S/'worker.py'),'--output',str(W),'--repo',str(repo),'--base',a.base,'--end',a.end,'--delta-base',a.delta_base,'--source-manifest-sha256',a.source_manifest_sha256]
out,err,row=run_owned(C,cmd,W,'WORKER',target=384*MIB,cpu=300,launcher=True)
save(W,'LAUNCHER-DIRECT-RETURN.json',{'launcher':C['launcher'],'worker':row,'stdout_preview':out[-5000:].decode(errors='replace'),'stderr_preview':err[-4000:].decode(errors='replace'),'within_original_useful':time.monotonic()<C['useful_monotonic'],'original_clock_unchanged':True})
print(out.decode(errors='replace'));print(err.decode(errors='replace'),file=sys.stderr);sys.exit(row['returncode'])
