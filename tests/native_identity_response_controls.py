"""Native ASGI identity controls over a fresh private declared-source copy. No services or network."""
import os, sys, resource, signal, time, json, hashlib, shutil, traceback
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate-native',required=True,type=Path)
parser.add_argument('--source-receipt',required=True,type=Path)
parser.add_argument('--baseline-native',type=Path)
parser.add_argument('--sdk-site',required=True,type=Path)
parser.add_argument('--output-dir',required=True,type=Path)
parser.add_argument('--before',action='store_true')
args=parser.parse_args()
HERE=args.output_dir.resolve(strict=True)
OLD=args.before
assert not OLD or args.baseline_native is not None
LABEL='before' if OLD else 'after'
HOME_FIXTURE=HERE/'fixture-home'
HOME_FIXTURE.mkdir(mode=0o700)
SOURCE=HOME_FIXTURE/'hermes-agent'
SOURCE.mkdir(mode=0o700)
sys.path.insert(0,str(args.sdk_site.resolve(strict=True)))
# Reproducible private copy of declared source only. Never copy credentials,
# data or generated products from an installation.
receipt=json.loads(args.source_receipt.read_bytes())
assert isinstance(receipt['files'],dict) and len(receipt['files'])>1000
for name,row in receipt['files'].items():
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    origin=args.candidate_native/relative
    assert origin.is_file() and not origin.is_symlink()
    data=origin.read_bytes()
    assert hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']
    target=SOURCE/relative
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target.write_bytes(data)
    target.chmod(0o700 if row['mode']=='100755' else 0o600)
(HOME_FIXTURE/'hermes-agent.source.json').write_text(json.dumps(receipt))
(HOME_FIXTURE/'hermes-agent.source.json').chmod(0o600)
stamp={'commit':receipt['commit'],'dirty':True,'fridaySource':{'baseTree':receipt['base_tree'],'layers':receipt['layers']}}
(SOURCE/'install-stamp.json').write_text(json.dumps(stamp))
(SOURCE/'install-stamp.json').chmod(0o600)
os.umask(0o077)
os.environ.update(HERMES_HOME=str(HOME_FIXTURE), PYTHONDONTWRITEBYTECODE='1',
    HERMES_DISABLE_TELEMETRY='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', GIT_OPTIONAL_LOCKS='0',
    HERMES_GATEWAY_LOCK_DIR=str(HOME_FIXTURE/'native-locks'),
    XDG_STATE_HOME=str(HOME_FIXTURE/'xdg-state'), XDG_CACHE_HOME=str(HOME_FIXTURE/'xdg-cache'))
for k in list(os.environ):
    if k.startswith('HERMES_DASHBOARD_') or k in ('HERMES_SAFE_MODE','HERMES_BUNDLED_PLUGINS'):
        del os.environ[k]
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
for key, limit in ((resource.RLIMIT_CPU,150),(resource.RLIMIT_AS,1024*1024**2),
    (resource.RLIMIT_FSIZE,64*1024**2),(resource.RLIMIT_CORE,0)):
    resource.setrlimit(key,(limit,limit))
signal.alarm(200)
started = time.monotonic(); checks=[]
def sha(b): return hashlib.sha256(b).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v)); p.chmod(0o600)
def check(name,fn):
    t=time.monotonic()
    try: detail=fn(); checks.append(dict(name=name,state='PASS',seconds=time.monotonic()-t,detail=detail))
    except Exception as e:
        checks.append(dict(name=name,state='FAIL',seconds=time.monotonic()-t,error=str(e),traceback=traceback.format_exc()))
def refuses(fn):
    try: fn()
    except (ValueError,OSError,KeyError,TypeError): return
    raise AssertionError('unproved identity accepted')
for name in ('hermes_cli/friday_dashboard_owner.py','hermes_cli/web_routers/status.py'):
    shutil.copyfile((args.baseline_native if OLD else args.candidate_native)/name,SOURCE/name)
receipt=json.loads((HOME_FIXTURE/'hermes-agent.source.json').read_text())
for name,row in receipt['files'].items():
    if name in ('hermes_cli/friday_dashboard_owner.py','hermes_cli/web_routers/status.py'):
        row['sha256']=sha((SOURCE/name).read_bytes());row['bytes']=(SOURCE/name).stat().st_size
write(HOME_FIXTURE/'hermes-agent.source.json',receipt)
plugin=HOME_FIXTURE/'plugins/friday_rework/plugin.yaml'; plugin.parent.mkdir(parents=True,exist_ok=True)
plugin.write_text('name: fixture\n');plugin.chmod(0o600)
marker={'schema':'friday.native-install.v1','state':'INSTALLED_TEMPLATE_INCOMPLETE',
    'home':str(HOME_FIXTURE),'source':str(SOURCE),
    'source_receipt_sha256':sha((HOME_FIXTURE/'hermes-agent.source.json').read_bytes()),
    'plugin_files':{'plugins/friday_rework/plugin.yaml':sha(plugin.read_bytes())}}
write(HOME_FIXTURE/'FRIDAY-INSTALL.json',marker)
operator={'provider':'basic','user_id':'private-fixture-operator','org_id':''}
contract={'profile':'default','native_dashboard':{'operator':operator,'host':'127.0.0.1',
    'port':19876,'public_url':'http://127.0.0.1:19876'}}
write(HOME_FIXTURE/'FRIDAY-PROFILE.json',contract)
cfg={'dashboard':{'require_auth':True,'public_url':'http://127.0.0.1:19876',
    'basic_auth':{'username':operator['user_id'],'password':'fixture-password-only',
    'secret':'FIXTURE_ONLY_SECRET_NOT_A_REAL_CREDENTIAL'}},
    'plugins':{'enabled':['dashboard_auth/basic'],'disabled':[],
    'entries':{'friday_rework':{'settings':{'admin':{'enabled':True,'operators':[operator],'profiles':['default']}}}}}}
write(HOME_FIXTURE/'config.yaml',cfg)
sys.path.insert(0,str(SOURCE))
import socket
native_socket=socket.socket
class NoNetworkSocket(native_socket):
    def __init__(self,family=socket.AF_INET,*args,**kwargs):
        if family in (socket.AF_INET,socket.AF_INET6): raise RuntimeError('network forbidden in source tests')
        super().__init__(family,*args,**kwargs)
socket.socket=NoNetworkSocket
try:
    import asyncio, httpx, contextvars, threading, copy
    from starlette.requests import Request
    from hermes_cli import friday_dashboard_owner as owner
    from hermes_cli import plugins
    from hermes_cli.plugins_manifest import PluginManifest
    from hermes_cli.dashboard_auth import get_provider
    manager=plugins.get_plugin_manager()
    manifest=PluginManifest(name='basic',key='dashboard_auth/basic',source='bundled',
        path=str(SOURCE/'plugins/dashboard_auth/basic'))
    manager._load_plugin(manifest)
    provider=get_provider('basic')
    assert provider is not None, manager._plugins['dashboard_auth/basic'].error
    assert type(provider) is owner.registered_basic().BasicAuthProvider
    from hermes_cli import web_server as web
    from hermes_cli.web_routers import status
    from gateway import host_rendezvous as hr
    app=web.app
    app.state.auth_required=True;app.state.bound_host='127.0.0.1';app.state.bound_port=19876
    app.state.serves_spa=True;app.state.host_role=hr.ROLE_SERVE
    assert hr.claim_host_lock(hr.ROLE_SERVE)[0] is hr.HostLockOutcome.ACQUIRED
    app.state.friday_dashboard_owner=owner.expected(registered=True,auth_required=True,host='127.0.0.1',port=19876)
    assert owner.live_identity(app)==app.state.friday_dashboard_owner
    nonce='a'*32
    scans=[]; real_scan=owner._verify_source_files
    def scan(*args):
        t=time.monotonic();out=real_scan(*args);scans.append(time.monotonic()-t);return out
    owner._verify_source_files=scan
    headers={web._SESSION_HEADER_NAME:web._SESSION_TOKEN,'X-Hermes-Probe-Nonce':nonce}
    async def http(path='/api/host/identity',headers_=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://127.0.0.1:19876') as client:
            return await client.get(path,headers=headers if headers_ is None else headers_)
    def req(path='/api/host/identity',token=True,method='GET'):
        h=[(web._SESSION_HEADER_NAME.lower().encode(),web._SESSION_TOKEN.encode())] if token else []
        return Request({'type':'http','method':method,'path':path,'raw_path':path.encode(),
            'query_string':b'','headers':h,'scheme':'http','server':('127.0.0.1',19876),
            'client':('127.0.0.1',1),'app':app})
    def positive():
        samples=[]
        for i in range(3):
            scans.clear();t=time.monotonic();r=asyncio.run(http());elapsed=time.monotonic()-t
            assert r.status_code==200,(r.status_code,r.text)
            v=r.json();assert v['fridayOwner']==app.state.friday_dashboard_owner
            assert v['probeNonce']==nonce and v['ownerProof']==owner.proof_mac(v['fridayOwner'],nonce,v['pid'],v['startTime'],web._SESSION_TOKEN,provider._secret)
            assert set(v)=={'ok','probeNonce','ownerProof','protocolVersion','pid','startTime','role','servesSpa','auth_required','fridayOwner'}
            assert len(scans)==(3 if OLD else 2),len(scans)
            samples.append({'temperature':'first' if i==0 else 'warm','seconds':elapsed,'scans':len(scans),'scan_seconds':sum(scans)})
        return samples
    check('native_full_ASGI_response_JSON_MAC_and_complete_scan_count',positive)
    def no_nonce():
        scans.clear();r=asyncio.run(http(headers_={web._SESSION_HEADER_NAME:web._SESSION_TOKEN}));assert r.status_code==200
        assert 'ownerProof' not in r.json() and 'probeNonce' not in r.json() and len(scans)==2
    check('native_response_without_nonce_retains_JSON',no_nonce)
    def standalone():
        scans.clear();p=owner.identity_proof(app,nonce);assert len(scans)==1 and p['probeNonce']==nonce
        for bad in (None,'','B'*32,'a'*31,'a'*33):refuses(lambda bad=bad:owner.identity_proof(app,bad))
    check('standalone_identity_proof_fullcheck_and_invalid_nonce',standalone)
    def token_controls():
        for h in ({},{web._SESSION_HEADER_NAME:'wrong'}):
            scans.clear();r=asyncio.run(http(headers_=h));assert r.status_code in (401,403),r.status_code;assert not scans
        for r in (req('/api/status'),req(token=False),req(method='POST')):
            assert owner.identity_session(r) is False and getattr(r.state,'session',None) is None
    check('wrong_missing_token_and_other_route_do_not_mint_authority',token_controls)
    def mint_order():
        request=req();scans.clear();assert owner.identity_session(request);assert len(scans)==1
        assert request.state.session.user_id==operator['user_id']
        return {'complete_checks_before_mint':len(scans),'native_class':type(provider).__module__+'.'+type(provider).__qualname__}
    check('native_Basic_request_principal_after_full_validation',mint_order)
    def changed_file(path,data,action):
        old=path.read_bytes()
        try:path.write_bytes(data);return action()
        finally:path.write_bytes(old)
    def reject_source():
        p=SOURCE/'hermes_cli/friday_dashboard_owner.py'
        def action():
            request=req();refuses(lambda:owner.identity_session(request));assert getattr(request.state,'session',None) is None
            refuses(lambda:owner.identity_proof(app,nonce))
            r=asyncio.run(http());assert r.status_code==503,r.status_code
        changed_file(p,p.read_bytes()+b'\n# drift\n',action)
    check('tampered_source_refused_before_mint_standalone_and_HTTP',reject_source)
    def between_checks():
        p=SOURCE/'hermes_cli/friday_dashboard_owner.py';original=p.read_bytes();real_mint=provider._mint_session
        def mint(*a,**kw):
            out=real_mint(*a,**kw);p.write_bytes(original+b'\n# drift after auth\n');return out
        try:
            provider._mint_session=mint;r=asyncio.run(http());assert r.status_code==503,r.status_code
        finally:provider._mint_session=real_mint;p.write_bytes(original)
    check('source_drift_after_session_mint_refused_before_response_proof',between_checks)
    for name,filename,data in (
        ('config','config.yaml',b'{}'),('profile','FRIDAY-PROFILE.json',b'{}'),
        ('install_marker','FRIDAY-INSTALL.json',b'{}'),('source_receipt','hermes-agent.source.json',b'{}'),
        ('plugin','plugins/friday_rework/plugin.yaml',b'changed'),
        ('stamp','hermes-agent/install-stamp.json',b'{}')):
        def bad(name=name,filename=filename,data=data):
            def action():
                r=req();refuses(lambda:owner.identity_session(r));assert getattr(r.state,'session',None) is None
                refuses(lambda:owner.identity_proof(app,nonce))
            changed_file(HOME_FIXTURE/filename,data,action)
        check('current_'+name+'_tamper_refuses_authority_and_standalone',bad)
    def auth_controls():
        old=provider._secret
        try:provider._secret=b'CHANGED_FIXTURE_SECRET';refuses(lambda:owner.identity_proof(app,nonce))
        finally:provider._secret=old
        old=app.state.auth_required
        try:app.state.auth_required=False;refuses(lambda:owner.identity_proof(app,nonce))
        finally:app.state.auth_required=old
        loaded=manager._plugins['dashboard_auth/basic'];old=loaded.manifest.source
        try:loaded.manifest.source='user';refuses(lambda:owner.identity_proof(app,nonce))
        finally:loaded.manifest.source=old
    check('native_auth_secret_required_and_registered_class_origin',auth_controls)
    def boot_lock():
        old=app.state.friday_dashboard_owner
        try:app.state.friday_dashboard_owner=dict(old,profile='other');refuses(lambda:owner.identity_proof(app,nonce))
        finally:app.state.friday_dashboard_owner=old
        hr.release_host_lock(hr.ROLE_SERVE)
        try:refuses(lambda:owner.identity_proof(app,nonce))
        finally:assert hr.claim_host_lock(hr.ROLE_SERVE)[0] is hr.HostLockOutcome.ACQUIRED
    check('boot_identity_and_actual_native_lock_refuse',boot_lock)
    def isolation():
        assert owner._SOURCE_CHECKS.get() is None
        first=req();assert owner.identity_session(first);assert getattr(req().state,'session',None) is None
        p=SOURCE/'hermes_cli/friday_dashboard_owner.py'
        changed_file(p,p.read_bytes()+b'\n# cross request drift\n',lambda:refuses(lambda:owner.identity_proof(app,nonce)))
        with owner._source_check_scope():ctx=contextvars.copy_context()
        changed_file(p,p.read_bytes()+b'\n# closed context drift\n',lambda:refuses(lambda:ctx.run(owner.identity_proof,app,nonce)))
        assert owner._SOURCE_CHECKS.get() is None
    check('requests_and_copied_closed_context_never_share_validated_trust',isolation)
    def nonce_mac():
        a=owner.identity_proof(app,'a'*32);b=owner.identity_proof(app,'b'*32)
        assert a['ownerProof']!=b['ownerProof'] and a['probeNonce']!=b['probeNonce']
    check('nonce_is_bound_to_proof_without_reuse',nonce_mac)
    def malformed_nonce_http():
        samples=[]
        for bad in ('B'*32,'a'*31,'a'*33):
            r=asyncio.run(http(headers_={web._SESSION_HEADER_NAME:web._SESSION_TOKEN,'X-Hermes-Probe-Nonce':bad}))
            assert r.status_code==503,(r.status_code,r.text)
            assert 'set-cookie' not in r.headers and 'ownerProof' not in r.text and 'probeNonce' not in r.text
            assert operator['user_id'] not in r.text and cfg['dashboard']['basic_auth']['secret'] not in r.text
            assert web._SESSION_TOKEN not in r.text
            assert r.json()=={'detail':'Dashboard ownership changed'}
            samples.append(r.status_code)
        return {'statuses':samples,'proof_principal_cookie_or_role_token_returned':False}
    check('malformed_nonce_HTTP_original_failure_response_preserved_no_authority_leak',malformed_nonce_http)
    def import_boundary():
        prefixes=('hermes_cli','gateway','pm','hermes_constants','hermes_bootstrap')
        bad=[name for name,m in list(sys.modules.items()) if name.split('.')[0] in prefixes and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(SOURCE)]
        assert not bad,bad
        assert owner.SOURCE==SOURCE and str(status.__file__).startswith(str(SOURCE))
        return {'installed_source_modules_imported':len(bad),'private_native_source':str(SOURCE)}
    check('private_source_import_boundary',import_boundary)
    hr.release_host_lock(hr.ROLE_SERVE)
except Exception as e:
    checks.append(dict(name='native_fixture_bootstrap',state='FAIL',error=str(e),traceback=traceback.format_exc()))
finally:
    result={'state':'PASS_SOURCE_ONLY' if checks and all(c['state']=='PASS' for c in checks) else 'FAIL',
        'label':LABEL,'checks':checks,'elapsed_seconds':time.monotonic()-started,
        'scope':'Private actual source inventory, actual native Basic loader/class, actual native lock and native ASGI middleware/route. No lifespan/startup/service/bind, network, model or installed runtime acceptance.',
        'resources':{'affinity':sorted(os.sched_getaffinity(0)),'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}}
    write(HERE/('TESTS-'+LABEL.upper()+'.json'),result)
    print(json.dumps({'state':result['state'],'label':LABEL,'checks':len(checks),'failed':[c['name'] for c in checks if c['state']!='PASS'],'seconds':result['elapsed_seconds']}))
    sys.exit(0 if result['state']=='PASS_SOURCE_ONLY' else 1)
