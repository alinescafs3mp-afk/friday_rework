"""Actual pinned native ownership consumers, offline; no runtime acceptance."""
import asyncio
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from scripts import friday_native
from test_native_installer import native_home
from test_product_profile import inputs


@pytest.fixture(scope='module')
def installation(tmp_path_factory):
    home = tmp_path_factory.mktemp('dashboard-owner'); home.chmod(0o700)
    source = home / 'hermes-agent'
    frozen = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']) / 'native'
    shutil.copytree(frozen, source)
    files = {str(p.relative_to(source)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'bytes': p.stat().st_size, 'mode': '100755' if p.stat().st_mode & 0o111 else '100644'}
             for p in source.rglob('*') if p.is_file()}
    receipt = {'schema': 'friday.hermes-source.v1', 'status': 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED',
               'commit': 'a' * 40, 'base_tree': 'b' * 40, 'layers': [], 'files': files}
    def publish(p, value):
        p.write_text(json.dumps(value)); p.chmod(0o600)
    publish(home / 'hermes-agent.source.json', receipt)
    publish(source / 'install-stamp.json', {'commit': 'a' * 40, 'dirty': True,
              'fridaySource': {'baseTree': 'b' * 40, 'layers': []}})
    with native_home(home):
        bundle = friday_native.profile_write(home, inputs())
    from plugins.dashboard_auth.basic import hash_password
    config = bundle['config']; config['dashboard']['basic_auth'].update(
        password_hash=hash_password('FIXTURE_PASSWORD_ONLY'), secret='FIXTURE_SIGNING_SECRET_32_BYTES_LONG')
    target = home / 'plugins/friday_rework'
    shutil.copytree(friday_native.ROOT / 'plugins/friday_rework', target)
    plugin_files = {}
    for p in target.rglob('*'):
        if p.is_dir(): p.chmod(0o700)
        else:
            p.chmod(0o600); plugin_files[str(p.relative_to(home))] = hashlib.sha256(p.read_bytes()).hexdigest()
    publish(home / 'FRIDAY-INSTALL.json', {'schema': 'friday.native-install.v1',
        'state': 'INSTALLED_TEMPLATE_INCOMPLETE', 'home': str(home), 'source': str(source),
        'source_receipt_sha256': hashlib.sha256((home / 'hermes-agent.source.json').read_bytes()).hexdigest(),
        'plugin_files': plugin_files})
    from hermes_cli.friday_dashboard_owner import source_identity
    verified = source_identity(home, source=source)
    return home, source, config, verified


@pytest.fixture
def owner(installation, monkeypatch):
    home, source, config, verified = installation
    from hermes_cli import friday_dashboard_owner as boundary
    from hermes_cli.config import atomic_config_replace
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from plugins.dashboard_auth import basic
    from gateway import host_rendezvous as hr, status
    monkeypatch.setattr(boundary, 'SOURCE', source)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(status, '_get_lock_dir', lambda: home / 'host-locks')
    for key in list(os.environ):
        if key.startswith('HERMES_DASHBOARD_') or key.startswith('HERMES_DESKTOP'):
            monkeypatch.delenv(key)
    (home / '.env').unlink(missing_ok=True)
    (home / 'host-locks').mkdir(mode=0o700, exist_ok=True)
    with native_home(home):
        atomic_config_replace(home / 'config.yaml', copy.deepcopy(config))
        clear_providers(); provider = basic.BasicAuthProvider(**basic._settings()); register_provider(provider)
        from hermes_cli import web_server as ws
        monkeypatch.setattr(ws.app.state, 'auth_required', True, raising=False)
        monkeypatch.setattr(ws.app.state, 'bound_host', '127.0.0.1', raising=False)
        monkeypatch.setattr(ws.app.state, 'bound_port', 9119, raising=False)
        monkeypatch.setattr(ws.app.state, 'host_role', 'serve', raising=False)
        monkeypatch.setattr(ws.app.state, 'serves_spa', True, raising=False)
        monkeypatch.setattr(ws.app.state, 'friday_dashboard_owner', None, raising=False)
        yield SimpleNamespace(home=home, source=source, boundary=boundary, hr=hr,
                              provider=provider, ws=ws, config=copy.deepcopy(config))
        hr.clear_record('serve'); hr.release_host_lock('serve'); clear_providers()


@pytest.fixture
def record_owner(owner, installation, monkeypatch):
    verified = installation[3]
    monkeypatch.setattr(owner.boundary, 'source_identity', lambda *a, **kw: copy.deepcopy(verified))
    return owner


def published(owner):
    owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119)
    owner.ws._publish_host_rendezvous('127.0.0.1', 9119)
    record = owner.hr.read_record('serve', include_stale=True)
    assert record is not None and owner.hr.owns_host_lock('serve')
    return record


def proof(owner):
    value = {'protocolVersion': 1, 'pid': os.getpid(),
            'startTime': owner.hr.read_record('serve').start_time,
            'role': 'serve', 'auth_required': True, 'servesSpa': True,
            'fridayOwner': owner.boundary.live_identity(owner.ws.app)}
    value.update(owner.boundary.identity_proof(owner.ws.app, '1' * 32))
    return value


def test_actual_native_lock_publication_and_matching_authenticated_identity(owner):
    record = published(owner); payload = proof(owner)
    assert owner.hr.HostRecord.from_json(record.to_json()) == record
    owner.boundary.check_attachment(record, payload)
    assert record.home == str(owner.home) and record.friday_owner['source']['root'] == str(owner.source)
    assert 'FIXTURE_PASSWORD_ONLY' not in json.dumps(record.to_json())
    assert 'FIXTURE_SIGNING_SECRET' not in json.dumps(payload)


@pytest.mark.parametrize('field,value', [('home', '/tmp/foreign'), ('profiles', ('other',)),
    ('start_time', None), ('start_time', 1), ('protocol_version', 0), ('host', '0.0.0.0'),
    ('port', 1), ('friday_owner', None), ('pid', 99999999), ('token_fingerprint', '')])
def test_foreign_or_unproved_native_record_refused(record_owner, field, value):
    owner = record_owner
    record = published(owner)
    with pytest.raises(ValueError): owner.boundary.check_attachment(replace(record, **{field: value}))


@pytest.mark.parametrize('field,value', [('protocolVersion', 0), ('pid', 99999999),
    ('startTime', 1), ('role', 'gateway'), ('auth_required', False), ('servesSpa', False),
    ('fridayOwner', {})])
def test_actual_native_probe_payload_requires_incarnation_auth_and_source(record_owner, field, value):
    owner = record_owner
    record = published(owner); payload = proof(owner); payload[field] = value
    with pytest.raises(ValueError): owner.boundary.check_attachment(record, payload)


@pytest.mark.parametrize('mutation', ['source', 'operator', 'profile', 'home', 'auth'])
def test_matching_editable_record_labels_cannot_replace_live_proof(record_owner, mutation):
    owner = record_owner
    record = published(owner); identity = copy.deepcopy(record.friday_owner)
    if mutation == 'source': identity['source']['receipt'] = '0' * 64
    elif mutation == 'operator': identity['operator']['user_id'] = 'foreign'
    elif mutation == 'profile': identity['profile'] = 'other'
    elif mutation == 'home': identity['home'] = '/tmp/foreign'
    else: identity['authBinding'] = '0' * 64
    with pytest.raises(ValueError): owner.boundary.check_attachment(replace(record, friday_owner=identity))


def test_recycled_pid_is_stale_but_missing_incarnation_is_never_adopted(record_owner):
    owner = record_owner
    record = published(owner)
    assert owner.hr.record_is_stale(replace(record, start_time=1))
    with pytest.raises(ValueError): owner.boundary.check_attachment(replace(record, start_time=None))
    # A provably stale native file remains intact until its existing owner cleans it.
    assert owner.hr.read_record('serve', include_stale=True) == record


@pytest.mark.parametrize('mutation', ['auth_off', 'wrong_provider', 'wrong_operator', 'wrong_secret', 'wrong_password'])
def test_actual_registered_basic_provider_and_gate_required(record_owner, mutation, monkeypatch):
    owner = record_owner
    if mutation == 'auth_off': monkeypatch.setattr(owner.ws.app.state, 'auth_required', False)
    elif mutation == 'wrong_provider':
        from hermes_cli import dashboard_auth
        monkeypatch.setattr(dashboard_auth, 'get_provider', lambda *a: SimpleNamespace(name='basic'))
    elif mutation == 'wrong_operator': monkeypatch.setattr(owner.provider, '_username', 'foreign')
    elif mutation == 'wrong_secret': monkeypatch.setattr(owner.provider, '_secret', b'FOREIGN_SECRET_CANARY')
    else: monkeypatch.setattr(owner.provider, '_password_hash', 'invalid')
    with pytest.raises(ValueError): owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119)
    assert not owner.hr.owns_host_lock('serve')


@pytest.mark.parametrize('flag', ['isolated', 'headless', 'ssh'])
def test_alternative_topology_cannot_skip_native_owner_boundary(record_owner, flag):
    owner = record_owner
    with pytest.raises(ValueError):
        owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119, **{flag: True})
    assert not owner.hr.owns_host_lock('serve')


@pytest.mark.parametrize('field', ['config', 'source', 'stamp', 'receipt'])
def test_actual_bytes_tamper_refuses_even_with_unchanged_receipt_label(owner, field):
    path = {'config': owner.home / 'config.yaml', 'source': owner.source / 'hermes_constants.py',
            'stamp': owner.source / 'install-stamp.json',
            'receipt': owner.home / 'hermes-agent.source.json'}[field]
    old = path.read_bytes()
    try:
        path.write_bytes(old + (b'\nforeign_data = True\n' if field == 'source' else b'\ninvalid'))
        with pytest.raises((ValueError, KeyError, TypeError)):
            owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119)
        assert not owner.hr.owns_host_lock('serve')
    finally: path.write_bytes(old)


def test_new_importable_source_not_declared_by_complete_inventory_refused(owner):
    path = owner.source / 'hermes_cli/foreign.py'; path.write_text('foreign = True\n')
    try:
        with pytest.raises(ValueError): owner.boundary.expected()
    finally: path.unlink()


@pytest.mark.parametrize('suffix', ['USERNAME', 'PASSWORD', 'PASSWORD_HASH', 'SECRET'])
def test_ambient_auth_override_not_scoped_to_home_refused(record_owner, suffix, monkeypatch):
    owner = record_owner
    monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_' + suffix, 'FOREIGN_CREDENTIAL_CANARY')
    with pytest.raises(ValueError): owner.boundary.expected()


def test_protected_native_plaintext_secret_capture_is_supported(record_owner, monkeypatch):
    owner = record_owner
    from plugins.dashboard_auth import basic
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    path = owner.home / '.env'; path.write_text('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=FIXTURE_NEW_PASSWORD\n'); path.chmod(0o600)
    monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', 'FIXTURE_NEW_PASSWORD')
    clear_providers(); register_provider(basic.BasicAuthProvider(**basic._settings()))
    record = published(owner)
    owner.boundary.check_attachment(record, proof(owner))
    assert 'FIXTURE_NEW_PASSWORD' not in json.dumps(record.to_json())


def test_native_cli_matching_owner_attaches_after_authenticated_probe(record_owner, monkeypatch):
    owner = record_owner
    from hermes_cli import main_dashboard as cli
    record = published(owner); payload = proof(owner); calls = []
    monkeypatch.setattr(owner.hr, 'probe_owner', lambda r: calls.append(r) or payload)
    args = SimpleNamespace(host='127.0.0.1', port=9119, isolated=False, no_open=True, open_profile='')
    with pytest.raises(SystemExit) as exc: cli._attach_to_host_backend(args, False)
    assert exc.value.code == 0 and calls == [record]


def test_native_cli_foreign_owner_refuses_before_probe(record_owner, monkeypatch):
    owner = record_owner
    from hermes_cli import main_dashboard as cli
    record = published(owner); calls = []
    monkeypatch.setattr(cli, '_host_backend_attachment', lambda: replace(record, home='/tmp/foreign'))
    monkeypatch.setattr(owner.hr, 'probe_owner', lambda *a: calls.append(a))
    args = SimpleNamespace(host='127.0.0.1', port=9119, isolated=False, no_open=True, open_profile='')
    with pytest.raises(SystemExit) as exc: cli._attach_to_host_backend(args, False)
    assert exc.value.code == 78
    assert calls == []


def test_native_cli_record_replacement_during_probe_refuses_attach(record_owner, monkeypatch):
    owner = record_owner
    from hermes_cli import main_dashboard as cli
    record = published(owner); payload = proof(owner)
    def raced(r):
        owner.hr.publish_record('serve', host='127.0.0.1', port=9119, profiles=('default',),
            home='/tmp/foreign', token='SYNTHETIC_REPLACEMENT_TOKEN')
        return payload
    monkeypatch.setattr(owner.hr, 'probe_owner', raced)
    args = SimpleNamespace(host='127.0.0.1', port=9119, isolated=False, no_open=True, open_profile='')
    with pytest.raises(SystemExit) as exc: cli._attach_to_host_backend(args, False)
    assert exc.value.code == 78


def test_native_start_claims_lock_before_uvicorn_and_releases_on_setup_failure(record_owner, monkeypatch):
    owner = record_owner
    from hermes_cli import resource_limits, nous_auth_keepalive
    monkeypatch.setattr(resource_limits, 'apply_nofile_soft_limit', lambda: None)
    monkeypatch.setattr(nous_auth_keepalive, 'start_nous_auth_keepalive', lambda: None)
    observed = []
    def stop_before_bind(*a, **kw):
        observed.append(owner.hr.owns_host_lock('serve'))
        raise RuntimeError('FIXTURE_STOP_BEFORE_ANY_BIND')
    monkeypatch.setattr(owner.ws, '_build_uvicorn_server', stop_before_bind)
    with pytest.raises(RuntimeError, match='FIXTURE_STOP_BEFORE_ANY_BIND'):
        owner.ws.start_server(host='127.0.0.1', port=9119, open_browser=False)
    assert observed == [True] and not owner.hr.owns_host_lock('serve')


def test_native_start_lock_contention_refuses_before_build_or_bind(record_owner, monkeypatch):
    owner = record_owner
    monkeypatch.setattr(owner.hr, 'claim_host_lock', lambda *a: (owner.hr.HostLockOutcome.HELD_BY_OTHER, None))
    calls = []; monkeypatch.setattr(owner.ws, '_build_uvicorn_server', lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError): owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119)
    assert calls == [] and getattr(owner.ws.app.state, 'friday_dashboard_owner', None) is None


def test_actual_native_identity_route_refuses_source_drift(owner):
    from hermes_cli.web_routers import status
    from fastapi import HTTPException
    published(owner)
    request = SimpleNamespace(app=owner.ws.app, state=SimpleNamespace(
        session=owner.provider.complete_password_login(username=owner.provider._username, password='FIXTURE_PASSWORD_ONLY')), headers={'x-hermes-probe-nonce': '1' * 32})
    out = asyncio.run(status.get_host_identity(request))
    assert out == proof(owner) | {'ok': True}
    path = owner.source / 'hermes_constants.py'; old = path.read_bytes()
    try:
        path.write_bytes(old + b'\nchanged = True\n')
        with pytest.raises(HTTPException) as exc: asyncio.run(status.get_host_identity(request))
        assert exc.value.status_code == 503
    finally: path.write_bytes(old)


def test_narrow_installer_source_check_keeps_runtime_and_credentials_unverified(owner):
    value = friday_native.dashboard_source_check(owner.home)
    assert value['ready'] is False and value['credentials_checked'] is False
    assert value['identity']['source']['root'] == str(owner.source)


def test_real_native_basic_gate_identity_and_cross_principal_denial(record_owner):
    owner = record_owner
    import httpx
    owner.ws._configure_auth_gate('127.0.0.1', False, None, None)
    published(owner)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owner.ws.app),
                                    base_url='http://127.0.0.1:9119') as client:
            anonymous = await client.get('/api/host/identity')
            foreign = owner.provider._mint_session('FOREIGN_ORDINARY_PRINCIPAL')
            denied = await client.get('/api/host/identity',
                                      headers={'Authorization': 'Bearer ' + foreign.access_token})
            session = owner.provider.complete_password_login(
                username=owner.provider._username, password='FIXTURE_PASSWORD_ONLY')
            accepted = await client.get('/api/host/identity',
                                       headers={'Authorization': 'Bearer ' + session.access_token, 'X-Hermes-Probe-Nonce': '1' * 32})
        return anonymous, denied, accepted
    anonymous, denied, accepted = asyncio.run(exercise())
    assert anonymous.status_code == 401 and denied.status_code == 403
    assert accepted.status_code == 200 and accepted.json() == proof(owner) | {'ok': True}


def test_actual_native_probe_private_ipc_and_basic_state_through_real_asgi_gate(record_owner, monkeypatch):
    owner = record_owner
    import httpx, socket, urllib.request
    owner.ws._configure_auth_gate('127.0.0.1', False, None, None)
    record = published(owner); calls = []
    class Connect:
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def connection(address, *, timeout):
        calls.append({'address': address, 'timeout': timeout}); return Connect()
    monkeypatch.setattr(socket, 'create_connection', connection)
    class Answer:
        status = 200
        def __init__(self, response): self.response = response
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, limit): return self.response.content[:limit]
    def request(req, *, timeout):
        assert not any(k.lower() == 'authorization' for k in dict(req.header_items()))
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owner.ws.app),
                                        base_url='http://127.0.0.1:9119') as client:
                return await client.get('/api/host/identity', headers=dict(req.header_items()))
        response = asyncio.run(exercise())
        assert response.status_code == 200
        return Answer(response)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, *a, **kw: request(*a, **kw))
    payload = owner.hr.probe_owner(record)
    owner.boundary.check_attachment(record, payload)
    expected = proof(owner) | {'ok': True}
    expected.update(owner.boundary.identity_proof(owner.ws.app, payload['probeNonce']))
    assert payload == expected
    assert calls == [{'address': ('127.0.0.1', 9119), 'timeout': 2.0}]


@pytest.mark.parametrize('change', ['public_url', 'admin_off', 'admin_operator', 'admin_profiles'])
def test_runtime_authority_config_cannot_override_declared_operator(record_owner, change, monkeypatch):
    owner = record_owner
    from hermes_cli.config import atomic_config_replace
    cfg = copy.deepcopy(owner.config)
    if change == 'public_url': monkeypatch.setenv('HERMES_DASHBOARD_PUBLIC_URL', 'https://foreign.example:9119')
    else:
        admin = cfg['plugins']['entries']['friday_rework']['settings']['admin']
        if change == 'admin_off': admin['enabled'] = False
        elif change == 'admin_operator': admin['operators'][0]['user_id'] = 'FOREIGN_PRINCIPAL'
        else: admin['profiles'] = ['other']
        atomic_config_replace(owner.home / 'config.yaml', cfg)
    with pytest.raises(ValueError): owner.boundary.expected()


def test_native_postbind_failure_shuts_down_before_host_lock_release(record_owner, monkeypatch):
    owner = record_owner
    from hermes_cli import resource_limits, nous_auth_keepalive
    from tui_gateway import launch_profile_policy, server as tui_server
    monkeypatch.setattr(resource_limits, 'apply_nofile_soft_limit', lambda: None)
    monkeypatch.setattr(nous_auth_keepalive, 'start_nous_auth_keepalive', lambda: None)
    monkeypatch.setattr(tui_server, 'install_exit_flush_signal_handlers', lambda: None)
    monkeypatch.setattr(launch_profile_policy, 'activate_multi_profile_hosting_eagerly', lambda: None)
    monkeypatch.setattr(owner.ws, '_port_bind_conflict', lambda *a: False)
    observations = []
    class Server:
        should_exit = False
        started = False
        def capture_signals(self):
            class Capture:
                def __enter__(self): pass
                def __exit__(self, *a): observations.append(('capture-exit', owner.hr.owns_host_lock('serve')))
            return Capture()
        async def startup(self): self.started = True; observations.append(('startup', owner.hr.owns_host_lock('serve')))
        async def main_loop(self): raise AssertionError('must not enter loop after failure')
        async def shutdown(self): observations.append(('shutdown', owner.hr.owns_host_lock('serve'))); self.started = False
    config = SimpleNamespace(loaded=True, lifespan_class=lambda c: object())
    server = Server()
    monkeypatch.setattr(owner.ws, '_build_uvicorn_server', lambda *a, **kw: (config, server))
    def failed(*a, **kw): raise RuntimeError('FIXTURE_PUBLISH_FAILURE')
    monkeypatch.setattr(owner.ws, '_on_server_started', failed)
    with pytest.raises(RuntimeError, match='FIXTURE_PUBLISH_FAILURE'):
        owner.ws.start_server(host='127.0.0.1', port=9119, open_browser=False)
    assert observations == [('startup', True), ('shutdown', True), ('capture-exit', False)]
    assert not owner.hr.owns_host_lock('serve') and not server.started


def test_stale_native_record_does_not_prevent_new_exclusive_owner(owner, monkeypatch):
    from hermes_cli import main_dashboard as cli
    old = owner.hr.HostRecord(role='serve', pid=99999999, create_time=None, start_time=1,
        host='127.0.0.1', port=9119, protocol_version=1, token_fingerprint='', profiles=('default',),
        updated_at='synthetic-stale', home='/tmp/foreign')
    owner.hr.record_path('serve').write_text(json.dumps(old.to_json()))
    calls = []; monkeypatch.setattr(owner.hr, 'probe_owner', lambda *a: calls.append(a))
    args = SimpleNamespace(host='127.0.0.1', port=9119, isolated=False, no_open=True, open_profile='')
    assert cli._attach_to_host_backend(args, False) is None and calls == []
    current = published(owner)
    assert current.pid == os.getpid() and current.home == str(owner.home)


@pytest.mark.parametrize('kind', ['plugin', 'plugin_extra', 'marker'])
def test_complete_friday_plugin_and_install_state_are_actual_source_inputs(owner, kind):
    target = owner.home / 'plugins/friday_rework'
    path = target / 'plugin.yaml' if kind == 'plugin' else target / 'foreign.py' if kind == 'plugin_extra' else owner.home / 'FRIDAY-INSTALL.json'
    old = path.read_bytes() if path.exists() else None
    try:
        path.write_bytes((old or b'') + b'\nchanged = True\n')
        with pytest.raises((ValueError, KeyError, TypeError)): owner.boundary.expected()
    finally:
        if old is None: path.unlink()
        else: path.write_bytes(old)


def test_actual_native_flock_contention_refuses_without_reaping_or_second_lock(record_owner):
    owner = record_owner
    from gateway.status import _try_acquire_file_lock, _release_file_lock
    # Two open file descriptions exercise real kernel flock contention in one
    # bounded fixture process; no process or alternative lock root is created.
    with owner.hr.lock_path('serve').open('a+') as holder:
        assert _try_acquire_file_lock(holder)
        try:
            with pytest.raises(ValueError): owner.boundary.prepare_start(owner.ws.app, '127.0.0.1', 9119)
            assert not owner.hr.owns_host_lock('serve')
            assert not owner.hr.record_path('serve').exists()
        finally: _release_file_lock(holder)
    assert published(owner).pid == os.getpid()


def test_unmarked_donor_preserves_native_cli_attach_behavior(owner, tmp_path, monkeypatch):
    from hermes_cli import main_dashboard as cli
    home = tmp_path / 'ordinary'; home.mkdir(mode=0o700)
    monkeypatch.setattr(owner.boundary, 'SOURCE', home / 'hermes-agent')
    monkeypatch.setenv('HERMES_HOME', str(home))
    record = owner.hr.HostRecord(role='serve', pid=os.getpid(), create_time=None,
        host='127.0.0.1', port=9119, protocol_version=1, token_fingerprint='',
        profiles=('default',), updated_at='synthetic', home=str(home), start_time=None)
    monkeypatch.setattr(cli, '_host_backend_attachment', lambda: record)
    monkeypatch.setattr(owner.hr, 'probe_owner', lambda r: {'pid': r.pid, 'role': 'serve', 'servesSpa': True})
    args = SimpleNamespace(host='127.0.0.1', port=9119, isolated=False, no_open=True, open_profile='')
    with native_home(home):
        assert owner.boundary.enabled() is False
        with pytest.raises(SystemExit) as exc: cli._attach_to_host_backend(args, False)
        assert exc.value.code == 0



def test_narrow_installer_checks_native_helper_before_executing_its_bytes(owner):
    path = owner.source / 'hermes_cli/friday_dashboard_owner.py'; old = path.read_bytes()
    try:
        path.write_bytes(old + b"\nraise AssertionError('UNPINNED_NATIVE_HELPER_EXECUTED')\n")
        with pytest.raises(ValueError, match='native_dashboard_source_code_changed'):
            friday_native.dashboard_source_check(owner.home)
    finally: path.write_bytes(old)



def test_friday_publication_does_not_unlock_from_signal_prehandler(record_owner, monkeypatch):
    owner = record_owner; calls = []
    monkeypatch.setattr(owner.hr, 'cleanup_on_exit', lambda *a: calls.append(a))
    published(owner)
    assert calls == [] and owner.hr.owns_host_lock('serve')



@pytest.mark.parametrize('failure', ['startup', 'shutdown'])
def test_unknown_native_stop_retains_host_lock_until_existing_owner_reconciles(record_owner, monkeypatch, failure):
    owner = record_owner
    from contextlib import nullcontext
    from hermes_cli import resource_limits, nous_auth_keepalive
    from tui_gateway import launch_profile_policy, server as tui_server
    monkeypatch.setattr(resource_limits, 'apply_nofile_soft_limit', lambda: None)
    monkeypatch.setattr(nous_auth_keepalive, 'start_nous_auth_keepalive', lambda: None)
    monkeypatch.setattr(tui_server, 'install_exit_flush_signal_handlers', lambda: None)
    monkeypatch.setattr(launch_profile_policy, 'activate_multi_profile_hosting_eagerly', lambda: None)
    monkeypatch.setattr(owner.ws, '_port_bind_conflict', lambda *a: False)
    class Server:
        should_exit = False
        started = False
        def capture_signals(self): return nullcontext()
        async def startup(self):
            if failure == 'startup': raise RuntimeError('FIXTURE_UNKNOWN_STARTUP')
            self.started = True
        async def main_loop(self): raise RuntimeError('FIXTURE_END_LOOP')
        async def shutdown(self): raise RuntimeError('FIXTURE_STOP_UNCONFIRMED')
    config = SimpleNamespace(loaded=True, lifespan_class=lambda c: object())
    monkeypatch.setattr(owner.ws, '_build_uvicorn_server', lambda *a, **kw: (config, Server()))
    monkeypatch.setattr(owner.ws, '_on_server_started', lambda *a, **kw: None)
    with pytest.raises(RuntimeError): owner.ws.start_server(host='127.0.0.1', port=9119, open_browser=False)
    assert owner.hr.owns_host_lock('serve')
    assert getattr(owner.ws.app.state, 'friday_dashboard_owner', None) is not None
    # No socket/process was started by this fixture. The owner fixture uses the
    # existing native cleanup; a real unknown stop requires the actual supervisor.



def test_native_probe_refuses_foreign_identity_before_tcp(record_owner, monkeypatch):
    owner = record_owner; record = published(owner)
    import socket
    calls = []; monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: calls.append(a))
    assert owner.hr.probe_owner(replace(record, home='/tmp/foreign')) is None
    assert calls == []


@pytest.mark.parametrize('kind', ['public', 'hardlink', 'symlink'])
def test_native_probe_private_token_provenance_before_tcp(record_owner, monkeypatch, kind):
    owner = record_owner; record = published(owner); token = owner.hr.token_path('serve')
    old = token.read_bytes(); alias = token.with_name('fixture-token-alias')
    if kind == 'public': token.chmod(0o644)
    elif kind == 'hardlink': os.link(token, alias)
    else:
        token.rename(alias); token.symlink_to(alias)
    import socket
    calls = []; monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: calls.append(a))
    try:
        assert owner.hr.probe_owner(record) is None
        assert calls == []
    finally:
        if kind == 'public': token.chmod(0o600)
        elif kind == 'hardlink': alias.unlink()
        else: token.unlink(); alias.rename(token)
    assert token.read_bytes() == old



def test_private_native_identity_token_never_grants_other_admin_routes(record_owner):
    owner = record_owner
    import httpx
    owner.ws._configure_auth_gate('127.0.0.1', False, None, None); published(owner)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owner.ws.app), base_url='http://127.0.0.1:9119') as c:
            headers = {'X-Hermes-Session-Token': owner.hr.read_token('serve'), 'X-Hermes-Probe-Nonce': '1' * 32}
            identity = await c.get('/api/host/identity', headers=headers)
            ordinary = await c.get('/api/plugins/friday_rework/admin/status', headers=headers)
            wrong = await c.get('/api/host/identity', headers={'X-Hermes-Session-Token': 'foreign'})
        return identity, ordinary, wrong
    identity, ordinary, wrong = asyncio.run(run())
    assert identity.status_code == 200 and ordinary.status_code == wrong.status_code == 401
    owner.boundary.verify_probe(owner.hr.read_record('serve'), identity.json(), '1' * 32)


@pytest.mark.parametrize('field', ['probeNonce', 'ownerProof', 'pid', 'startTime'])
def test_native_owner_proof_cannot_replay_for_another_nonce_or_incarnation(record_owner, field):
    owner = record_owner; record = published(owner); payload = proof(owner)
    payload[field] = '0' * 32 if field == 'probeNonce' else '0' * 64 if field == 'ownerProof' else 1
    with pytest.raises(ValueError): owner.boundary.check_attachment(record, payload)
    with pytest.raises(ValueError): owner.boundary.verify_probe(record, proof(owner), '2' * 32)
