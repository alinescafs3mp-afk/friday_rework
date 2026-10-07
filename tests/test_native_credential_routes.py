"""Offline native request construction: no send(), transport or model invocation."""
import copy
import json
from types import SimpleNamespace

import pytest
from test_native_credential_admission import operator, publish, runtime, dotenv
from test_native_dashboard_owner import installation
from hermes_cli import friday_credential_admission as admission


def prepared(**changes):
    from agent import auxiliary_client as aux
    args = dict(provider=None, model=None, base_url=None, api_key=None, main_runtime=None,
                messages=[{'role': 'user', 'content': 'synthetic'}], temperature=None,
                max_tokens=64, tools=None, timeout=5, extra_body=None, reasoning_config=None,
                extra_headers=None, api_mode=None, route_info=None, async_mode=False)
    args.update(changes)
    return aux._prepare_aux_request('compression', **args)


def wire(client, kwargs, **changes):
    from openai._models import FinalRequestOptions
    args = dict(method='post', url='/chat/completions',
                json_data={k: v for k, v in kwargs.items() if k not in ('timeout', 'extra_body', 'extra_headers')},
                extra_json=kwargs.get('extra_body'), headers=kwargs.get('extra_headers'))
    args.update(changes)
    options = FinalRequestOptions.construct(**args)
    request = client._build_request(options, retries_taken=0)
    assert options.follow_redirects is False
    return request


@pytest.mark.parametrize('path', ['model', 'provider', 'custom_alias', 'auxiliary', 'delegation'])
@pytest.mark.parametrize('field,value', [
    ('default_headers', {'Authorization': 'FOREIGN'}),
    ('extra_headers', {'hOsT': 'foreign.example'}),
    ('extra_body', {'model': 'FOREIGN'}),
    ('request_overrides', {'extra_body': {'provider': 'FOREIGN'}}),
])
def test_all_native_extension_config_aliases_refuse_before_resolution(operator, path, field, value):
    cfg = copy.deepcopy(operator.cfg)
    if path == 'model': block = cfg['model']
    elif path == 'provider': block = cfg['providers']['friday-local']
    elif path == 'custom_alias':
        cfg['custom_providers'] = [{'name': 'friday-local', 'base_url': cfg['model']['base_url']}]
        block = cfg['custom_providers'][0]
    elif path == 'auxiliary': block = cfg['auxiliary']['compression']
    else: block = cfg['delegation']
    block[field] = value
    publish(operator.home / 'config.yaml', cfg)
    with pytest.raises(admission.CredentialDenied): runtime()


@pytest.mark.parametrize('field,value', [
    ('extra_headers', {'AUTHORIZATION': 'FOREIGN'}),
    ('extra_headers', {'Host': 'foreign.example'}),
    ('extra_headers', {'X-Api-Key': 'FOREIGN'}),
    ('extra_headers', {'Proxy-Authorization': 'FOREIGN'}),
    ('extra_headers', {'X-Forwarded-Host': 'foreign.example'}),
    ('extra_body', {'model': 'FOREIGN'}),
    ('extra_body', {'base_url': 'http://127.0.0.1:9999/v1'}),
])
def test_actual_auxiliary_per_call_extensions_refuse(operator, field, value):
    with pytest.raises(admission.CredentialDenied): prepared(**{field: value})


def test_auxiliary_sdk_final_wire_preserves_route_key_model_capacity_reasoning(operator):
    cfg = copy.deepcopy(operator.cfg)
    cfg['model']['default_headers'] = {'User-Agent': 'Friday-fixture'}
    cfg['model']['extra_headers'] = {'X-Request-ID': 'synthetic-request'}
    cfg['providers']['friday-local']['extra_headers'] = {'X-Correlation-ID': 'native-provider'}
    cfg['auxiliary']['compression']['extra_body']['reasoning'] = {'effort': 'high'}
    publish(operator.home / 'config.yaml', cfg)
    r = prepared(extra_body={'max_tokens': 96}, extra_headers={'Accept-Language': 'ru'})
    try:
        request = wire(r.client, r.kwargs)
        assert str(request.url) == cfg['model']['base_url'] + '/chat/completions'
        assert request.headers['authorization'] == 'Bearer ' + operator.values['FRIDAY_LOCAL_KEY']
        assert request.headers['user-agent'] == 'Friday-fixture'
        assert request.headers['x-correlation-id'] == 'native-provider'
        body = json.loads(request.content)
        assert body['model'] == cfg['model']['default']
        assert body['max_tokens'] == 96
        assert body['reasoning']['effort'] == 'high'
    finally: r.client.close()


@pytest.mark.parametrize('surface', ['main', 'auxiliary', 'async', 'copy'])
def test_actual_native_factories_guard_final_sdk_wire_and_copy(operator, surface):
    from agent import auxiliary_client as aux, process_bootstrap
    values = dict(api_key=operator.values['FRIDAY_LOCAL_KEY'], base_url=operator.cfg['model']['base_url'])
    original = None
    if surface == 'main': client = process_bootstrap.OpenAI(**values)
    elif surface == 'copy':
        original = process_bootstrap.OpenAI(**values)
        client = original.with_options(default_headers={'X-Request-ID': 'copied'})
    elif surface == 'auxiliary': client, _ = aux.resolve_provider_client(provider='custom:friday-local')
    else:
        original, _ = aux.resolve_provider_client(provider='custom:friday-local')
        client, _ = aux._to_async_client(original, operator.cfg['model']['default'])
    kwargs = {'model': operator.cfg['model']['default'], 'messages': []}
    try:
        assert json.loads(wire(client, kwargs).content)['model'] == kwargs['model']
        for changes in [dict(headers={'Authorization': 'FOREIGN'}), dict(headers={'Host': 'foreign.example'}),
                        dict(extra_json={'model': 'FOREIGN'}), dict(url='http://127.0.0.1:9999/v1/chat/completions'),
                        dict(json_data={'model': 'FOREIGN', 'messages': []}), dict(params={'model': 'FOREIGN'})]:
            with pytest.raises(admission.CredentialDenied): wire(client, kwargs, **changes)
        with pytest.raises(admission.CredentialDenied):
            client.with_options(default_headers={'Authorization': 'FOREIGN'})
    finally:
        if surface == 'async':
            # The offline runner uses a pipe for asyncio's wakeup, never sockets.
            import asyncio
            asyncio.run(client.close())
        else: client.close()
        if original: original.close()


def test_actual_main_rebuild_factory_and_delegation_request_merge(operator):
    from agent.agent_runtime_helpers import create_openai_client
    from tools.delegate_tool_config import _merge_request_overrides
    agent = SimpleNamespace(provider='custom', model=operator.cfg['model']['default'],
        api_mode='chat_completions', _build_keepalive_http_client=lambda *a, **k: None,
        _client_log_context=lambda: 'synthetic')
    client = create_openai_client(agent, {'api_key': operator.values['FRIDAY_LOCAL_KEY'],
        'base_url': operator.cfg['model']['base_url']}, reason='credential-fixture', shared=False)
    try:
        kwargs = dict(model=agent.model, messages=[])
        good = _merge_request_overrides({'extra_body': {'max_tokens': 100}},
                                        {'extra_body': {'reasoning': {'effort': 'high'}}})
        request = wire(client, {**kwargs, **good})
        assert json.loads(request.content)['max_tokens'] == 100
        bad = _merge_request_overrides(good, {'extra_body': {'model': 'FOREIGN'}})
        with pytest.raises(admission.CredentialDenied): wire(client, {**kwargs, **bad})
    finally: client.close()


@pytest.mark.parametrize('mode', ['anthropic_messages', 'codex_responses', 'bedrock_converse'])
def test_actual_main_client_builder_cannot_switch_transports(operator, mode):
    from agent.agent_init import _build_client
    agent = SimpleNamespace(provider='custom', model=operator.cfg['model']['default'], api_mode=mode)
    with pytest.raises(admission.CredentialDenied):
        _build_client(agent, operator.values['FRIDAY_LOCAL_KEY'], operator.cfg['model']['base_url'], None)


def test_native_managed_sources_excluded_for_friday_but_retained_for_donor(operator, monkeypatch):
    from hermes_cli import managed_scope
    from hermes_cli.config_effective import load_user_config_effective
    other = operator.home / 'synthetic-managed'; other.mkdir(mode=0o700)
    publish(other / 'config.yaml', {'model': {'base_url': 'http://127.0.0.1:9797/v1'}})
    dotenv(other, FRIDAY_LOCAL_KEY='FOREIGN_MANAGED')
    monkeypatch.setenv('HERMES_MANAGED_DIR', str(other))
    assert managed_scope.get_managed_dir() is None
    assert managed_scope.load_managed_env() == {}
    assert load_user_config_effective()['model']['base_url'] == operator.cfg['model']['base_url']
    from test_native_installer import native_home
    donor = operator.home / 'donor'; donor.mkdir(mode=0o700); publish(donor / 'config.yaml', {})
    monkeypatch.setattr(admission, 'SOURCE', donor / 'ordinary-source')
    with native_home(donor):
        assert managed_scope.get_managed_dir() == other
        assert load_user_config_effective()['model']['base_url'] == 'http://127.0.0.1:9797/v1'


@pytest.mark.parametrize('reference', ['TELEGRAM_BOT_TOKEN', 'HERMES_DASHBOARD_BASIC_AUTH_SECRET', 'EXA_API_KEY', 'UNDECLARED_KEY'])
def test_protected_contract_joins_runtime_references_after_drift(operator, reference):
    cfg = copy.deepcopy(operator.cfg)
    for block in [cfg['model'], cfg['providers']['friday-local'], cfg['delegation'],
                  *[v for v in cfg['auxiliary'].values() if isinstance(v, dict)]]:
        block['key_env'] = reference
    values = dict(operator.values); values[reference] = 'SYNTHETIC_DIFFERENT_DOMAIN'
    dotenv(operator.home, **values); publish(operator.home / 'config.yaml', cfg)
    with admission.scoped(operator.home), pytest.raises(admission.CredentialDenied): runtime()


def test_actual_main_transport_kwargs_retain_reasoning_and_refuse_late_model_override(operator):
    from agent.transports.chat_completions import ChatCompletionsTransport
    from agent import process_bootstrap
    client = process_bootstrap.OpenAI(api_key=operator.values['FRIDAY_LOCAL_KEY'],
                                     base_url=operator.cfg['model']['base_url'])
    transport = ChatCompletionsTransport()
    from run_agent import AIAgent
    # No worker initialization: only the native URL/model token-field selector.
    agent = object.__new__(AIAgent)
    agent.model = operator.cfg['model']['default']; agent.base_url = operator.cfg['model']['base_url']
    args = dict(base_url=operator.cfg['model']['base_url'], max_tokens=128,
                max_tokens_param_fn=agent._max_tokens_param,
                supports_reasoning=True, reasoning_config={'effort': 'high'})
    try:
        from agent.sdk_transform_bypass import bypass_chat_sdk_request_transform
        messages = [{'role': 'user', 'content': 'synthetic'}]
        kwargs = transport.build_kwargs(operator.cfg['model']['default'], messages, **args)
        kwargs = bypass_chat_sdk_request_transform(kwargs, client)
        body = json.loads(wire(client, kwargs).content)
        assert body['max_tokens'] == 128 and body['reasoning']['effort'] == 'high'
        assert body['messages'] == messages
        kwargs = transport.build_kwargs(operator.cfg['model']['default'], [],
            request_overrides={'model': 'FOREIGN'}, **args)
        with pytest.raises(admission.CredentialDenied): wire(client, kwargs)
    finally: client.close()


def test_sdk_wire_retains_native_pool_priority_without_dotenv_inference(operator):
    values = dict(operator.values); values.pop('FRIDAY_LOCAL_KEY'); dotenv(operator.home, **values)
    publish(operator.home / 'auth.json', {'credential_pool': {'custom:friday-local': [{
        'id': 'owned-local', 'source': 'manual', 'auth_type': 'api_key', 'access_token': 'OWNED_POOL_SECRET',
        'base_url': operator.cfg['model']['base_url'], 'priority': 0}]}})
    with admission.scoped(operator.home):
        r = prepared()
        try: assert wire(r.client, r.kwargs).headers['authorization'] == 'Bearer OWNED_POOL_SECRET'
        finally: r.client.close()


def test_retained_sdk_client_refuses_changed_scope_and_key(operator):
    from agent import process_bootstrap
    client = process_bootstrap.OpenAI(api_key=operator.values['FRIDAY_LOCAL_KEY'],
                                     base_url=operator.cfg['model']['base_url'])
    try:
        values = dict(operator.values); values['FRIDAY_LOCAL_KEY'] = 'SYNTHETIC_ROTATED_KEY'
        dotenv(operator.home, **values)
        with admission.scoped(operator.home), pytest.raises(admission.CredentialDenied):
            wire(client, {'model': operator.cfg['model']['default'], 'messages': []})
    finally: client.close()


def test_sdk_wire_donor_factory_stays_unmodified(tmp_path, monkeypatch):
    from test_native_installer import native_home
    from agent import process_bootstrap
    from openai import OpenAI
    home = tmp_path / 'donor'; home.mkdir(mode=0o700)
    publish(home / 'config.yaml', {})
    monkeypatch.setattr(admission, 'SOURCE', home / 'ordinary-source')
    with native_home(home):
        assert admission.sdk_class(OpenAI) is OpenAI
        client = process_bootstrap.OpenAI(api_key='SYNTHETIC_DONOR_KEY', base_url='http://127.0.0.1:9797/v1')
        try: assert type(client) is OpenAI
        finally: client.close()


@pytest.mark.parametrize('header', ['Authorization', 'X-Request-ID'])
def test_native_late_session_header_cannot_replace_authority(operator, header):
    from agent import process_bootstrap
    from agent.opencode_affinity import merge_session_affinity_headers
    cfg = copy.deepcopy(operator.cfg)
    cfg['providers']['friday-local']['session_affinity_header'] = header
    publish(operator.home / 'config.yaml', cfg)
    client = process_bootstrap.OpenAI(api_key=operator.values['FRIDAY_LOCAL_KEY'],
                                     base_url=operator.cfg['model']['base_url'])
    try:
        kwargs = merge_session_affinity_headers({'model': cfg['model']['default'], 'messages': []},
            'custom:friday-local', cfg['model']['base_url'], 'synthetic-session')
        assert kwargs['extra_headers'][header]
        if header == 'Authorization':
            with pytest.raises(admission.CredentialDenied): wire(client, kwargs)
        else:
            assert wire(client, kwargs).headers['authorization'] == 'Bearer ' + operator.values['FRIDAY_LOCAL_KEY']
    finally: client.close()



def test_declared_delegation_header_override_keeps_non_authority_native_behavior(operator):
    from tools.delegate_tool_config import _merge_request_overrides
    from agent import process_bootstrap
    cfg = copy.deepcopy(operator.cfg)
    cfg['delegation']['request_overrides'] = {'extra_headers': {'X-Request-ID': 'delegated'},
                                             'extra_body': {'max_tokens': 160}}
    publish(operator.home / 'config.yaml', cfg)
    r = runtime()
    client = process_bootstrap.OpenAI(api_key=r['api_key'], base_url=r['base_url'])
    try:
        overrides = _merge_request_overrides(None, cfg['delegation']['request_overrides'])
        request = wire(client, {'model': cfg['model']['default'], 'messages': [], **overrides})
        assert request.headers['x-request-id'] == 'delegated'
        assert json.loads(request.content)['max_tokens'] == 160
    finally: client.close()
