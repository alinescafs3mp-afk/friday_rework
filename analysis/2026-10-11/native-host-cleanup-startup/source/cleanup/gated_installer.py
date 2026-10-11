#!/usr/bin/python3
"""INACTIVE future gated source; no launcher authority or actual effects."""
raise RuntimeError('INACTIVE_SOURCE_ONLY_HOST_CUSTODY_UNBOUND_NO_LAUNCH')
import os, resource, time, sys
from pathlib import Path
def source_boundary():
    b=globals().get('__verified_source_boundary__')
    if b is None: raise RuntimeError('HOST_VERIFIED_BOUNDARY_REQUIRED_BEFORE_IMPORT_OR_EFFECT')
    b.require_host_custody()
    return b
def own_identity():
    raw=Path('/proc/self/stat').read_text();a=raw[raw.rfind(')')+2:].split()
    return {'pid':os.getpid(),'ppid':int(a[1]),'start_token':a[19],
            'affinity':sorted(os.sched_getaffinity(0))}
def main():
    b=source_boundary(); host=b.require_host_custody()
    if len(sys.argv)<6: raise RuntimeError('EXACT_GATED_INPUT_REQUIRED')
    root,token,helper_sha,program_sha=Path(sys.argv[1]),sys.argv[2],sys.argv[3],sys.argv[4]
    program=Path(sys.argv[5]); identity=own_identity()
    # Custody predates READY and every release; self/program descriptors remain
    # held across the entire boundary. Root identity comes from the held host.
    with b.SecureDirectory(root,host.reserved_root_identity) as parent, \
         b.VerifiedBytes(Path(__file__),helper_sha,mode=0o500) as own, \
         b.VerifiedBytes(program,program_sha,mode=0o500) as source:
        host.record_ready_before_go(identity,own.identity,source.identity,
                                    parent.identity,resource.getrlimit(resource.RLIMIT_AS))
        while True:
            host.verify_original_wall_before_go(); parent.verify(); own.verify(); source.verify()
            try:
                with b.VerifiedBytes(root/'LAUNCH-RESERVATION.json',max_bytes=16384,mode=0o600,parent_identity=parent.identity) as reserve, \
                     b.VerifiedBytes(root/'LAUNCH-RELEASE.json',max_bytes=16384,mode=0o600,parent_identity=parent.identity) as release:
                    r=b.strict_json(reserve.raw); go=b.strict_json(release.raw)
                    b.validate_release(r,go,identity,token,program_sha,helper_sha,parent.identity,
                                       host.original_useful_deadline_monotonic)
                    host.verify_ready_and_resources_before_go(identity,go)
                    reserve.verify(); release.verify(); parent.verify(); own.verify(); source.verify()
                    break
            except FileNotFoundError: time.sleep(0.005)
        sys.argv=[str(program),*sys.argv[6:]]
        return b.execute_verified(source,{'__name__':'__main__','__file__':str(program),
                                         '__verified_source_boundary__':b})
if __name__=='__main__': main()
