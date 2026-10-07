"""Portable ownership refusal and native module extraction behavior contracts."""
from types import SimpleNamespace

import pytest


def test_private_home_rejects_unavailable_uid_with_admission_error(tmp_path, monkeypatch):
    import os
    from hermes_cli.friday_credential_admission import CredentialDenied, private_home
    tmp_path.chmod(0o700)
    config = tmp_path / 'config.yaml'
    config.write_text('{}'); config.chmod(0o600)
    assert private_home(tmp_path) == tmp_path
    with monkeypatch.context() as missing:
        missing.delattr(os, 'getuid')
        with pytest.raises(CredentialDenied, match='^friday_credential_home_unproved$'):
            private_home(tmp_path)
    with monkeypatch.context() as invalid:
        invalid.setattr(os, 'getuid', None)
        with pytest.raises(CredentialDenied, match='^friday_credential_home_unproved$'):
            private_home(tmp_path)
    with monkeypatch.context() as foreign:
        foreign.setattr(os, 'getuid', lambda: tmp_path.stat().st_uid + 1)
        with pytest.raises(CredentialDenied, match='^friday_credential_home_unproved$'):
            private_home(tmp_path)
    assert private_home(tmp_path) == tmp_path


@pytest.mark.parametrize('unsafe', ['directory_mode', 'file_mode', 'symlink'])
def test_private_home_still_requires_private_owned_home_and_config(tmp_path, unsafe):
    from hermes_cli.friday_credential_admission import private_home
    home = tmp_path / 'profile'; home.mkdir(mode=0o700)
    config = home / 'config.yaml'; config.write_text('{}'); config.chmod(0o600)
    target = home
    if unsafe == 'directory_mode': home.chmod(0o755)
    elif unsafe == 'file_mode': config.chmod(0o644)
    else:
        target = tmp_path / 'alias'; target.symlink_to(home, target_is_directory=True)
    with pytest.raises(ValueError): private_home(target)


@pytest.mark.parametrize('provider', [None, 'own', 'fallback', 'invalid', 'absent'])
def test_auth_pool_facade_preserves_fallback_shadowing_and_copy(provider, monkeypatch):
    from hermes_cli import auth, friday_credential_admission as admission
    monkeypatch.setattr(admission, 'managed', lambda: False)
    own = {'own': [{'id': 'profile'}], 'fallback': [], 'invalid': 'bad'}
    root = {'own': [{'id': 'global-shadowed'}], 'fallback': [{'id': 'global'}], 'invalid': []}
    reads = []
    monkeypatch.setattr(auth, '_load_auth_store', lambda: reads.append('profile') or {'credential_pool': own})
    monkeypatch.setattr(auth, '_load_global_auth_store', lambda: reads.append('global') or {'credential_pool': root})
    result = auth.read_credential_pool(provider)
    assert reads == ['profile', 'global']
    if provider is None:
        assert result == {'own': [{'id': 'profile'}], 'fallback': [{'id': 'global'}], 'invalid': 'bad'}
        assert result is not own and result['fallback'] is not root['fallback']
    else:
        expected = {'own': [{'id': 'profile'}], 'fallback': [{'id': 'global'}]}.get(provider, [])
        assert result == expected
        assert result is not own.get(provider) and result is not root.get(provider)


@pytest.mark.parametrize('provided', [False, True])
def test_native_gemini_factory_preserves_kwargs_transport_and_facade_seam(monkeypatch, provided):
    from agent.agent_runtime_gemini import _gemini_native_client
    from agent import agent_runtime_helpers, gemini_native_adapter
    made, logs, builders = [], [], []
    monkeypatch.setattr(gemini_native_adapter, 'GeminiNativeClient', lambda **kw: made.append(kw) or SimpleNamespace(**kw))
    monkeypatch.setattr(agent_runtime_helpers, '_ra', lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *args: logs.append(args))))
    transport = object()
    agent = SimpleNamespace(_build_keepalive_http_client=lambda *args, **kw: builders.append((args, kw)) or transport,
                            _client_log_context=lambda: 'context')
    kwargs = {'base_url': 'https://generativelanguage.googleapis.com/v1beta', 'api_key': 'synthetic',
              'unrelated': 'must-not-leak', 'timeout': 30}
    if provided: kwargs['http_client'] = transport
    before = dict(kwargs)
    result = _gemini_native_client(agent, kwargs, True, reason='rebuild', shared=False)
    assert kwargs == before
    assert result.http_client is transport and result.api_key == 'synthetic'
    assert 'unrelated' not in made[0]
    assert len(builders) == (0 if provided else 1)
    assert logs[0][1:] == ('rebuild', False, 'context')
    assert _gemini_native_client(agent, {'base_url': 'https://example.invalid/v1'}, True,
                                 reason='non-gemini', shared=False) is None
    assert len(made) == 1
