"""Finite OWN inert controls; target source is read/audited, NEVER imported."""
import os, sys, resource, time, json, hashlib, types

O = os.path.dirname(os.path.abspath(__file__))
os.umask(0o077)
os.sched_setaffinity(0, [min(os.sched_getaffinity(0))])
resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
START = time.time(); DEADLINE = min(START+45, 1791722320)

def put(name, obj):
    path = O+'/'+name
    data = (json.dumps(obj, indent=2, sort_keys=True)+'\n').encode()
    assert len(data) <= 1024**2
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, 0o600)
    try: os.write(fd, data)
    finally: os.close(fd)

def birth():
    with open('/proc/self/stat','rb') as f: raw = f.read(16384)
    return int(raw[raw.rfind(b')')+2:].split()[19])

IDENTITY = {'pid':os.getpid(), 'ppid':os.getppid(), 'start':birth()}
OBSERVED = {'identity':IDENTITY, 'affinity':sorted(os.sched_getaffinity(0)),
            'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),
            'RLIMIT_CPU':resource.getrlimit(resource.RLIMIT_CPU),
            'RLIMIT_FSIZE':resource.getrlimit(resource.RLIMIT_FSIZE),
            'threads':len(os.listdir('/proc/self/task')), 'unix':START,
            'deadline_unix':DEADLINE,'aggregate_cgroup_claim':False,
            'scope':'single inert helper; no child processes/native/network/effects'}
assert len(OBSERVED['affinity']) == 1 and OBSERVED['threads'] == 1
assert OBSERVED['RLIMIT_AS'] == (256*1024**2,)*2 and time.time()<DEADLINE
if os.path.exists(O+'/observations/CONTROLS-PREGO.json'):
    with open(O+'/observations/CONTROLS-PREGO.json') as f: prior=json.load(f)
    try:
        with open('/proc/'+str(prior['identity']['pid'])+'/stat','rb') as f:priorraw=f.read(16384)
        priorbirth=int(priorraw[priorraw.rfind(b')')+2:].split()[19])
        absence=priorbirth != prior['identity']['start']
    except FileNotFoundError:absence=True
    assert absence
    prior_status=1
    if os.path.exists(O+'/observations/CONTROLS-SELF-CLOSED.json'):
        with open(O+'/observations/CONTROLS-SELF-CLOSED.json') as f: closed=json.load(f)
        if closed['identity']==prior['identity']:
            prior_status=0
            os.rename(O+'/observations/CONTROLS.json',O+'/observations/PRIOR-PASSED-CONTROLS-'+str(prior['identity']['pid'])+'.json')
    put('observations/PRIOR-CONTROLS-CLOSED-'+str(prior['identity']['pid'])+'.json',{'identity':prior['identity'],
        'actual_tool_wait_exit':prior_status,'fresh_birth_absence':absence,'observation_unix':time.time(),
        'status':'prior finite run preserved; exact earlier tool exit supplied; no execution transferred'})
    os.rename(O+'/observations/CONTROLS-PREGO.json',O+'/observations/FAILED-CONTROLS-PREGO-'+str(prior['identity']['pid'])+'.json')
    os.rename(O+'/observations/CONTROLS-GO.json',O+'/observations/FAILED-CONTROLS-GO-'+str(prior['identity']['pid'])+'.json')
put('observations/CONTROLS-PREGO.json', OBSERVED)
put('observations/CONTROLS-GO.json', {'identity':IDENTITY,'observed_caps_before_GO':True,'unix':time.time()})

with open(O+'/SOURCE/held_startup_imports.py','rb') as f: SOURCE = f.read(1024**2)
MOD = types.ModuleType('_own_custody_component')
sys.modules[MOD.__name__] = MOD
exec(compile(SOURCE, O+'/SOURCE/held_startup_imports.py', 'exec', dont_inherit=True), vars(MOD))
OWNERS=(0,os.geteuid()); RESULTS=[]; held=[]
F=O+'/fixtures/run-'+str(os.getpid());os.mkdir(F,0o700)

def record(name, fn, expected=None):
    assert time.time()<DEADLINE, 'original useful deadline'
    try:
        detail=fn()
        if expected is not None: raise AssertionError('negative control unexpectedly passed')
        RESULTS.append({'name':name,'pass':True,'kind':'positive','detail':detail})
    except (MOD.Unbound,OSError) as exc:
        if expected is None: raise
        assert expected in str(exc), (name, expected, str(exc))
        RESULTS.append({'name':name,'pass':True,'kind':'negative','refusal':str(exc)})

def fixture(name, raw, mode=0o600):
    path=F+'/'+name
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,mode)
    try: os.write(fd,raw)
    finally: os.close(fd)
    os.chmod(path,mode)
    return path

def keep(path, sha=None, mode=0o600):
    with open(path,'rb') as f: raw=f.read(16*1024**2)
    item=MOD.HeldFile(path,sha or hashlib.sha256(raw).hexdigest(),owners=OWNERS,mode=mode,limit=16*1024**2)
    held.append(item);return item

def graph(recordmap, externals=None):
    return MOD.HeldImportGraph(recordmap,externals)

def entry(item, imports=(), package=False, dynamic=()):
    return {'held':item,'package':package,'imports':imports,'dynamic_unbound':dynamic}

A=keep(fixture('alpha.py',b'import own_beta\nVALUE = own_beta.VALUE + 1\ndef answer():\n    return VALUE\n'))
B=keep(fixture('beta.py',b'VALUE = 41\n'))

def positive_import():
    g=graph({'own_alpha':entry(A,('own_beta',)), 'own_beta':entry(B)})
    g.install()
    try:
        module=g.load('own_alpha'); assert module.answer()==42
        assert module.answer.__code__.co_filename.startswith('<held:own_alpha:')
        return g.verify_loaded()
    finally:g.close()
record('held_source_transitive_import_original_bytes',positive_import)

PKG=keep(fixture('package.py',b'from . import child\nVALUE = child.VALUE\n'))
CHILD=keep(fixture('child.py',b'import sys\nVALUE = 44\n'))
def relative_package():
    g=graph({'own_pkg':entry(PKG,('own_pkg','own_pkg.child'),package=True),
             'own_pkg.child':entry(CHILD,('sys',))},{'sys':sys})
    g.install()
    try:
        module=g.load('own_pkg');assert module.VALUE==44
        return g.verify_loaded()
    finally:g.close()
record('held_relative_package_builtin_dependency',relative_package)

record('missing_transitive_dependency',lambda:graph({'own_alpha':entry(A,('own_beta',))}),
       'TRANSITIVE_IMPORT_GRAPH_INCOMPLETE')
record('missing_declared_edge',lambda:graph({'own_alpha':entry(A),'own_beta':entry(B)}),
       'DECLARED_IMPORT_EDGE_INCOMPLETE')
record('stale_sha',lambda:keep(A.path,'0'*64),'STALE_SHA')
LINK=F+'/link.py';os.symlink('beta.py',LINK)
record('source_symlink',lambda:keep(LINK),'Too many levels')
UNSAFE=fixture('unsafe.py',b'VALUE=1\n',0o622)
record('unsafe_source_mode',lambda:keep(UNSAFE,mode=0o622),'SAFE_EXACT_MODE')
os.chmod(UNSAFE,0o600)
ANCESTOR=F+'/writable';os.mkdir(ANCESTOR,0o700)
P=ANCESTOR+'/inside.py'
with open(P,'wb') as f:f.write(b'VALUE=1\n')
os.chmod(P,0o600);os.chmod(ANCESTOR,0o722)
record('unsafe_ancestor_mode',lambda:keep(P),'UNSAFE_ANCESTOR')
os.chmod(ANCESTOR,0o700)

D=keep(fixture('dynamic.py',b'import runpy\nrunpy.run_path("unretained.py")\n'))
record('runpy_dynamic_path_graph_gap',lambda:graph({'own_dynamic':entry(D,('runpy',))}),
       'UNBOUND_DYNAMIC_IMPORT_GRAPH')
record('explicit_dynamic_graph_gap',lambda:graph({'own_beta':entry(B,dynamic=('unclosed_route',))}),
       'UNBOUND_DYNAMIC_IMPORT_GRAPH')
record('extension_cannot_be_existing_module_authority',
       lambda:graph({'own_beta':entry(B)}, {'_hashlib':sys.modules['_hashlib']}),
       'UNBOUND_EXTENSION_OR_SOURCE_STARTUP_MODULE')

def mutate_case(kind):
    g=graph({'own_alpha':entry(A,('own_beta',)),'own_beta':entry(B)})
    g.install()
    try:
        module=g.load('own_alpha')
        if kind=='namespace':module.VALUE=43
        elif kind=='code':module.answer.__code__=module.answer.__code__.replace()
        elif kind=='builtin':module.__builtins__['__import__']=__import__
        elif kind=='unknown':sys.modules['own_unexpected']=types.ModuleType('own_unexpected')
        elif kind=='path':sys.path.append('/unretained')
        elif kind=='route':g.meta.append(object())
        return g.verify_loaded()
    finally:
        sys.modules.pop('own_unexpected',None)
        if kind=='path':sys.path.remove('/unretained')
        g.close()
for kind,reason in [('namespace','LOADED_NAMESPACE_OR_CODE_DRIFT'),
                    ('code','LOADED_NAMESPACE_OR_CODE_DRIFT'),('builtin','BUILTINS_IMPORT_GUARD_DRIFT'),
                    ('unknown','UNKNOWN_LOADED_MODULE'),('path','IMPORT_ROUTE_OR_PATH_DRIFT'),
                    ('route','IMPORT_ROUTE_OR_PATH_DRIFT')]:
    record('loaded_'+kind+'_drift',lambda kind=kind:mutate_case(kind),reason)

S=keep(fixture('stale_inode.py',b'VALUE=17\n'))
os.rename(S.path,S.path+'.original')
fixture('stale_inode.py',b'VALUE=17\n')
record('same_bytes_replacement_inode',S.verify,'DRIFT')
M=keep(fixture('modified.py',b'VALUE=17\n'))
fixture('modified.py',b'VALUE=18\n')
record('retained_fd_bytes_drift',M.verify,'HELD_INODE_OR_BYTES_DRIFT')

def received_fd_positive():
    item=MOD.HeldFile.from_received_fds(B.path,B.expected_sha256,ancestor_fds=tuple(B.fds[:-1]),
        file_fd=B.fd,expected_signature=B.signature,owners=OWNERS,mode=0o600)
    try:
        assert item.fd!=B.fd and item.raw==B.raw
        return {'original_fd':B.fd,'duplicated_fd':item.fd,'sha':item.verify()}
    finally:item.close()
record('received_fd_exact_ancestor_buffer_custody',received_fd_positive)
record('received_fd_stale_signature',lambda:MOD.HeldFile.from_received_fds(
    B.path,B.expected_sha256,ancestor_fds=tuple(B.fds[:-1]),file_fd=B.fd,
    expected_signature=(B.signature[0],B.signature[1]+1,*B.signature[2:]),owners=OWNERS,mode=0o600),
    'RECEIVED_FD_SIGNATURE_MISMATCH')

with open('/proc/self/maps') as f: maplines=f.read(512*1024).splitlines()
maps={}
for line in maplines:
    parts=line.split(None,5)
    if 'x' in parts[1] and len(parts)==6 and parts[5].startswith('/'):
        path=parts[5]
        if path not in maps:maps[path]=keep(path,mode=os.stat(path).st_mode&0o7777)
INTERP=maps['/usr/bin/python3.14']
EXPECTED=('/usr/lib/python314.zip','/usr/lib/python3.14','/usr/lib/python3.14/lib-dynload')
HOST=MOD.HostProvenance(INTERP,maps,expected_sys_path=EXPECTED)
record('actual_interpreter_elf_proc_maps_inert_observation',HOST.verify_observations)
record('genuine_startup_admission_stays_unbound',HOST.verify_before_effects,
       'UNBOUND_INDEPENDENT_STARTUP_EXTENSION_RELOCATION_ACCEPTANCE')
record('missing_exec_map_catalog',lambda:MOD.HostProvenance(INTERP,{INTERP.path:INTERP},
       expected_sys_path=EXPECTED),'UNBOUND_UNKNOWN_OR_WRITABLE_EXECUTABLE_MAP')
record('wrong_isolated_path',lambda:MOD.HostProvenance(INTERP,maps,expected_sys_path=('/bad',)),
       'ISOLATED_NO_SITE_NO_BYTECODE_PATH_REQUIRED')

VALIDATOR='/PORTABLE_UNBOUND/PATH_0003'
with open(VALIDATOR,'rb') as f:raw=f.read(1024**2)
assert hashlib.sha256(raw).hexdigest()=='a17caac467eca718ffa87b0aef2a55037914b3e3562bd808c6959c160dbd8365'
audit=MOD.source_import_audit(raw,'immutable_validator','')
assert {'jsonschema','websockets.asyncio.client','native_endpoint','runpy'} <= set(audit['static_imports'])
assert 'DYNAMIC_LOADER:runpy' in audit['dynamic_gaps']
put('observations/NATIVE-GRAPH-REFUSAL.json', {'validator_sha256':hashlib.sha256(raw).hexdigest(),
    'actual_target_imported':False,'audit':audit,'native_graph':'EXPLICITLY_REFUSED',
    'required_missing_retained_graphs':['jsonschema recursive dependencies',
      'websockets.asyncio.client recursive dependencies','native_endpoint dependencies',
      'runpy profile helper astra-https-transport-profile.py',
      'runpy reconnect sol-link-native-reconnect.py','all stdlib source/extension startup dependencies'],
    'admission':'NOT_RUN','AST_closure_exhaustive':False})

for item in reversed(held):item.close()
os.unlink(LINK)  # own inert symlink only; retain all source fixtures
put('observations/CONTROLS.json', {'source_sha256':hashlib.sha256(SOURCE).hexdigest(),
    'controls':RESULTS,'all_pass':all(x['pass'] for x in RESULTS),
    'target_imports':False,'elapsed_seconds':time.time()-START,'completed_unix':time.time(),
    'qualification':'NOT_RUN','inert_fixture_execution_only':True})
put('observations/CONTROLS-SELF-CLOSED.json', {'identity':IDENTITY,'held_fds_closed':True,
    'descendants_created':False,'completed_unix':time.time(),'wait_and_birthabsence':'OUTSIDE_WITNESS_PENDING'})
print(json.dumps({'controls':len(RESULTS),'all_pass':True,'runtime_admission':'NOT_RUN'}))
