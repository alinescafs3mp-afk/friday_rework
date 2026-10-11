"""One finite NO-FORK inert helper; execute exact source, never strip a guard."""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import sys
import time
import types

ROOT = Path(__file__).resolve().parent
START = time.monotonic()
END = min(float(sys.argv[1]), START + 120)
os.sched_setaffinity(0, {0, 1})
resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
signal.alarm(max(1, int(END - START)))
source = (ROOT / 'finite_outside_unit.py').read_bytes()
token = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
ready = {'pid': os.getpid(), 'start_token': token, 'affinity': sorted(os.sched_getaffinity(0)),
         'RLIMIT_AS': list(resource.getrlimit(resource.RLIMIT_AS)),
         'RLIMIT_CPU': list(resource.getrlimit(resource.RLIMIT_CPU)),
         'RLIMIT_NOFILE': list(resource.getrlimit(resource.RLIMIT_NOFILE)),
         'source_sha256': hashlib.sha256(source).hexdigest(), 'descendants': [],
         'single_process_no_fork': True, 'original_end_monotonic': END}
print(json.dumps(ready, sort_keys=True), flush=True)
need_go = sys.stdin.readline(128).strip()
assert need_go == 'GO:' + token and time.monotonic() < END
module = types.ModuleType('finite_exact_inert')
sys.modules[module.__name__] = module
exec(compile(source, str(ROOT / 'finite_outside_unit.py'), 'exec', dont_inherit=True), module.__dict__)
results = []

def check(name, predicate):
    assert predicate, name
    results.append({'name': name, 'passed': True})

def reject(name, function):
    try:
        function()
    except (module.Unbound, ValueError, TypeError, KeyError):
        check(name, True)
    else:
        check(name, False)

check('source_compiles_whole_unchanged', hashlib.sha256(source).hexdigest() == ready['source_sha256'])
check('whole_module_source_gate_is_unconditional', module.SOURCE_ONLY is True)
reject('launch_gate_precedes_effects', lambda: module.FiniteOutsideOwner.launch_held(object()))
reject('release_gate_precedes_effects', lambda: module.FiniteOutsideOwner.release_once(object(), {}))
reject('controller_gate_precedes_effects', lambda: module.controller_main('', '', 0, 0))
reject('worker_gate_precedes_effects', lambda: module.WorkerHeldChannel.from_bootstrap_arguments(0, '', 0, 0, 0))
reject('wait_gate_precedes_effects', lambda: module.FiniteOutsideOwner.wait_exit_and_close(object()))
reject('native_stop_gate_precedes_effects', lambda: module.FiniteOutsideOwner._stop_unit(object()))
check('owner_exact_target_rejected', module.is_within('/a/b.service', '/a/b.service'))
check('owner_nonmain_descendant_rejected', module.is_within('/a/b.service/delegated/leaf', '/a/b.service'))
check('similar_prefix_not_descendant', not module.is_within('/a/b.service2', '/a/b.service'))
reject('dotdot_cgroup_rejected', lambda: module.is_within('/a/../b', '/a'))
check('two_cpu_cpuset_actual_parser', module.parse_cpuset('0-1\n') == (0, 1))
reject('three_cpu_cpuset_rejected', lambda: module.parse_cpuset('0-2'))
reject('duplicate_cpu_cpuset_rejected', lambda: module.parse_cpuset('0,0'))
reject('duplicate_wire_keys_rejected', lambda: module.exact_json(b'{"a":1,"a":1}'))
reject('noncanonical_wire_rejected', lambda: module.exact_json(b'{"a": 1}'))
reject('nonfinite_wire_rejected', lambda: module.exact_json(b'{"a":NaN}'))
reject('oversized_wire_rejected', lambda: module.exact_json(b'a' * 65537))
check('actual_birth_observer', module.process_birth(os.getpid()) ==
      (os.getpid(), os.getppid(), int(token)))
now_u, now_m = time.time(), time.monotonic()
grant = module.Grant(token='a' * 64, unit='friday-rework-worker-' + 'b' * 32 + '.service',
    admission_hash='c' * 64, accepted_unix=now_u, accepted_monotonic=now_m,
    useful_unix=now_u + 300, final_unix=now_u + 360,
    useful_monotonic=now_m + 300, final_monotonic=now_m + 360,
    parent_useful_unix=now_u + 400, parent_final_unix=now_u + 500,
    reservation=(1, 2), cpus=(0, 1))
check('original_clock_validates', grant.validate() is grant)
reject('clock_renewal_over_original600_rejected', lambda: module.replace(grant, final_unix=now_u + 601).validate())
reject('clock_parent_escape_rejected', lambda: module.replace(grant, parent_final_unix=now_u + 350).validate())
reject('cleanup_reserve_cut_rejected', lambda: module.replace(grant, useful_unix=now_u + 350).validate())
reject('clock_unix_monotonic_drift_rejected', lambda: module.replace(grant, final_monotonic=now_m + 359).validate())
argv = module.command_vector(4, 5, 'd' * 64, module.process_birth(os.getpid()),
                             '/tmp/finite-inert.sock', grant, 'friday-rework-' + 'e' * 32 + '.slice')
check('actual_systemd_run_interfaces', argv[:4] == ['/usr/bin/systemd-run', '--user', '--unit=' + grant.unit, '--service-type=exec'])
check('actual_native_description_stop_boundary', '--property=Description=Friday rework ' + grant.admission_hash in argv
      and '--property=KillMode=control-group' in argv and '--property=SendSIGKILL=yes' in argv)
check('no_retry_restart_and_non_delegation', '--property=Restart=no' in argv and '--property=Delegate=no' in argv)
check('requested_unit_hardcaps_are_not_observed_credit', '--property=MemoryMax=1073741824' in argv and '--property=CPUQuota=200%' in argv)
check('separate_per_process_limit_as', '--property=LimitAS=1073741824' in argv)
check('proc_outside_fd_no_generic_forwarding', '/proc/' + str(os.getpid()) + '/fd/4' in argv and not any('pass-fd' in s for s in argv))
check('isolated_exact_literal_bootstrap', argv[argv.index('-I'):argv.index('-I') + 5] == ['-I', '-S', '-B', '-c', module.CONTROLLER_BOOTSTRAP])
check('runtime_original_not_extended', any(s.startswith('--property=RuntimeMaxSec=') and int(s.split('=')[-1][:-1]) <= 300 for s in argv))
reject('unqualified_aggregate_slice_rejected', lambda: module.command_vector(4, 5, 'd' * 64,
       module.process_birth(os.getpid()), '/tmp/finite-inert.sock', grant, 'app.slice'))
left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
fd = os.open(ROOT / 'finite_outside_unit.py', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
try:
    module.send_packet(left, {'phase': 'CUSTODY', 'token': 'a' * 64}, (fd,))
    packet, rights = module.recv_packet(right, expect_rights=True)
    try:
        check('actual_kernel_scm_rights_exactbytes', packet == {'phase': 'CUSTODY', 'token': 'a' * 64}
              and len(rights) == 1 and module.read_fd(rights[0], len(source) + 1) == source)
        check('received_descriptor_cloexec', not os.get_inheritable(rights[0]))
    finally:
        for received in rights:
            os.close(received)
    check('actual_kernel_sameuid_peercredential', module.peer_credential(left)[0] == os.getpid())
    module.send_packet(left, {'phase': 'READY'})
    reject('missing_rights_rejected', lambda: module.recv_packet(right, expect_rights=True))
finally:
    os.close(fd)
    left.close()
    right.close()

events = []
def fail(stage):
    events.append(stage)
    raise OSError(stage)
errors, observed = module.independent_attempts([('signal', lambda: fail('signal')),
    ('wait', lambda: fail('wait')), ('stop', lambda: events.append('stop')),
    ('witness', lambda: events.append('witness'))])
check('signal_wait_failures_do_not_suppress_stop_witness', events == ['signal', 'wait', 'stop', 'witness']
      and [s for s, _ in errors] == ['signal', 'wait'])
for failure in ['outside_stop', 'tool_signal', 'tool_wait']:
    owner = object.__new__(module.FiniteOutsideOwner)
    events = []
    owner.cgroup = None
    owner.tool = None
    owner.tool_pidfd = owner.controller_pidfd = owner.worker_pidfd = None
    owner.dirfd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    def action(stage, result=True):
        def run():
            events.append(stage)
            if stage == failure:
                raise OSError(stage)
            return result
        return run
    owner._stop_unit = action('outside_stop')
    owner._kill_tool = action('tool_signal')
    owner._wait_tool = action('tool_wait')
    owner._close_sockets = action('sockets_close')
    owner._unlink_owned_socket = action('socket_unlink')
    owner.observe_owned = action('native_witness', types.SimpleNamespace(quiescent=True))
    owner._fresh_cgroup_empty = action('cgroup_witness')
    owner._births_absent = action('birth_witness', {'worker': True})
    owner._path_absent = action('path_witness')
    owner._endpoints_absent = action('endpoint_witness')
    primary = ValueError('original-primary')
    try:
        owner.cleanup(primary=primary)
    except module.CleanupUnconfirmed as exc:
        check('whole_cleanup_exactbody_independent_after_' + failure,
              events == ['outside_stop', 'tool_signal', 'tool_wait', 'sockets_close', 'socket_unlink',
                         'native_witness', 'cgroup_witness', 'birth_witness', 'path_witness', 'endpoint_witness']
              and exc.primary_error is primary and any(stage.endswith(failure.split('_')[-1])
                                                       for stage, _ in exc.cleanup_errors))
    else:
        check('whole_cleanup_rejected_failure_' + failure, False)

tree = ast.parse(source)
launch = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'launch_held')
check('launch_exception_unconditional_cleanup_ast', any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
      and n.func.attr == 'cleanup' for handler in ast.walk(launch) if isinstance(handler, ast.ExceptHandler)
      for n in ast.walk(handler)))
check('helper_no_fork_or_subprocess_ast', not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
      and n.func.attr in ('fork', 'Popen', 'run', 'system', 'posix_spawn', 'execve')
      for n in ast.walk(ast.parse(Path(__file__).read_bytes()))))
report = {'schema': 'finite-outside-unit.inert-controls.v1', 'source_sha256': ready['source_sha256'],
          'passed': True, 'count': len(results), 'controls': results,
          'source_executed_whole_without_guard_stripping': True,
          'seams': 'inert cleanup action callbacks only; no NativeSupervisor product import or native effects',
          'real_channel_scope': 'same-helper AF_UNIX SO_PEERCRED/SCM_RIGHTS only; no service/host admission',
          'native_service_execution': 'NOT_RUN', 'whole_acceptance': 'UNBOUND',
          'elapsed_seconds': time.monotonic() - START}
with (ROOT / 'CONTROLS.json').open('x') as target:
    json.dump(report, target, indent=2, sort_keys=True)
os.chmod(ROOT / 'CONTROLS.json', 0o600)
print(json.dumps({'passed': True, 'count': len(results), 'pid': os.getpid(), 'start_token': token}), flush=True)
