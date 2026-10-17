"""Synthetic pure config composition; never a deployment/readiness attestation."""
import copy
import json
from pathlib import Path

import pytest
from tools.configure_local_test import build_config, validate_exact_renderer
from tools.configure_product import _inference, compose_product
from test_spark_request_budget_config import PRIMARY, COMPRESSOR, MULTIPASS
from test_product_profile import split_inputs, template

ROOT = Path(__file__).resolve().parents[1]
EXACT = {
    'binding': {'path': '/synthetic-not-installed/renderer-binding.json', 'sha256': 'a' * 64},
    'deployment': {'path': '/synthetic-not-installed/renderer-deployment.json', 'sha256': 'b' * 64},
}


def bounded(config, name='friday-compression'):
    entry = config['providers'][name]
    return entry['models'][entry['default_model']]['bounded_context']


@pytest.mark.parametrize('split', [False, True])
def test_absent_exact_renderer_matches_frozen_existing_output(split):
    args = dict(PRIMARY, request_budget_seconds={'first_event': 180, 'idle': 120, 'total': 900})
    if split:
        args.update(compression_inference=COMPRESSOR, compression_multipass=MULTIPASS)
    baseline = json.loads((ROOT/'tests/fixtures/exact_renderer_config_baseline.json').read_text())
    assert baseline['source_sha256'] == '6859d082f85620c160b388a9b70077cb8ac59393bdb9af5739315a4f15fb1c19'
    assert build_config(**args) == baseline['cases']['split' if split else 'single']
    assert 'exact_renderer' not in str(build_config(**args))


def test_only_compressor_bounded_leaf_changes_preserving_all_budgets_and_routes():
    args = dict(PRIMARY, compression_inference=copy.deepcopy(COMPRESSOR), compression_multipass=MULTIPASS,
                request_budget_seconds={'first_event': 180, 'idle': 120, 'total': 900})
    args['compression_inference']['request_budget_seconds'] = {'first_event': 20, 'idle': 15, 'total': 60}
    args['compression_inference']['request_options'] = {'reasoning_effort': 'high', 'temperature': 0.6}
    before = build_config(**args)
    args['compression_inference']['exact_renderer'] = copy.deepcopy(EXACT)
    snapshot = copy.deepcopy(args)
    after = build_config(**args)
    assert args == snapshot
    expected = copy.deepcopy(before)
    bounded(expected)['exact_renderer'] = EXACT
    assert after == expected
    assert 'exact_renderer' not in bounded(after, 'friday-local')
    args['compression_inference']['exact_renderer']['binding']['sha256'] = 'c' * 64
    assert bounded(after)['exact_renderer'] == EXACT


def test_native_compose_and_onboarding_preserve_only_compression_leaf_and_unready_contract():
    from plugins.friday_rework.onboarding import validate_template
    spec = split_inputs()
    spec['inference']['request_budget_seconds'] = {'first_event': 180, 'idle': 120, 'total': 900}
    spec['compression_inference']['request_budget_seconds'] = {'first_event': 20, 'idle': 15, 'total': 60}
    before = compose_product(spec)
    spec['compression_inference']['exact_renderer'] = copy.deepcopy(EXACT)
    original = copy.deepcopy(spec)
    after = compose_product(spec)
    expected = copy.deepcopy(before)
    bounded(expected['config'])['exact_renderer'] = EXACT
    bounded(template(expected)['config'])['exact_renderer'] = EXACT
    assert after == expected
    assert spec == original
    assert after['contract']['ready'] is False
    assert after['contract']['state'] == 'TEMPLATE_INCOMPLETE'
    assert after['config']['plugins']['entries']['friday_rework']['settings']['runtime'] == {'enabled': False}
    validate_template(template(after))
    bounded(after['config'])['exact_renderer']['binding']['sha256'] = 'c' * 64
    assert bounded(template(after)['config'])['exact_renderer'] == EXACT


@pytest.mark.parametrize('bad', [
    None, False, {}, [], {'enabled': True}, {'binding': EXACT['binding']},
    dict(EXACT, enabled=True),
    {'binding': {'path': '/a'}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a', 'sha256': 'A' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a', 'sha256': 'a' * 63}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a', 'sha256': 'z' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a', 'sha256': 123}, 'deployment': EXACT['deployment']},
    {'binding': {'path': 'relative', 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '', 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a\n', 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/a\x00', 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': '/${ASSET}', 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': {'path': Path('/a'), 'sha256': 'a' * 64}, 'deployment': EXACT['deployment']},
    {'binding': EXACT['binding'], 'deployment': {'path': '/b', 'sha256': None}},
    {'binding': EXACT['binding'], 'deployment': {'path': '/b', 'sha256': 'b'*64, 'ready': True}},
])
def test_malformed_unpinned_or_enable_shortcuts_reject_at_all_entry_points(bad):
    compressor = dict(COMPRESSOR, exact_renderer=bad)
    with pytest.raises(ValueError): validate_exact_renderer(bad)
    with pytest.raises(ValueError): _inference(compressor, 'compression_inference')
    with pytest.raises(ValueError): build_config(**PRIMARY, compression_inference=compressor, compression_multipass=MULTIPASS)
    spec = split_inputs(); spec['compression_inference']['exact_renderer'] = bad
    with pytest.raises(ValueError): compose_product(spec)


@pytest.mark.parametrize('bad', [EXACT, None, {}, False])
def test_primary_route_enable_rejects_even_with_valid_refs(bad):
    with pytest.raises(ValueError): _inference(dict(PRIMARY, exact_renderer=bad), 'inference')
    with pytest.raises(ValueError): build_config(**PRIMARY, exact_renderer=bad)
    spec = split_inputs(); spec['inference']['exact_renderer'] = bad
    with pytest.raises(ValueError): compose_product(spec)


def test_compression_route_still_requires_separate_key_and_finite_multipass():
    comp = dict(COMPRESSOR, exact_renderer=EXACT)
    for multipass in (None, {}, dict(MULTIPASS, enabled=False), dict(MULTIPASS, max_calls=257)):
        with pytest.raises(ValueError): build_config(**PRIMARY, compression_inference=comp, compression_multipass=multipass)
    with pytest.raises(ValueError):
        build_config(**PRIMARY, compression_inference=dict(comp, key_env=PRIMARY['key_env']), compression_multipass=MULTIPASS)


def test_config_rendering_performs_no_binding_file_read_and_runtime_missing_docs_fail_closed():
    from agent.bounded_context import compression_policy_from_config, BoundedRendererBindingError
    # These refs intentionally do not exist. Composition is source-only; native
    # route admission must perform real pin/readiness verification and refuse.
    config = build_config(**PRIMARY, compression_inference=dict(COMPRESSOR, exact_renderer=EXACT),
                          compression_multipass=MULTIPASS)
    with pytest.raises(BoundedRendererBindingError, match='readiness not verified'):
        compression_policy_from_config(config)


def test_native_runtime_accepts_exact_ref_shape_and_compression_route_only(monkeypatch):
    from agent.bounded_context import compression_policy_from_config, policy_from_config, BoundedRendererBindingError
    from agent import protected_compressor_renderer as renderer
    seen = []
    class ShapeOnlyRenderer:
        identity = {'fixture': 'shape-only-no-readiness-claim'}
    def fixture_loader(*refs):
        seen.append(refs)
        return ShapeOnlyRenderer()
    monkeypatch.setattr(renderer, 'load_renderer', fixture_loader)
    config = build_config(**PRIMARY, compression_inference=dict(COMPRESSOR, exact_renderer=EXACT),
                          compression_multipass=MULTIPASS)
    policy = compression_policy_from_config(config)
    assert policy.exact_renderer == tuple(EXACT[k][f] for k in ('binding','deployment') for f in ('path','sha256'))
    assert seen[-1] == policy.exact_renderer
    bounded(config, 'friday-local')['exact_renderer'] = copy.deepcopy(EXACT)
    with pytest.raises(BoundedRendererBindingError, match='compression-only'):
        policy_from_config(config)
