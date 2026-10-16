"""Pure config checks: no credential reads, native homes or model requests."""
import copy
import math

import pytest

from tools.configure_local_test import build_config
from tools.configure_product import _inference


PRIMARY = dict(base_url='http://127.0.0.195:30000/v1',
    model='synthetic-primary', key_env='FRIDAY_LLM_API_KEY',
    context=262144, max_input=262138, main_output=8192, summary_output=2048,
    margin=1024, template_overhead=2048)
COMPRESSOR = dict(base_url='http://127.0.0.35:8001/v1', model='retained-27b',
    key_env='FRIDAY_COMPRESSION_API_KEY', context=40960, max_input=40954,
    main_output=4096, summary_output=2048, margin=1024, template_overhead=2048)
MULTIPASS = dict(enabled=True, max_calls=16, max_depth=4,
    max_attempt_seconds=600, max_call_seconds=180)


def test_explicit_primary_budget_does_not_change_auxiliary_or_compressor_contracts():
    args = dict(PRIMARY, compression_inference=COMPRESSOR, compression_multipass=MULTIPASS)
    before = build_config(**args)
    policy = dict(first_event=180, idle=120, total=900)
    after = build_config(**args, request_budget_seconds=policy)
    expected = copy.deepcopy(before)
    expected['providers']['friday-local']['request_budget_seconds'] = policy
    assert after == expected
    assert after['providers']['friday-compression'] == before['providers']['friday-compression']
    assert after['auxiliary'] == before['auxiliary']
    assert after['model']['context_length'] == 262144
    policy['total'] = 1
    assert after['providers']['friday-local']['request_budget_seconds']['total'] == 900


def test_product_inference_accepts_only_explicit_budget_field():
    value = dict(PRIMARY, request_budget_seconds={'first_event': 180, 'idle': 120, 'total': 900})
    assert _inference(value, 'inference') == value
    with pytest.raises(ValueError):
        _inference(dict(value, total_timeout=900), 'inference')


@pytest.mark.parametrize('policy', [
    {}, {'total': 900}, {'first_event': 180, 'idle': 120, 'total': 900, 'retry': 1},
    {'first_event': True, 'idle': 120, 'total': 900},
    {'first_event': 0, 'idle': 120, 'total': 900},
    {'first_event': -1, 'idle': 120, 'total': 900},
    {'first_event': '180', 'idle': 120, 'total': 900},
    {'first_event': math.inf, 'idle': 120, 'total': 900},
    {'first_event': math.nan, 'idle': 120, 'total': 900},
    {'first_event': 901, 'idle': 120, 'total': 900},
    {'first_event': 180, 'idle': 901, 'total': 900},
    {'first_event': 180, 'idle': 120, 'total': 86401},
])
def test_malformed_or_unbounded_policy_rejects(policy):
    with pytest.raises(ValueError):
        build_config(**PRIMARY, request_budget_seconds=policy)


def test_independent_compressor_policy_is_never_inherited_from_primary():
    compressor = dict(COMPRESSOR, request_budget_seconds={'first_event': 20, 'idle': 15, 'total': 60})
    config = build_config(**PRIMARY, request_budget_seconds={'first_event': 180, 'idle': 120, 'total': 900},
        compression_inference=compressor, compression_multipass=MULTIPASS)
    assert config['providers']['friday-compression']['request_budget_seconds']['total'] == 60
    assert 'request_budget_seconds' not in config['auxiliary']['compression']
