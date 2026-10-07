"""Native alias selection and HTTPX authority joins; request construction only."""
import asyncio
import copy
import json

import pytest
from test_native_credential_admission import operator, publish, runtime, dotenv
from test_native_dashboard_owner import installation
from test_native_installer import native_home
from hermes_cli import friday_credential_admission as admission


def observe_keys(monkeypatch):
    from hermes_cli import runtime_provider_custom as custom
    reads = []
    original = custom.get_secret_str
    def observe(name, *args, **kwargs):
        reads.append(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(custom, 'get_secret_str', observe)
    return reads


@pytest.mark.parametrize('name', ['friday-local', 'Friday Local', 'custom:friday-local'])
@pytest.mark.parametrize('first', [False, True])
@pytest.mark.parametrize('foreign_endpoint', [False, True])
def test_native_alias_ambiguity_refused_before_any_provider_key_read(operator, monkeypatch, name, first, foreign_endpoint):
    cfg = copy.deepcopy(operator.cfg)
    shadow = {'name': name, 'api': 'http://127.0.0.1:9797/v1' if foreign_endpoint else cfg['model']['base_url'],
              'key_env': 'TELEGRAM_BOT_TOKEN', 'transport': 'chat_completions'}
    cfg['providers'] = ({'shadow-route': shadow, **cfg['providers']} if first
                        else {**cfg['providers'], 'shadow-route': shadow})
    publish(operator.home / 'config.yaml', cfg)
    reads = observe_keys(monkeypatch)
    with pytest.raises(admission.CredentialDenied, match='named_provider_ambiguous'):
        runtime()
    assert reads == []


@pytest.mark.parametrize('shape', ['disabled', 'disabled_string', 'no_endpoint', 'unrelated', 'legacy'])
def test_native_nonparticipating_aliases_preserve_selected_key(operator, monkeypatch, shape):
    cfg = copy.deepcopy(operator.cfg)
    shadow = {'name': 'friday-local', 'api': cfg['model']['base_url'], 'key_env': 'TELEGRAM_BOT_TOKEN'}
    if shape == 'disabled': shadow['enabled'] = False
    elif shape == 'disabled_string': shadow['enabled'] = 'false'
    elif shape == 'no_endpoint': shadow.pop('api')
    elif shape == 'unrelated': shadow['name'] = 'unrelated'
    if shape == 'legacy':
        shadow['base_url'] = shadow.pop('api')
        cfg['custom_providers'] = [shadow]
    else: cfg['providers'] = {'shadow-route': shadow, **cfg['providers']}
    publish(operator.home / 'config.yaml', cfg)
    reads = observe_keys(monkeypatch)
    assert runtime()['api_key'] == operator.values['FRIDAY_LOCAL_KEY']
    assert reads and set(reads) == {'FRIDAY_LOCAL_KEY'}


@pytest.mark.parametrize('requested', [None, 'custom'])
@pytest.mark.parametrize('pool', [False, True])
def test_generic_native_request_binds_admitted_named_provider_and_pool(operator, monkeypatch, requested, pool):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    cfg = copy.deepcopy(operator.cfg)
    cfg['providers'] = {'shadow-route': {'name': 'custom', 'api': cfg['model']['base_url'],
                                       'key_env': 'TELEGRAM_BOT_TOKEN'}, **cfg['providers']}
    publish(operator.home / 'config.yaml', cfg)
    if pool:
        values = dict(operator.values); values.pop('FRIDAY_LOCAL_KEY'); dotenv(operator.home, **values)
        publish(operator.home / 'auth.json', {'credential_pool': {'custom:friday-local': [{
            'id': 'owned-local', 'source': 'manual', 'auth_type': 'api_key', 'access_token': 'OWNED_POOL_SECRET',
            'base_url': cfg['model']['base_url'], 'priority': 0}]}})
    reads = observe_keys(monkeypatch)
    with admission.scoped(operator.home):
        result = resolve_runtime_provider(requested=requested, target_model=cfg['model']['default'])
    assert result['api_key'] == ('OWNED_POOL_SECRET' if pool else operator.values['FRIDAY_LOCAL_KEY'])
    assert not (set(reads) - {'FRIDAY_LOCAL_KEY'})


@pytest.mark.parametrize('selected', ['display', 'key', 'normalized'])
def test_non_friday_native_display_key_aliases_keep_insertion_winner(operator, monkeypatch, selected):
    from hermes_cli import runtime_provider_custom as custom, runtime_provider as rp
    donor = operator.home / ('donor-' + selected); donor.mkdir(mode=0o700)
    cfg = {'providers': {
        'first': {'name': 'Friday Local', 'api': 'http://127.0.0.1:9001/v1', 'key_env': 'DONOR_ONE'},
        'friday-local': {'api': 'http://127.0.0.1:9002/v1', 'key_env': 'DONOR_TWO'}}}
    publish(donor / 'config.yaml', cfg)
    monkeypatch.setattr(admission, 'SOURCE', donor / 'ordinary-source')
    with native_home(donor), admission.scoped(donor, {'DONOR_ONE': 'SYNTHETIC_ONE', 'DONOR_TWO': 'SYNTHETIC_TWO'}):
        assert admission.managed() is False
        # Use actual effective config and actual native lookup, not a replacement resolver.
        requested = {'display': 'Friday Local', 'key': 'custom:first', 'normalized': 'custom:friday-local'}[selected]
        reads = observe_keys(monkeypatch)
        result = custom._get_named_custom_provider(requested)
        assert result['api_key'] == 'SYNTHETIC_ONE' and result['provider_key'] == 'first'
        assert reads == ['DONOR_ONE']


def endpoint_config(operator, endpoint):
    from tools.configure_product import compose_product
    from test_product_profile import inputs
    spec = inputs(); spec['inference']['base_url'] = endpoint
    cfg = compose_product(spec)['config']; cfg['dashboard'] = copy.deepcopy(operator.cfg['dashboard'])
    publish(operator.home / 'config.yaml', cfg)
    return cfg


def client_pair(operator, endpoint, asynchronous):
    from agent import process_bootstrap, auxiliary_client as aux
    cfg = endpoint_config(operator, endpoint)
    resolved = runtime(); assert resolved['base_url'] == endpoint
    sync = process_bootstrap.OpenAI(api_key=resolved['api_key'], base_url=resolved['base_url'])
    if asynchronous:
        client, _ = aux._to_async_client(sync, cfg['model']['default'])
        return client, sync
    return sync, None


def cleanup(client, sync):
    if sync:
        asyncio.run(client.close()); sync.close()
    else: client.close()


def options(operator, **changes):
    from openai._models import FinalRequestOptions
    values = dict(method='post', url='/chat/completions',
                  json_data={'model': operator.cfg['model']['default'], 'messages': []})
    values.update(changes)
    return FinalRequestOptions.construct(**values)


@pytest.mark.parametrize('endpoint', ['http://127.0.0.1:80/v1', 'https://127.0.0.1:443/v1',
    'http://[::1]:80/v1', 'https://[::1]:443/v1', 'http://[0:0:0:0:0:0:0:1]:9000/v1',
    'http://127.0.0.1:9000/v1'])
@pytest.mark.parametrize('asynchronous', [False, True])
def test_actual_native_sync_async_default_port_ipv6_sdk_requests(operator, endpoint, asynchronous):
    import httpx
    client, sync = client_pair(operator, endpoint, asynchronous)
    class Captured(BaseException): pass
    captured = []
    def stop(request): captured.append(request); raise Captured()
    async def astop(request): stop(request)
    client._prepare_request = astop if asynchronous else stop
    try:
        with pytest.raises(Captured):
            call = lambda: client.chat.completions.create(model=operator.cfg['model']['default'], messages=[],
                        max_tokens=64, extra_body={'reasoning': {'effort': 'high'}},
                        extra_headers={'X-Request-ID': 'synthetic-safe'})
            if asynchronous: asyncio.run(call())
            else: call()
        assert len(captured) == 1
        request = captured[0]; expected = httpx.URL(endpoint + '/chat/completions')
        assert request.url == expected and request.headers['host'] == expected.netloc.decode('ascii')
        assert request.headers['authorization'] == 'Bearer ' + operator.values['FRIDAY_LOCAL_KEY']
        assert json.loads(request.content)['reasoning'] == {'effort': 'high'}
        retry_options = options(operator, follow_redirects=True)
        assert client._build_request(retry_options, retries_taken=2).url == expected
        assert retry_options.follow_redirects is False
        copied = client.with_options(default_headers={'X-Correlation-ID': 'copied'})
        try:
            assert copied._build_request(options(operator)).url == expected
        finally:
            if asynchronous: asyncio.run(copied.close())
            else: copied.close()
    finally: cleanup(client, sync)


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('mutation', ['authority', 'scheme', 'port', 'path', 'query', 'empty_query', 'userinfo',
                                    'fragment', 'method', 'host'])
def test_default_port_normalization_preserves_exact_authority_negative_controls(operator, asynchronous, mutation):
    client, sync = client_pair(operator, 'http://127.0.0.1:80/v1', asynchronous)
    changes = {
        'authority': {'url': 'http://127.0.0.2/v1/chat/completions'},
        'scheme': {'url': 'https://127.0.0.1/v1/chat/completions'},
        'port': {'url': 'http://127.0.0.1:81/v1/chat/completions'},
        'path': {'url': '/other'}, 'query': {'params': {'x': 'foreign'}},
        'empty_query': {'url': 'http://127.0.0.1/v1/chat/completions?'},
        'userinfo': {'url': 'http://user:pass@127.0.0.1/v1/chat/completions'},
        'fragment': {'url': 'http://127.0.0.1/v1/chat/completions#foreign'},
        'method': {'method': 'get'}, 'host': {'headers': {'Host': '127.0.0.1:81'}},
    }[mutation]
    try:
        with pytest.raises(admission.CredentialDenied): client._build_request(options(operator, **changes))
    finally: cleanup(client, sync)
