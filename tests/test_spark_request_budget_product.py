"""Actual product composition and native config reads; no provider/worker calls."""
import copy
import pytest

from tools.configure_product import compose_product


PRIMARY_BUDGET = {'first_event': 180, 'idle': 120, 'total': 900}
COMPRESSOR_BUDGET = {'first_event': 20, 'idle': 15, 'total': 60}


def split_spec():
    # Proposal fixtures only: these limits must never become deployment defaults.
    return {
        'profile': 'default',
        'inference': {
            'base_url': 'http://127.0.0.195:30000/v1',
            'model': 'synthetic-spark', 'key_env': 'FRIDAY_LLM_API_KEY',
            'context': 262144, 'max_input': 250000, 'main_output': 8192,
            'summary_output': 4096, 'margin': 1024, 'template_overhead': 2048,
            'request_options': {'reasoning_echo': True, 'reasoning_effort': 'xhigh',
                'extra_body': {'chat_template_kwargs': {
                    'enable_thinking': True, 'preserve_thinking': True}}}},
        'compression_inference': {
            'base_url': 'http://127.0.0.35:8001/v1',
            'model': 'synthetic-retained-27b', 'key_env': 'FRIDAY_COMPRESSION_API_KEY',
            'context': 40960, 'max_input': 40954, 'main_output': 4096,
            'summary_output': 2048, 'margin': 1024, 'template_overhead': 2048},
        'compression_multipass': {'enabled': True, 'max_calls': 16, 'max_depth': 4,
            'max_attempt_seconds': 600, 'max_call_seconds': 180},
        'web': {'profile': 'exa-paid', 'extract_char_limit': 20000, 'extract_timeout': 30},
        'dashboard': {'host': '127.0.0.1', 'port': 9119,
            'public_url': 'https://friday.example:9119',
            'operator': {'provider': 'basic', 'user_id': 'synthetic-operator', 'org_id': ''}},
        'accounts': [{'platform': 'telegram', 'transport_profile': 'default',
            'account_id': 'synthetic-account'}],
        'runtime': {'enabled': False},
    }


def ordinary(bundle):
    return bundle['config']['plugins']['entries']['friday_rework']['settings'][
        'onboarding']['templates']['friday-local']['config']


@pytest.fixture
def native_home(tmp_path, monkeypatch):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    home = tmp_path / 'synthetic-native-home'
    home.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(home))
    token = set_hermes_home_override(str(home))
    try:
        yield home
    finally:
        reset_hermes_home_override(token)


def native_load(home, config):
    from hermes_cli.config import atomic_config_replace, load_config_readonly
    atomic_config_replace(home / 'config.yaml', config)
    return load_config_readonly()


def test_actual_composition_changes_only_explicit_primary_budget():
    spec = split_spec()
    baseline = compose_product(spec)
    spec['inference']['request_budget_seconds'] = copy.deepcopy(PRIMARY_BUDGET)
    before = copy.deepcopy(spec)
    actual = compose_product(spec)
    expected = copy.deepcopy(baseline)
    for config in (expected['config'], ordinary(expected)):
        config['providers']['friday-local']['request_budget_seconds'] = PRIMARY_BUDGET
    assert actual == expected
    assert spec == before
    for config in (actual['config'], ordinary(actual)):
        assert config['providers']['friday-compression'] == baseline['config'][
            'providers']['friday-compression']
        assert config['auxiliary']['compression'] == baseline['config']['auxiliary']['compression']
        assert config['model']['reasoning_echo'] is True
        assert config['providers']['friday-local']['extra_body']['reasoning_effort'] == 'xhigh'
        assert config['providers']['friday-local']['extra_body'][
            'chat_template_kwargs']['preserve_thinking'] is True
        assert config['display']['show_reasoning'] is False
        assert config['display']['platforms']['telegram']['show_reasoning'] is False
    spec['inference']['request_budget_seconds']['total'] = 1
    actual['config']['providers']['friday-local']['request_budget_seconds']['total'] = 2
    assert ordinary(actual)['providers']['friday-local']['request_budget_seconds'] == PRIMARY_BUDGET


@pytest.mark.parametrize('surface', ['root', 'ordinary'])
@pytest.mark.parametrize('compressor_policy', [False, True])
def test_rendered_budgets_reach_actual_named_native_consumer(
        native_home, surface, compressor_policy):
    from hermes_cli.timeouts import get_provider_request_budget, get_provider_request_timeout
    spec = split_spec()
    spec['inference']['request_budget_seconds'] = copy.deepcopy(PRIMARY_BUDGET)
    if compressor_policy:
        spec['compression_inference']['request_budget_seconds'] = copy.deepcopy(COMPRESSOR_BUDGET)
    bundle = compose_product(spec)
    config = bundle['config'] if surface == 'root' else ordinary(bundle)
    loaded = native_load(native_home, config)
    assert loaded['providers'] == config['providers']
    main = get_provider_request_budget('custom', spec['inference']['model'], 'custom:friday-local')
    assert vars(main) == PRIMARY_BUDGET
    compressor = get_provider_request_budget(
        'custom', spec['compression_inference']['model'], 'custom:friday-compression')
    assert (vars(compressor) if compressor is not None else None) == (
        COMPRESSOR_BUDGET if compressor_policy else None)
    assert get_provider_request_budget('custom', spec['inference']['model'], 'custom:foreign') is None
    assert get_provider_request_budget('custom', spec['inference']['model']) is None
    assert get_provider_request_timeout('custom', spec['inference']['model'], 'custom:friday-local') == 30
    assert get_provider_request_timeout('custom', spec['compression_inference']['model'],
        'custom:friday-compression') == 30
    assert loaded['auxiliary']['compression']['multipass'] == spec['compression_multipass']
    assert loaded['auxiliary']['compression']['extra_body'] == {'max_tokens': 2048}
    assert loaded['providers']['friday-compression']['key_env'] == 'FRIDAY_COMPRESSION_API_KEY'
    assert loaded['providers']['friday-compression']['models'][spec['compression_inference']['model']][
        'bounded_context']['server_max_input_tokens'] == 40954


@pytest.mark.parametrize('surface', ['root', 'ordinary'])
def test_legacy_product_omits_policy_and_keeps_native_scalar_timeout(native_home, surface):
    from hermes_cli.timeouts import get_provider_request_budget, get_provider_request_timeout
    bundle = compose_product(split_spec())
    config = bundle['config'] if surface == 'root' else ordinary(bundle)
    native_load(native_home, config)
    for name in ('friday-local', 'friday-compression'):
        assert 'request_budget_seconds' not in config['providers'][name]
        model = config['providers'][name]['default_model']
        assert get_provider_request_budget('custom', model, 'custom:' + name) is None
        assert get_provider_request_timeout('custom', model, 'custom:' + name) == 30


MALFORMED = [
    None, {}, {'total': 900}, dict(PRIMARY_BUDGET, retry=1),
    dict(PRIMARY_BUDGET, first_event=True), dict(PRIMARY_BUDGET, first_event='180'),
    dict(PRIMARY_BUDGET, idle=0), dict(PRIMARY_BUDGET, idle=-1),
    dict(PRIMARY_BUDGET, total=float('inf')), dict(PRIMARY_BUDGET, idle=float('nan')),
    dict(PRIMARY_BUDGET, first_event=901), dict(PRIMARY_BUDGET, idle=901),
    dict(PRIMARY_BUDGET, total=86401), dict(PRIMARY_BUDGET, first_event=10 ** 1000),
]


@pytest.mark.parametrize('role', ['inference', 'compression_inference'])
@pytest.mark.parametrize('policy', MALFORMED)
def test_actual_product_rejects_malformed_explicit_policy(role, policy):
    spec = split_spec()
    spec[role]['request_budget_seconds'] = policy
    with pytest.raises(ValueError):
        compose_product(spec)


@pytest.mark.parametrize('policy', MALFORMED)
def test_native_config_consumer_rejects_tampered_explicit_policy(native_home, policy):
    from hermes_cli.timeouts import get_provider_request_budget
    spec = split_spec()
    config = compose_product(spec)['config']
    config['providers']['friday-local']['request_budget_seconds'] = policy
    native_load(native_home, config)
    with pytest.raises(ValueError):
        get_provider_request_budget('custom', spec['inference']['model'], 'custom:friday-local')
    # A malformed main route must not poison or lend policy to the other route.
    assert get_provider_request_budget(
        'custom', spec['compression_inference']['model'], 'custom:friday-compression') is None


@pytest.mark.parametrize('fault', ['public_main', 'public_compressor', 'shared_key',
    'budget_route_override', 'unsupported_alias'])
def test_policy_does_not_expand_existing_route_authority(fault):
    spec = split_spec()
    spec['inference']['request_budget_seconds'] = copy.deepcopy(PRIMARY_BUDGET)
    if fault == 'public_main':
        spec['inference']['base_url'] = 'https://api.openai.com/v1'
    elif fault == 'public_compressor':
        spec['compression_inference']['base_url'] = 'https://api.openai.com/v1'
    elif fault == 'shared_key':
        spec['compression_inference']['key_env'] = spec['inference']['key_env']
    elif fault == 'budget_route_override':
        spec['inference']['request_budget_seconds']['base_url'] = 'http://127.0.0.1:9001/v1'
    else:
        spec['inference']['total_timeout'] = 900
    with pytest.raises(ValueError):
        compose_product(spec)
