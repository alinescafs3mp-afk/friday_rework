"""Native local password gate, without socket or real credential access."""
import pytest

from test_native_installer import native_home, install_input
from test_product_profile import inputs
from tools.configure_product import compose_product, materialize_product


@pytest.mark.parametrize('host,url', [
    ('127.0.0.1', 'http://127.0.0.1:9119'),
    ('::1', 'http://[::1]:9119'),
    ('127.0.0.1', 'http://localhost:9119'),
    ('127.0.0.1', 'https://friday.example:9119'),
])
def test_native_local_profile_installer_and_gate(host, url, install_input, tmp_path, monkeypatch):
    from scripts import friday_install, friday_native
    from hermes_cli import web_server, dashboard_auth
    spec = inputs(); spec['dashboard'].update(host=host, public_url=url)
    install_input['product'] = spec
    assert friday_install.commands(install_input)['dashboard'][-4:] == [host, '--port', '9119', '--no-open']
    home = tmp_path / 'protected'; home.mkdir(mode=0o700)
    with native_home(home):
        bundle = friday_native.profile_write(home, spec)
        assert friday_native.native_profile_check(bundle, home)['ready'] is False
        monkeypatch.setattr(dashboard_auth, 'list_providers', lambda: [])
        with pytest.raises(SystemExit):
            web_server._configure_auth_gate(host, True, None, None)
        assert web_server.app.state.auth_required is True
        assert bundle['config']['dashboard']['require_auth'] is True


@pytest.mark.parametrize('value', ['true', 'false', 0, 1, None, [], {}])
def test_malformed_auth_policy_refuses(value, monkeypatch):
    from hermes_cli import web_server
    monkeypatch.setattr(web_server, 'load_config', lambda: {'dashboard': {'require_auth': value}})
    with pytest.raises(ValueError, match='must be a boolean'):
        web_server.should_require_dashboard_auth('127.0.0.1', frozenset())


@pytest.mark.parametrize('host', ['0.0.0.0', '192.168.1.10', '::'])
def test_plain_http_local_authority_cannot_open_network_bind(host, install_input):
    from scripts import friday_install
    spec = inputs(); spec['dashboard'].update(host=host, public_url='http://localhost:9119')
    with pytest.raises(ValueError, match='https'):
        compose_product(spec)
    install_input['product'] = spec
    with pytest.raises(ValueError, match='public_authority'):
        friday_install.commands(install_input)


def test_forced_native_gate_survives_desktop_and_insecure_with_real_provider(tmp_path, monkeypatch):
    from hermes_cli import web_server
    from hermes_cli.dashboard_auth import registry, InvalidCredentialsError
    from plugins.dashboard_auth.basic import BasicAuthProvider, hash_password
    parent = tmp_path / 'private'; parent.mkdir(mode=0o700)
    home = parent / 'product'; spec = inputs()
    spec['dashboard']['public_url'] = 'http://127.0.0.1:9119'
    materialize_product(home, spec)
    monkeypatch.setattr(registry, '_providers', {})
    monkeypatch.setattr(registry, '_scoped_providers', {})
    provider = BasicAuthProvider(username='explicit-operator', password_hash=hash_password('SYNTHETIC-ONLY'),
                                 secret=b'SYNTHETIC-SECRET-NOT-AN-OWNER-KEY')
    registry.register_provider(provider)
    monkeypatch.setenv('HERMES_DESKTOP', '1')
    monkeypatch.setenv('HERMES_DASHBOARD_SESSION_TOKEN', 'SYNTHETIC-UNTRUSTED-TOKEN')
    with native_home(home):
        web_server._configure_auth_gate('127.0.0.1', True, 'synthetic-ssh', 'synthetic-nonce')
        assert web_server.app.state.auth_required is True
        with pytest.raises(InvalidCredentialsError):
            provider.complete_password_login(username='explicit-operator', password='wrong')
        logged_in = provider.complete_password_login(username='explicit-operator', password='SYNTHETIC-ONLY')
        session = provider.verify_session(access_token=logged_in.access_token)
        from hermes_cli.friday_product_access import session_allowed
        assert session_allowed(session)


def test_unconfigured_donor_local_policy_is_preserved(monkeypatch):
    from hermes_cli import web_server
    monkeypatch.setattr(web_server, 'load_config', lambda: {})
    assert not web_server.should_require_dashboard_auth('127.0.0.1', frozenset())
    assert web_server.should_require_dashboard_auth('0.0.0.0', frozenset())
    assert web_server.should_require_dashboard_auth('127.0.0.1', frozenset({'friday.example'}))
