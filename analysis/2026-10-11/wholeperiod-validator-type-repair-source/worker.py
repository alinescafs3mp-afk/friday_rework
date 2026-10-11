"""One384MiB SOURCE worker, serial stages; only one inert reader at a time."""
import os,sys,pathlib,json,hashlib,time,runpy,argparse,traceback
if sys.flags.optimize:raise SystemExit('REFUSED: SOURCE requires Python assertions enabled')
from bounded_transport import save,run_owned,proof,birth,MIB
from composition import verify
p=argparse.ArgumentParser()
for k in ('output','repo','base','end','delta-base','source-manifest-sha256'):p.add_argument('--'+k,required=True)
a=p.parse_args();W=pathlib.Path(a.output);S=pathlib.Path(__file__).parent;C=json.loads((W/'EXECUTION-CLOCK.json').read_text())

def stage(name,file,args):
 assert time.monotonic()<C['useful_monotonic'];sys.argv=[str(S/file),*args]
 save(W,name+'-STAGE-PREGO.json',{'worker_pid':os.getpid(),'birth':birth(os.getpid()),'stage':name,'source_sha256':hashlib.sha256((S/file).read_bytes()).hexdigest(),'actual_HARD':proof(C),'actual_limits':pathlib.Path('/proc/self/limits').read_text()})
 begin=time.monotonic()
 try:runpy.run_path(str(S/file),run_name='__main__')
 except SystemExit as e:assert e.code in (None,0),(name,e.code)
 save(W,name+'-STAGE-RETURN.json',{'stage':name,'elapsed_seconds':time.monotonic()-begin,'remaining_direct_children':pathlib.Path(f'/proc/self/task/{os.getpid()}/children').read_text().strip()})
 print('STAGE',name,'COMPLETE',flush=True)
try:
 save(W,'COMPOSITION-BEFORE.json',verify(S,a.source_manifest_sha256))
 common=[str(W),a.repo,a.base,a.end]
 stage('short','controls.py',['short',*common])
 stage('producer','producer.py',['--run-dir',str(W),'--repo',a.repo,'--base',a.base,'--end',a.end,'--delta-base',a.delta_base,'--builder',str(S/'daily_finalizer.py.inert.txt'),'--clock',str(W/'EXECUTION-CLOCK.json')])
 stage('physical-controls','controls.py',['negative',*common])
 out,err,row=run_owned(C,[sys.executable,'-B','-O',str(S/'verify_fullperiod.py'),'--help'],W,'OPTIMIZE')
 assert row['returncode']==1 and b'requires Python assertions enabled' in err
 save(W,'OPTIMIZE-CONTROL.json',{'PASS':1,'new_source_optimized_execution_refused':True,'no_git_execution':True,'stderr':err.decode()})
 args=['--repo',a.repo,'--reports',str(W/'reports'),'--public',str(W/'PUBLIC'),'--base',a.base,'--end',a.end,'--builder',str(S/'daily_finalizer.py.inert.txt'),'--clock',str(W/'EXECUTION-CLOCK.json'),'--receipts',str(W/'full-gate'),'--report-manifest-sha256',hashlib.sha256((W/'reports/MANIFEST.json').read_bytes()).hexdigest(),'--public-manifest-sha256',hashlib.sha256((W/'PUBLIC/MANIFEST.json').read_bytes()).hexdigest()]
 stage('full-gate','verify_fullperiod.py',args)
 save(W,'COMPOSITION-AFTER.json',verify(S,a.source_manifest_sha256))
 save(W,'PIPELINE-COMPLETE.json',{'source_full_gate_pass':True,'author_only_independent_PENDING':True,'named_fork_HARD_max_bytes':896*MIB,'named_steady_HARD_max_bytes':704*MIB,'actual_birth_and_GO_proofs':True,'remaining_direct_children':pathlib.Path(f'/proc/self/task/{os.getpid()}/children').read_text().strip(),'within_original_useful':time.monotonic()<C['useful_monotonic']})
except BaseException as e:
 save(W,'PIPELINE-FAILURE.json',{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc(),'original_clock_unchanged':True});raise
