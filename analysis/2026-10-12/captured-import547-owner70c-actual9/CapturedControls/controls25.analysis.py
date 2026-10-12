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

import dataclasses
actual_core = pinned(v['dependencies_provenance']['lifecycle_core'])
original_R = M.R
scratch = O / 'scratch'
scratch.mkdir(mode=0o700)
rows = []
locks = []
def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as f: f.write(raw)
def case(name, native=b'VALUE=1\n', core=actual_core, control=b'VALUE=1\n'):
    root = scratch / name
    root.mkdir(mode=0o700)
    M.R = root
    refs = {}
    for key, rel in M.DEPENDENCIES.items():
        raw = native if key == 'native_endpoint' else core if key == 'lifecycle_core' else control if key == 'control' else b'VALUE=1\n'
        path = root / rel
        write(path, raw)
        refs[key] = M.reference(path)
    held = M.acquire()
    locks.extend(held)
    d = {'dependencies':refs, '_held_locks':held}
    return M.CapturedDependencies(d), d

def ok(label, fn):
    fn(); rows.append({'case':label, 'observation':'PASS_AFFECTED_SOURCE_FIXTURE'})
def refuse(label, fn):
    try: fn()
    except M.Refusal as exc:
        rows.append({'case':label, 'observation':'REFUSED_EXPECTED', 'reason':str(exc)})
    else: raise AssertionError(label + ' unexpectedly accepted')
try:
    c, d = case('positive', b'from __future__ import annotations\nimport tempfile\nimport tomllib\nimport sys\nsys.path.insert(0, "/PRIVATE-CLOSURE-ONLY")\nclass C:\n value: MissingType\nVALUE = tomllib.loads("value=7")["value"]\n')
    global_path = list(sys.path)
    global_modules = {name:sys.modules.get(name) for name in ('native_endpoint','lifecycle_core','<captured_dependency:native_endpoint>','<captured_dependency:lifecycle_core>')}
    native = c.module('native_endpoint')
    assert native.VALUE == 7 and native.C.__annotations__ == {'value':'MissingType'}
    assert c.sys.path[0] == '/PRIVATE-CLOSURE-ONLY' and sys.path == global_path
    rows.append({'case':'exact_annotations_tempfile_tomllib_private_sys_path', 'observation':'PASS_AFFECTED_SOURCE_FIXTURE'})
    core = c.module('lifecycle_core')
    env = core.Envelope('fixture', '1', 'fresh', 'goal', {'SCOPE':'fixture'})
    assert env.key == 'fixture#1'
    assert core.Envelope.__annotations__ == {'assignment_id':'str','generation':'str','context':'str','owner_scope':'str','fields':'dict[str, str]'}
    assert {f.name:f.type for f in dataclasses.fields(env)} == core.Envelope.__annotations__
    try: env.context = 'full'
    except dataclasses.FrozenInstanceError: pass
    else: raise AssertionError('trusted frozen dataclass weakened')
    assert c.module('lifecycle_core') is core
    assert all(sys.modules.get(name) is value for name,value in global_modules.items())
    rows.append({'case':'actual_pinned_Envelope_frozen_string_annotations_no_global_module_pollution','observation':'PASS_AFFECTED_SOURCE_FIXTURE'})
    for label, name, args in [
        ('unknown_app','unlisted_application',{}), ('unknown_stdlib','random',{}),
        ('unlisted_application_submodule','native_endpoint.child',{}),
        ('relative_import','native_endpoint',{'level':1}),
        ('future_bare','__future__',{}), ('future_other_feature','__future__',{'fromlist':('division',)}),
        ('future_unknown_submodule','__future__.annotations',{}),
        ('dataclasses_bare','dataclasses',{}), ('dataclasses_other_symbol','dataclasses',{'fromlist':('field',)}),
        ('dataclasses_wrong_captured_caller','dataclasses',{'fromlist':('dataclass',),'globals':{'__name__':'<captured_dependency:native_endpoint>'}}),
        ('dataclasses_unknown_submodule','dataclasses.other',{}),
    ]:
        refuse(label, lambda n=name,a=args:c.importer(n,**a))
    refuse('uncaptured_module',lambda:c.module('unlisted_application'))
    refuse('uncaptured_run_path',lambda:c.run_path(str(M.R/'unknown.py')))
    refuse('relative_run_path',lambda:c.run_path('native_endpoint.py'))
    refuse('run_path_init_globals',lambda:c.run_path(str(M.R/'native_endpoint.py'),{}))
    refuse('run_path_main',lambda:c.run_path(str(M.R/'native_endpoint.py'),run_name='__main__'))
    same, same_d = case('same-read', b'VALUE=11\n')
    path = Path(same_d['dependencies']['native_endpoint']['path'])
    path.chmod(0o600);path.write_bytes(b'raise RuntimeError("uncaptured path bytes executed")\n');path.chmod(0o400)
    assert same.module('native_endpoint').VALUE == 11
    rows.append({'case':'same_read_captured_bytes_not_reopened','observation':'PASS_AFFECTED_SOURCE_FIXTURE'})
    refuse('next_pre_effect_dependency_pin_drift',lambda:M.pin(same_d['dependencies']['native_endpoint']))
    cyc, cyc_d = case('cycle', b'from native_endpoint import VALUE\n')
    refuse('cyclic_captured_import',lambda:cyc.module('native_endpoint'))
    assert not cyc.active and not cyc.modules and not cyc.namespaces
    rows.append({'case':'failed_module_private_namespace_removed','observation':'PASS_AFFECTED_SOURCE_FIXTURE'})
    bad_d = dict(cyc_d);bad_d['dependencies'] = dict(cyc_d['dependencies']);bad_d['dependencies']['native_endpoint'] = dict(cyc_d['dependencies']['native_endpoint'],sha256='0'*64)
    refuse('capture_dependency_pin_mismatch',lambda:M.CapturedDependencies(bad_d))
    drift, drift_d = case('lock-drift')
    old = M.R/M.LOCK_NAMES[0];old.rename(M.R/'retained-old-lock');write(old,b'')
    refuse('held_lock_name_inode_drift_before_import',lambda:drift.importer('json'))
    # Rebind to the corresponding private root; this is only a fixture close check.
    M.R = scratch/'positive'
    os.close(d['_held_locks'][0]);locks.remove(d['_held_locks'][0])
    try:c.importer('json')
    except OSError:rows.append({'case':'closed_held_lock_before_import','observation':'REFUSED_EXPECTED'})
    else:raise AssertionError('closed lock accepted')
    assert not any(Path(scratch).rglob('UNREVIEWED-EXECUTED'))
    print(json.dumps({'status':'PASS_AFFECTED_CAPTURED_IMPORT_SOURCE_FIXTURES','cases':rows,'count':len(rows),
                      'source':v['source'],'actual_native_constructor_RPC_install_effects':0,
                      'prior_or_final_runtime_release_accepted':False}),flush=True)
finally:
    for fd in reversed(locks):os.close(fd)
    M.R = original_R
