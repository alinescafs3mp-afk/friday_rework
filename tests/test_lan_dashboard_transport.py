"""Actual TLS/native ownership consumers; certificates and transports are fixtures."""
import asyncio
import copy
from dataclasses import replace
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
from types import SimpleNamespace
import urllib.request

import pytest

from hermes_cli import friday_dashboard_tls as tls
from scripts import friday_install, friday_native
from test_native_installer import native_home, install_input
from test_native_dashboard_owner import installation, owner, record_owner
from test_product_profile import inputs
from tools.configure_product import compose_product

GUEST = '192.168.12.128'
PUBLIC = 'https://192.168.1.50:9119'  # Synthetic host; the real owner host is pending.


def spec():
    value = inputs()
    value['dashboard'].update(host=GUEST, public_url=PUBLIC, tls=dict(tls.FILES))
    return value


@pytest.fixture(scope='module')
def certificates(tmp_path_factory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import ipaddress
    folder = tmp_path_factory.mktemp('synthetic-certs'); folder.chmod(0o700)
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SYNTHETIC FIXTURE CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=2))
          .not_valid_after(now+datetime.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    def server(label, hosts, expired=False):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SYNTHETIC SERVER')])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=2))
            .not_valid_after(now-datetime.timedelta(days=1) if expired else now+datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(h)) for h in hosts]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        (folder/label).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    server('server.pem', [GUEST, '192.168.1.50'])
    server('wrong.pem', ['192.168.1.99'])
    server('public-only.pem', ['192.168.1.50'])
    server('guest-only.pem', [GUEST])
    server('expired.pem', [GUEST, '192.168.1.50'], expired=True)
    (folder/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for label, private in [('server.key', key), ('wrong.key', ca_key)]:
        (folder/label).write_bytes(private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    for p in folder.iterdir(): p.chmod(0o600)
    return folder


def pinned_inputs(folder):
    return {key: {'path': str(folder/Path(path).name),
                 'sha256': hashlib.sha256((folder/Path(path).name).read_bytes()).hexdigest()}
            for key, path in tls.FILES.items()}


def stage(home, certificates):
    value = {'home': str(home), 'product': spec(), 'dashboard_tls': pinned_inputs(certificates)}
    friday_native.stage_dashboard_tls(value, home)
    return value


@pytest.fixture
def tls_owner(record_owner, certificates, monkeypatch):
    owner = record_owner
    stage(owner.home, certificates)
    original = (owner.home/'FRIDAY-PROFILE.json').read_bytes()
    marker_path=owner.home/'FRIDAY-INSTALL.json'; original_marker=marker_path.read_bytes()
    marker=json.loads(original_marker);marker['tls_files']={path:hashlib.sha256((owner.home/path).read_bytes()).hexdigest() for path in tls.FILES.values()}
    marker_path.write_text(json.dumps(marker))
    contract = json.loads(original)
    contract['native_dashboard'].update(host=GUEST, public_url=PUBLIC, tls=dict(tls.FILES))
    (owner.home/'FRIDAY-PROFILE.json').write_text(json.dumps(contract))
    config = copy.deepcopy(owner.config)
    config['dashboard'].update(public_url=PUBLIC, tls=dict(tls.FILES))
    from hermes_cli.config import atomic_config_replace
    atomic_config_replace(owner.home/'config.yaml', config)
    monkeypatch.setattr(owner.ws.app.state, 'bound_host', GUEST)
    monkeypatch.setattr(owner.ws.app.state, 'bound_port', 9119)
    monkeypatch.setattr(owner.ws.app.state, 'trusted_public_hosts', frozenset({'192.168.1.50'}), raising=False)
    owner.boundary.prepare_start(owner.ws.app, GUEST, 9119)
    owner.ws._publish_host_rendezvous(GUEST, 9119)
    record = owner.hr.read_record('serve', include_stale=True)
    assert record.friday_owner['tls']['files'] == tls.FILES
    yield owner, record
    (owner.home/'FRIDAY-PROFILE.json').write_bytes(original)
    marker_path.write_bytes(original_marker)
    shutil.rmtree(owner.home/'dashboard-tls')


def test_normal_compiler_installer_and_native_profile_wire_tls(certificates, install_input, tmp_path):
    install_input['product'] = spec()
    install_input['dashboard_tls'] = pinned_inputs(certificates)
    commands = friday_install.commands(install_input)
    assert commands['dashboard'][-4:] == [GUEST, '--port', '9119', '--no-open']
    bundle = compose_product(spec())
    assert bundle['config']['dashboard']['tls'] == tls.FILES
    assert bundle['contract']['native_dashboard']['tls'] == tls.FILES
    assert 'dashboard' not in bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']['config']
    home = tmp_path/'fresh'; home.mkdir(mode=0o700)
    stage(home, certificates)
    with native_home(home):
        real = friday_native.profile_write(home, spec())
        assert friday_native.native_profile_check(real, home)['ready'] is False
    assert not bundle['contract']['ready']
    for p in (home/'dashboard-tls').iterdir(): assert p.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match='not_adopted'): stage(home, certificates)


@pytest.mark.parametrize('mutation', ['missing', 'http', 'port', 'path', 'all', 'ipv6-all', 'foreign-path', 'symlink', 'public-file', 'key-mismatch', 'wrong-san', 'public-only', 'guest-only', 'expired', 'bad-ca', 'encrypted-key', 'hardlink', 'foreign-owner'])
def test_tls_inputs_fail_closed(certificates, tmp_path, mutation, monkeypatch):
    home = tmp_path/'owned'; home.mkdir(mode=0o700)
    stage(home, certificates)
    value = dict(tls.FILES); host=GUEST; port=9119; url=PUBLIC
    folder = home/'dashboard-tls'
    if mutation == 'missing': (folder/'server.key').unlink()
    elif mutation == 'http': url=PUBLIC.replace('https:', 'http:')
    elif mutation == 'port': port=9120
    elif mutation == 'path': url=PUBLIC+'/other'
    elif mutation == 'all': host='0.0.0.0'
    elif mutation == 'ipv6-all': host='::'
    elif mutation == 'foreign-path': value['keyfile']=str(certificates/'server.key')
    elif mutation == 'symlink':
        (folder/'server.key').unlink(); (folder/'server.key').symlink_to(certificates/'server.key')
    elif mutation == 'public-file': (folder/'server.pem').chmod(0o644)
    elif mutation == 'key-mismatch': (folder/'server.key').write_bytes((certificates/'wrong.key').read_bytes())
    elif mutation in ('wrong-san','public-only','guest-only','expired'):
        filename={'wrong-san':'wrong.pem','public-only':'public-only.pem','guest-only':'guest-only.pem','expired':'expired.pem'}[mutation]
        (folder/'server.pem').write_bytes((certificates/filename).read_bytes())
    elif mutation == 'encrypted-key':
        from cryptography.hazmat.primitives import serialization
        key=serialization.load_pem_private_key((certificates/'server.key').read_bytes(),password=None)
        (folder/'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.BestAvailableEncryption(b'SYNTHETIC')))
    elif mutation == 'hardlink':
        os.link(folder/'server.key',folder/'second.key')
    elif mutation == 'foreign-owner':
        original=os.getuid;monkeypatch.setattr(os,'getuid',lambda:original()+1)
    elif mutation == 'bad-ca': (folder/'ca.pem').write_text('not a CA certificate')
    with pytest.raises((ValueError,OSError,ssl.SSLError)): tls.checked(home,value,host,port,url)


@pytest.mark.parametrize('mutation', ['absent', 'foreign-name', 'changed-pin', 'public-key', 'symlink-parent', 'unexpected'])
def test_normal_installer_requires_protected_pinned_deployment_inputs(install_input, certificates, tmp_path, mutation):
    install_input['product']=spec(); install_input['dashboard_tls']=pinned_inputs(certificates)
    if mutation=='absent': del install_input['dashboard_tls']
    elif mutation=='foreign-name': install_input['dashboard_tls']['keyfile']=dict(install_input['dashboard_tls']['certfile'])
    elif mutation=='changed-pin': install_input['dashboard_tls']['keyfile']['sha256']='0'*64
    elif mutation=='public-key':
        folder=tmp_path/'copy';shutil.copytree(certificates,folder);folder.chmod(0o700);(folder/'server.key').chmod(0o644)
        install_input['dashboard_tls']=pinned_inputs(folder)
    elif mutation=='symlink-parent':
        folder=tmp_path/'alias';folder.symlink_to(certificates);install_input['dashboard_tls']=pinned_inputs(folder)
    else: install_input['dashboard_tls']['foreign']={}
    with pytest.raises((ValueError,OSError)):friday_install.commands(install_input)


def test_real_uvicorn_configuration_loads_owned_tls_without_proxy(tls_owner):
    owner, record = tls_owner
    config, server = owner.ws._build_uvicorn_server(GUEST, 9119)
    assert config.host==GUEST and config.port==9119
    assert config.ssl_certfile==str(owner.home/'dashboard-tls/server.pem')
    assert config.ssl_keyfile==str(owner.home/'dashboard-tls/server.key')
    assert config.proxy_headers is False and config.forwarded_allow_ips==''
    config.load()
    assert config.is_ssl and config.ssl.minimum_version>=ssl.TLSVersion.TLSv1_2
    assert not server.started


@pytest.mark.parametrize('mutation', ['auth-off','config-tls-missing','contract-tls-missing','certificate-drift','foreign-listener','marker-tls-missing','marker-tls-drift'])
def test_native_identity_binds_transport_and_refuses_drift(tls_owner, mutation, monkeypatch, certificates):
    owner, record = tls_owner
    if mutation=='auth-off': monkeypatch.setattr(owner.ws.app.state,'auth_required',False)
    elif mutation=='config-tls-missing':
        from hermes_cli.config import atomic_config_replace
        config=copy.deepcopy(owner.config);config['dashboard']['public_url']=PUBLIC
        atomic_config_replace(owner.home/'config.yaml',config)
    elif mutation=='contract-tls-missing':
        p=owner.home/'FRIDAY-PROFILE.json';c=json.loads(p.read_text());del c['native_dashboard']['tls'];p.write_text(json.dumps(c))
    elif mutation=='certificate-drift':(owner.home/'dashboard-tls/server.pem').write_bytes((certificates/'wrong.pem').read_bytes())
    elif mutation.startswith('marker-tls'):
        p=owner.home/'FRIDAY-INSTALL.json';v=json.loads(p.read_text())
        if mutation=='marker-tls-missing':del v['tls_files']
        else:v['tls_files']['dashboard-tls/server.key']='0'*64
        p.write_text(json.dumps(v))
    else: record=replace(record,port=8443)
    with pytest.raises((ValueError,OSError,ssl.SSLError)):
        if mutation=='foreign-listener':owner.boundary.check_attachment(record)
        else:owner.boundary.live_identity(owner.ws.app)


@pytest.mark.parametrize('host,origin,scheme,allowed', [
    ('192.168.1.50:9119',PUBLIC,'https',True),('192.168.1.50:9119',None,'https',True),
    ('192.168.1.50:8443',PUBLIC,'https',False),('192.168.12.128:9119',PUBLIC,'https',False),
    ('192.168.1.51:9119',PUBLIC,'https',False),('192.168.1.50:9119','http://192.168.1.50:9119','https',False),
    ('192.168.1.50:9119',PUBLIC+'/other','https',False),('192.168.1.50:9119','null','https',False),
    ('192.168.1.50:9119',PUBLIC,'http',False)])
def test_real_http_and_websocket_authority_guard(tls_owner,host,origin,scheme,allowed):
    owner,record=tls_owner
    from starlette.requests import Request
    from starlette.websockets import WebSocket
    from hermes_cli.web_server_chat import _ws_host_origin_is_allowed
    headers=[(b'host',host.encode())]
    if origin:headers.append((b'origin',origin.encode()))
    scope={'type':'http','method':'GET','scheme':scheme,'path':'/api/host/identity','headers':headers,'query_string':b'','app':owner.ws.app,'server':(GUEST,9119),'client':('192.168.1.22',40000)}
    request=Request(scope)
    assert tls.request_allowed(request,record.friday_owner) is allowed
    async def run():
        async def next_handler(r):return SimpleNamespace(status_code=204)
        return await owner.ws.host_header_middleware(request,next_handler)
    assert asyncio.run(run()).status_code==(204 if allowed else 400)
    scope.update(type='websocket',scheme='wss' if scheme=='https' else 'ws')
    assert _ws_host_origin_is_allowed(WebSocket(scope, receive=lambda: None, send=lambda x: None)) is allowed


def test_actual_identity_https_request_context_host_nonce_and_response(tls_owner,monkeypatch):
    owner,record=tls_owner
    import socket,httpx
    seen=[]
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:Conn())
    original_build=urllib.request.build_opener
    def build(*handlers):
        actual=original_build(*handlers)
        https=[h for h in actual.handlers if isinstance(h,urllib.request.HTTPSHandler)][0]
        assert https._context.check_hostname and https._context.verify_mode==ssl.CERT_REQUIRED
        assert https._context.cert_store_stats()['x509_ca']==1
        assert not any(isinstance(h,urllib.request.ProxyHandler) and h.proxies for h in actual.handlers)
        def opened(request,timeout):
            seen.append(request)
            assert request.full_url==f'https://{GUEST}:9119/api/host/identity'
            assert request.get_header('Host')=='192.168.1.50:9119'
            assert request.get_header('Authorization') is None
            assert request.get_header('X-hermes-probe-nonce')
            async def run():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owner.ws.app),base_url=f'https://{GUEST}:9119') as client:
                    return await client.get('/api/host/identity',headers=dict(request.header_items()))
            response=asyncio.run(run());assert response.status_code==200
            class Answer:
                status=200
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self,limit):return response.content[:limit]
            return Answer()
        actual.open=opened;return actual
    monkeypatch.setattr(urllib.request,'build_opener',build)
    monkeypatch.setenv('HTTPS_PROXY','http://foreign.invalid:8000')
    payload=owner.hr.probe_owner(record)
    assert payload is not None;owner.boundary.check_attachment(record,payload)
    assert payload['fridayOwner']==record.friday_owner and len(seen)==1
    assert tls.public_url(record.friday_owner,'foo/bar')==PUBLIC+'/?profile=foo%2Fbar'


@pytest.mark.parametrize('mutation', ['foreign-port','wrong-cert','redirect','response-proof'])
def test_tls_identity_client_rejects_foreign_certificate_redirect_and_body(tls_owner,monkeypatch,mutation,certificates):
    owner,record=tls_owner
    import socket
    called=[]
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:Conn())
    def opened(self,request,timeout):
        called.append(request)
        if mutation=='redirect':
            tls.NoRedirect().redirect_request(request,None,302,'redirect',{},'https://foreign.invalid:9119')
        class Answer:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,limit):return json.dumps({'role':'serve','pid':record.pid,'probeNonce':request.get_header('X-hermes-probe-nonce'),'ownerProof':'0'*64}).encode()
        return Answer()
    monkeypatch.setattr(urllib.request.OpenerDirector,'open',opened)
    if mutation=='foreign-port':record=replace(record,port=8443)
    if mutation=='wrong-cert':(owner.home/'dashboard-tls/server.pem').write_bytes((certificates/'wrong.pem').read_bytes())
    assert owner.hr.probe_owner(record) is None
    assert len(called)==(0 if mutation in ('foreign-port','wrong-cert') else 1)


def test_plugin_activation_verifies_owner_before_https_request(tls_owner,monkeypatch):
    owner,record=tls_owner
    from hermes_cli import plugins_activation
    seen=[]
    monkeypatch.setattr(plugins_activation,'_serve_backend_record',lambda:record)
    monkeypatch.setattr(owner.hr,'probe_owner',lambda r:seen.append('verified') or {'verified':True})
    def opened(self,request,timeout):
        assert seen==['verified'];seen.append(request.full_url)
        assert request.full_url==f'https://{GUEST}:9119/api/dashboard/agent-plugins/activate'
        assert request.get_header('Host')=='192.168.1.50:9119'
        class Answer:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):return b'{"fixture": true}'
        return Answer()
    monkeypatch.setattr(urllib.request.OpenerDirector,'open',opened)
    assert plugins_activation.notify_serve_backend('synthetic-plugin',owner.home)=={'fixture':True}
    monkeypatch.setattr(owner.hr,'probe_owner',lambda r:None)
    assert plugins_activation.notify_serve_backend('synthetic-plugin',owner.home) is None
    assert len(seen)==2


def test_actual_cli_attach_and_browser_use_public_https_authority(tls_owner,monkeypatch,capsys):
    owner,record=tls_owner
    from hermes_cli import main_dashboard as cli
    from hermes_cli import web_server_lifecycle as lifecycle
    import threading,time,webbrowser
    payload={'protocolVersion':1,'pid':record.pid,'startTime':record.start_time,'role':'serve',
             'auth_required':True,'servesSpa':True,'fridayOwner':record.friday_owner}
    payload.update(owner.boundary.identity_proof(owner.ws.app,'1'*32))
    monkeypatch.setattr(owner.hr,'probe_owner',lambda r:payload)
    monkeypatch.setattr(cli,'_host_backend_attachment',lambda:record)
    monkeypatch.setattr(cli,'_explicit_endpoint_flags',lambda:set())
    opened=[];monkeypatch.setattr(webbrowser,'open',lambda url:opened.append(url))
    args=SimpleNamespace(host=GUEST,port=9119,isolated=False,open_profile='',no_open=False)
    with pytest.raises(SystemExit) as stopped:cli._attach_to_host_backend(args,False)
    assert stopped.value.code==0 and opened==[PUBLIC+'/?profile=default']
    assert PUBLIC in capsys.readouterr().out
    class Immediate:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(threading,'Thread',Immediate)
    monkeypatch.setattr(time,'sleep',lambda _:None)
    monkeypatch.setenv('DISPLAY','SYNTHETIC_ONLY')
    lifecycle._maybe_open_browser(GUEST,9119,True,'default')
    assert opened==[PUBLIC+'/?profile=default']*2


def test_native_activation_retains_real_route_and_auth_refusal(tls_owner):
    owner,record=tls_owner
    import httpx
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owner.ws.app),base_url=PUBLIC) as client:
            role=await client.post('/api/dashboard/agent-plugins/activate',json={'name':'synthetic','home':str(owner.home)},
                headers={'X-Hermes-Session-Token':owner.hr.read_token('serve')})
            login=owner.provider.complete_password_login(username=owner.provider._username,password='FIXTURE_PASSWORD_ONLY')
            authenticated=await client.post('/api/dashboard/agent-plugins/activate',json={'name':'synthetic','home':str(owner.home)},
                headers={'Authorization':'Bearer '+login.access_token})
            return role,authenticated
    role,authenticated=asyncio.run(run())
    assert role.status_code==401 and authenticated.status_code==403


def test_installer_refuses_certificate_input_drift_between_pin_and_read(certificates,tmp_path,monkeypatch):
    folder=tmp_path/'input';shutil.copytree(certificates,folder);folder.chmod(0o700)
    value={'product':spec(),'dashboard_tls':pinned_inputs(folder)}
    home=tmp_path/'fresh';home.mkdir(mode=0o700)
    original_pin=friday_install.pin
    def drift(row):
        path=original_pin(row)
        if path.name=='server.key':path.write_bytes(b'SYNTHETIC DRIFT AFTER PIN VALIDATION')
        return path
    monkeypatch.setattr(friday_install,'pin',drift)
    with pytest.raises(ValueError,match='input_changed'):friday_native.stage_dashboard_tls(value,home)
    assert not (home/'dashboard-tls').exists()
