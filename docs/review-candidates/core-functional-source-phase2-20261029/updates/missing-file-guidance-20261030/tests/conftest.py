import contextvars
import hashlib
import json
from types import SimpleNamespace
import weakref
import pytest
from hermes_cli import friday_user_scope as scope
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

@pytest.fixture
def admitted(tmp_path, monkeypatch):
    from hermes_cli.friday_product_access import KEY, principal_id
    from hermes_cli.plugins_state import PluginState
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity

    root = tmp_path / 'home'
    root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(root))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(root))
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('argument-test-scope', default=None))
    monkeypatch.setattr(scope, '_SOURCE', contextvars.ContextVar('argument-test-source', default=None))
    monkeypatch.setattr(scope, '_ENGAGED', False)

    def put(path, value):
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    binding = dict(platform='telegram', transport_profile='default', account_id='synthetic-account',
                   user_id='1', runtime_profile='fixture-user-1', tools=['memory', 'read_file', 'write_file'])
    principal = principal_id(*(binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')))
    cfg = {'plugins': {'enabled': ['friday_rework'], 'entries': {'friday_rework': {'settings': {
        'product_access': {'enabled': True, 'accounts': [dict(platform='telegram', transport_profile='default',
            account_id='synthetic-account', runtime_profiles=['fixture-user-1'])]},
        'user_isolation': {'enabled': True, 'bindings': [binding]}}}}},
        'gateway': {'multiplex_profiles': True, 'profile_routes': [dict(name='friday-' + principal,
            platform='telegram', bot_profile='default', user_id='1', profile='fixture-user-1', enabled=True)]}}
    put(root / 'config.yaml', cfg)
    with scope.authority(root):
        PluginState('friday_rework').set(KEY, dict(schema=KEY, users={principal: {
            k: binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')} |
            dict(enabled=True, role='user')}))
    home = scope.provision_new_home(root, binding, {'max_iterations': 8, 'toolsets': ['file']})
    from hermes_cli.config import atomic_config_write
    with scope.authority(home):
        atomic_config_write(home / 'config.yaml', {'max_iterations': 8, 'toolsets': ['file'], 'tools': {
            'tool_search': {'enabled': 'auto', 'defer': ['write_file', 'read_file']}}})
    (home / 'SOUL.md').write_text('Synthetic identity')
    (home / 'SOUL.md').chmod(0o600)
    (home / '.env').write_text('SYNTHETIC_FIXTURE_KEY=offline-fixture\n')
    (home / '.env').chmod(0o600)
    info = home.stat()
    put(home / scope.ONBOARDING, dict(schema='friday.onboarding.v1',
        binding_sha256=scope._fingerprint(binding), config_sha256=sha(home / 'config.yaml'),
        soul_sha256=sha(home / 'SOUL.md'), required_secrets=['SYNTHETIC_FIXTURE_KEY'],
        directory_identity=[info.st_dev, info.st_ino], template='synthetic', authorization_home=str(root)))
    marker = json.loads((home / scope.MARKER).read_text())
    marker['onboarding_sha256'] = sha(home / scope.ONBOARDING)
    put(home / scope.MARKER, marker)
    # RoutingIdentity retains a weak reference to the transport.
    class Transport:
        pass
    adapter = Transport()
    source = SessionSource(Platform.TELEGRAM, 'synthetic-chat', user_id='1', chat_type='dm', profile='fixture-user-1')
    source._identity = RoutingIdentity('default', 'fixture-user-1', root, home,
        multiplexed=True, transport_inferred=False, transport=weakref.ref(adapter))
    with scope.authority(root):
        scope.admit_source(source)
    token = set_hermes_home_override(str(root))
    try:
        with scope.authority(home), scope.scoped_source(source) as cap:
            yield SimpleNamespace(root=root, home=home, cap=cap)
    finally:
        reset_hermes_home_override(token)
