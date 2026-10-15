"""Independent offline tests; execute with python -B. No native services or sockets."""
import os, sys, resource, signal, time
from pathlib import Path
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate-native', required=True, type=Path)
parser.add_argument('--baseline-native', required=True, type=Path)
parser.add_argument('--sdk-site', required=True, type=Path)
parser.add_argument('--output-dir', required=True, type=Path)
args = parser.parse_args()
HERE = args.output_dir.resolve(strict=True)
OLD = False
D = args.candidate_native.resolve(strict=True) / 'hermes_cli'
NATIVE = args.baseline_native.resolve(strict=True)
R = Path(__file__).resolve().parents[1]
SDK = args.sdk_site.resolve(strict=True)
for key, limit in ((resource.RLIMIT_CPU,90),(resource.RLIMIT_AS,768*1024**2),(resource.RLIMIT_FSIZE,32*1024**2),(resource.RLIMIT_CORE,0)):
    resource.setrlimit(key,(limit,limit))
signal.alarm(110)
os.umask(0o077)
import tempfile, hashlib, json, ast, importlib.util, contextvars, threading, traceback
from unittest.mock import patch
started=time.monotonic(); results=[]; findings=[]
PINS={'friday_dashboard_owner.py':'47a3bd9a23d7207756b51c1da90b36ba6c05fca5a710882633bba591cac45c9d','friday_gateway_owner.py':'b91dca50fdb6213b9852b1cbf080b3d7f592519f5d6f3ae8ca9d4a6c76c92a88','friday_product_access.py':'612d1416d566f6df33479a41e4e87e16d8ff3caf9c9eac07320dcb6a62863711'}
if not OLD:PINS.update({'friday_dashboard_owner.py':'5453e69f5551b6c969b4c7d765566db2844faebb81f9447f73c5af0610e21c7f','friday_gateway_owner.py':'1356b30f879de3b0b55ed083c5a9dd60b3f3f1ddc2c7e332268669135b439a23'})
def sha(b):return hashlib.sha256(b).hexdigest()
def check(name, fn):
    t=time.monotonic()
    try: detail=fn(); results.append({'name':name,'state':'PASS','seconds':time.monotonic()-t,'detail':detail})
    except Exception as exc:
        results.append({'name':name,'state':'FAIL','seconds':time.monotonic()-t,'error':str(exc),'traceback':traceback.format_exc()})
def refuses(fn):
    try:fn()
    except (ValueError, PermissionError, RuntimeError, OSError, TypeError, KeyError):return
    raise AssertionError('invalid current input accepted')
def module(name, filename):
    spec=importlib.util.spec_from_file_location(name,filename); m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def astfn(path,name):
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
    node.name='normalized';return ast.dump(node,include_attributes=False)
with tempfile.TemporaryDirectory(prefix='offline-',dir=HERE) as tmp:
    temp=Path(tmp);home=temp/'home';home.mkdir()
    os.environ.update(HOME=str(home),HERMES_HOME=str(home),PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',HERMES_DISABLE_TELEMETRY='1',GIT_OPTIONAL_LOCKS='0')
    sys.path[:0]=[str(args.candidate_native.resolve(strict=True)),str(SDK),str(R)]
    import hermes_cli
    hermes_cli.__path__.insert(0,str(D))
    owner=module('hermes_cli.friday_dashboard_owner',D/'friday_dashboard_owner.py');hermes_cli.friday_dashboard_owner=owner
    gateway=module('hermes_cli.friday_gateway_owner',D/'friday_gateway_owner.py')
    access=module('hermes_cli.friday_product_access',D/'friday_product_access.py')
    for filename,pin in PINS.items():check('pin_'+filename,lambda filename=filename,pin=pin: (sha((D/filename).read_bytes())==pin) or (_ for _ in ()).throw(AssertionError('SHA mismatch')))
    for name in ('credentials','registered_basic','_expected'):
        oldname='expected' if name=='_expected' else name
        check('unchanged_owner_'+name,lambda name=name,oldname=oldname: (astfn(D/'friday_dashboard_owner.py',name)==astfn(NATIVE/'hermes_cli/friday_dashboard_owner.py',oldname)) or (_ for _ in ()).throw(AssertionError('body changed')))
    check('gateway_identity_body_only_private_delegation_changed',lambda: (astfn(D/'friday_gateway_owner.py','_expected').replace("attr='_expected'","attr='expected'")==astfn(NATIVE/'hermes_cli/friday_gateway_owner.py','expected')) or (_ for _ in ()).throw(AssertionError('body changed')))
    source=home/'hermes-agent';source.mkdir();(source/'hermes_cli').mkdir();files={}
    for index in range(1001):
        p=source/('file%04d.py'%index);p.write_text('value=1\n');files[p.name]={'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,'mode':'100644'}
    p=source/'hermes_cli/friday_dashboard_owner.py';p.write_bytes((D/'friday_dashboard_owner.py').read_bytes());files[str(p.relative_to(source))]={'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,'mode':'100644'}
    def write(path,value):path.write_text(json.dumps(value));path.chmod(0o600)
    receipt={'schema':'friday.hermes-source.v1','status':'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED','files':files,'commit':'a'*40,'base_tree':'b'*40,'layers':[]}
    receiptpath=home/'hermes-agent.source.json';write(receiptpath,receipt)
    stamp=source/'install-stamp.json';write(stamp,{'fridaySource':{'baseTree':'b'*40,'layers':[]},'commit':'a'*40,'dirty':True})
    plugin=home/'plugins/friday_rework/plugin.yaml';plugin.parent.mkdir(parents=True);plugin.write_text('name: fixture\n');plugin.chmod(0o600)
    marker=home/'FRIDAY-INSTALL.json';write(marker,{'schema':'friday.native-install.v1','state':'INSTALLED_TEMPLATE_INCOMPLETE','home':str(home),'source':str(source),'source_receipt_sha256':sha(receiptpath.read_bytes()),'plugin_files':{'plugins/friday_rework/plugin.yaml':sha(plugin.read_bytes())}})
    scan=owner._verify_source_files;scans=[]
    def spy(*args):scans.append(str(args[0]));return scan(*args)
    owner._verify_source_files=spy
    def identity():return owner.source_identity(home,source=source)
    def body(**kw):
        v=identity();identity();identity();return v
    owner._expected=body
    def standalone():
        scans.clear();v=identity();assert len(scans)==1;return {'scans':len(scans)}
    check('standalone_source_identity_immediate',standalone)
    def expected_once():
        scans.clear();owner.expected();assert len(scans)==1;owner.expected();assert len(scans)==2;assert owner._SOURCE_CHECKS.get() is None
    check('every_outer_expected_full_check_no_cross_request_cache',expected_once)
    def gateway_once():
        scans.clear()
        with patch.object(gateway,'_expected',lambda home:body()):gateway.expected(home)
        assert len(scans)==1 and owner._SOURCE_CHECKS.get() is None
    check('gateway_outer_expected_full_check',gateway_once)
    def real_gateway_private():
        scans.clear()
        def declared_stub(**kw):return {'home':str(home),'operator':{'user_id':'fixture'},'source':body()}
        with patch.object(owner,'_expected',declared_stub),patch.object(owner,'credentials',lambda *args:(None,{'secret':b'FIXTURE_SECRET_32_BYTES_LONG_____'},None,None)):
            proof=gateway.expected(home)
        assert proof['home']==str(home) and len(scans)==1 and owner._SOURCE_CHECKS.get() is None
    check('actual_gateway_private_delegation_one_final_scan',real_gateway_private)
    def nested():
        scans.clear()
        with owner._source_check_scope():
            owner.expected();owner.expected();assert len(scans)==(0 if OLD else 2)
        assert len(scans)==(1 if OLD else 2) and owner._SOURCE_CHECKS.get() is None
    check('nested_public_expected_owns_proof_after_repair',nested)
    def abort():
        scans.clear()
        with patch.object(owner,'_expected',side_effect=RuntimeError('synthetic')):refuses(owner.expected)
        assert owner._SOURCE_CHECKS.get() is None;owner.expected();assert len(scans)==1
    check('exception_resets_context',abort)
    def mutate_refused(path,new=None,mode=None):
        old=path.read_bytes() if path.exists() else None;oldmode=path.stat().st_mode if old is not None else None
        def bad(**kw):
            value=identity()
            if new is not None:path.write_bytes(new)
            if mode is not None:path.chmod(mode)
            return value
        try:
            with patch.object(owner,'_expected',bad):refuses(owner.expected)
            assert owner._SOURCE_CHECKS.get() is None
        finally:
            if old is None:path.unlink(missing_ok=True)
            else:path.write_bytes(old);path.chmod(oldmode)
    for name,path,new,mode in (
        ('source_bytes',source/'file0000.py',b'value=2\n',None),
        ('source_executable',source/'file0000.py',None,0o700),
        ('extra_importable',source/'unexpected.py',b'evil=True\n',None),
        ('hidden_env',source/'.env',b'BAD=1\n',None),
        ('receipt_final_recheck',receiptpath,b'{}',None)):
        check('deferred_refuses_'+name,lambda path=path,new=new,mode=mode:mutate_refused(path,new,mode))
    def receipt_mid():
        raw=receiptpath.read_bytes()
        try:
            with owner._source_check_scope():
                identity();receiptpath.write_bytes(raw+b' ');refuses(identity)
        except ValueError:pass
        finally:receiptpath.write_bytes(raw)
        assert owner._SOURCE_CHECKS.get() is None
    check('receipt_changed_between_reads_refused',receipt_mid)
    def direct_mutation(path,data):
        original=path.read_bytes()
        try:path.write_bytes(data);refuses(owner.expected)
        finally:path.write_bytes(original)
    check('native_stamp_current_each_read',lambda:direct_mutation(stamp,b'{}'))
    check('plugin_current_each_read',lambda:direct_mutation(plugin,b'name: changed\n'))
    def copied_context():
        scans.clear()
        with owner._source_check_scope():identity();ctx=contextvars.copy_context()
        assert len(scans)==1
        p=source/'file0000.py';original=p.read_bytes();p.write_bytes(b'value=2\n')
        try:
            before=len(scans)
            if OLD:
                returned=ctx.run(owner.expected);bypassed=len(scans)==before
                assert returned['root']==str(source) and bypassed
                findings.append({'id':'R1','severity':'high','issue':'A copied context retains mutable pending dict after original scope reset; later expected returns unverified tampered source with zero scans.','line':64,'reproducer':'copied_context_retains_closed_scope_proof_bypass'})
            else:refuses(lambda:ctx.run(owner.expected));assert len(scans)==before+1
            return {'tampered_source_proof_returned':OLD,'additional_full_scans':len(scans)-before}
        finally:p.write_bytes(original)
    check('copied_context_retains_closed_scope_proof_bypass',copied_context)
    def stale_direct_source():
        scans.clear()
        with owner._source_check_scope():identity();ctx=contextvars.copy_context()
        p=source/'file0000.py';original=p.read_bytes();p.write_bytes(b'value=2\n')
        try:
            before=len(scans)
            if OLD:
                ctx.run(identity);assert len(scans)==before
                return {'old_inherited_closed_scope_bypass':True}
            refuses(lambda:ctx.run(identity));assert len(scans)==before+1
        finally:p.write_bytes(original)
    check('standalone_source_in_closed_copied_context_is_immediate',stale_direct_source)
    def stale_after_failed_scope():
        scans.clear();p=source/'file0000.py';original=p.read_bytes();ctx=None
        try:
            try:
                with owner._source_check_scope():
                    identity();ctx=contextvars.copy_context();raise RuntimeError('abort')
            except RuntimeError:pass
            p.write_bytes(b'value=2\n')
            before=len(scans)
            if OLD:ctx.run(identity);assert len(scans)==before
            else:refuses(lambda:ctx.run(identity));assert len(scans)==before+1
        finally:p.write_bytes(original)
        assert owner._SOURCE_CHECKS.get() is None
    check('aborted_scope_copied_context_cannot_keep_trust',stale_after_failed_scope)
    def copied_thread():
        scans.clear();out=[];errors=[]
        with owner._source_check_scope():
            ctx=contextvars.copy_context()
            def run():
                try:out.append(ctx.run(owner.expected))
                except BaseException as exc:errors.append(type(exc).__name__)
            thread=threading.Thread(target=run);thread.start();thread.join(3)
            assert not thread.is_alive() and not errors and out and len(scans)==(0 if OLD else 1)
        assert len(scans)==1
        return {'thread_returned_proof_before_any_scan':OLD}
    check('copied_context_cross_thread_shares_pending',copied_thread)
    def copied_direct_thread():
        scans.clear();errors=[];out=[]
        with owner._source_check_scope():
            ctx=contextvars.copy_context()
            def run():
                try:out.append(ctx.run(identity))
                except BaseException as exc:errors.append(type(exc).__name__)
            thread=threading.Thread(target=run);thread.start();thread.join(3)
            assert not thread.is_alive() and not errors and out and len(scans)==(0 if OLD else 1)
        assert len(scans)==1
    check('direct_source_in_other_thread_is_immediate',copied_direct_thread)
    def ordinary_thread():
        scans.clear();errors=[]
        with owner._source_check_scope():
            def run():
                try:owner.expected()
                except BaseException as exc:errors.append(type(exc).__name__)
            thread=threading.Thread(target=run);thread.start();thread.join(3)
            assert not thread.is_alive() and not errors and len(scans)==1
    check('fresh_thread_has_separate_context',ordinary_thread)
    import hermes_cli.config as config, utils, hermes_constants
    configpath=home/'config.yaml'
    def cfg(value):write(configpath,{'plugins':{'entries':{'friday_rework':{'settings':{'review':value}}}}})
    cfg('A')
    check('policy_valid_current_config',lambda: (access.settings()['review']=='A') or (_ for _ in ()).throw(AssertionError('wrong policy')))
    def bad_policy(data):
        cfg('A');assert access.settings()['review']=='A';configpath.write_text(data);refuses(access.settings);cfg('A')
    for name,data in (('malformed','bad: ['),('list','[1,2]'),('scalar','yes'),('string','example')):check('policy_refuses_'+name,lambda data=data:bad_policy(data))
    def mtime_preserved():
        cfg('A');assert access.settings()['review']=='A';st=configpath.stat();raw=configpath.read_bytes();configpath.write_bytes(raw.replace(b'"A"',b'"B"'));os.utime(configpath,ns=(st.st_atime_ns,st.st_mtime_ns));assert access.settings()['review']=='B'
    check('policy_mtime_size_preserved_change_invalidates_by_ctime',mtime_preserved)
    def mode_refused():
        cfg('A');access.settings();configpath.chmod(0)
        try:refuses(access.settings)
        finally:configpath.chmod(0o600)
    check('policy_cached_then_permission_denied_refuses',mode_refused)
    def home_cache():
        cfg('A');assert access.settings()['review']=='A';other=temp/'other';other.mkdir();write(other/'config.yaml',{'plugins':{'entries':{'friday_rework':{'settings':{'review':'B'}}}}})
        token=hermes_constants.set_hermes_home_override(str(other))
        try:assert access.settings()['review']=='B'
        finally:hermes_constants.reset_hermes_home_override(token)
        assert access.settings()['review']=='A'
    check('policy_cross_home_cache_separate',home_cache)
    def cache_no_reparse():
        cfg('A');access.settings()
        with patch.object(utils,'fast_safe_load',side_effect=AssertionError('unexpected parse')),patch.object(config,'require_readable_config_before_write',side_effect=AssertionError('unexpected guard parse')):
            assert access.settings()['review']=='A'
    check('policy_unchanged_native_cache_used',cache_no_reparse)
result={'state':'REQUEST_CHANGES' if findings or any(r['state']=='FAIL' for r in results) else 'PASS_SOURCE_ONLY','candidate_sha256':PINS,'checks':results,'findings':findings,'elapsed_seconds':time.monotonic()-started,'runtime_acceptance':False,'effects':'offline isolated temporary files only; no sockets, processes, services, installed writes, credentials or source-tree mutations','completed_at_moscow':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
(HERE/('ORIGINAL-RESULT.json' if OLD else 'RESULT.json')).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'state':result['state'],'checks':len(results),'failed':[r['name'] for r in results if r['state']=='FAIL'],'findings':findings,'elapsed_seconds':result['elapsed_seconds']}))
sys.exit(0 if not any(r['state']=='FAIL' for r in results) else 1)
