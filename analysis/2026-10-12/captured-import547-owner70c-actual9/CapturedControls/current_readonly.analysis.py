import os, json, time, hashlib, ctypes, signal, resource, types, sys, stat
from pathlib import Path

O = Path(__file__).parent
AS = 268435456
assert resource.getrlimit(resource.RLIMIT_AS) == (AS, AS)
assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
parent = os.getppid()
libc = ctypes.CDLL(None, use_errno=True)
assert libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0 and os.getppid() == parent
ticks = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
print(json.dumps({'pid': os.getpid(), 'birth': ticks, 'parent': parent,
                  'AS': list(resource.getrlimit(resource.RLIMIT_AS)),
                  'limits': Path('/proc/self/limits').read_text(),
                  'affinity': sorted(os.sched_getaffinity(0))}), flush=True)
assert sys.stdin.buffer.read(1) == b'G'
v = json.loads((O / 'INPUT.json').read_bytes())
def pinned(ref):
    b = Path(ref['path']).read_bytes()
    assert len(b) == ref['bytes'] and hashlib.sha256(b).hexdigest() == ref['sha256']
    return b
clk = json.loads(pinned(v['Root_clock']))
repair_clock = json.loads(pinned(v['repair_clock']))
assert time.time() + 10 < repair_clock['useful_deadline_unix']
assert time.time() + 10 < clk['useful_deadline_unix']
p = Path(v['source']['path'])
raw = p.read_bytes()
assert len(raw) == v['source']['bytes'] and hashlib.sha256(raw).hexdigest() == v['source']['sha256']
M = types.ModuleType('<Root-current-readonly-route>')
M.__file__ = str(p)
exec(compile(raw, str(p), 'exec'), M.__dict__)
for name in M.LOCK_NAMES:
    s = (M.R / name).lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1 and not s.st_mode & 0o077
held = M.acquire()
try:
    d = {'routes': v['routes'], 'dependencies': v['dependencies'], '_held_locks': held}
    captured = M.CapturedDependencies(d)
    imported = {name: captured.module(name) for name in M.DEPENDENCIES}
    assert imported['lifecycle_core'].Envelope('fixture', '1', 'fresh', 'goal', {}).key == 'fixture#1'
    M.validate_routes(d)
    print(json.dumps({'status': 'PASS_ACTUAL_CURRENT_CAPTURED_ROUTE_METADATA_ONLY',
                      'source': v['source'], 'roles': ['sol', 'astra'],
                      'four_births': {k: r['births'] for k, r in v['routes'].items()},
                      'historical_binding_pids_not_targets': True,
                      'existing_locks_NB_held_before_dependency_execution': True,
                      'actual_NativeControl_constructors': 2,
                      'all_exact_five_dependency_top_level_imports': True,
                      'native_enter_call_RPC_installer_effects': 0,
                      'runtime_install_release_accepted': False}), flush=True)
finally:
    for fd in reversed(held):
        os.close(fd)
