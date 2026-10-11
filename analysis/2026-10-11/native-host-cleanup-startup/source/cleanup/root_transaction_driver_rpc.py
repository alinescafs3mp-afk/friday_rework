#!/usr/bin/env python3
"""Inactive root-only transaction/capture adapter. Never infer success from filenames.
Author tests call publish_witness on owned fixtures only; no subprocess execution.
"""
raise RuntimeError('INACTIVE_SOURCE_ONLY_DRIVER_NO_STARTUP_AUTHORITY')
import argparse,json,os,resource,stat,subprocess,sys,time,signal,uuid
from types import ModuleType
from pathlib import Path
from types import SimpleNamespace
SOURCE=Path('/PORTABLE_UNBOUND/PATH_0001')
m=None
def source_boundary():
    b=globals().get('__verified_source_boundary__')
    if b is None: raise RuntimeError('HOST_VERIFIED_BOUNDARY_REQUIRED_BEFORE_INSTALLER_IMPORT')
    b.require_host_custody()
    return b
def bind_installer(program_sha):
    global m
    b=source_boundary()
    with b.VerifiedBytes(SOURCE,program_sha,mode=0o500) as source:
        m=ModuleType('reviewed_native_rpc_f1_f4');m.__file__=str(SOURCE)
        b.execute_verified(source,m.__dict__)
    return m

def exact_forward_custody(attempt, returned, return_identity, dependencies, identities, held, targets):
    m.verify_pins(dependencies,identities)
    _, actual=m.read_file(return_identity['path'],return_identity['sha256'])
    if (not m.json_exact(actual, return_identity)):raise m.Refusal('CAPTURED_FORWARD_RETURN_CUSTODY_DRIFT')
    if ((not m.json_exact(returned.get('state'), 'COMMITTED_LOCAL_FILES_ONLY')) or returned.get('durable_commit_completed') is not True
            or any(k in returned for k in ['cause','cleanup_errors','failure_receipt_error'])):
        raise m.Refusal('ACTUAL_SUCCESSFUL_FORWARD_RETURN_REQUIRED')
    attempt_id=m.stable_directory_identity(attempt)
    if (not m.json_exact(attempt_id[2], os.getuid())) or (not m.json_exact(attempt_id[4], 0o700)):raise m.Refusal('EXACT_FORWARD_JOURNAL_DIRECTORY_REQUIRED')
    commit_ref=returned['commit_record_ref'];commit=Path(commit_ref['path'])
    raw,observed=m.read_file(commit,commit_ref['sha256']);committed=m.load_json(raw)
    if ((not m.json_exact(observed, returned['commit_record_identity'])) or committed.get('durable_commit_completed') is not False
            or (not m.json_exact({k:v for k,v in returned.items() if k not in ['durable_commit_completed','commit_record_ref','commit_record_identity']}, {k:v for k,v in committed.items() if k!='durable_commit_completed'}))):
        raise m.Refusal('ORIGINAL_COMMITTED_RETURN_BINDING_REQUIRED')
    records=sorted(attempt.glob('*.json'));originals=[*committed['prior_journal_custody'],returned['commit_record_identity']]
    if (not m.json_exact([str(p) for p in records], [i['path'] for i in originals])) or (not m.json_exact(records[-1], commit)) or any('stopped' in p.name for p in records):
        raise m.Refusal('EXACT_COMPLETE_FORWARD_HISTORY_REQUIRED')
    for i in originals:
        _,v=m.read_file(i['path'],i['sha256'])
        if (not m.json_exact(v, i)):raise m.Refusal('WITNESS_ORIGINAL_JOURNAL_CUSTODY_DRIFT')
    if (not m.json_exact([i['target'] for i in committed['images']], [str(p) for p in targets])):raise m.Refusal('WITNESS_EXACT_TARGET_SET_REQUIRED')
    for n,i in enumerate(committed['images']):
        backup=i['backup_identity']
        if (not m.json_exact(backup['path'], str(attempt/f'{n:02d}-before.bin'))) or (not m.json_exact(backup['path'], i['backup'])) or (not m.json_exact(backup['sha256'], i['before']['sha256'])) or (not m.json_exact(backup['mode'], 0o600)):
            raise m.Refusal('WITNESS_ORIGINAL_BACKUP_BINDING_REQUIRED')
        _,v=m.read_file(backup['path'],backup['sha256'])
        if (not m.json_exact(v, backup)):raise m.Refusal('WITNESS_ORIGINAL_BACKUP_CUSTODY_DRIFT')
        _,v=m.read_file(i['target'],i['after_sha'])
        if (not m.json_exact(v, i['installed'])):raise m.Refusal('WITNESS_INSTALLED_TARGET_CUSTODY_DRIFT')
    for path,fd,identity in held:
        _,v=m.read_file(path)
        if (not m.json_exact(v['signature'], identity['signature'])) or (not m.json_exact(m.signature(os.fstat(fd)), identity['signature'])):
            raise m.Refusal('WITNESS_HELD_LOCK_PATH_DRIFT')
    return committed,originals


def publish_witness(root, returned_path, returned_sha, observed_exit_code, program_sha, proof_sha,
                    lock_paths, dependencies, dependency_identities, targets, invariant, ops=None):
    """Root authority requires actually observed exit0; fixture callers are not authority."""
    if (not m.json_exact(observed_exit_code, 0)):raise m.Refusal('OBSERVED_SUCCESSFUL_FORWARD_EXIT_REQUIRED')
    ops=ops or m.Ops();attempt=root/'INSTALLATION-ATTEMPT';root_id=m.stable_directory_identity(root)
    raw,return_identity=m.read_file(returned_path,returned_sha);returned=m.load_json(raw)
    with m.locks(lock_paths) as held, m.directory(root) as parent:
        def guard():
            if (not m.json_exact(m.stable_directory_identity(root), root_id)):raise m.Refusal('ROOT_WITNESS_DIRECTORY_DRIFT')
            invariant()
            return exact_forward_custody(attempt,returned,return_identity,dependencies,dependency_identities,held,targets)
        committed,records=guard()
        # Make the captured successful returned result durable with custody on both sides.
        with m.directory(Path(returned_path).parent) as captured_parent:
            fd=os.open(Path(returned_path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=captured_parent)
            try:guard();ops.fsync(fd,'root-return:file');guard()
            finally:os.close(fd)
            ops.fsync(captured_parent,'root-return:directory');guard()
        witness={'schema':'friday.native-peer-rpc-forward-confirmed.v1','status':'FORWARD_COMMIT_CONFIRMED',
                 'owner_thread':m.OWNER,'operation':'install','operation_id':returned['operation_id'],
                 'program_sha256':program_sha,'forward_exit_code':observed_exit_code,
                 'commit_ref':returned['commit_record_ref'],'installed_proof_sha256':proof_sha,
                 'returned_result_ref':{'path':str(returned_path),'sha256':returned_sha},
                 'journal_records':[{'path':r['path'],'sha256':r['sha256']} for r in records]}
        class Guarded(m.Ops):
            def fsync(self,fd,boundary):guard();ops.fsync(fd,boundary);guard()
        original=m.exclusive_file(parent,'FORWARD-CONFIRMATION.json',(json.dumps(witness,sort_keys=True)+'\n').encode(),0o600,Guarded(),'root-witness')
        guard()
        args=SimpleNamespace(forward_confirmation_file=Path(original['path']),forward_confirmation_sha=original['sha256'],expected_program_sha=program_sha,expected_commit_sha=returned['commit_record_ref']['sha256'],proof_sha=proof_sha)
        m.confirmed_forward(args,attempt,Path(returned['commit_record_ref']['path']),committed)
        return {'state':'FORWARD_WITNESS_DURABLE_RETURNED','forward_exit_code':0,'witness_ref':{'path':original['path'],'sha256':original['sha256']},'commit_ref':returned['commit_record_ref'],'native_delivery':'NOT_RUN'}


def bounded_run_once(command, root, stdout, stderr, program_sha):
    """No inherited environment/path source read. Host owns exact startup + wall."""
    b=source_boundary(); host=b.require_host_custody()
    helper=Path(__file__).parent/'gated_installer.py'
    token=uuid.uuid4().hex; child=None; identity=None; launch_custody=None
    with b.SecureDirectory(root,host.reserved_root_identity) as parent, \
         b.VerifiedBytes(helper,host.gated_helper_sha256,mode=0o500) as gate, \
         b.VerifiedBytes(SOURCE,program_sha,mode=0o500) as installer:
        try:
            # Existing host must start the pinned interpreter from verified FDs,
            # with explicit environment/import graph and a pre-effect hold.
            child=host.launch_verified_source_held(gate,installer,command,root,token,stdout,stderr)
            launch_custody=b.LaunchCustody(child)
            identity=host.validate_actual_ready(child,token,gate.identity,installer.identity,parent.identity)
            launch_custody.bind_ready(identity)
            host.verify_aggregate_hard_resources(2,1024**3)
            reserved={'schema':'friday.native-peer-rpc.exact-prebarrier-child.v2',**identity,
                      'program_sha256':program_sha,'helper_sha256':gate.sha256,'token':token,
                      'root_identity':parent.identity,'ready':True,
                      'aggregate_AS_limit_bytes':1024**3,'aggregate_affinity':identity['affinity'],
                      'wall_deadline_monotonic':host.original_useful_deadline_monotonic}
            b.validate_release(reserved,reserved,identity,token,program_sha,gate.sha256,
                               parent.identity,host.original_useful_deadline_monotonic)
            m.exclusive_file(parent.fd,'LAUNCH-RESERVATION.json',(json.dumps(reserved,sort_keys=True,allow_nan=False)+'\n').encode(),0o600,m.Ops(),'launch-reservation')
            host.verify_ready_and_resources_before_go(identity,reserved)
            gate.verify(); installer.verify(); parent.verify()
            m.exclusive_file(parent.fd,'LAUNCH-RELEASE.json',(json.dumps(reserved,sort_keys=True,allow_nan=False)+'\n').encode(),0o600,m.Ops(),'launch-release')
            host.release_exact_held_child(child,identity)
            code=host.wait_exact_with_original_wall(child,identity)
            closure=host.fresh_exact_stop_reap_and_absence(child,identity)
            if not b.exact_closure_complete(closure): raise m.Refusal('STOP_UNCONFIRMED_EXACT_DESCENDANT_CLOSURE')
            m.exclusive_file(parent.fd,'LAUNCH-REAP.json',(json.dumps({'identity':identity,'actual_returncode':code,'wait_returned':True,'closure':closure},sort_keys=True)+'\n').encode(),0o600,m.Ops(),'launch-reap')
            return subprocess.CompletedProcess(command,code)
        except BaseException as primary:
            if child is not None:
                b.cleanup_returned_child(host, child, launch_custody, primary=primary)
            raise
        finally:
            if launch_custody is not None:launch_custody.close()

def main():
    raise RuntimeError("INACTIVE_SOURCE_ONLY_DRIVER_REQUIRES_FRESH_GATED_LAUNCH_REVIEW")
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected-driver-sha',required=True);p.add_argument('--expected-program-sha',required=True);p.add_argument('--attempt-root',type=Path,required=True);p.add_argument('--expected-attempt-root-identity',required=True);p.add_argument('--proof-file',type=Path,required=True);p.add_argument('--proof-sha',required=True);p.add_argument('--acceptance-file',type=Path,required=True);p.add_argument('--acceptance-sha',required=True);args=p.parse_args()
    bind_installer(args.expected_program_sha)
    os.umask(0o077);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    if (not m.json_exact(os.environ.get('CODEX_THREAD_ID'), m.OWNER)):raise m.Refusal('EXACT_ROOT_ASTRA_CALLER_REQUIRED')
    m.read_file(Path(__file__),args.expected_driver_sha);m.verify_reviewed_program_location();m.read_file(SOURCE,args.expected_program_sha)
    root,root_identity=m.approved_attempt_root(args);audit,pins,lock_paths=m.real_inputs();dependencies=m.accepted_proof(args,audit,pins);dependencies.append({'path':str(SOURCE),'sha256':args.expected_program_sha});dependencies.append({'path':str(Path(__file__)),'sha256':args.expected_driver_sha});identities=m.verify_pins(dependencies)
    def invariant():
        if (not m.json_exact(m.stable_directory_identity(root), root_identity)):raise m.Refusal('ROOT_ATTEMPT_IDENTITY_DRIFT')
        m.verify_reviewed_program_location();m.verify_release_layout(audit)
    invariant()
    # No shell, no native client, no child of the filesystem installer. Run once only.
    command=[sys.executable,'-B',str(SOURCE),'install','--expected-program-sha',args.expected_program_sha,'--attempt-root',str(root),'--expected-attempt-root-identity',args.expected_attempt_root_identity,'--proof-file',str(args.proof_file),'--proof-sha',args.proof_sha,'--acceptance-file',str(args.acceptance_file),'--acceptance-sha',args.acceptance_sha]
    with m.directory(root) as parent:
        output=os.open('FORWARD-RETURN.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        stderr=None
        try:
            stderr=os.open('FORWARD-STDERR.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
            execution=bounded_run_once(command,root,output,stderr,args.expected_program_sha)
            # Retain actual stdout bytes/identity before the first root fsync.
            raw,identity=m.read_file(root/'FORWARD-RETURN.json')
            os.fsync(output);os.fsync(stderr);os.fsync(parent)
            _,after_sync=m.read_file(root/'FORWARD-RETURN.json',identity['sha256'])
            if (not m.json_exact(after_sync, identity)):raise m.Refusal('ACTUAL_CAPTURE_CHANGED_DURING_FSYNC')
        finally:
            os.close(output)
            if stderr is not None:os.close(stderr)
        exit_record={'schema':'friday.root-observed-forward-exit.v1','owner_thread':m.OWNER,'forward_exit_code':execution.returncode,'program_sha256':args.expected_program_sha,'captured_return_ref':{'path':identity['path'],'sha256':identity['sha256']}}
        exit_identity=m.exclusive_file(parent,'FORWARD-EXIT.json',(json.dumps(exit_record,sort_keys=True)+'\n').encode(),0o600,m.Ops(),'root-exit')
    if (not m.json_exact(execution.returncode, 0)):
        print(json.dumps({'state':'STOP_UNCERTAIN_RECONCILE_REQUIRED','actual_forward_exit_code':execution.returncode,'automatic_rollback':False,'return_ref':exit_record['captured_return_ref']}));return 2
    # Retain original root durable exit/return identities across ALL witness fsyncs.
    for original in [identity,exit_identity]:
        dependencies.append(original)
        identities.append(m.pin_identity(original))
    witness=publish_witness(root,root/'FORWARD-RETURN.json',identity['sha256'],execution.returncode,args.expected_program_sha,args.proof_sha,lock_paths,dependencies,identities,[m.TARGET,m.PROOF_TARGET],invariant)
    print(json.dumps(witness,sort_keys=True));return 0

if __name__ == '__main__':
    try:raise SystemExit(main())
    except BaseException as e:
        if isinstance(e,SystemExit):raise
        print(json.dumps({'state':'STOP_UNCERTAIN_RECONCILE_REQUIRED','cause':{'type':type(e).__name__,'message':str(e)},'automatic_rollback':False,'native_delivery':'NOT_RUN'}),file=sys.stderr);raise SystemExit(2)
