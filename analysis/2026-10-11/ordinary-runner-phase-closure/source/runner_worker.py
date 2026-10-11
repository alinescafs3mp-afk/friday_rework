#!/usr/bin/env python3
"""Worker entrypoint for the existing authenticated host source custody.

Standalone CLI has no host capability and fails before effects. Source fixtures
exercise pure contracts separately; they cannot install a runtime adapter.
"""
import importlib.util
import os
from pathlib import Path
import resource
import sys
import threading
import time
import types

PKG = Path(__file__).absolute().parent
retained = globals().get('__gate_loader__')
if retained is not None:
    contract, data = retained.load_dependency('runner_contract')
else:
    path = PKG / 'runner_contract.py'; data = path.read_bytes()
    contract = importlib.util.module_from_spec(importlib.util.spec_from_loader('worker_contract', loader=None))
    contract.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), contract.__dict__)
LOADED_CONTRACT_SHA = contract.digest(data)

def execute_bytes(data, filename):
    """Consume already verified immutable bytes; no runpy/path reopening."""
    module = types.ModuleType('__main__')
    namespace = module.__dict__
    namespace.update({'__file__': filename, '__package__': '', '__spec__': None,
                      '__cached__': None, '__loader__': None, '__builtins__': __builtins__})
    code = compile(data, filename, 'exec')
    old_argv = sys.argv[:]
    old_main = sys.modules.get('__main__')
    sys.modules['__main__'] = module
    if sys.argv:
        sys.argv[0] = filename
    else:
        sys.argv.append(filename)
    try:
        exec(code, namespace)
    except SystemExit as error:
        contract.need(error.code in (None, 0), 'checker_nonzero_exit')
    finally:
        sys.argv[:] = old_argv
        if old_main is None:
            sys.modules.pop('__main__', None)
        else:
            sys.modules['__main__'] = old_main
    return namespace

def run(output, job_ref, admission_sha256, *, custody=None, loader=None):
    out = contract.canonical_path(output)
    job, checker = contract.verify_job(job_ref, out, admission_sha256)
    a = job['admission']
    contract.need(a['implementation']['runner_contract.py']['sha256'] == LOADED_CONTRACT_SHA, 'loaded_worker_contract_changed')
    worker = {'pid': os.getpid(), 'start_ticks': contract.pid_start(os.getpid())}
    loaded_identity = contract.loaded_implementation(loader, a['implementation'], 'worker_before_configure', 'worker', globals(), {'binding_sha256': a['binding_sha256'], 'grant': a['pins']['grant']}, worker)
    contract.need(loaded_identity.decode('utf-8') == a.get('loaded_identity'), 'admitted_loaded_identity_changed')
    # A retained approved launch is verified before changing any limits or FD.
    contract.require_custody(custody, a, 'worker_before_configure', worker, job_ref)
    limits = contract.resources(a['resources']); hard, useful = contract.budget_limits(a['budget'])
    resource.setrlimit(resource.RLIMIT_AS, (limits['worker_address_space_bytes'], limits['worker_address_space_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits['output_bytes'], limits['output_bytes']))
    cpus = contract.cpu_affinity(a.get('approved_affinity'), limits['CPUs']); os.sched_setaffinity(0, cpus)
    contract.require_custody(custody, a, 'worker_before_ready', worker, job_ref)
    # The custody callback is a mutation seam: reobserve actual retained
    # buffers/interpreter/context AFTER it and immediately before READY.
    loaded_identity = contract.loaded_implementation(loader, a['implementation'], 'worker_before_ready', 'worker', globals(), {'binding_sha256': a['binding_sha256'], 'grant': a['pins']['grant']}, worker)
    contract.need(loaded_identity.decode('utf-8') == a['loaded_identity'], 'admitted_loaded_identity_changed')
    contract.save(out, 'READY.json', {'worker': worker, 'job': job_ref, 'affinity': cpus,
                                    'resources': limits, 'runtime_grant': False})
    while not (out / 'BARRIER.json').exists():
        contract.need(time.time() < useful, 'worker_barrier_deadline')
        time.sleep(.01)
    barrier = contract.document(contract.pin(out / 'BARRIER.json'), 'barrier')
    # Typed canonical joins avoid Python bool/int and float/int equality.
    actual = contract.cpu_affinity(sorted(os.sched_getaffinity(0)), 4096)
    approved = contract.cpu_affinity(cpus, limits['CPUs'], actual)
    contract.need(contract.cpu_affinity(barrier.get('approved_affinity'), limits['CPUs'], actual) == approved,
                  'barrier_affinity_mismatch')
    contract.need(contract.canonical(barrier) == contract.canonical({'worker': worker, 'job': job_ref, 'admission_sha256': admission_sha256,
                              'useful_epoch': useful, 'hard_epoch': hard, 'approved_affinity': approved}), 'barrier_identity_or_budget_mismatch')
    # JOB, original checker/auxiliary/implementation/read inputs, private copied
    # checker/auxiliary are reverified AFTER barrier. Execute those exact bytes.
    job, checker = contract.verify_job(job_ref, out, admission_sha256)
    loaded_identity = contract.loaded_implementation(loader, a['implementation'], 'worker_after_barrier', 'worker', globals(), {'binding_sha256': a['binding_sha256'], 'grant': a['pins']['grant']}, worker)
    contract.need(loaded_identity.decode('utf-8') == a['loaded_identity'], 'admitted_loaded_identity_changed')
    contract.require_custody(custody, a, 'worker_after_barrier', worker, job_ref)
    initial_fd = len(list(Path(f'/proc/{os.getpid()}/fd').iterdir()))
    policy = contract.AuditPolicy(out, a['read_scope'])
    # Exact process diagnostic paths, not blanket /proc or read-all admission.
    policy.files.add(f'/proc/{os.getpid()}/task/{os.getpid()}/children')
    policy.roots += (Path(f'/proc/{os.getpid()}/fd'),)
    sys.addaudithook(policy.check)
    completed = False
    execute_bytes(checker, job['checker']['path'])
    completed = True
    children = Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()
    threads = [t.name for t in threading.enumerate()]
    fd_delta = len(list(Path(f'/proc/{os.getpid()}/fd').iterdir())) - initial_fd
    contract.need(not children and threads == ['MainThread'] and fd_delta == 0, 'worker_obligations_unclosed')
    contract.need(time.time() <= useful, 'source_checker_original_useful_deadline')
    # Parent's real host adapter independently captures closure and observes
    # kernel obligations; the checker cannot confer trust by writing this JSON.
    output_bytes = sum(p.stat().st_size for p in out.rglob('*') if p.is_file() and not p.is_symlink())
    contract.need(output_bytes <= limits['output_bytes'], 'aggregate_output_bound')
    loaded_identity = contract.loaded_implementation(loader, a['implementation'], 'worker_before_closure', 'worker', globals(), {'binding_sha256': a['binding_sha256'], 'grant': a['pins']['grant']}, worker)
    contract.need(loaded_identity.decode('utf-8') == a['loaded_identity'], 'admitted_loaded_identity_changed')
    contract.require_custody(custody, a, 'worker_before_closure', worker, job_ref)
    contract.need(sorted(os.sched_getaffinity(0)) == cpus, 'worker_affinity_changed')
    closure = {'schema': 'friday.source-worker-closure.v2', 'worker': worker, 'job': job_ref,
               'approved_affinity': cpus, 'completed': completed, 'children': children, 'threads': threads, 'FD_delta': fd_delta,
               'original_budget': a['budget'], 'resources': limits, 'ended_epoch': time.time(),
               'observed_limits': {'affinity': sorted(os.sched_getaffinity(0)),
                   'address_space_bytes': list(resource.getrlimit(resource.RLIMIT_AS)),
                   'CPU_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
                   'file_size_bytes': list(resource.getrlimit(resource.RLIMIT_FSIZE))},
               'output_bytes': output_bytes, 'runtime_grant': False, 'independent_acceptance': False}
    # Under the retained host kernel fence; diagnostic rejects symlink/traversal.
    path = policy.write(out / 'WORKER-CLOSURE.json')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags, 0o600)
    try:
        payload = contract.canonical(closure) + b'\n'
        view = memoryview(payload)
        while view:
            count = os.write(fd, view); contract.need(count > 0, 'short_closure_write'); view = view[count:]
    finally:
        os.close(fd)
    return closure

def main():
    # No JSON/PID, CLI flag, environment variable or stand-alone invocation can
    # supply the authenticated existing-host custody capability.
    print('{"status":"NOT_RUN","cause":"existing_host_custody_adapter_unavailable","runtime_grant":false}')
    return 2

if __name__ == '__main__':
    raise SystemExit(main())
